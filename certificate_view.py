# certificate_view.py
import os
import sys
import math
import tkinter as tk
import tkinter.font as tkfont
from typing import List
from tkinter import ttk, messagebox
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from tdms_reader import (
    NPTDMS_OK,
    read_contract_and_loop_data,
    read_performance_tables_dynamic,
)

# Export PDF (opzionale)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False


# -------------------- UI helper --------------------
def _kv_row(parent, label, value="—"):
    row = tk.Frame(parent, bg="#f0f0f0")
    row.pack(fill="x", padx=8, pady=2)
    tk.Label(row, text=label, width=22, anchor="w", bg="#f0f0f0",
             font=("Segoe UI", 10, "bold")).pack(side="left")
    tk.Label(row, text=value if value else "—", anchor="w", bg="#f0f0f0",
             font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)
    return row


# -------------------- Formattazione numerica (UI-side) --------------------
def _fmt_num(x):
    try:
        d = Decimal(str(x))
    except Exception:
        return ""
    try:
        q = d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return ""
    try:
        if not math.isfinite(float(q)):
            return ""
    except Exception:
        return ""
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s

def _fmt_if_number(value):
    if value is None:
        return "—"
    s = str(value).strip()
    if s == "" or s == "—":
        return "—"
    try:
        s_num = s.replace(",", ".")
        Decimal(s_num)
        return _fmt_num(s_num) or "—"
    except Exception:
        return s


# -------------------- Export PDF placeholder --------------------
def _export_pdf_placeholder(pdf_path: str, header_text: str, meta_lines: List[str]):
    if not REPORTLAB_OK:
        raise RuntimeError("ReportLab non installato")
    c = rl_canvas.Canvas(pdf_path, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18); c.drawString(40, h - 60, header_text)
    y = h - 100; c.setFont("Helvetica", 10)
    for line in meta_lines:
        c.drawString(40, y, line); y -= 16
    y -= 12; c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Contractual Data")
    y -= 10; c.setFont("Helvetica", 10); c.drawString(40, y, "(contenuti in arrivo)")
    y -= 24; c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Loop Details — Test performed with :")
    y -= 10; c.setFont("Helvetica", 10); c.drawString(40, y, "(contenuti in arrivo)")
    y -= 24; c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Recorded / Calculated / Converted")
    y -= 10; c.setFont("Helvetica", 10); c.drawString(40, y, "(tabelle in arrivo)")
    c.showPage(); c.save()


# -------------------- Apertura file con OS --------------------
def _open_file_with_os(path: str):
    if not path or not os.path.exists(path):
        messagebox.showwarning("File", "File non trovato.")
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["open", path], check=False)
    else:
        import subprocess
        subprocess.run(["xdg-open", path], check=False)


# -------------------- util UI --------------------
def _measure_title(widget, text: str) -> int:
    try:
        style = ttk.Style()
        font_name = style.lookup("Treeview.Heading", "font") or "TkDefaultFont"
    except Exception:
        font_name = "TkDefaultFont"
    fnt = tkfont.nametofont(font_name)
    return fnt.measure(text if text else " ") + 35

def _spread_even_in_tv(tv, cols, minwidths, total_target, *, stretch=False):
    if not cols:
        mw = max(minwidths[0], total_target)
        tv.column("—", width=mw, minwidth=minwidths[0], stretch=stretch, anchor="center")
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
def open_detail_window(root, columns, values, meta):
    win = tk.Toplevel(root)
    win.title("Test Certificate")
    win.minsize(400, 800)
    win.configure(bg="#f0f0f0")

    cert_num   = values[1] if len(values) > 1 else "—"
    test_date  = values[4] if len(values) > 4 else "—"
    job_dash   = values[0] if len(values) > 0 else "—"
    pump_dash  = values[3] if len(values) > 3 else "—"

    state = {"tdms_path": (meta.get("_FilePath") if isinstance(meta, dict) else None)}

    # Notebook
    nb = ttk.Notebook(win); nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    tab = tk.Frame(nb, bg="#f0f0f0"); nb.add(tab, text="Certificato")
    curva_tab = tk.Frame(nb, bg="#f0f0f0"); nb.add(curva_tab, text="Curva")

    try:
        from curve_view import render_curve_tab
        render_curve_tab(curva_tab, state.get("tdms_path") or "")
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
    tk.Label(right, text=f"N° Cert.: {cert_num}", bg="#f0f0f0", font=("Segoe UI", 10)).pack(anchor="e")
    tk.Label(right, text="U.M. System: SI (Metric)", bg="#f0f0f0", font=("Segoe UI", 10)).pack(anchor="e")
    tk.Label(right, text=f"Test Date: {test_date}", bg="#f0f0f0", font=("Segoe UI", 10)).pack(anchor="e")

    # Body scroll
    body_wrap = tk.Frame(tab, bg="#f0f0f0"); body_wrap.grid(row=1, column=0, sticky="nsew")
    body_wrap.columnconfigure(0, weight=1); body_wrap.rowconfigure(0, weight=1)
    canvas = tk.Canvas(body_wrap, highlightthickness=0, bg="#f0f0f0")
    vscroll = ttk.Scrollbar(body_wrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)
    canvas.grid(row=0, column=0, sticky="nsew"); vscroll.grid(row=0, column=1, sticky="ns")
    body = tk.Frame(canvas, bg="#f0f0f0"); body_id = canvas.create_window((0,0), window=body, anchor="nw")
    canvas.bind("<Configure>", lambda _e=None: (canvas.configure(scrollregion=canvas.bbox("all")),
                                                canvas.itemconfigure(body_id, width=canvas.winfo_width())) )
    body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

    # Containers
    blocks = tk.Frame(body, bg="#f0f0f0")
    blocks.pack(fill="x", expand=True, padx=16, pady=(8,8))
    blocks.columnconfigure(0, weight=1)
    blocks.columnconfigure(1, weight=1)

    tables_row = tk.Frame(body, bg="#f0f0f0")
    tables_row.pack(fill="both", expand=True, padx=16, pady=(8,16))
    tables_row.grid_columnconfigure(0, weight=0)
    tables_row.grid_columnconfigure(1, weight=1)
    tables_row.grid_columnconfigure(2, weight=0)
    tables_row.grid_rowconfigure(0, weight=1)

    # --- Contractual + Loop (usa tdms_reader) ---
    def render_contract_and_loop(tdms_path: str):
        for w in blocks.winfo_children():
            w.destroy()

        cap = tdh = eff = abs_pow = speed = sg = temp = visc = npsh = liquid = "—"
        cust = po = end_user = specs = "—"
        item = pump = sn = imp_draw = imp_mat = imp_dia = "—"
        suction = discharge = watt_const = atmpress = knpsh = watertemp = kventuri = "—"

        if NPTDMS_OK and tdms_path and os.path.exists(tdms_path):
            try:
                data = read_contract_and_loop_data(tdms_path)
                # Contractual
                cap     = _fmt_if_number(data.get("Capacity [m3/h]", ""))
                tdh     = _fmt_if_number(data.get("TDH [m]", ""))
                eff     = _fmt_if_number(data.get("Efficiency [%]", ""))
                abs_pow = _fmt_if_number(data.get("ABS_Power [kW]", ""))
                speed   = _fmt_if_number(data.get("Speed [rpm]", ""))
                sg      = _fmt_if_number(data.get("SG Contract", ""))
                temp    = _fmt_if_number(data.get("Temperature [°C]", ""))
                visc    = _fmt_if_number(data.get("Viscosity [cP]", ""))
                npsh    = _fmt_if_number(data.get("NPSH [m]", ""))
                liquid  = data.get("Liquid", "") or "—"

                cust    = data.get("Customer", "") or "—"
                po      = data.get("Purchaser Order", "") or "—"
                end_user= data.get("End User", "") or "—"
                specs   = data.get("Applic. Specs.", "") or "—"

                item    = data.get("Item", "") or "—"
                pump    = data.get("Pump", "") or "—"
                sn      = data.get("Serial Number_Elenco", "") or "—"
                imp_draw= data.get("Impeller Drawing", "") or "—"
                imp_mat = data.get("Impeller Material", "") or "—"
                imp_dia = data.get("Diam Nominal", "") or "—"

                suction     = _fmt_if_number(data.get("Suction [Inch]", ""))
                discharge   = _fmt_if_number(data.get("Discharge [Inch]", ""))
                watt_const  = _fmt_if_number(data.get("Wattmeter Const.", ""))
                atmpress    = _fmt_if_number(data.get("AtmPress [m]", ""))
                knpsh       = _fmt_if_number(data.get("KNPSH [m]", ""))
                watertemp   = _fmt_if_number(data.get("WaterTemp [°C]", ""))
                kventuri    = _fmt_if_number(data.get("KVenturi", ""))
            except Exception:
                pass

        contractual = tk.LabelFrame(blocks, text="Contractual Data", bg="#f0f0f0")
        contractual.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        contractual.columnconfigure(0, weight=1); contractual.columnconfigure(1, weight=1)

        col1 = tk.Frame(contractual, bg="#f0f0f0"); col1.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        _kv_row(col1, "Capacity [m³/h]", cap); _kv_row(col1, "TDH [m]", tdh); _kv_row(col1, "Efficiency", eff)
        _kv_row(col1, "ABS_Power [kW]", abs_pow); _kv_row(col1, "Speed [rpm]", speed); _kv_row(col1, "SG", sg)
        _kv_row(col1, "Temperature [°C]", temp)
        _kv_row(col1, "Viscosity [cP]", visc); _kv_row(col1, "NPSH [m]", npsh); _kv_row(col1, "Liquid", liquid)

        col2 = tk.Frame(contractual, bg="#f0f0f0"); col2.grid(row=0, column=1, sticky="nsew", padx=(8,0))
        _kv_row(col2, "FSG ORDER", job_dash if job_dash and job_dash != "—" else "—")
        _kv_row(col2, "CUSTOMER", cust); _kv_row(col2, "P.O.", po)
        _kv_row(col2, "End User", end_user); _kv_row(col2, "Item", item)
        pump_model = pump if pump and pump != "—" else (values[3] if len(values) > 3 else "—")
        _kv_row(col2, "Pump", pump_model)
        _kv_row(col2, "S. N.", sn); _kv_row(col2, "Imp. Draw.", imp_draw); _kv_row(col2, "Imp. Mat.", imp_mat)
        _kv_row(col2, "Imp Dia [mm]", imp_dia); _kv_row(col2, "Specs", specs)

        loop = tk.LabelFrame(blocks, text="Loop Details", bg="#f0f0f0")
        loop.grid(row=0, column=1, sticky="nsew", padx=(8,0))
        tk.Label(loop, text="Test performed with :", bg="#f0f0f0", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8, pady=(6,2))
        for line in [
            f"Suction [Inch] {suction}",
            f"Discharge [Inch] {discharge}",
            f"Wattmeter Const. {watt_const}",
            f"AtmPress [m] {atmpress}",
            f"KNPSH [m] {knpsh}",
            f"WaterTemp [°C] {watertemp}",
            f"Kventuri {kventuri}",
        ]:
            tk.Label(loop, text=line, bg="#f0f0f0", font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=2)

    # --- Tre tabelle (Recorded/Calc/Converted) ---
    def render_tables(tdms_path: str):
        for w in tables_row.winfo_children():
            w.destroy()

        perf = read_performance_tables_dynamic(tdms_path, test_index=0) if tdms_path else {
            "Recorded": {"columns": [], "rows": []},
            "Calc": {"columns": [], "rows": []},
            "Converted": {"columns": [], "rows": []},
        }
        rec_cols, rec_rows    = perf["Recorded"]["columns"], perf["Recorded"]["rows"]
        calc_cols, calc_rows  = perf["Calc"]["columns"],     perf["Calc"]["rows"]
        conv_cols, conv_rows  = perf["Converted"]["columns"], perf["Converted"]["rows"]

        def _make_table(parent, title, cols, mode):
            lf = tk.LabelFrame(parent, text=title, bg="#f0f0f0")
            lf.rowconfigure(0, weight=1)
            lf.columnconfigure(0, weight=(1 if mode == "center" else 0))

            tv = ttk.Treeview(lf, columns=cols or ("—",), show="headings", height=12, selectmode="browse")

            minwidths = []
            if not cols:
                tv.heading("—", text="—")
                mw = _measure_title(tv, "—")
                tv.column("—", minwidth=mw, width=mw, anchor="center", stretch=(mode=="center"))
                minwidths = [mw]
            else:
                for c in cols:
                    tv.heading(c, text=c)
                    mw = _measure_title(tv, c)
                    tv.column(c, minwidth=mw, width=mw, anchor="center", stretch=(mode=="center"))
                    minwidths.append(mw)

            tv.grid(row=0, column=0, sticky=("nsew" if mode=="center" else "ns"))
            return lf, tv, (cols if cols else ["—"]), minwidths

        # crea le tre tabelle
        lf_left,  tv_left,  left_cols,  left_mins  = _make_table(tables_row, "Recorded Data",    rec_cols,  "left")
        lf_mid,   tv_mid,   mid_cols,   mid_mins   = _make_table(tables_row, "Calculated Values", calc_cols, "center")
        lf_right, tv_right, right_cols, right_mins = _make_table(tables_row, "Converted Values",  conv_cols, "right")

        # posizionamento
        lf_left.grid (row=0, column=0, sticky="w",   padx=(0,8))
        lf_mid.grid  (row=0, column=1, sticky="nsew", padx=8)
        lf_right.grid(row=0, column=2, sticky="e",   padx=(8,0))

        # clamp laterali
        def _clamp_tv_to_frame(tv, cols, mins, frame, pad=16):
            try:
                frame.update_idletasks()
            except Exception:
                pass

            if not cols:
                avail = max(mins[0], frame.winfo_width() - pad)
                cur   = tv.column("—", option="width")
                tv.column("—", width=min(cur, avail))
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
            tv_left.insert("", "end", iid=f"p{idx:03d}", values=vals)
        for idx, vals in enumerate(calc_rows, start=1):
            tv_mid.insert("", "end", iid=f"p{idx:03d}", values=vals)
        for idx, vals in enumerate(conv_rows, start=1):
            tv_right.insert("", "end", iid=f"p{idx:03d}", values=vals)

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

            try:
                vscroll_w = max(vscroll.winfo_reqwidth(), 15)
            except Exception:
                vscroll_w = 15

            safety = 12
            min_window_width = content_req + outer_tables + outer_nb + vscroll_w + safety
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
                except Exception: pass

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

        # selezione iniziale
        try:
            first_iid = next(iter(tv_left.get_children()), None)
            if first_iid:
                tv_left.selection_set(first_iid); tv_left.focus(first_iid); tv_left.see(first_iid)
        except StopIteration:
            pass

    # Render iniziale
    render_contract_and_loop(state["tdms_path"])
    render_tables(state["tdms_path"])
