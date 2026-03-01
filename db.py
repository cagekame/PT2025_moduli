import os
import sqlite3
from typing import Iterable, Optional
from datetime import datetime

# ================== GESTIONE PERCORSO DB ==================

# Percorso di default: file "collaudi.db" nella stessa cartella del modulo
_DB_PATH = os.path.join(os.path.dirname(__file__), "collaudi.db")


def set_db_path(path: str) -> None:
    """
    Imposta il percorso del database da usare in tutto il modulo.
    Esempio: set_db_path("D:/dati/collaudi_produzione.db")
    """
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> str:
    """Ritorna il percorso attualmente in uso per il database."""
    return _DB_PATH


def db_file_exists(path: Optional[str] = None) -> bool:
    """
    Ritorna True se il file fisico esiste.
    NON apre connessioni, NON crea il file.
    """
    p = path or _DB_PATH
    return os.path.exists(p)


def connect() -> sqlite3.Connection:
    """
    Apre una connessione al DB corrente (_DB_PATH), con le PRAGMA già impostate.
    ATTENZIONE: se il file non esiste, QUI viene creato.
    Per questo motivo NON deve essere chiamata nelle funzioni
    che fanno solo "controllo esistenza".
    """
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ================== INIZIALIZZAZIONE TABELLE ==================

def _ensure_tabelle_collaudi(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Tabella principale collaudi / acquisizioni
    cur.execute("""
        CREATE TABLE IF NOT EXISTS acquisizioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job TEXT,
            n_collaudo TEXT,
            matricola TEXT,
            tipo_pompa TEXT,
            data TEXT,
            stato TEXT,
            data_approvazione TEXT,
            nome_approvatore TEXT,
            tipo_test TEXT,
            taglio_girante TEXT,
            filepath TEXT,
            filename TEXT,
            data_file TEXT,
            ora_file TEXT,
            progressivo INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            created_by TEXT,
            checked_by TEXT,
            checked_at TEXT,
            engineering_user TEXT,
            engineering_at TEXT,
            UNIQUE(filepath, tipo_test)
        )
    """)

    # Tabella note: note separate per collaudatore / ingegneria
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            filepath TEXT PRIMARY KEY,
            note_collaudatore TEXT DEFAULT '',
            note_ingegneria   TEXT DEFAULT ''
        )
    """)

    # Indici principali
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_acq_sort "
        "ON acquisizioni(data_file, ora_file, progressivo)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_acq_job ON acquisizioni(job)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_acq_matricola ON acquisizioni(matricola)")


def _ensure_curve_settings_table(conn: sqlite3.Connection) -> None:
    """Garantisce l'esistenza della tabella impostazioni curva."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS curve_settings (
            acquisizione_id INTEGER PRIMARY KEY,
            show_points INTEGER DEFAULT 1,
            eff_min REAL DEFAULT 0.0,
            eff_max REAL DEFAULT 100.0,
            FOREIGN KEY(acquisizione_id) REFERENCES acquisizioni(id) ON DELETE CASCADE
        )
    """)


def _ensure_tabella_utenti(
    conn: sqlite3.Connection,
    create_admin_if_missing: bool = True
) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Utenti (
            ID_Utente INTEGER PRIMARY KEY AUTOINCREMENT,
            Username TEXT UNIQUE,
            Password TEXT,
            Ruolo TEXT
        )
    """)
    if create_admin_if_missing:
        cur.execute("SELECT 1 FROM Utenti WHERE Ruolo = 'Admin' LIMIT 1")
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO Utenti (Username, Password, Ruolo) VALUES (?, ?, ?)",
                ("admin", "adminpass", "Admin")
            )


def _column_exists(table: str, column: str) -> bool:
    """Verifica se una colonna esiste in una tabella."""
    try:
        with connect() as conn:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            return column in columns
    except Exception:
        return False


def init() -> None:
    """
    Inizializza SOLO le tabelle dei collaudi (acquisizioni, notes)
    nel DB corrente (_DB_PATH). Usata dalla dashboard.
    Se il file DB non esiste, QUI viene creato.
    """
    with connect() as conn:
        _ensure_tabelle_collaudi(conn)
        _ensure_curve_settings_table(conn)
        conn.commit()
    
    # Migrazioni schema
    _ensure_taglio_girante_column()
    _ensure_unit_system_column()


def ensure_full_schema(
    path: Optional[str] = None,
    create_if_missing: bool = True,
    create_admin_if_missing: bool = True,
) -> str:
    """
    Garantisce che il file DB 'path' (o il default) contenga:
      - tabella Utenti (con almeno un Admin, se richiesto)
      - tabelle collaudi (acquisizioni, notes)

    Se il file non esiste e create_if_missing=False:
        NON viene creato nulla, non viene aperta alcuna connessione.
        Si limita a impostare il percorso e ritorna il path.

    Se il file non esiste e create_if_missing=True:
        viene creato, viene applicato lo schema completo e creato l'Admin.

    Ritorna SEMPRE il percorso attualmente impostato come DB corrente.
    """
    global _DB_PATH

    if path is not None:
        _DB_PATH = path

    db_path = _DB_PATH
    file_exists = os.path.exists(db_path)

    # Se il file NON esiste e non devo crearlo, NON chiamare connect()
    if not file_exists and not create_if_missing:
        return db_path

    # Da qui in avanti: o il file esiste, oppure voglio crearlo
    with connect() as conn:
        _ensure_tabelle_collaudi(conn)
        _ensure_curve_settings_table(conn)
        _ensure_tabella_utenti(conn, create_admin_if_missing=create_admin_if_missing)
        conn.commit()

    # Migrazioni schema su DB esistenti
    _ensure_taglio_girante_column()
    _ensure_unit_system_column()

    return db_path


def ensure_default_db(create_if_missing: bool = False) -> str:
    """
    Usa il DB di default (collaudi.db accanto al modulo).

    - Se il file NON esiste:
        - create_if_missing=False -> NON crea nulla, NON apre connessioni.
                                     Ritorna solo il path.
        - create_if_missing=True  -> crea file + schema completo (Utenti + collaudi).

    - Se il file ESISTE:
        viene solo verificato/aggiornato lo schema (senza problemi).

    Ritorna il percorso del DB di default.
    """
    default_path = _DB_PATH  # è già impostato alla partenza

    if not os.path.exists(default_path):
        if not create_if_missing:
            # NON creare, NON aprire connessione
            return default_path
        # voglio crearlo ora con schema completo
        return ensure_full_schema(default_path, create_if_missing=True)

    # il file esiste: posso assicurare lo schema senza creare nulla
    return ensure_full_schema(default_path, create_if_missing=False)


# ================== CRUD ACQUISIZIONI ==================

def insert_acquisizione(rec: dict) -> None:
    """
    Inserisce un record nella tabella acquisizioni del DB corrente.
    rec atteso: chiavi job, n_collaudo, matricola, tipo_pompa, data_iso, stato,
                filepath, filename, data_file, ora_file, progressivo, tipo_test

    created_by / checked_* / engineering_* rimangono NULL in inserimento
    e verranno compilati dalle logiche di cambio stato.
    """
    sql = """
        INSERT INTO acquisizioni
        (job, n_collaudo, matricola, tipo_pompa, data, stato,
         data_approvazione, nome_approvatore, tipo_test, taglio_girante,
         filepath, filename, data_file, ora_file, progressivo,
         created_by, checked_by, checked_at, engineering_user, engineering_at)
        VALUES
        (?,   ?,          ?,         ?,          ?,    ?,
         NULL,              '',               ?,         '',
         ?,        ?,        ?,        ?,       ?,
         ?,         NULL,      NULL,      NULL,           NULL)
    """
    vals = (
        rec["job"],
        rec.get("n_collaudo", ""),
        rec["matricola"],
        rec.get("tipo_pompa", ""),
        rec["data_iso"],
        rec.get("stato", "Unchecked"),
        rec.get("tipo_test", ""),
        rec["filepath"],
        rec["filename"],
        rec["data_file"],
        rec["ora_file"],
        rec["progressivo"],
        rec.get("created_by", None),
    )
    with connect() as conn:
        conn.execute(sql, vals)
        conn.commit()


def _ensure_taglio_girante_column():
    """Aggiunge la colonna taglio_girante se non esiste."""
    if not _column_exists("acquisizioni", "taglio_girante"):
        with connect() as conn:
            conn.execute("ALTER TABLE acquisizioni ADD COLUMN taglio_girante TEXT DEFAULT ''")
            conn.commit()


def _ensure_unit_system_column():
    """Aggiunge la colonna unit_system se non esiste."""
    if not _column_exists("acquisizioni", "unit_system"):
        with connect() as conn:
            conn.execute("ALTER TABLE acquisizioni ADD COLUMN unit_system TEXT DEFAULT 'Metric'")
            conn.commit()


def select_all_acquisizioni() -> Iterable[tuple]:
    """
    Ritorna tutte le acquisizioni ordinate per data_file, ora_file, progressivo.
    (Usata dalla dashboard: ritorna solo le colonne necessarie per la lista.)
    """
    sql = """
        SELECT id, job, n_collaudo, matricola, tipo_pompa, data, stato, 
               data_approvazione, nome_approvatore, tipo_test, taglio_girante,
               filepath, filename
        FROM acquisizioni
        ORDER BY data_file ASC, ora_file ASC, progressivo ASC
    """
    with connect() as conn:
        return list(conn.execute(sql).fetchall())


def get_unit_system(acq_id: Optional[int]) -> str:
    """Ritorna il sistema unità per una acquisizione ('Metric' default)."""
    if acq_id is None:
        return "Metric"
    # Sicurezza per DB legacy.
    _ensure_unit_system_column()
    with connect() as conn:
        row = conn.execute(
            "SELECT unit_system FROM acquisizioni WHERE id = ?",
            (acq_id,)
        ).fetchone()
    val = (row[0] if row else None) or "Metric"
    return val if val in ("Metric", "US") else "Metric"


def set_unit_system(acq_id: Optional[int], unit_system: str) -> None:
    """Imposta il sistema unità per una acquisizione."""
    if acq_id is None:
        return
    unit = unit_system if unit_system in ("Metric", "US") else "Metric"
    _ensure_unit_system_column()
    with connect() as conn:
        conn.execute(
            "UPDATE acquisizioni SET unit_system = ? WHERE id = ?",
            (unit, acq_id)
        )
        conn.commit()


def curve_settings_get(acq_id: Optional[int]) -> Optional[dict]:
    """
    Legge impostazioni curva per acquisizione.
    Ritorna None se non presenti.
    """
    if acq_id is None:
        return None
    with connect() as conn:
        _ensure_curve_settings_table(conn)
        row = conn.execute(
            "SELECT show_points, eff_min, eff_max FROM curve_settings WHERE acquisizione_id = ?",
            (acq_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "show_points": bool(row[0]),
        "eff_min": float(row[1]),
        "eff_max": float(row[2]),
    }


def curve_settings_set(
    acq_id: Optional[int],
    *,
    show_points: bool = True,
    eff_min: float = 0.0,
    eff_max: float = 100.0,
) -> None:
    """Crea/aggiorna impostazioni curva per acquisizione."""
    if acq_id is None:
        return
    show_points_i = 1 if bool(show_points) else 0
    with connect() as conn:
        _ensure_curve_settings_table(conn)
        conn.execute("""
            INSERT INTO curve_settings(acquisizione_id, show_points, eff_min, eff_max)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(acquisizione_id) DO UPDATE SET
                show_points = excluded.show_points,
                eff_min = excluded.eff_min,
                eff_max = excluded.eff_max
        """, (acq_id, show_points_i, float(eff_min), float(eff_max)))
        conn.commit()


def select_filepath_by_id(acq_id: int) -> Optional[str]:
    with connect() as conn:
        row = conn.execute("SELECT filepath FROM acquisizioni WHERE id=?", (acq_id,)).fetchone()
        return row[0] if row else None


def delete_acquisizione(acq_id: int) -> None:
    """
    Cancella il record dalla tabella acquisizioni e l'eventuale nota collegata.
    """
    path = select_filepath_by_id(acq_id)
    with connect() as conn:
        conn.execute("DELETE FROM acquisizioni WHERE id=?", (acq_id,))
        if path:
            conn.execute("DELETE FROM notes WHERE filepath=?", (path,))
        conn.commit()


def update_stato(
    acq_id: int,
    nuovo_stato: str,
    data_approvazione: Optional[str],
    username: Optional[str] = None,
    ruolo: Optional[str] = None,
) -> None:
    """
    Aggiorna lo stato di una acquisizione.

    - 'stato' viene sempre aggiornato.
    - 'data_approvazione' contiene la data dell'ULTIMO cambio di stato (Approved/Rejected/altro).
    - 'nome_approvatore' contiene l'utente che ha fatto l'ULTIMO cambio di stato.
    - Se il nuovo stato è "Checked" e il ruolo è "Collaudatore":
        -> aggiorna anche checked_by / checked_at.
    - Se il nuovo stato è "Approved" o "Rejected" e il ruolo è "Ingegneria" o "Admin":
        -> aggiorna anche engineering_user / engineering_at.
    """
    with connect() as conn:
        fields = ["stato = ?"]
        params = [nuovo_stato]

        # Data generica di ultimo cambio stato (per la colonna visibile in lista)
        if data_approvazione is not None:
            fields.append("data_approvazione = ?")
            params.append(data_approvazione)
        else:
            fields.append("data_approvazione = NULL")

        # Nome "approvatore" = chi ha fatto l'ultimo cambio di stato
        if username is not None:
            fields.append("nome_approvatore = ?")
            params.append(username)

        now_ts = datetime.now().isoformat(sep=" ", timespec="seconds")

        # Collaudatore che passa a CHECKED
        if ruolo == "Collaudatore" and nuovo_stato == "Checked" and username is not None:
            fields.append("checked_by = ?")
            fields.append("checked_at = ?")
            params.append(username)
            params.append(now_ts)

        # Ingegneria (o Admin) che approva o rifiuta
        if ruolo in ("Ingegneria", "Admin") and nuovo_stato in ("Approved", "Rejected") and username is not None:
            fields.append("engineering_user = ?")
            fields.append("engineering_at = ?")
            params.append(username)
            params.append(now_ts)

        sql = f"UPDATE acquisizioni SET {', '.join(fields)} WHERE id = ?"
        params.append(acq_id)

        conn.execute(sql, params)
        conn.commit()


# ================== NOTE ==================

def note_collaudatore_get(filepath: str) -> str:
    """
    Ritorna la nota del collaudatore per il file indicato.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT note_collaudatore FROM notes WHERE filepath = ?",
            (filepath,)
        ).fetchone()
        return row[0] if row and row[0] else ""


def note_collaudatore_set(filepath: str, note: str) -> None:
    """
    Imposta la nota del collaudatore (note_collaudatore).
    Se la riga non esiste, la crea.
    """
    with connect() as conn:
        conn.execute("""
            INSERT INTO notes(filepath, note_collaudatore)
            VALUES(?, ?)
            ON CONFLICT(filepath) DO UPDATE SET
                note_collaudatore = excluded.note_collaudatore
        """, (filepath, note))
        conn.commit()


def note_ingegneria_get(filepath: str) -> str:
    """
    Ritorna la nota di ingegneria per il file indicato.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT note_ingegneria FROM notes WHERE filepath = ?",
            (filepath,)
        ).fetchone()
        return row[0] if row and row[0] else ""


def note_ingegneria_set(filepath: str, note: str) -> None:
    """
    Imposta la nota di ingegneria (note_ingegneria).
    Se la riga non esiste, la crea.
    """
    with connect() as conn:
        conn.execute("""
            INSERT INTO notes(filepath, note_ingegneria)
            VALUES(?, ?)
            ON CONFLICT(filepath) DO UPDATE SET
                note_ingegneria = excluded.note_ingegneria
        """, (filepath, note))
        conn.commit()

