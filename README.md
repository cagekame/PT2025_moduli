# Documentazione File App

Riferimento: file principali dell'applicazione avviata da `login.py`.


| File | A cosa serve | Ultima modifica |
|---|---|---|
| `login.py` | Finestra di login, selezione/creazione DB, apertura dashboard. | 27/02/2026 23:02:45 |
| `dashboard.py` | Dashboard principale collaudi: lista test, stato, note, apertura certificato/PDF. | 27/02/2026 18:02:23 |
| `db.py` | Accesso SQLite, schema, migrazioni e CRUD (acquisizioni, note, utenti, impostazioni curva/unità). | 27/02/2026 19:27:57 |
| `config_manager.py` | Lettura/scrittura `config.ini` (es. ultimo percorso DB usato). | 27/02/2026 18:02:23 |
| `icon_helper.py` | Caricamento risorse/icona (`PT2025.ico`) in sviluppo o build PyInstaller. | 27/02/2026 18:02:23 |
| `certificate_view.py` | Finestra certificato: dettagli TDMS, tabella dati e integrazione tab curva. | 01/03/2026 00:37:49 |
| `notes_window.py` | UI per note collaudatore/ingegneria con regole di edit per ruolo/stato. | 27/02/2026 19:03:23 |
| `tdms_reader.py` | Parsing file TDMS e estrazione campi/tabelle/performance. | 27/02/2026 18:29:31 |
| `pdf_report.py` | Generazione ed export PDF del certificato (layout/reportlab + dati TDMS/DB). | 27/02/2026 19:10:38 |
| `curve_view.py` | Rendering grafici curva in Tkinter (matplotlib), trendline e metriche. | 27/02/2026 18:02:23 |
| `ui_format.py` | Utility di formattazione valori/colonne per UI e report. | 27/02/2026 19:24:15 |
| `unit_converter.py` | Conversione unità Metric/US per visualizzazione e report. | 27/02/2026 20:17:57 |
| `PT2025.ico` | Icona dell'applicazione e delle finestre. | 27/02/2026 18:02:23 |
| `logo.png` | Logo mostrato nella schermata di login. | 27/02/2026 18:02:23 |
| `collaudi.db` | Database SQLite dati applicativi. | 01/03/2026 01:10:04 |
| `config.ini` | Configurazione locale (ultimo DB selezionato). | 27/02/2026 18:02:23 |

