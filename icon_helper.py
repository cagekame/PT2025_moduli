"""
Helper per caricare l'icona PT2025.ico nelle finestre Tkinter.
Funziona sia in sviluppo che nell'eseguibile PyInstaller.
"""
import os
import sys

def get_resource_path(filename):
    """
    Restituisce il percorso di un file risorsa (icona, logo, ecc.).
    Funziona sia in sviluppo che nell'eseguibile PyInstaller.
    
    Args:
        filename: Nome del file (es. 'PT2025.ico', 'logo.png')
    
    Returns:
        str: Percorso completo del file, o None se non trovato
    """
    if getattr(sys, 'frozen', False):
        # Eseguibile PyInstaller - le risorse sono in _MEIPASS
        base_path = sys._MEIPASS
    else:
        # Sviluppo - cerca nella cartella dello script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    resource_path = os.path.join(base_path, filename)
    
    # Verifica che il file esista
    if os.path.exists(resource_path):
        return resource_path
    return None

def get_icon_path():
    """
    Restituisce il percorso dell'icona PT2025.ico.
    Funziona sia in sviluppo che nell'eseguibile PyInstaller.
    """
    return get_resource_path('PT2025.ico')

def set_window_icon(window):
    """
    Imposta l'icona PT2025.ico su una finestra Tkinter.
    
    Args:
        window: Una finestra tk.Tk() o tk.Toplevel()
    
    Returns:
        bool: True se l'icona è stata impostata, False altrimenti
    """
    icon_path = get_icon_path()
    
    if icon_path:
        try:
            window.iconbitmap(icon_path)
            return True
        except Exception:
            # Se fallisce (es. formato non supportato), ignora silenziosamente
            pass
    
    return False