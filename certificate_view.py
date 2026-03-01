# certificate_view.py
import os
import logging
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
from ui_format import fmt_if_number as _fmt_if_number, normalize_headers
from tdms_reader import read_contract_and_loop_data, read_performance_tables_dynamic, read_power_calc_type

logger = logging.getLogger(__name__)


# -------------------- Recupero TDMS Mancanti --------------------
def find_missing_tdms(old_path):
    """
    Apre file dialog per trovare TDMS mancante.
    Suggerisce il nome file originale.
    
    Returns:
        str: Nuovo percorso o None se annullato
    """
    old_filename = os.path.basename(old_path) if old_path else "file.tdms"
    
    new_path = filedialog.askopenfilename(
        title=f"Cerca: {old_filename}",
        filetypes=[("TDMS files", "*.tdms"), ("All files", "*.*")],
        initialfile=old_filename
    )
    
    if new_path:
        # Verifica che il nome file corrisponda (opzionale ma consigliato)
        new_filename = os.path.basename(new_path)
        if new_filename != old_filename:
            conferma = messagebox.askyesno(
                "Nome file diverso",
                f"Attenzione:\n\n"
                f"File originale: {old_filename}\n"
                f"File selezionato: {new_filename}\n\n"
                f"Sei sicuro che sia lo stesso file?"
            )
            if not conferma:
                return None
    
    return new_path


def update_tdms_path(acquisizione_id, new_path):
    """Aggiorna il path TDMS nel database."""
    if not acquisizione_id:
        return False
    
    try:
        import db
        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE acquisizioni SET filepath = ? WHERE id = ?",
                (new_path, acquisizione_id)
            )
            conn.commit()
        return True
    except Exception as e:
        messagebox.showerror("Errore DB", f"Impossibile aggiornare il percorso:\n{e}")
        return False


# -------------------- UI helper --------------------
def _kv_row(parent, label, value="-"):
    row = tk.Frame(parent, bg="#f0f0f0")
    row.pack(fill="x", padx=8, pady=2)
    tk.Label(row, text=label, width=22, anchor="w", bg="#f0f0f0",
             font=("Segoe UI", 10, "bold")).pack(side="left")
    tk.Label(row, text=value if value else "-", anchor="w", bg="#f0f0f0",
             font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)
    return row

# -------------------- util UI --------------------
def _measure_title(widget, text: str) -> int:
    try:
        style = ttk.Style()
        font_name = style.lookup("Treeview.Heading", "font") or "TkDefaultFont"
    except Exception:
        font_name = "TkDefaultFont"
    fnt = tkfont.nametofont(font_name)
    return fnt.measure(text if text else " ") + 30

def _spread_even_in_tv(tv, cols, minwidths, total_target, *, stretch=False):
    if not cols:
        mw = max(minwidths[0], total_target)
        tv.column("-", width=mw, minwidth=minwidths[0], stretch=stretch, anchor="center")
        return
    base_sum = sum(minwidths)
    extra = max(0, total_target - base_sum)
    n = len(cols)
    add_each = extra // n
    rem = extra % n
    for i, (c, wmin) in enumerate(zip(cols, minwidths)):
        w = wmin + add_each + (1 if i < rem else 0)
        tv.column(c, width=w, minwidth=wmin, stretch=stretch, anchor="center")


# -------------------- Finestra di dettaglio --------------------
def open_detail_window(root, columns, values, meta, tipo_test="PERFORMANCE"):
    win = tk.Toplevel(root)
    win.title("Test Certificate")
    win.minsize(400, 800)
    win.configure(bg="#f0f0f0")
    
    # Imposta l'icona
    try:
        import icon_helper
        icon_helper.set_window_icon(win)
    except Exception:
        logger.debug("Impossibile impostare l'icona finestra certificato", exc_info=True)
    
    # Converti tipo_test â†’ test_index per leggere i gruppi corretti
    # PERFORMANCE â†’ 0 (gruppi 0_X_PERFORMANCE)
    # NPSH â†’ 1 (gruppi 1_X_NPSH)
    # RUNNING â†’ 2 (gruppi 2_X_RUNNING)
    test_index_map = {
        "PERFORMANCE": 0,
        "NPSH": 1,
        "RUNNING": 2
    }
    test_index = test_index_map.get(tipo_test.upper(), 0)  # Default a PERFORMANCE

    cert_num   = values[1] if len(values) > 1 else "-"
    test_date  = values[4] if len(values) > 4 else "-"
    job_dash   = values[0] if len(values) > 0 else "-"
    pump_dash  = values[3] if len(values) > 3 else "-"

    tdms_path = meta.get("_FilePath") if isinstance(meta, dict) else None
    acquisizione_id = meta.get("id") if isinstance(meta, dict) else None
    
    # CONTROLLO: Verifica se il file TDMS esiste
    if tdms_path and not os.path.exists(tdms_path):
        # File mancante - chiedi all'utente cosa fare
        risposta = messagebox.askyesnocancel(
            "âš ï¸ File TDMS non trovato",
            f"Il file:\n{tdms_path}\n\nnon esiste piÃ¹.\n\n"
            "Vuoi cercarlo in un'altra posizione?\n\n"
            "â€¢ SI: Seleziona nuova posizione\n"
            "â€¢ NO: Apri certificato senza dati\n"
            "â€¢ ANNULLA: Torna alla dashboard"
        )
        
        if risposta is None:  # ANNULLA
            win.destroy()
            return
        elif risposta:  # SI - Cerca
            new_path = find_missing_tdms(tdms_path)
            if new_path:
                # Aggiorna DB con nuovo percorso
                if update_tdms_path(acquisizione_id, new_path):
                    messagebox.showinfo(
                        "Percorso aggiornato", 
                        f"Il nuovo percorso Ã¨ stato salvato:\n{new_path}\n\n"
                        "La finestra certificato verrÃ  chiusa.\n"
                        "Riaprila dalla dashboard per visualizzare i dati aggiornati."
                    )
                    # Chiudi la finestra certificato
                    win.destroy()
                    return
                else:
                    tdms_path = ""
            else:
                # Annullato o non trovato
                tdms_path = ""
        else:  # NO - Ignora
            tdms_path = ""
    
    state = {
        "tdms_path": tdms_path,
        "acquisizione_id": acquisizione_id
    }

    # Notebook
    nb = ttk.Notebook(win); nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    tab = tk.Frame(nb, bg="#f0f0f0"); nb.add(tab, text="Certificato")
    curva_tab = tk.Frame(nb, bg="#f0f0f0"); nb.add(curva_tab, text="Curva")

    try:
        from curve_view import render_curve_tab
        render_curve_tab(
            curva_tab,
            state.get("tdms_path") or "",
            acquisizione_id=state.get("acquisizione_id")
        )
    except Exception as e:
        tk.Label(curva_tab, text=f"Curva non disponibile: {e}", bg="#f0f0f0", justify="left").pack(anchor="w", padx=12, pady=12)

    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(1, weight=1)

    # Header
    header = tk.Frame(tab, bg="#f0f0f0")
    header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16,8))
    header.columnconfigure(0, weight=1)
    header.columnconfigure(1, weight=1)
    tk.Label(header, text="TEST CERTIFICATE", bg="#f0f0f0", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
    right = tk.Frame(header, bg="#f0f0f0"); right.grid(row=0, column=1, sticky="e")
    tk.Label(right, text=f"N. Cert.: {cert_num}", bg="#f0f0f0", font=("Segoe UI", 10)).pack(anchor="e")
    
    # ComboBox per Unit System (al posto della label statica)
    unit_frame = tk.Frame(right, bg="#f0f0f0")
    unit_frame.pack(anchor="e")
    tk.Label(unit_frame, text="U.M. System: ", bg="#f0f0f0", font=("Segoe UI", 10)).pack(side="left")
    
    # Carica unit_system dal DB
    acquisizione_id = state.get("acquisizione_id")
    try:
        from db import get_unit_system, set_unit_system
        current_system = get_unit_system(acquisizione_id) if acquisizione_id else "Metric"
    except Exception:
        current_system = "Metric"
    
    unit_var = tk.StringVar(value=current_system)
    unit_combo = ttk.Combobox(
        unit_frame,
        textvariable=unit_var,
        values=["Metric", "US"],
        state="readonly",
        width=10,
        font=("Segoe UI", 9)
    )
    unit_combo.pack(side="left")
    
    def on_unit_change(event=None):
        """Quando cambia il sistema di unitÃ , salva nel DB e ricarica tutto."""
        new_system = unit_var.get()
        if acquisizione_id:
            try:
                set_unit_system(acquisizione_id, new_system)
            except Exception:
                logger.warning("Salvataggio unit_system fallito per acquisizione_id=%s", acquisizione_id, exc_info=True)
        # Ricarica i blocchi con le nuove unitÃ 
        render_blocks(state.get("tdms_path") or "", new_system)
        render_tables(state.get("tdms_path") or "", new_system)
        
        # Ricarica anche la tab Curva
        try:
            # Distruggi tutti i widget nella curva_tab
            for widget in curva_tab.winfo_children():
                widget.destroy()
            
            # Ri-renderizza con il nuovo unit_system
            from curve_view import render_curve_tab
            render_curve_tab(
                curva_tab,
                state.get("tdms_path") or "",
                acquisizione_id=acquisizione_id
            )
        except Exception as e:
            tk.Label(curva_tab, text=f"Curva non disponibile: {e}", bg="#f0f0f0", justify="left").pack(anchor="w", padx=12, pady=12)
    
    unit_combo.bind("<<ComboboxSelected>>", on_unit_change)
    
    tk.Label(right, text=f"Test Date: {test_date}", bg="#f0f0f0", font=("Segoe UI", 10)).pack(anchor="e")

    # Body senza scroll (le tabelle hanno le proprie scrollbar)
    body = tk.Frame(tab, bg="#f0f0f0")
    body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8,16))
    body.columnconfigure(0, weight=1)
    body.rowconfigure(1, weight=1)  # la riga delle tabelle si espande

    # Containers
    blocks = tk.Frame(body, bg="#f0f0f0")
    blocks.grid(row=0, column=0, sticky="ew", pady=(0,8))
    # Tre colonne: Contractual Data | Rated Point | Loop Details
    blocks.columnconfigure(0, weight=1)
    blocks.columnconfigure(1, weight=1)
    blocks.columnconfigure(2, weight=1)

    tables_row = tk.Frame(body, bg="#f0f0f0")
    tables_row.grid(row=1, column=0, sticky="nsew")
    tables_row.grid_columnconfigure(0, weight=0)
    tables_row.grid_columnconfigure(1, weight=1)
    tables_row.grid_columnconfigure(2, weight=0)
    tables_row.grid_rowconfigure(0, weight=1)

    # --- Contractual + Rated Point + Loop (usa tdms_reader) ---
    def render_blocks(tdms_path: str, unit_system: str = "Metric"):
        """Renderizza i blocchi Contractual/Rated/Loop con conversione unitÃ ."""
        for w in blocks.winfo_children():
            w.destroy()

        # Init
        cap = tdh = eff = abs_pow = speed = sg = temp = visc = npsh = liquid = "-"
        cust = po = end_user = specs = "-"
        item = pump = sn = imp_draw = imp_mat = imp_dia = "-"
        suction = discharge = watt_const = atmpress = knpsh = watertemp = kventuri = "-"
        power_calc_type = "-"  # Nuovo: tipo di calcolo potenza

        try:
            import unit_converter as uc
            data = read_contract_and_loop_data(tdms_path)
            # Converti i dati contrattuali da Metric â†’ unit_system selezionato
            data = uc.convert_contractual_data(data, "Metric", unit_system)
        except Exception:
            data = {}
            uc = None
        
        # Leggi Power Calc Type
        if tdms_path:
            try:
                power_calc_type = read_power_calc_type(tdms_path)
            except Exception:
                power_calc_type = "-"

        # Rated point (Capacity..Liquid) - ora con etichette convertite
        cap_key = f"Capacity [{uc.get_unit_label('flow', unit_system)}]" if uc else "Capacity [m3/h]"
        tdh_key = f"TDH [{uc.get_unit_label('head', unit_system)}]" if uc else "TDH [m]"
        pow_key = f"ABS_Power [{uc.get_unit_label('power', unit_system)}]" if uc else "ABS_Power [kW]"
        temp_key = f"Temperature [{uc.get_unit_label('temp', unit_system)}]" if uc else "Temperature [°C]"
        npsh_key = f"NPSH [{uc.get_unit_label('npsh', unit_system)}]" if uc else "NPSH [m]"
        
        # Capacity può arrivare come [m3/h] (TDMS) o [m³/h] (label UI)
        cap     = _fmt_if_number(
            data.get(
                cap_key,
                data.get("Capacity [m3/h]", data.get("Capacity [m³/h]", ""))
            )
        )
        tdh     = _fmt_if_number(data.get(tdh_key, ""))
        eff     = _fmt_if_number(data.get("Efficiency [%]", ""))
        abs_pow = _fmt_if_number(data.get(pow_key, ""))
        speed   = _fmt_if_number(data.get("Speed [rpm]", ""))
        sg      = _fmt_if_number(data.get("SG Contract", ""))
        temp    = _fmt_if_number(
            data.get(
                temp_key,
                data.get("Temperature [°C]", data.get("Temperature [Â°C]", data.get("Temperature [C]", "")))
            )
        )
        visc    = _fmt_if_number(data.get("Viscosity [cP]", ""))
        npsh    = _fmt_if_number(data.get(npsh_key, ""))
        liquid  = data.get("Liquid", "") or "-"

        # Contractual data (FSG ORDER..Specs)
        cust     = data.get("Customer", "") or "-"
        po       = data.get("Purchaser Order", "") or "-"
        end_user = data.get("End User", "") or "-"
        specs    = data.get("Applic. Specs.", "") or "-"

        item     = data.get("Item", "") or "-"
        pump     = data.get("Pump", "") or "-"
        sn       = data.get("Serial Number_Elenco", "") or "-"
        imp_draw = data.get("Impeller Drawing", "") or "-"
        imp_mat  = data.get("Impeller Material", "") or "-"
        imp_dia  = data.get("Diam Nominal", "") or "-"

        suction     = _fmt_if_number(data.get("Suction [Inch]", ""))
        discharge   = _fmt_if_number(data.get("Discharge [Inch]", ""))
        watt_const  = _fmt_if_number(data.get("Wattmeter Const.", ""))

        # Loop Details: leggi con chiavi dinamiche (convertite) e fallback metrico.
        atm_key = f"AtmPress [{uc.get_unit_label('pressure', unit_system)}]" if uc else "AtmPress [m]"
        knpsh_key = f"KNPSH [{uc.get_unit_label('npsh', unit_system)}]" if uc else "KNPSH [m]"
        wt_key = f"WaterTemp [{uc.get_unit_label('temp', unit_system)}]" if uc else "WaterTemp [°C]"

        atmpress    = _fmt_if_number(data.get(atm_key, data.get("AtmPress [m]", "")))
        knpsh       = _fmt_if_number(data.get(knpsh_key, data.get("KNPSH [m]", "")))
        watertemp   = _fmt_if_number(
            data.get(wt_key, data.get("WaterTemp [°C]", data.get("WaterTemp [Â°C]", data.get("WaterTemp [C]", ""))))
        )
        kventuri    = _fmt_if_number(data.get("KVenturi", ""))

        # --- 1) Contractual Data (FSG ORDER .. Specs)
        contractual = tk.LabelFrame(blocks, text="Contractual Data", bg="#f0f0f0")
        contractual.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        contractual.columnconfigure(0, weight=1)

        _kv_row(contractual, "FSG ORDER", job_dash if job_dash and job_dash != "-" else "-")
        _kv_row(contractual, "CUSTOMER", cust)
        _kv_row(contractual, "P.O.", po)
        _kv_row(contractual, "End User", end_user)
        _kv_row(contractual, "Item", item)

        pump_model = pump if pump and pump != "-" else (values[3] if len(values) > 3 else "-")
        _kv_row(contractual, "Pump", pump_model)

        _kv_row(contractual, "S. N.", sn)
        _kv_row(contractual, "Imp. Draw.", imp_draw)
        _kv_row(contractual, "Imp. Mat.", imp_mat)
        _kv_row(contractual, "Imp Dia [mm]", imp_dia)
        _kv_row(contractual, "Specs", specs)

        # --- 2) Rated Point (Capacity .. Liquid) con unitÃ  dinamiche
        rated = tk.LabelFrame(blocks, text="Rated Point", bg="#f0f0f0")
        rated.grid(row=0, column=1, sticky="nsew", padx=8)
        rated.columnconfigure(0, weight=1)

        flow_unit = uc.get_unit_label('flow', unit_system) if uc else "m³/h"
        head_unit = uc.get_unit_label('head', unit_system) if uc else "m"
        power_unit = uc.get_unit_label('power', unit_system) if uc else "kW"
        temp_unit = uc.get_unit_label('temp', unit_system) if uc else "°C"
        npsh_unit = uc.get_unit_label('npsh', unit_system) if uc else "m"
        
        _kv_row(rated, f"Capacity [{flow_unit}]", cap)
        _kv_row(rated, f"TDH [{head_unit}]", tdh)
        _kv_row(rated, "Efficiency [%]", eff)
        _kv_row(rated, f"ABS_Power [{power_unit}]", abs_pow)
        _kv_row(rated, "Speed [rpm]", speed)
        _kv_row(rated, "SG", sg)
        _kv_row(rated, f"Temperature [{temp_unit}]", temp)
        _kv_row(rated, "Viscosity [cP]", visc)
        _kv_row(rated, f"NPSH [{npsh_unit}]", npsh)
        _kv_row(rated, "Liquid", liquid)

        # --- 3) Loop Details con unitÃ  dinamiche
        loop = tk.LabelFrame(blocks, text="Loop Details", bg="#f0f0f0")
        loop.grid(row=0, column=2, sticky="nsew", padx=(8,0))
        # Test performed with - stesso formato di _kv_row ma con titolo inline
        test_row = tk.Frame(loop, bg="#f0f0f0")
        test_row.pack(fill="x", padx=8, pady=(6,2))
        tk.Label(test_row, text="Test performed with:", width=22, anchor="w", bg="#f0f0f0",
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(test_row, text=power_calc_type if power_calc_type else "-", anchor="w", bg="#f0f0f0",
                 font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)
        
        _kv_row(loop, "Suction [Inch]", suction)
        _kv_row(loop, "Discharge [Inch]", discharge)
        _kv_row(loop, "Wattmeter Const.", watt_const)
        _kv_row(loop, f"AtmPress [{head_unit}]", atmpress)
        _kv_row(loop, f"KNPSH [{npsh_unit}]", knpsh)
        _kv_row(loop, f"WaterTemp [{temp_unit}]", watertemp)
        _kv_row(loop, "Kventuri", kventuri)

    # --- Tre tabelle (Recorded/Calc/Converted) ---
    def render_tables(tdms_path: str, unit_system: str = "Metric"):
        """Renderizza le tabelle Recorded/Calculated/Converted con conversione unitÃ ."""
        for w in tables_row.winfo_children():
            w.destroy()

        try:
            import unit_converter as uc
            perf = read_performance_tables_dynamic(tdms_path, test_index=test_index)
        except Exception:
            perf = {
                "Recorded": {"columns": [], "rows": []},
                "Calc": {"columns": [], "rows": []},
                "Converted": {"columns": [], "rows": []},
            }
            uc = None
            
        rec_cols, rec_rows    = perf["Recorded"]["columns"], perf["Recorded"]["rows"]
        calc_cols, calc_rows  = perf["Calc"]["columns"],     perf["Calc"]["rows"]
        conv_cols, conv_rows  = perf["Converted"]["columns"], perf["Converted"]["rows"]

        def _prune_empty_columns(cols, rows):
            """
            Rimuove le colonne:
            - completamente vuote
            - con soli zeri (eventuali celle vuote incluse)
            """
            if not cols:
                return cols, rows
            if not rows:
                return [], []

            keep_idx = []
            for i, _c in enumerate(cols):
                has_value = False
                for r in rows:
                    if i >= len(r):
                        continue
                    v = r[i]
                    if v is None:
                        continue
                    if isinstance(v, str):
                        s = v.strip()
                        if s == "":
                            continue
                        try:
                            # "0", "0.0", "0,000" -> zero
                            num = float(s.replace(",", "."))
                            if abs(num) > 1e-12:
                                has_value = True
                                break
                            continue
                        except Exception:
                            # Testo non numerico: consideralo valore valido
                            has_value = True
                            break
                    try:
                        num = float(v)
                        if abs(num) > 1e-12:
                            has_value = True
                            break
                    except Exception:
                        has_value = True
                        break
                if has_value:
                    keep_idx.append(i)

            if not keep_idx:
                return [], []

            new_cols = [cols[i] for i in keep_idx]
            new_rows = [tuple((r[i] if i < len(r) else "") for i in keep_idx) for r in rows]
            return new_cols, new_rows
        
        # Converti Calculated e Converted da Metric â†’ unit_system
        if uc:
            calc_cols, calc_rows = uc.convert_performance_table(calc_cols, calc_rows, "Metric", unit_system)
            conv_cols, conv_rows = uc.convert_performance_table(conv_cols, conv_rows, "Metric", unit_system)

        # Nascondi colonne completamente vuote in ciascuna tabella
        rec_cols, rec_rows = _prune_empty_columns(rec_cols or [], rec_rows or [])
        calc_cols, calc_rows = _prune_empty_columns(calc_cols or [], calc_rows or [])
        conv_cols, conv_rows = _prune_empty_columns(conv_cols or [], conv_rows or [])
        
        # Format intestazioni colonna
        # Recorded: mantiene i nomi originali (incluse unitÃ )
        # calc_cols e conv_cols: normalizza con unitÃ 
        calc_cols = normalize_headers(calc_cols or [], "Calculated Values", unit_system)
        conv_cols = normalize_headers(conv_cols or [], "Converted Values", unit_system)

        def _make_table(parent, title, cols, mode):
            lf = tk.LabelFrame(parent, text=title, bg="#f0f0f0")
            lf.rowconfigure(0, weight=1)
            lf.columnconfigure(0, weight=(1 if mode == "center" else 0))
            lf.columnconfigure(1, weight=0)  # colonna per scrollbar

            # Treeview SENZA height fissa per espandersi completamente
            tv = ttk.Treeview(lf, columns=cols or ("-",), show="headings", selectmode="browse")
            
            # Aggiungi scrollbar verticale (il command verrÃ  configurato dopo per la sincronizzazione)
            vsb = ttk.Scrollbar(lf, orient="vertical")

            minwidths = []
            if not cols:
                tv.heading("-", text="-")
                mw = _measure_title(tv, "-")
                tv.column("-", minwidth=mw, width=mw, anchor="center", stretch=(mode=="center"))
                minwidths = [mw]
            else:
                for c in cols:
                    tv.heading(c, text=c)
                    mw = _measure_title(tv, c)
                    tv.column(c, minwidth=mw, width=mw, anchor="center", stretch=(mode=="center"))
                    minwidths.append(mw)

            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            return lf, tv, vsb, (cols if cols else ["-"]), minwidths

        # crea le tre tabelle
        lf_left,  tv_left,  vsb_left,  left_cols,  left_mins  = _make_table(tables_row, "Recorded Data",    rec_cols,  "left")
        lf_mid,   tv_mid,   vsb_mid,   mid_cols,   mid_mins   = _make_table(tables_row, "Calculated Values", calc_cols, "center")
        lf_right, tv_right, vsb_right, right_cols, right_mins = _make_table(tables_row, "Converted Values",  conv_cols, "right")

        # posizionamento - TUTTE le tabelle devono espandersi verticalmente
        lf_left.grid (row=0, column=0, sticky="nsew", padx=(0,8))
        lf_mid.grid  (row=0, column=1, sticky="nsew", padx=8)
        lf_right.grid(row=0, column=2, sticky="nsew", padx=(8,0))

        # clamp laterali
        def _clamp_tv_to_frame(tv, cols, mins, frame, pad=16):
            try:
                frame.update_idletasks()
            except Exception:
                logger.debug("Aggiornamento layout frame fallito durante clamp colonne", exc_info=True)
                return

            if not cols:
                avail = max(mins[0], frame.winfo_width() - pad)
                cur   = tv.column("-", option="width")
                tv.column("-", width=min(cur, avail))
                return

            avail = max(sum(mins), frame.winfo_width() - pad)
            widths = [tv.column(c, "width") for c in cols]
            total  = sum(widths)
            if total <= avail:
                return

            extra = total - avail
            while extra > 0 and any(w > m for w, m in zip(widths, mins)):
                idxs = [i for i, (w, m) in enumerate(zip(widths, mins)) if w > m]
                if not idxs:
                    break
                dec = max(1, extra // len(idxs))
                for i in idxs:
                    if extra <= 0:
                        break
                    room = widths[i] - mins[i]
                    d = min(dec, room)
                    widths[i] -= d
                    extra -= d

            for c, w in zip(cols, widths):
                tv.column(c, width=w)

        lf_left.bind("<Configure>",  lambda e: _clamp_tv_to_frame(tv_left,  left_cols,  left_mins,  lf_left))
        lf_right.bind("<Configure>", lambda e: _clamp_tv_to_frame(tv_right, right_cols, right_mins, lf_right))

        def _maybe_clamp_after_drag(tv, cols, mins, frame):
            tv.update_idletasks()
            _clamp_tv_to_frame(tv, cols, mins, frame)

        tv_left.bind("<ButtonRelease-1>",  lambda e: _maybe_clamp_after_drag(tv_left,  left_cols,  left_mins,  lf_left))
        tv_right.bind("<ButtonRelease-1>", lambda e: _maybe_clamp_after_drag(tv_right, right_cols, right_mins, lf_right))

        # min larghezze da titoli
        left_base  = sum(left_mins)  if left_mins  else 0
        mid_base   = sum(mid_mins)   if mid_mins   else 0
        right_base = sum(right_mins) if right_mins else 0

        tables_row.grid_columnconfigure(0, weight=0, minsize=left_base)
        tables_row.grid_columnconfigure(1, weight=1, minsize=mid_base)
        tables_row.grid_columnconfigure(2, weight=0, minsize=right_base)
        
        # inserisci righe
        for idx, vals in enumerate(rec_rows, start=1):
            tv_left.insert("", "end", iid=f"p{idx:03d}", values=[_fmt_if_number(v) for v in vals])

        for idx, vals in enumerate(calc_rows, start=1):
            tv_mid.insert("", "end", iid=f"p{idx:03d}", values=[_fmt_if_number(v) for v in vals])

        for idx, vals in enumerate(conv_rows, start=1):
            tv_right.insert("", "end", iid=f"p{idx:03d}", values=[_fmt_if_number(v) for v in vals])

        # ridistribuzione equa SOLO nella tabella centrale
        def _resize_center(_e=None):
            try:
                lf_mid.update_idletasks()
            except Exception:
                return
            target = max(mid_base, lf_mid.winfo_width() - 16)
            _spread_even_in_tv(tv_mid, mid_cols, mid_mins, target, stretch=True)
        lf_mid.bind("<Configure>", _resize_center)
        win.after_idle(_resize_center)

        # minsize finestra robusta
        def _apply_minsize_once():
            win.update_idletasks()
            tables_req = tables_row.winfo_reqwidth()
            header_req  = header.winfo_reqwidth()
            blocks_req  = blocks.winfo_reqwidth()
            content_req = max(tables_req, blocks_req, header_req)

            def _padx_total(widget):
                try:
                    px = widget.pack_info().get("padx", 0)
                except Exception:
                    return 0
                if isinstance(px, (tuple, list)):
                    return sum(int(p) for p in px)
                try:
                    return int(px) * 2
                except Exception:
                    return 0

            outer_tables = _padx_total(tables_row)
            outer_nb     = _padx_total(nb)

            # Aggiunta per il padding del body
            body_padx = 16 * 2  # padx=16 su entrambi i lati

            safety = 12
            min_window_width = content_req + outer_tables + outer_nb + body_padx + safety
            min_window_height = 840  # valore pratico

            win.minsize(min_window_width, min_window_height)
            if win.winfo_width() < min_window_width or win.winfo_height() < min_window_height:
                win.geometry(f"{min_window_width}x{min_window_height}")

        win.after_idle(_apply_minsize_once)
        win.after_idle(lambda: win.after_idle(_apply_minsize_once))

        # sync selezione tra le tabelle
        sync_state = {"syncing": False, "current_iid": None}
        def _apply_sync(iid, origin):
            if not iid: return
            for tv in (tv_left, tv_mid, tv_right):
                if tv is origin: continue
                try:
                    if not tv.exists(iid): continue
                    cur = tv.selection()
                    if cur and cur[0] == iid: continue
                    tv.selection_set(iid); tv.focus(iid); tv.see(iid)
                except Exception:
                    logger.debug("Sync selezione fallita su una tabella", exc_info=True)

        def _on_select(src_tv, _e=None):
            if sync_state["syncing"]: return
            try:
                sel = src_tv.selection()
                iid = sel[0] if sel else None
            except Exception:
                iid = None
            if not iid or sync_state["current_iid"] == iid: return
            sync_state["syncing"] = True
            sync_state["current_iid"] = iid
            win.after_idle(lambda: (_apply_sync(iid, src_tv), sync_state.update(syncing=False)))

        for tv in (tv_left, tv_mid, tv_right):
            tv.bind("<<TreeviewSelect>>", lambda e, src=tv: _on_select(src, e))

        # ============ SINCRONIZZAZIONE SCROLLING ============
        scroll_sync_state = {"scrolling": False}
        
        def _sync_scroll(*args):
            """Sincronizza lo scrolling tra tutte le tabelle"""
            if scroll_sync_state["scrolling"]:
                return
            
            scroll_sync_state["scrolling"] = True
            
            # Ottieni la posizione di scroll
            first, last = args[0], args[1]
            
            # Aggiorna tutte e tre le scrollbar e le tabelle
            for vsb, tv in [(vsb_left, tv_left), (vsb_mid, tv_mid), (vsb_right, tv_right)]:
                tv.yview_moveto(first)
                vsb.set(first, last)
            
            scroll_sync_state["scrolling"] = False
        
        def _on_scrollbar_move(tv_to_move, *args):
            """Gestisce il movimento tramite scrollbar e sincronizza le altre"""
            if scroll_sync_state["scrolling"]:
                return
            
            scroll_sync_state["scrolling"] = True
            
            # Muovi la tabella corrente
            tv_to_move.yview(*args)
            
            # Ottieni la nuova posizione
            first, last = tv_to_move.yview()
            
            # Sincronizza tutte le altre tabelle
            for vsb, tv in [(vsb_left, tv_left), (vsb_mid, tv_mid), (vsb_right, tv_right)]:
                if tv != tv_to_move:
                    tv.yview_moveto(first)
                vsb.set(first, last)
            
            scroll_sync_state["scrolling"] = False
        
        # Configura yscrollcommand per sincronizzare quando si scrolla con la rotella
        tv_left.configure(yscrollcommand=_sync_scroll)
        tv_mid.configure(yscrollcommand=_sync_scroll)
        tv_right.configure(yscrollcommand=_sync_scroll)
        
        # Configura command delle scrollbar per sincronizzare quando si usa la scrollbar
        vsb_left.configure(command=lambda *args: _on_scrollbar_move(tv_left, *args))
        vsb_mid.configure(command=lambda *args: _on_scrollbar_move(tv_mid, *args))
        vsb_right.configure(command=lambda *args: _on_scrollbar_move(tv_right, *args))

        # selezione iniziale
        try:
            first_iid = next(iter(tv_left.get_children()), None)
            if first_iid:
                tv_left.selection_set(first_iid); tv_left.focus(first_iid); tv_left.see(first_iid)
        except StopIteration:
            return

    # Render iniziale
    render_blocks(state["tdms_path"], current_system)
    render_tables(state["tdms_path"], current_system)



