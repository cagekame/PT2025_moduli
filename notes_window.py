# notes_window.py
import tkinter as tk
from tkinter import ttk, messagebox


def open_notes_window(
    parent,
    *,
    filepath: str,
    filename: str,
    ruolo: str,
    stato_cur: str,
    # funzioni DB (passate dal chiamante)
    note_collaudatore_get,
    note_collaudatore_set,
    note_ingegneria_get,
    note_ingegneria_set,
):

    filepath = (filepath or "").strip()
    if not filepath:
        messagebox.showwarning("Errore", "Percorso file TDMS non valido per la gestione note.")
        return

    stato_cur = (stato_cur or "").strip()
    ruolo = (ruolo or "").strip()

    # ---- regole edit ----
    can_edit_coll = (ruolo == "Collaudatore" and stato_cur == "Unchecked")
    can_edit_ing = ((ruolo in ("Ingegneria", "Admin")) and stato_cur == "Checked")

    win = tk.Toplevel(parent)
    win.title(f"NOTE — {filename}")
    win.geometry("900x520")
    win.minsize(760, 420)
    win.configure(bg="#f0f0f0")
    win.transient(parent)
    
    # Imposta l'icona
    try:
        import icon_helper
        icon_helper.set_window_icon(win)
    except:
        pass
    win.grab_set()

    # layout: 2 colonne
    win.columnconfigure(0, weight=1)
    win.columnconfigure(1, weight=1)
    win.rowconfigure(1, weight=1)

    # header info
    info = tk.Label(
        win,
        text=f"Stato: {stato_cur}   |   Ruolo: {ruolo}",
        font=("Segoe UI", 10, "bold"),
        bg="#f0f0f0",
        anchor="w"
    )
    info.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="ew")

    def make_note_box(col, title: str):
        box = tk.LabelFrame(win, text=title, bg="#f0f0f0", font=("Segoe UI", 11, "bold"))
        box.grid(row=1, column=col, padx=10, pady=10, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        txt = tk.Text(box, wrap="word", font=("Segoe UI", 10), undo=True)
        txt.grid(row=0, column=0, sticky="nsew")

        scr = ttk.Scrollbar(box, orient="vertical", command=txt.yview)
        scr.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=scr.set)

        return txt

    txt_coll = make_note_box(0, "Note Collaudo")
    txt_ing  = make_note_box(1, "Note Ingegneria")

    # carico sempre entrambe
    try:
        txt_coll.insert(tk.END, note_collaudatore_get(filepath) or "")
    except Exception as e:
        txt_coll.insert(tk.END, f"[ERRORE lettura Note Collaudo: {e}]")

    try:
        txt_ing.insert(tk.END, note_ingegneria_get(filepath) or "")
    except Exception as e:
        txt_ing.insert(tk.END, f"[ERRORE lettura Note Ingegneria: {e}]")

    # blocco in sola lettura dove non editabile
    if not can_edit_coll:
        txt_coll.config(state="disabled")
    if not can_edit_ing:
        txt_ing.config(state="disabled")

    # footer con bottoni
    footer = tk.Frame(win, bg="#f0f0f0")
    footer.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
    footer.columnconfigure(0, weight=1)

    def save_if_allowed(txt_widget: tk.Text, setter, label: str):
        try:
            # se disabled, non dovrebbe arrivare qui, ma gestiamo comunque
            if str(txt_widget.cget("state")) == "disabled":
                return
            val = txt_widget.get("1.0", tk.END).strip()
            setter(filepath, val)
            messagebox.showinfo("Successo", f"{label} salvate.")
        except Exception as e:
            messagebox.showwarning("Errore", f"Impossibile salvare {label}:\n{e}")

    btn_close = tk.Button(footer, text="Chiudi", width=12, command=win.destroy)
    btn_close.pack(side=tk.RIGHT, padx=(8, 0))

    # Salva Collaudo (solo se editabile)
    if can_edit_coll:
        btn_save_coll = tk.Button(
            footer, text="Salva Collaudo", width=14,
            bg="#1a73e8", fg="white",
            command=lambda: save_if_allowed(txt_coll, note_collaudatore_set, "Note Collaudo")
        )
        btn_save_coll.pack(side=tk.RIGHT)

    # Salva Ingegneria (solo se editabile)
    if can_edit_ing:
        btn_save_ing = tk.Button(
            footer, text="Salva Ingegneria", width=16,
            bg="#1a73e8", fg="white",
            command=lambda: save_if_allowed(txt_ing, note_ingegneria_set, "Note Ingegneria")
        )
        btn_save_ing.pack(side=tk.RIGHT, padx=(0, 8))

    # messaggino chiaro sui permessi
    perm_msg = []
    if can_edit_coll:
        perm_msg.append("Collaudo: MODIFICA")
    else:
        perm_msg.append("Collaudo: sola lettura")
    if can_edit_ing:
        perm_msg.append("Ingegneria: MODIFICA")
    else:
        perm_msg.append("Ingegneria: sola lettura")

    hint = tk.Label(
        footer,
        text=" | ".join(perm_msg),
        bg="#f0f0f0",
        fg="#444",
        anchor="w",
        font=("Segoe UI", 9)
    )
    hint.pack(side=tk.LEFT)
