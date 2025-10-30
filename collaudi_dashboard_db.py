# collaudi_dashboard_db.py
import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date

from certificate_view import open_detail_window
from tdms_reader import read_tdms_fields

# === DB layer (modulo esterno) ===
from db import (
    init as db_init,
    select_all_acquisizioni,
    insert_acquisizione,
    delete_acquisizione,
    update_stato,
    note_get as db_note_get,
    note_set as db_note_set,
)

# ========= CONFIG =========
FOLDER_PATH = os.path.expanduser("~")   # cartella predefinita utente
DB_PATH     = "collaudi.db"

# Regex "stretta": DATA-REC_<commessa>_<matricola>_<YYYYMMDD>-<HHMMSS>_<00000>.tdms
TDMS_PATTERN = re.compile(
    r'^DATA-REC_(?P<commessa>[A-Z0-9]+)_(?P<matricola>[A-Z0-9]+)_(?P<data>\d{8})-(?P<ora>\d{6})_(?P<progressivo>\d{5})\.tdms$'
)

# Stato: valori consentiti
STATO_VALUES = ["Approved", "Rejected", "Unchecked", "Checked", "Inactive"]

# UI defaults
DEFAULT_USERNAME = "Operatore"
DEFAULT_RUOLO = "Visualizzatore"


# ========= PARSING NOME FILE =========
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


# ========= INGEST (usa tdms_reader + db.py) =========
def ingest_one_record(rec: dict):
    """
    Arricchisce il record con i dati dal TDMS e lo inserisce a DB.
    rec atteso: job, matricola, data_file, ora_file, data_iso, progressivo, filepath, filename
    """
    tdms_vals  = read_tdms_fields(rec["filepath"])
    n_collaudo = tdms_vals.get("n_collaudo", "")
    tipo_pompa = tdms_vals.get("tipo_pompa", "")
    to_insert = {
        **rec,
        "n_collaudo": n_collaudo,
        "tipo_pompa": tipo_pompa,
        "stato": "Unchecked",
    }
    insert_acquisizione(DB_PATH, to_insert)


# ========= UI =========
def launch_dashboard(folder_path: str, username: str, ruolo: str):
    # Inizializza DB
    db_init(DB_PATH)

    root = tk.Tk()
    root.title("Dashboard Collaudi")
    root.geometry("1500x650")
    root.minsize(1100, 650)
    root.configure(bg="#f0f0f0")

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
        "TAGLIO GIRANTE",
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
        "TAGLIO GIRANTE": 1.3,
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
            minw = 80 if col not in ("TIPO POMPA", "NOME APPROVATORE", "TAGLIO GIRANTE") else 120
            tree.column(col, width=max(w, minw))

    tree.bind("<Configure>", autosize_columns)
    root.after(100, autosize_columns)

    data_by_iid = {}

    # Pulsanti
    frame_btn = tk.Frame(root, bg="#f0f0f0")
    frame_btn.pack(pady=10, fill=tk.X)

    btn_visualizza = tk.Button(frame_btn, text="VISUALIZZA", bg="#1a73e8", fg="white", width=15)
    btn_note       = tk.Button(frame_btn, text="NOTE",       bg="#1a73e8", fg="white", width=15)
    btn_cartella   = tk.Button(frame_btn, text="CARTELLA",   bg="#1a73e8", fg="white", width=15)
    btn_load_tdms  = tk.Button(frame_btn, text="Load TDMS",   bg="#34a853", fg="white", width=15)
    btn_unload_tdms= tk.Button(frame_btn, text="Unload TDMS", bg="#ea4335", fg="white", width=15)
    btn_refresh    = tk.Button(frame_btn, text="AGGIORNA",   width=12)

    btn_visualizza.pack(side=tk.LEFT, padx=5)
    btn_note.pack(side=tk.LEFT, padx=5)
    btn_cartella.pack(side=tk.LEFT, padx=5)
    btn_load_tdms.pack(side=tk.LEFT, padx=(20,5))
    btn_unload_tdms.pack(side=tk.LEFT, padx=5)
    btn_refresh.pack(side=tk.RIGHT, padx=5)

    for b in (btn_visualizza, btn_note, btn_cartella, btn_unload_tdms):
        b.config(state="disabled")

    stato_combo = ttk.Combobox(tree, values=STATO_VALUES, state="readonly")
    stato_combo.place_forget()

    # ---- Helpers DB → UI ----
    def refresh_from_db():
        tree.delete(*tree.get_children())
        data_by_iid.clear()

        rows = select_all_acquisizioni(DB_PATH)

        for idx, r in enumerate(rows, start=1):
            acq_id = r[0]
            raw_vals = r[1:11]
            values = tuple("" if v is None else v for v in raw_vals)
            stato_val = values[5]
            tag = tag_for_status(stato_val)
            iid = f"row_{idx}"
            tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
            data_by_iid[iid] = {"id": acq_id, "_FilePath": r[11], "_FileName": r[12]}

        autosize_columns()
        status_var.set(f"Record caricati: {len(rows)}")
        on_tree_select()

    def on_tree_select(_=None):
        sel = tree.focus()
        state = "normal" if sel else "disabled"
        for b in (btn_visualizza, btn_note, btn_cartella, btn_unload_tdms):
            b.config(state=state)
        stato_combo.place_forget()

    def open_folder(filepath: str):
        if sys.platform.startswith("win"):
            try:
                subprocess.run(["explorer", "/select,", filepath], check=False)
            except Exception:
                subprocess.run(["explorer", os.path.dirname(filepath)], check=False)
        elif sys.platform == "darwin":
            try:
                subprocess.run(["open", "-R", filepath], check=False)
            except Exception:
                subprocess.run(["open", os.path.dirname(filepath)], check=False)
        else:
            subprocess.run(["xdg-open", os.path.dirname(filepath)], check=False)

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
            if meta and new_val in STATO_VALUES:
                approved_date = date.today().isoformat() if (new_val == "Approved" and current_stato != "Approved") else None
                update_stato(DB_PATH, meta["id"], new_val, approved_date)

                current_values[5] = new_val
                current_values[6] = approved_date if approved_date else ""
                tree.item(item, values=tuple(current_values))
                tree.item(item, tags=(tag_for_status(new_val),))
            stato_combo.place_forget()

        stato_combo.unbind("<<ComboboxSelected>>")
        stato_combo.bind("<<ComboboxSelected>>", on_sel)

    # ---- Azioni ----
    def get_sel_row_meta():
        sel = tree.focus()
        if not sel:
            return None
        return data_by_iid.get(sel)

    def do_visualizza():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return
        vals = tree.item(tree.focus(), "values")
        open_detail_window(root, columns, vals, meta)

    def do_note():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return

        win = tk.Toplevel(root)
        win.title(f"Note — {meta['_FileName']}")
        win.geometry("560x480")
        win.minsize(480, 360)
        win.configure(bg="#f0f0f0")
        win.transient(root)
        win.grab_set()

        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)

        lbl = tk.Label(win, text="Modifica la nota:", font=("Segoe UI", 12, "bold"), bg="#f0f0f0", anchor="w")
        lbl.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")

        editor_frame = tk.Frame(win, bg="#f0f0f0")
        editor_frame.grid(row=1, column=0, padx=10, pady=0, sticky="nsew")
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        text_note = tk.Text(editor_frame, wrap="word", font=("Segoe UI", 10), undo=True)
        text_note.grid(row=0, column=0, sticky="nsew")

        scroll_y = ttk.Scrollbar(editor_frame, orient="vertical", command=text_note.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        text_note.configure(yscrollcommand=scroll_y.set)

        text_note.insert(tk.END, db_note_get(DB_PATH, meta["_FilePath"]) or "")

        btn_frame = tk.Frame(win, bg="#f0f0f0")
        btn_frame.grid(row=2, column=0, padx=10, pady=10, sticky="e")

        def salva():
            try:
                nuova = text_note.get("1.0", tk.END).strip()
                db_note_set(DB_PATH, meta["_FilePath"], nuova)
                messagebox.showinfo("Successo", "Nota salvata.")
                win.destroy()
            except Exception as e:
                messagebox.showwarning("Errore", f"Impossibile salvare la nota:\n{e}")

        btn_salva = tk.Button(btn_frame, text="Salva", command=salva, bg="#1a73e8", fg="white", width=12)
        btn_chiudi = tk.Button(btn_frame, text="Chiudi", command=win.destroy, width=12)
        btn_chiudi.pack(side=tk.RIGHT, padx=(6, 0))
        btn_salva.pack(side=tk.RIGHT)

    def do_cartella():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return
        open_folder(meta["_FilePath"])

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
        }
        try:
            ingest_one_record(rec)
            set_status("TDMS importato correttamente.")
            refresh_from_db()
        except Exception as e:
            # sqlite3.IntegrityError (record duplicato) o altre eccezioni:
            if "UNIQUE constraint failed" in str(e):
                messagebox.showinfo("Già presente", "Questo file è già presente in archivio.")
            else:
                messagebox.showerror("Errore import", f"Non è stato possibile importare il file:\n{e}")

    def do_unload_tdms():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga da rimuovere.")
            return
        conferma = messagebox.askyesno(
            "Conferma rimozione",
            "Vuoi rimuovere la riga selezionata dal database?\n"
            "L'eventuale nota associata verrà eliminata."
        )
        if not conferma:
            return
        try:
            delete_acquisizione(DB_PATH, meta["id"])
            set_status("Record rimosso dal database.")
            refresh_from_db()
        except Exception as e:
            messagebox.showerror("Errore rimozione", f"Impossibile rimuovere il record:\n{e}")

    # Wiring bottoni ed eventi
    btn_visualizza.config(command=do_visualizza)
    btn_note.config(command=do_note)
    btn_cartella.config(command=do_cartella)
    btn_load_tdms.config(command=do_load_tdms)
    btn_unload_tdms.config(command=do_unload_tdms)
    tree.bind("<<TreeviewSelect>>", on_tree_select)
    tree.bind("<Button-1>", on_tree_click)

    # Carica dalla base dati
    refresh_from_db()

    def do_refresh():
        set_status("Ricarico dati dal database…")
        refresh_from_db()
        set_status("Dati aggiornati dal database.")
    btn_refresh.config(command=do_refresh)

    root.mainloop()


# ========= MAIN =========
if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else FOLDER_PATH
    launch_dashboard(folder, DEFAULT_USERNAME, DEFAULT_RUOLO)
