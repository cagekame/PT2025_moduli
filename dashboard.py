# collaudi_dashboard_db.py
import os
import re
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date

import icon_helper  # Per l'icona PT2025.ico
from notes_window import open_notes_window
from certificate_view import open_detail_window
from tdms_reader import read_tdms_fields

from pdf_report import preview_pdf_report

# === DB layer (modulo esterno) ===
from db import (
    init as db_init,
    select_all_acquisizioni,
    insert_acquisizione,
    delete_acquisizione,
    update_stato,
    note_collaudatore_get,
    note_collaudatore_set,
    note_ingegneria_get,
    note_ingegneria_set,
)

# ========= CONFIG =========
FOLDER_PATH = os.path.expanduser("~")   # cartella predefinita utente

TDMS_PATTERN = re.compile(
    r'^DATA-REC_(?P<commessa>[A-Z0-9]+)_(?P<matricola>[A-Z0-9]+)_(?P<data>\d{8})-(?P<ora>\d{6})_(?P<progressivo>\d{5})\.tdms$'
)

STATO_VALUES = ["Approved", "Rejected", "Unchecked", "Checked", "Inactive"]

DEFAULT_USERNAME = "Operatore"
DEFAULT_RUOLO = "Visualizzatore"


def parse_tdms_name(fname: str):
    m = TDMS_PATTERN.fullmatch(fname)
    if not m:
        return None
    commessa  = m.group("commessa")
    matricola = m.group("matricola")
    data_raw  = m.group("data")
    ora_raw   = m.group("ora")
    prog_raw  = m.group("progressivo")
    data_iso  = f"{data_raw[0:4]}-{data_raw[4:6]}-{data_raw[6:8]}"
    prog_int  = int(prog_raw)
    return {
        "job": commessa,
        "matricola": matricola,
        "data_file": data_raw,
        "ora_file": ora_raw,
        "data_iso": data_iso,
        "progressivo": prog_int,
    }


def ingest_one_record(rec: dict):
    """
    Inserisce uno o più record nella dashboard in base ai tipi di test presenti nel TDMS.
    
    Un file TDMS può contenere più tipi di test (PERFORMANCE, NPSH, RUNNING).
    Viene creato un record separato per ogni tipo di test trovato.
    """
    from tdms_reader import detect_test_types
    
    tdms_vals  = read_tdms_fields(rec["filepath"])
    n_collaudo = tdms_vals.get("n_collaudo", "")
    tipo_pompa = tdms_vals.get("tipo_pompa", "")
    
    # Rileva i tipi di test presenti nel TDMS
    test_types = detect_test_types(rec["filepath"])
    
    # Se non trova nessun test type, usa un fallback (probabilmente PERFORMANCE)
    if not test_types:
        test_types = ["PERFORMANCE"]
    
    # Crea un record per ogni tipo di test trovato
    for test_type in test_types:
        to_insert = {
            **rec,
            "n_collaudo": n_collaudo,
            "tipo_pompa": tipo_pompa,
            "tipo_test": test_type,  # Imposta il tipo di test
            "stato": "Unchecked",
        }
        insert_acquisizione(to_insert)


def launch_dashboard(folder_path: str, username: str, ruolo: str, parent_root=None, on_close_callback=None):
    db_init()

    # Se abbiamo un parent (login), usa Toplevel, altrimenti usa Tk (standalone)
    if parent_root:
        root = tk.Toplevel(parent_root)
    else:
        root = tk.Tk()
    
    root.title("Dashboard Collaudi")
    root.geometry("1500x650")
    root.minsize(1100, 650)
    root.configure(bg="#f0f0f0")
    
    # Imposta l'icona della finestra
    icon_helper.set_window_icon(root)
    
    # Gestisci chiusura finestra
    def on_closing():
        root.destroy()
        if on_close_callback:
            on_close_callback()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)

    header = tk.Label(
        root,
        text=f"Benvenuto {username} ({ruolo})",
        font=("Segoe UI", 16, "bold"),
        bg="#f0f0f0"
    )
    header.pack(pady=10)

    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(root, textvariable=status_var, bg="#f0f0f0", anchor="w")
    status_lbl.pack(padx=20, fill=tk.X)

    def set_status(msg: str):
        root.after(0, lambda: status_var.set(msg))

    frame_tree = tk.Frame(root, bg="#f0f0f0")
    frame_tree.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)

    columns = (
        "JOB",
        "N° COLLAUDO",
        "MATRICOLA",
        "TIPO POMPA",
        "DATA",
        "STATO",
        "DATA APPROVAZIONE",
        "NOME APPROVATORE",
        "TIPO TEST",
    )
    header_texts = {c: c for c in columns}

    col_weights = {
        "JOB": 1.0,
        "N° COLLAUDO": 1.0,
        "MATRICOLA": 1.0,
        "TIPO POMPA": 1.4,
        "DATA": 0.9,
        "STATO": 0.9,
        "DATA APPROVAZIONE": 1.2,
        "NOME APPROVATORE": 1.4,
        "TIPO TEST": 1.1,
    }
    total_weight = sum(col_weights[c] for c in columns)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    tree = ttk.Treeview(frame_tree, columns=columns, show="headings", height=20)
    vsb = ttk.Scrollbar(frame_tree, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)

    for col in columns:
        tree.heading(col, text=header_texts[col])
        tree.column(col, width=100, anchor="w", stretch=True)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    frame_tree.rowconfigure(0, weight=1)
    frame_tree.columnconfigure(0, weight=1)

    tree.tag_configure("tag_checked", background="#FFD8A8")
    tree.tag_configure("tag_unchecked", background="#FFF7C2")
    tree.tag_configure("tag_approved",  background="#D0F0C0")
    tree.tag_configure("tag_rejected",  background="#F8D0D0")
    tree.tag_configure("tag_inactive",  background="#E6E6E6")

    def tag_for_status(st: str) -> str:
        s = (st or "").strip().lower()
        if s == "approved": return "tag_approved"
        if s == "rejected": return "tag_rejected"
        if s == "inactive": return "tag_inactive"
        if s == "checked":  return "tag_checked"
        return "tag_unchecked"

    def autosize_columns(_event=None):
        tree.update_idletasks()
        total_width = tree.winfo_width()
        margin = 12
        avail = max(total_width - margin, 200)
        for col in columns:
            w = int(avail * (col_weights[col] / total_weight))
            minw = 80 if col not in ("TIPO POMPA", "NOME APPROVATORE") else 120
            tree.column(col, width=max(w, minw))

    tree.bind("<Configure>", autosize_columns)
    root.after(100, autosize_columns)

    data_by_iid = {}

    # -------------------------
    # PULSANTI
    # -------------------------
    frame_btn = tk.Frame(root, bg="#f0f0f0")
    frame_btn.pack(padx=20, pady=10, fill=tk.X)

    btn_load_tdms   = tk.Button(frame_btn, text="Load TDMS",   bg="#34a853", fg="white", width=15)
    btn_unload_tdms = tk.Button(frame_btn, text="Unload TDMS", bg="#ea4335", fg="white", width=15)
    btn_note        = tk.Button(frame_btn, text="NOTE",        bg="#1a73e8", fg="white", width=15)
    btn_open_cert   = tk.Button(frame_btn, text="Apri certificato", bg="#6c757d", fg="white", width=15)
    btn_pdf_preview = tk.Button(frame_btn, text="Export PDF", bg="#0b5ed7", fg="white", width=15)
    btn_verify_tdms = tk.Button(frame_btn, text="Verifica TDMS", bg="#fbbc04", fg="black", width=15)

    btn_load_tdms.pack(side=tk.LEFT, padx=(0, 5))
    btn_unload_tdms.pack(side=tk.LEFT, padx=5)
    btn_note.pack(side=tk.LEFT, padx=5)
    btn_open_cert.pack(side=tk.LEFT, padx=5)
    btn_pdf_preview.pack(side=tk.LEFT, padx=5)
    btn_verify_tdms.pack(side=tk.LEFT, padx=5)

    for b in (btn_note, btn_unload_tdms, btn_open_cert, btn_pdf_preview):
        b.config(state="disabled")

    stato_combo = ttk.Combobox(tree, values=STATO_VALUES, state="readonly")
    stato_combo.place_forget()

    # ---- Helpers DB → UI ----
    def refresh_from_db():
        tree.delete(*tree.get_children())
        data_by_iid.clear()

        rows = select_all_acquisizioni()

        for idx, r in enumerate(rows, start=1):
            acq_id = r[0]

            # r[1:10] = job, n_collaudo, matricola, tipo_pompa, data, stato,
            #           data_approvazione, nome_approvatore, tipo_test
            # ESCLUDIAMO taglio_girante dalla visualizzazione
            raw_vals = r[1:10]

            values = tuple("" if v is None else v for v in raw_vals)
            stato_val = values[5]
            tag = tag_for_status(stato_val)
            iid = f"row_{idx}"
            tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))

            # taglio_girante = r[10], filepath = r[11], filename = r[12]
            data_by_iid[iid] = {"id": acq_id, "_FilePath": r[11], "_FileName": r[12]}

        autosize_columns()
        status_var.set(f"Record caricati: {len(rows)}")
        on_tree_select()

    def _selected_state():
        sel = tree.focus()
        if not sel:
            return ""
        vals = tree.item(sel, "values")
        return vals[5] if vals and len(vals) > 5 else ""

    def on_tree_select(_=None):
        sel = tree.focus()
        has_sel = bool(sel)

        btn_open_cert.config(state="normal" if has_sel else "disabled")
        btn_note.config(state="normal" if has_sel else "disabled")

        # Solo Admin può cancellare TDMS
        if has_sel and ruolo == "Admin":
            btn_unload_tdms.config(state="normal")
        else:
            btn_unload_tdms.config(state="disabled")

        stato_cur = _selected_state()
        if has_sel and stato_cur in ("Approved", "Rejected"):
            btn_pdf_preview.config(state="normal")
        else:
            btn_pdf_preview.config(state="disabled")

    # ---- In-cell editor per STATO ----
    def on_tree_click(event):
        item = tree.identify_row(event.y)
        col_id  = tree.identify_column(event.x)
        if not item or col_id != "#6":
            stato_combo.place_forget()
            return

        bbox = tree.bbox(item, column=col_id)
        if not bbox:
            stato_combo.place_forget()
            return

        x, y, w, h = bbox
        current_values = list(tree.item(item, "values"))
        current_stato = current_values[5] if len(current_values) > 5 else ""
        stato_combo.set(current_stato if current_stato in STATO_VALUES else "")
        stato_combo.place(x=x, y=y, width=w, height=h)

        def on_sel(_e=None):
            new_val = stato_combo.get()
            meta = data_by_iid.get(item)
            if not (meta and new_val in STATO_VALUES):
                stato_combo.place_forget()
                return

            current_stato_local = current_values[5] if len(current_values) > 5 else ""

            if new_val == current_stato_local:
                stato_combo.place_forget()
                return

            if new_val == "Unchecked":
                messagebox.showwarning("Cambio non consentito", "Non è possibile riportare un collaudo allo stato UNCHECKED.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            if new_val == "Checked" and current_stato_local in ("Approved", "Rejected"):
                messagebox.showwarning("Cambio non consentito", "Non è possibile riportare un collaudo da APPROVED/REJECTED a CHECKED.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            if ruolo == "Visualizzatore":
                messagebox.showwarning("Permesso negato", "Con il ruolo Visualizzatore non puoi modificare lo stato.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            if ruolo == "Collaudatore":
                if not (current_stato_local == "Unchecked" and new_val == "Checked"):
                    messagebox.showwarning("Permesso negato", "Come collaudatore puoi solo passare lo stato da UNCHECKED a CHECKED.")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return
                note_coll = (note_collaudatore_get(meta["_FilePath"]) or "").strip()
                if not note_coll:
                    messagebox.showwarning("Nota mancante", "Per passare lo stato a CHECKED devi prima inserire una nota (pulsante NOTE).")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return

            elif ruolo == "Ingegneria":
                if not (current_stato_local == "Checked" and new_val in ("Approved", "Rejected")):
                    messagebox.showwarning("Permesso negato", "Con il ruolo Ingegneria puoi cambiare stato solo da CHECKED a APPROVED o REJECTED.")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return
                note_ing = (note_ingegneria_get(meta["_FilePath"]) or "").strip()
                if not note_ing:
                    messagebox.showwarning("Nota mancante", "Per passare lo stato a APPROVED o REJECTED devi prima inserire una nota di ingegneria (pulsante NOTE).")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return

            elif ruolo == "Admin":
                if new_val in ("Approved", "Rejected"):
                    note_ing = (note_ingegneria_get(meta["_FilePath"]) or "").strip()
                    if not note_ing:
                        messagebox.showwarning("Nota mancante", "Per passare lo stato a APPROVED o REJECTED devi prima inserire una nota di ingegneria (pulsante NOTE).")
                        stato_combo.set(current_stato_local)
                        stato_combo.place_forget()
                        return

            if new_val == "Inactive" and ruolo != "Admin":
                messagebox.showwarning("Permesso negato", "Solo un Admin può impostare lo stato a INACTIVE.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            change_date_local = date.today().isoformat()
            update_stato(meta["id"], new_val, change_date_local, username, ruolo)

            current_values[5] = new_val
            current_values[6] = change_date_local
            current_values[7] = username

            tree.item(item, values=tuple(current_values))
            tree.item(item, tags=(tag_for_status(new_val),))
            stato_combo.place_forget()

            on_tree_select()

        stato_combo.unbind("<<ComboboxSelected>>")
        stato_combo.bind("<<ComboboxSelected>>", on_sel)

    # ---- Azioni ----
    def get_sel_row_meta():
        sel = tree.focus()
        if not sel:
            return None
        return data_by_iid.get(sel)

    def do_note():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return

        sel = tree.focus()
        vals = tree.item(sel, "values")
        stato_cur = vals[5] if vals and len(vals) > 5 else ""

        open_notes_window(
            root,
            filepath=meta["_FilePath"],
            filename=meta["_FileName"],
            ruolo=ruolo,
            stato_cur=stato_cur,
            note_collaudatore_get=note_collaudatore_get,
            note_collaudatore_set=note_collaudatore_set,
            note_ingegneria_get=note_ingegneria_get,
            note_ingegneria_set=note_ingegneria_set,
        )

    def do_open_cert():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return
        sel = tree.focus()
        vals = tree.item(sel, "values")
        
        # vals[8] contiene TIPO TEST (PERFORMANCE, NPSH, RUNNING)
        tipo_test = vals[8] if vals and len(vals) > 8 else "PERFORMANCE"
        
        open_detail_window(root, columns, vals, meta, tipo_test=tipo_test)

    def do_pdf_preview():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return

        sel = tree.focus()
        vals = tree.item(sel, "values")
        stato_cur = vals[5] if vals and len(vals) > 5 else ""
        if stato_cur not in ("Approved", "Rejected"):
            messagebox.showinfo("PDF non disponibile", "Il PDF è disponibile solo per collaudi APPROVED o REJECTED.")
            return

        change_date_local = vals[6] if vals and len(vals) > 6 else date.today().isoformat()

        preview_pdf_report(
            root,
            meta_dict=meta,
            values_tuple=vals,
            change_date=change_date_local,
            username=username,
            note_collaudatore_get=note_collaudatore_get,
            note_ingegneria_get=note_ingegneria_get,
        )

    # ---- Load / Unload TDMS ----
    def do_load_tdms():
        initial_dir = folder_path if os.path.isdir(folder_path) else os.path.expanduser("~")
        path = filedialog.askopenfilename(
            title="Seleziona file TDMS",
            initialdir=initial_dir,
            filetypes=[("TDMS files", "*.tdms"), ("Tutti i file", "*.*")]
        )
        if not path:
            return

        fname = os.path.basename(path)
        meta_name = parse_tdms_name(fname)
        if not meta_name:
            messagebox.showwarning(
                "Formato non valido",
                "Il nome del file non rispetta il formato richiesto:\n"
                "DATA-REC_<commessa>_<matricola>_<YYYYMMDD>-<HHMMSS>_<00000>.tdms"
            )
            return

        rec = {
            **meta_name,
            "filepath": path,
            "filename": fname,
            "created_by": username,
        }
        try:
            ingest_one_record(rec)
            set_status("TDMS importato correttamente.")
            refresh_from_db()
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                messagebox.showinfo("Già presente", "Questo file è già presente in archivio.")
            else:
                messagebox.showerror("Errore import", f"Non è stato possibile importare il file:\n{e}")

    def do_unload_tdms():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga da rimuovere.")
            return

        # Solo Admin può rimuovere record
        if ruolo != "Admin":
            messagebox.showwarning("Permesso negato", "Solo Admin può rimuovere record dal database.")
            return

        conferma = messagebox.askyesno(
            "Conferma rimozione",
            "Vuoi rimuovere la riga selezionata dal database?\n"
            "L'eventuale nota associata verrà eliminata."
        )
        if not conferma:
            return
        try:
            delete_acquisizione(meta["id"])
            set_status("Record rimosso dal database.")
            refresh_from_db()
        except Exception as e:
            messagebox.showerror("Errore rimozione", f"Impossibile rimuovere il record:\n{e}")
    
    def do_verify_tdms():
        """Verifica l'esistenza di tutti i file TDMS nel database."""
        try:
            all_rows = select_all_acquisizioni()
            
            missing = []
            found = 0
            
            for row in all_rows:
                # row[11] è filepath
                tdms_path = row[11] if row and len(row) > 11 else None
                
                if tdms_path:
                    if os.path.exists(tdms_path):
                        found += 1
                    else:
                        filename = os.path.basename(tdms_path)
                        missing.append(filename)
            
            # Mostra report
            if len(missing) == 0:
                messagebox.showinfo(
                    "✅ Verifica completata",
                    f"Tutti i file TDMS sono stati trovati!\n\n"
                    f"✓ {found} file verificati"
                )
            else:
                missing_list = "\n".join(f"  • {f}" for f in missing[:10])
                if len(missing) > 10:
                    missing_list += f"\n  ... e altri {len(missing) - 10} file"
                
                messagebox.showwarning(
                    "⚠️ File mancanti",
                    f"Verifica completata:\n\n"
                    f"✓ {found} file trovati\n"
                    f"✗ {len(missing)} file mancanti:\n\n"
                    f"{missing_list}\n\n"
                    f"Apri i certificati per aggiornare i percorsi."
                )
        
        except Exception as e:
            messagebox.showerror("Errore verifica", f"Impossibile verificare i file:\n{e}")

    # Wiring bottoni ed eventi
    btn_note.config(command=do_note)
    btn_load_tdms.config(command=do_load_tdms)
    btn_unload_tdms.config(command=do_unload_tdms)
    btn_open_cert.config(command=do_open_cert)
    btn_pdf_preview.config(command=do_pdf_preview)
    btn_verify_tdms.config(command=do_verify_tdms)

    tree.bind("<<TreeviewSelect>>", on_tree_select)
    tree.bind("<Button-1>", on_tree_click)

    refresh_from_db()
    
    # mainloop solo se standalone (non chiamato da login)
    if not parent_root:
        root.mainloop()


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else FOLDER_PATH
    launch_dashboard(folder, DEFAULT_USERNAME, DEFAULT_RUOLO)