import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from PIL import Image, ImageTk
import os

import dashboard
import db
import icon_helper  # Per l'icona PT2025.ico
import config_manager  # Per salvare percorso DB

# === DB ===
# Prova a caricare l'ultimo database usato
last_db = config_manager.get_last_db_path()
if last_db:
    db.set_db_path(last_db)
    db_path = last_db
else:
    # Altrimenti usa il default (NON crea il file se manca)
    db_path = db.ensure_default_db(create_if_missing=False)


def cambia_db():
    """
    Seleziona un nuovo file SQLite e lo usa sia per:
      - tabella Utenti
      - tabelle dei collaudi (acquisizioni, notes)
    La creazione/inizializzazione è delegata al modulo db
    (qui è esplicitamente consentita).
    """
    global db_path

    path = filedialog.askopenfilename(
        title="Seleziona il database SQLite",
        filetypes=[("SQLite DB", "*.db")]
    )
    if not path:
        return

    # Assicura che il DB scelto abbia lo schema completo.
    db.ensure_full_schema(path, create_if_missing=True)
    db_path = db.get_db_path()
    label_db.config(text=f"Database: {db_path}")
    
    # Salva il percorso nelle configurazioni
    config_manager.save_last_db_path(db_path)


def login():
    global db_path

    user = entry_username.get()
    pwd = entry_password.get()

    if user == "Nome utente" or pwd == "Password":
        messagebox.showwarning("Attenzione", "Inserisci le credenziali corrette!")
        return

    # Se il file DB NON esiste, blocco il login
    if not db.db_file_exists(db_path):
        messagebox.showerror(
            "Database mancante",
            f"Il database '{db_path}' non esiste.\n\n"
            "Per creare un nuovo database:\n"
            "1. Esegui 'create_fresh_db.py' dalla cartella del progetto\n"
            "2. Oppure usa 'Cambia DB' per selezionare un database esistente"
        )
        return

    # A questo punto il DB esiste e lo schema è garantito.
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM Utenti WHERE Username = ? AND Password = ?",
            (user, pwd)
        )
        row = cursor.fetchone()

    if row:
        username = row[1]
        ruolo = row[3]
        messagebox.showinfo("Login", f"Benvenuto {username} ({ruolo})!")
        
        # Nascondi la finestra di login
        root.withdraw()

        # Callback quando si chiude la dashboard
        def on_dashboard_close():
            # Mostra di nuovo il login
            root.deiconify()
            # Ripristina i placeholder iniziali nei campi login
            entry_username.delete(0, tk.END)
            entry_username.insert(0, "Nome utente")
            entry_password.delete(0, tk.END)
            entry_password.insert(0, "Password")
            entry_password.config(show="")

        folder_path = os.path.expanduser("~")
        # Passa root come parent e callback
        dashboard.launch_dashboard(folder_path, username, ruolo, 
                                               parent_root=root, 
                                               on_close_callback=on_dashboard_close)
    else:
        messagebox.showerror("Errore", "Credenziali errate!")


def chiedi_password_admin():
    win_pwd = crea_finestra_figlia("Verifica amministratore", 350, 220)

    tk.Label(
        win_pwd,
        text="Password amministratore",
        bg="#d91e18",
        fg="white",
        font=("Helvetica", 12, "bold")
    ).pack(pady=10)

    frame = tk.Frame(win_pwd, bg="#F2F2F2", padx=20, pady=20)
    frame.pack(pady=5)

    entry_pwd_admin = tk.Entry(frame, show="*")
    entry_pwd_admin.pack()

    def verifica_admin():
        pwd_admin = entry_pwd_admin.get()
        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM Utenti WHERE Ruolo = 'Admin' AND Password = ?",
                (pwd_admin,)
            )
            row = cursor.fetchone()

        if row:
            win_pwd.destroy()
            apri_finestra_crea_utente()
        else:
            messagebox.showerror("Errore", "Password amministratore errata!")

    tk.Button(
        frame,
        text="Verifica",
        command=verifica_admin,
        width=20,
        bg="#1a73e8",
        fg="white"
    ).pack(pady=10)


def chiedi_password_admin_elimina():
    win_pwd = crea_finestra_figlia("Verifica amministratore", 350, 220)

    tk.Label(
        win_pwd,
        text="Password amministratore",
        bg="#d91e18",
        fg="white",
        font=("Helvetica", 12, "bold")
    ).pack(pady=10)

    frame = tk.Frame(win_pwd, bg="#F2F2F2", padx=20, pady=20)
    frame.pack(pady=5)

    entry_pwd_admin = tk.Entry(frame, show="*")
    entry_pwd_admin.pack()

    def verifica_admin():
        pwd_admin = entry_pwd_admin.get()
        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM Utenti WHERE Ruolo = 'Admin' AND Password = ?",
                (pwd_admin,)
            )
            row = cursor.fetchone()

        if row:
            win_pwd.destroy()
            apri_finestra_elimina_utente()
        else:
            messagebox.showerror("Errore", "Password amministratore errata!")

    tk.Button(
        frame,
        text="Verifica",
        command=verifica_admin,
        width=20,
        bg="#1a73e8",
        fg="white"
    ).pack(pady=10)


def apri_finestra_crea_utente():
    win = crea_finestra_figlia("Crea nuovo utente", 350, 300)

    tk.Label(
        win,
        text="Crea nuovo utente",
        bg="#d91e18",
        fg="white",
        font=("Helvetica", 12, "bold")
    ).pack(pady=10)

    frame = tk.Frame(win, bg="#F2F2F2", padx=20, pady=20)
    frame.pack(pady=5)

    tk.Label(frame, text="Username", bg="#F2F2F2").pack(pady=2)
    entry_new_user = tk.Entry(frame)
    entry_new_user.pack()

    tk.Label(frame, text="Password", bg="#F2F2F2").pack(pady=2)
    entry_new_pwd = tk.Entry(frame, show="*")
    entry_new_pwd.pack()

    tk.Label(frame, text="Ruolo", bg="#F2F2F2").pack(pady=2)
    roles = ["Collaudatore", "Ingegneria", "Visualizzatore"]
    combo_role = ttk.Combobox(frame, values=roles, state="readonly")
    combo_role.pack()

    def crea_utente():
        new_user = entry_new_user.get()
        new_pwd = entry_new_pwd.get()
        new_role = combo_role.get()

        if not new_user or not new_pwd or not new_role:
            messagebox.showwarning("Attenzione", "Compila tutti i campi!")
            return

        try:
            with db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO Utenti (Username, Password, Ruolo) VALUES (?, ?, ?)",
                    (new_user, new_pwd, new_role)
                )
                conn.commit()
            messagebox.showinfo("Successo", f"Utente '{new_user}' creato!")
            win.destroy()
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile creare l'utente:\n{e}")

    tk.Button(
        frame,
        text="Crea",
        command=crea_utente,
        width=20,
        bg="#1a73e8",
        fg="white"
    ).pack(pady=10)


def apri_finestra_elimina_utente():
    win = crea_finestra_figlia("Elimina utente", 350, 250)

    tk.Label(
        win,
        text="Elimina utente",
        bg="#d91e18",
        fg="white",
        font=("Helvetica", 12, "bold")
    ).pack(pady=10)

    frame = tk.Frame(win, bg="#F2F2F2", padx=20, pady=20)
    frame.pack(pady=5)

    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Username FROM Utenti WHERE Ruolo != 'Admin'")
        utenti = [row[0] for row in cursor.fetchall()]

    if not utenti:
        tk.Label(frame, text="Nessun utente eliminabile.", bg="white", fg="red").pack(pady=10)
        return

    combo_utenti = ttk.Combobox(frame, values=utenti, state="readonly")
    combo_utenti.pack(pady=5)

    def elimina_utente():
        user_to_delete = combo_utenti.get()
        if not user_to_delete:
            messagebox.showwarning("Attenzione", "Seleziona un utente.")
            return

        confirm = messagebox.askyesno(
            "Conferma",
            f"Sei sicuro di voler eliminare l'utente '{user_to_delete}'?"
        )
        if not confirm:
            return

        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Utenti WHERE Username = ?", (user_to_delete,))
            conn.commit()

        messagebox.showinfo("Successo", f"Utente '{user_to_delete}' eliminato.")
        win.destroy()

    tk.Button(
        frame,
        text="Elimina",
        command=elimina_utente,
        width=20,
        bg="red",
        fg="white"
    ).pack(pady=10)


def password_dimenticata():
    win_reset = crea_finestra_figlia("Recupero password", 400, 360)

    tk.Label(
        win_reset,
        text="Recupero password",
        bg="#d91e18",
        fg="white",
        font=("Helvetica", 12, "bold")
    ).pack(pady=10)

    frame = tk.Frame(win_reset, bg="#F2F2F2", padx=20, pady=20)
    frame.pack(pady=5)

    tk.Label(frame, text="Inserisci il tuo username", bg="#F2F2F2").pack(pady=5)
    entry_user_reset = tk.Entry(frame)
    entry_user_reset.pack()

    label_password_attuale = tk.Label(frame, text="", fg="green", bg="#F2F2F2")
    label_password_attuale.pack(pady=5)

    label_new_pwd = tk.Label(frame, text="Nuova password", bg="#F2F2F2")
    entry_new_pwd = tk.Entry(frame, show="*")
    btn_conferma = tk.Button(
        frame,
        text="Conferma",
        width=20,
        bg="#1a73e8",
        fg="white"
    )

    def mostra_password():
        username = entry_user_reset.get()
        if not username:
            messagebox.showwarning("Attenzione", "Inserisci il nome utente.")
            return

        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT Password, Ruolo FROM Utenti WHERE Username = ?",
                (username,)
            )
            row = cursor.fetchone()

        if row:
            pwd_attuale, ruolo = row
            if ruolo == "Admin":
                messagebox.showerror(
                    "Errore",
                    "Il recupero della password non è consentito per l'amministratore."
                )
                return

            label_password_attuale.config(text=f"Password attuale: {pwd_attuale}")

            label_new_pwd.pack(pady=5)
            entry_new_pwd.pack()
            btn_conferma.pack(pady=10)
        else:
            messagebox.showerror("Errore", "Utente non trovato.")

    def aggiorna_password():
        nuova_pwd = entry_new_pwd.get()
        if not nuova_pwd:
            messagebox.showwarning("Attenzione", "Inserisci la nuova password.")
            return

        username = entry_user_reset.get()
        with db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Utenti SET Password = ? WHERE Username = ?",
                (nuova_pwd, username)
            )
            conn.commit()

        messagebox.showinfo("Successo", "Password aggiornata con successo!")
        win_reset.destroy()

    btn_conferma.config(command=aggiorna_password)

    tk.Button(
        frame,
        text="Recupera password",
        command=mostra_password,
        width=20,
        bg="#1a73e8",
        fg="#F2F2F2"
    ).pack(pady=10)


def crea_finestra_figlia(titolo, larghezza, altezza):
    win = tk.Toplevel(root)
    win.title(titolo)
    win.geometry(f"{larghezza}x{altezza}")
    win.configure(bg="#d91e18")
    
    # Imposta l'icona sulla finestra figlia
    icon_helper.set_window_icon(win)
    
    centra_finestra(win)
    win.transient(root)
    win.grab_set()
    win.focus_force()
    win.resizable(False, False)
    return win


def centra_finestra(win):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()

    main_x = root.winfo_rootx()
    main_y = root.winfo_rooty()
    main_w = root.winfo_width()
    main_h = root.winfo_height()

    x = main_x + (main_w // 2) - (w // 2)
    y = main_y + (main_h // 2) - (h // 2)

    win.geometry(f"+{x}+{y}")


# === Interfaccia principale ===
root = tk.Tk()
root.title("Login Flowserve PT2025")
root.geometry("400x600")
root.configure(bg="#d91e18")
root.resizable(False, False)

# Imposta l'icona della finestra
icon_helper.set_window_icon(root)

# Carica il logo (funziona sia in sviluppo che nell'eseguibile)
logo_path = icon_helper.get_resource_path("logo.png")
if logo_path:
    logo_img = Image.open(logo_path)
    logo_img.thumbnail((250, 250))
    logo_photo = ImageTk.PhotoImage(logo_img)
    
    label_logo = tk.Label(root, image=logo_photo, bg="#d91e18")
    label_logo.pack(pady=10)
else:
    # Fallback se logo non trovato
    label_logo = tk.Label(root, text="PT2025", font=("Calibri", 32, "bold"), 
                         bg="#d91e18", fg="white")
    label_logo.pack(pady=10)

label_logo.pack(pady=10)

label_benvenuto = tk.Label(
    root,
    text="Benvenuto in PT2025",
    font=("Calibri", 20, "bold"),
    bg="#d91e18",
    fg="white"
)
label_benvenuto.pack(pady=10)

frame_login = tk.Frame(root, bg="#F2F2F2", padx=20, pady=20)
frame_login.pack(pady=10)

entry_username = tk.Entry(frame_login, width=25, font=("Helvetica", 12))
entry_username.insert(0, "Nome utente")
entry_username.pack(pady=5)

entry_password = tk.Entry(frame_login, width=25, font=("Helvetica", 12))
entry_password.insert(0, "Password")
entry_password.pack(pady=5)


def on_entry_click_username(event):
    if entry_username.get() == "Nome utente":
        entry_username.delete(0, tk.END)


def on_focusout_username(event):
    if entry_username.get() == "":
        entry_username.insert(0, "Nome utente")


def on_entry_click_password(event):
    if entry_password.get() == "Password":
        entry_password.delete(0, tk.END)
        entry_password.config(show="*")


def on_focusout_password(event):
    if entry_password.get() == "":
        entry_password.insert(0, "Password")
        entry_password.config(show="")


entry_username.bind("<FocusIn>", on_entry_click_username)
entry_username.bind("<FocusOut>", on_focusout_username)

entry_password.bind("<FocusIn>", on_entry_click_password)
entry_password.bind("<FocusOut>", on_focusout_password)
entry_password.bind("<Return>", lambda e: login())  # Enter per login

btn_login = tk.Button(
    frame_login,
    text="Accedi",
    command=login,
    bg="#1a73e8",
    fg="white",
    width=20,
    font=("Helvetica", 12, "bold")
)
btn_login.pack(pady=10)

# Anche username può inviare con Enter
entry_username.bind("<Return>", lambda e: login())

link_pwd = tk.Label(
    frame_login,
    text="Password dimenticata?",
    fg="#1a73e8",
    bg="#F2F2F2",
    cursor="hand2",
    font=("Helvetica", 10, "underline")
)
link_pwd.pack()
link_pwd.bind("<Button-1>", lambda e: password_dimenticata())

label_db = tk.Label(
    root,
    text=f"Database: {db_path}",
    height=2,
    bg="#d91e18",
    fg="white",
    wraplength=350
)
label_db.pack(pady=10)

btn_db = tk.Button(
    root,
    text="Cambia DB",
    command=cambia_db,
    width=20,
    font=("Helvetica", 10, "bold")
)
btn_db.pack(pady=5)

def crea_database_nuovo():
    """Crea un database nuovo con lo schema completo (richiede password admin)."""
    global db_path
    
    # PRIMA verifica password admin (stesso layout di "Crea Nuovo Utente")
    pwd_win = crea_finestra_figlia("Verifica amministratore", 350, 220)
    pwd_win.lift()  # Porta in primo piano
    
    tk.Label(
        pwd_win,
        text="Password amministratore",
        bg="#d91e18",
        fg="white",
        font=("Helvetica", 12, "bold")
    ).pack(pady=10)
    
    frame = tk.Frame(pwd_win, bg="#F2F2F2", padx=20, pady=20)
    frame.pack(pady=5)
    
    entry_pwd = tk.Entry(frame, show="*")
    entry_pwd.pack()
    entry_pwd.focus()
    
    def verifica_e_procedi():
        pwd_admin = entry_pwd.get()
        with db.connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT * FROM Utenti WHERE Ruolo = 'Admin' AND Password = ?",
                    (pwd_admin,)
                )
                row = cursor.fetchone()
            except Exception:
                row = None
        
        if not row:
            messagebox.showerror("Errore", "Password amministratore errata!")
            return
        
        # Password corretta, chiudi finestra password e procedi
        pwd_win.destroy()
        
        # Ora chiedi dove salvare il nuovo DB
        path = filedialog.asksaveasfilename(
            title="Crea nuovo database",
            defaultextension=".db",
            initialfile="collaudi.db",
            filetypes=[("SQLite DB", "*.db")]
        )
        if not path:
            return
        
        # Conferma se il file esiste già
        if os.path.exists(path):
            conferma = messagebox.askyesno(
                "File esistente",
                f"Il file '{os.path.basename(path)}' esiste già.\n\n"
                "Sovrascriverlo con un database vuoto?\n"
                "⚠️ ATTENZIONE: Tutti i dati esistenti verranno persi!"
            )
            if not conferma:
                return
        
        # Crea il database usando lo script create_fresh_db
        try:
            from create_fresh_db import create_database
            success = create_database(path, make_backup=True)
            
            if success:
                messagebox.showinfo(
                    "Database creato",
                    f"Database creato con successo:\n{path}\n\n"
                    "📊 Tabelle: Utenti, acquisizioni, notes, curve_settings\n"
                    "🔐 Utente iniziale: admin / admin\n\n"
                    "⚠️ Cambia la password admin al primo accesso!"
                )
                
                # Imposta il nuovo DB come corrente
                db.set_db_path(path)
                db_path = path
                label_db.config(text=f"Database: {db_path}")
                
                # Salva il percorso nelle configurazioni
                config_manager.save_last_db_path(db_path)
            else:
                messagebox.showerror("Errore", "Creazione database fallita")
                
        except Exception as e:
            messagebox.showerror("Errore creazione", f"Impossibile creare il database:\n{e}")
    
    tk.Button(
        frame,
        text="Verifica",
        command=verifica_e_procedi,
        width=20,
        bg="#1a73e8",
        fg="white"
    ).pack(pady=10)
    
    entry_pwd.bind("<Return>", lambda e: verifica_e_procedi())

btn_crea_db = tk.Button(
    root,
    text="Crea Nuovo Database",
    command=crea_database_nuovo,
    width=20,
    font=("Helvetica", 10, "bold")
)
btn_crea_db.pack(pady=5)

btn_crea_utente = tk.Button(
    root,
    text="Crea nuovo utente",
    command=chiedi_password_admin,
    width=20,
    font=("Helvetica", 10, "bold")
)
btn_crea_utente.pack(pady=5)

btn_elimina_utente = tk.Button(
    root,
    text="Elimina utente",
    command=chiedi_password_admin_elimina,
    width=20,
    font=("Helvetica", 10, "bold")
)
btn_elimina_utente.pack(pady=5)

# ---- Controllo DB appena parte il login ----
if not db.db_file_exists(db_path):
    crea_subito = messagebox.askyesno(
        "Database mancante",
        f"Il database '{db_path}' non esiste.\n\n"
        "Vuoi crearne uno nuovo con le tabelle necessarie\n"
        "e l'utente Admin (admin / adminpass)?"
    )
    if crea_subito:
        db.ensure_full_schema(db_path, create_if_missing=True)
        db_path = db.get_db_path()
        label_db.config(text=f"Database: {db_path}")
    else:
        label_db.config(text=f"Database mancante: {db_path}")

root.mainloop()
