# db.py
import sqlite3
from typing import Iterable, Optional

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init(db_path: str) -> None:
    with connect(db_path) as conn:
        cur = conn.cursor()
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
            filepath TEXT UNIQUE,
            filename TEXT,
            data_file TEXT,
            ora_file TEXT,
            progressivo INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            filepath TEXT PRIMARY KEY,
            note TEXT DEFAULT ''
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_acq_sort ON acquisizioni(data_file, ora_file, progressivo)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_acq_job ON acquisizioni(job)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_acq_matricola ON acquisizioni(matricola)")
        conn.commit()

# ---------- CRUD acquisizioni ----------
def insert_acquisizione(db_path: str, rec: dict) -> None:
    sql = """
        INSERT INTO acquisizioni
        (job, n_collaudo, matricola, tipo_pompa, data, stato, data_approvazione, nome_approvatore, tipo_test, taglio_girante,
         filepath, filename, data_file, ora_file, progressivo)
        VALUES
        (?,   ?,          ?,         ?,          ?,    ?,     NULL,              '',               '',         '',
         ?,        ?,        ?,        ?,       ?)
    """
    vals = (
        rec["job"], rec.get("n_collaudo",""), rec["matricola"], rec.get("tipo_pompa",""),
        rec["data_iso"], rec.get("stato","Unchecked"),
        rec["filepath"], rec["filename"], rec["data_file"], rec["ora_file"], rec["progressivo"]
    )
    with connect(db_path) as conn:
        conn.execute(sql, vals)
        conn.commit()

def select_all_acquisizioni(db_path: str) -> Iterable[tuple]:
    sql = """
        SELECT id, job, n_collaudo, matricola, tipo_pompa, data, stato, 
               data_approvazione, nome_approvatore, tipo_test, taglio_girante,
               filepath, filename
        FROM acquisizioni
        ORDER BY data_file ASC, ora_file ASC, progressivo ASC
    """
    with connect(db_path) as conn:
        return list(conn.execute(sql).fetchall())

def select_filepath_by_id(db_path: str, acq_id: int) -> Optional[str]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT filepath FROM acquisizioni WHERE id=?", (acq_id,)).fetchone()
        return row[0] if row else None

def delete_acquisizione(db_path: str, acq_id: int) -> None:
    path = select_filepath_by_id(db_path, acq_id)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM acquisizioni WHERE id=?", (acq_id,))
        if path:
            conn.execute("DELETE FROM notes WHERE filepath=?", (path,))
        conn.commit()

def update_stato(db_path: str, acq_id: int, nuovo_stato: str, data_approvazione: Optional[str]) -> None:
    with connect(db_path) as conn:
        if data_approvazione:
            conn.execute(
                "UPDATE acquisizioni SET stato=?, data_approvazione=? WHERE id=?",
                (nuovo_stato, data_approvazione, acq_id)
            )
        else:
            conn.execute(
                "UPDATE acquisizioni SET stato=?, data_approvazione=NULL WHERE id=?",
                (nuovo_stato, acq_id)
            )
        conn.commit()

# ---------- Note ----------
def note_get(db_path: str, filepath: str) -> str:
    with connect(db_path) as conn:
        row = conn.execute("SELECT note FROM notes WHERE filepath = ?", (filepath,)).fetchone()
        return row[0] if row and row[0] else ""

def note_set(db_path: str, filepath: str, note: str) -> None:
    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO notes(filepath, note) VALUES(?, ?)
            ON CONFLICT(filepath) DO UPDATE SET note=excluded.note
        """, (filepath, note))
        conn.commit()
