"""
Gestione configurazione dell'applicazione (file config.ini).
Salva impostazioni come il percorso del database.
"""
import os
import configparser

CONFIG_FILE = "config.ini"

def get_config_path():
    """Restituisce il percorso del file config.ini nella cartella dell'eseguibile."""
    if hasattr(os.sys, 'frozen'):
        # Eseguibile - usa la cartella dell'exe
        base_path = os.path.dirname(os.sys.executable)
    else:
        # Sviluppo - usa la cartella dello script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, CONFIG_FILE)

def load_config():
    """Carica la configurazione dal file config.ini."""
    config = configparser.ConfigParser()
    config_path = get_config_path()
    
    if os.path.exists(config_path):
        try:
            config.read(config_path)
        except:
            pass
    
    return config

def save_config(config):
    """Salva la configurazione nel file config.ini."""
    config_path = get_config_path()
    
    try:
        with open(config_path, 'w') as f:
            config.write(f)
        return True
    except Exception as e:
        print(f"Errore salvataggio config: {e}")
        return False

def get_last_db_path():
    """Restituisce l'ultimo percorso database usato, o None."""
    config = load_config()
    
    if 'Database' in config and 'last_path' in config['Database']:
        path = config['Database']['last_path']
        # Verifica che il file esista ancora
        if os.path.exists(path):
            return path
    
    return None

def save_last_db_path(db_path):
    """Salva il percorso del database nelle configurazioni."""
    config = load_config()
    
    if 'Database' not in config:
        config['Database'] = {}
    
    config['Database']['last_path'] = db_path
    
    return save_config(config)