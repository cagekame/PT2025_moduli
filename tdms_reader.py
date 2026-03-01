# tdms_reader.py
"""
Lettura TDMS riutilizzabile.
- Mantiene le unità di misura nel NOME canale (es. "Capacity [m3/h]") senza rimuoverle.
- Nessun array 'units' nelle tabelle: solo 'columns' e 'rows'.

Espone:
- NPTDMS_OK : bool
- read_tdms_fields(tdms_path) -> {"n_collaudo": str, "tipo_pompa": str}
- read_scalar_string(tdms_path, group, channel) -> str
- read_contract_and_loop_data(tdms_path) -> dict[str,str]  # include "FSG ORDER"
- read_performance_tables_dynamic(tdms_path, test_index=0) -> dict
    # NOTA: da questa versione, le "rows" contengono valori **RAW** (float o "")
- read_curve_data(tdms_path, test_index=0) -> (meta: dict, points: list)  # meta-only (points=[])
"""

import os
import re
import math
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# nptdms
try:
    from nptdms import TdmsFile
    NPTDMS_OK = True
except Exception:
    TdmsFile = None
    NPTDMS_OK = False

# numpy (opzionale)
try:
    import numpy as np
    NUMPY_OK = True
except Exception:
    NUMPY_OK = False


# -------------------- Util di base TDMS --------------------
def _first_nonempty(seq):
    if not (hasattr(seq, "__iter__") and not isinstance(seq, (str, bytes, bytearray))):
        seq = [seq]
    for x in seq:
        if x is None:
            continue
        if isinstance(x, (bytes, bytearray)):
            try:
                x = x.decode("utf-8", errors="ignore")
            except Exception:
                x = str(x)
        s = str(x).strip()
        if s:
            return s
    return ""

def _to_float_safe(v):
    """Converte in float in modo robusto (virgole, testo misto, unità)."""
    try:
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            s = s.replace("\u00a0", " ")
            # Estrai il primo token numerico, utile per stringhe tipo "12,34 bar"
            m = re.search(r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", s)
            if not m:
                return None
            token = m.group(0).replace(",", ".")
            f = float(token)
        else:
            f = float(v)
        if math.isfinite(f):
            return f
    except Exception:
        return None
    return None

def _get_group_ci(tdms, group_name: str):
    tgt = (group_name or "").lower()
    for g in tdms.groups():
        if (g.name or "").lower() == tgt:
            return g
    return None

def _get_channel_ci(group, channel_name: str):
    tgt = (channel_name or "").lower()
    for ch in group.channels():
        if (ch.name or "").lower() == tgt:
            return ch
    return None

def _read_prop_or_channel(tdms, group_name: str, prop_key: str, channel_name: str) -> str:
    """Legge prima la property del gruppo, poi (se vuota) il canale."""
    try:
        grp = _get_group_ci(tdms, group_name)
        if not grp:
            return ""
        # property (se presente)
        try:
            if prop_key in getattr(grp, "properties", {}):
                val = grp.properties.get(prop_key)
                val = _first_nonempty([val])
                if val:
                    return val
        except Exception:
            pass
        # canale
        ch = _get_channel_ci(grp, channel_name)
        if not ch:
            return ""
        try:
            data = ch[:]
        except Exception:
            data = getattr(ch, "data", [])
        return _first_nonempty(data) or ""
    except Exception:
        return ""


# -------------------- API usate dalla dashboard --------------------
def read_tdms_fields(tdms_path: str) -> dict:
    """
    Estrae:
      - n_collaudo: gruppo 'N_Certif', property/canale 'N_Certif'
      - tipo_pompa: gruppo 'Ref. Pump Type', property/canale 'Pump'
    """
    out = {"n_collaudo": "", "tipo_pompa": ""}
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return out
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return out
    try:
        out["n_collaudo"] = _read_prop_or_channel(tdms, "N_Certif", "N_Certif", "N_Certif") or ""
        out["tipo_pompa"] = _read_prop_or_channel(tdms, "Ref. Pump Type", "Pump", "Pump") or ""
        return out
    finally:
        try:
            tdms.close()
        except Exception:
            pass


def read_scalar_string(tdms_path: str, group_name: str, channel_name: str) -> str:
    """Legge un valore stringa dal canale (prima occorrenza non vuota)."""
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return ""
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return ""
    try:
        grp = _get_group_ci(tdms, group_name)
        if not grp:
            return ""
        ch = _get_channel_ci(grp, channel_name)
        if not ch:
            return ""
        try:
            data = ch[:]
        except Exception:
            data = getattr(ch, "data", [])
        return _first_nonempty(data) or ""
    except Exception:
        return ""
    finally:
        try:
            tdms.close()
        except Exception:
            pass


# -------------------- Contract/Loop aggregati --------------------
def _read_scalar_from_tdms(tdms, group_name: str, channel_name: str) -> str:
    try:
        grp = _get_group_ci(tdms, group_name)
        if not grp:
            return ""
        ch = _get_channel_ci(grp, channel_name)
        if not ch:
            return ""
        try:
            data = ch[:]
        except Exception:
            data = getattr(ch, "data", [])
        return _first_nonempty(data) or ""
    except Exception:
        return ""

def _read_fsg_order(tdms) -> str:
    """
    Legge FSG ORDER da:
      - gruppo:  'Ref. Test Param.'
      - canali:  'FSG Order_Value' (indice) e 'FSG Order_Elenco' (lista)
    Usa il campione in posizione indicata da FSG Order_Value.
    Gestisce indici 1-based e 0-based in modo robusto.
    """
    try:
        grp = _get_group_ci(tdms, "Ref. Test Param.")
        if not grp:
            return ""
        ch_val = _get_channel_ci(grp, "FSG Order_Value")
        ch_list = _get_channel_ci(grp, "FSG Order_Elenco")
        if not ch_val or not ch_list:
            return ""

        try:
            vals = ch_val[:]
        except Exception:
            vals = getattr(ch_val, "data", [])
        try:
            elenco = ch_list[:]
        except Exception:
            elenco = getattr(ch_list, "data", [])

        idx_raw = _first_nonempty(vals)
        if not idx_raw:
            return ""
        try:
            idx_num = int(str(idx_raw).strip())
        except Exception:
            try:
                idx_num = int(float(str(idx_raw).replace(",", ".").strip()))
            except Exception:
                return ""

        elenco_str = []
        for x in elenco:
            s = _first_nonempty([x])
            if s is None:
                s = ""
            elenco_str.append(str(s).strip())

        n = len(elenco_str)
        if n == 0:
            return ""
        if 1 <= idx_num <= n:
            return elenco_str[idx_num - 1] or ""
        if 0 <= idx_num < n:
            return elenco_str[idx_num] or ""
        return ""
    except Exception:
        return ""

def read_contract_and_loop_data(tdms_path: str) -> dict:
    """
    Ritorna un dict con i principali campi per Contractual / Test Param / Pump Type / Test Detail.
    Le unità sono parte del nome canale, non vengono rimosse.
    Include anche "FSG ORDER" derivato da FSG Order_Value/Elenco.
    """
    out = {
        # Contract data
        "Capacity [m3/h]": "", "TDH [m]": "", "Efficiency [%]": "", "ABS_Power [kW]": "",
        "Speed [rpm]": "", "SG Contract": "", "Temperature [°C]": "", "Viscosity [cP]": "",
        "NPSH [m]": "", "Liquid": "",
        # Test param
        "FSG ORDER": "", "Customer": "", "Purchaser Order": "", "End User": "", "Applic. Specs.": "",
        # Pump type
        "Item": "", "Pump": "", "Serial Number_Elenco": "", "Impeller Drawing": "",
        "Impeller Material": "", "Diam Nominal": "",
        # Test detail
        "Suction [Inch]": "", "Discharge [Inch]": "", "Wattmeter Const.": "",
        "AtmPress [m]": "", "KNPSH [m]": "", "WaterTemp [°C]": "", "KVenturi": "",
    }
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return out
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return out
    try:
        # Contract
        out["Capacity [m3/h]"] = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "Capacity [m3/h]")
        out["TDH [m]"]         = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "TDH [m]")
        out["Efficiency [%]"]  = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "Efficiency [%]")
        out["ABS_Power [kW]"]  = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "ABS_Power [kW]")
        out["Speed [rpm]"]     = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "Speed [rpm]")
        out["SG Contract"]     = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "SG Contract")
        out["Temperature [°C]"]= (_read_scalar_from_tdms(tdms, "Ref. Contract Data", "Temperature [°C]") or
                                   _read_scalar_from_tdms(tdms, "Ref. Contract Data", "Temperature [C]"))
        out["Viscosity [cP]"]  = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "Viscosity [cP]")
        out["NPSH [m]"]        = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "NPSH [m]")
        out["Liquid"]          = _read_scalar_from_tdms(tdms, "Ref. Contract Data", "Liquid")

        # Test Param
        out["Customer"]        = _read_scalar_from_tdms(tdms, "Ref. Test Param.", "Customer")
        out["Purchaser Order"] = _read_scalar_from_tdms(tdms, "Ref. Test Param.", "Purchaser Order")
        out["End User"]        = _read_scalar_from_tdms(tdms, "Ref. Test Param.", "End User")
        out["Applic. Specs."]  = _read_scalar_from_tdms(tdms, "Ref. Test Param.", "Applic. Specs.")
        out["FSG ORDER"]       = _read_fsg_order(tdms)

        # Pump Type
        out["Item"]                = _read_scalar_from_tdms(tdms, "Ref. Pump Type", "Item")
        out["Pump"]                = _read_scalar_from_tdms(tdms, "Ref. Pump Type", "Pump")
        out["Serial Number_Elenco"]= _read_scalar_from_tdms(tdms, "Ref. Pump Type", "Serial Number_Elenco")
        out["Impeller Drawing"]    = _read_scalar_from_tdms(tdms, "Ref. Pump Type", "Impeller Drawing")
        out["Impeller Material"]   = _read_scalar_from_tdms(tdms, "Ref. Pump Type", "Impeller Material")
        out["Diam Nominal"]        = _read_scalar_from_tdms(tdms, "Ref. Pump Type", "Diam Nominal")

        # Test Detail
        out["Suction [Inch]"]   = _read_scalar_from_tdms(tdms, "Ref. Test Detail", "Suction [Inch]")
        out["Discharge [Inch]"] = _read_scalar_from_tdms(tdms, "Ref. Test Detail", "Discharge [Inch]")
        out["Wattmeter Const."] = _read_scalar_from_tdms(tdms, "Ref. Test Detail", "Wattmeter Const.")
        out["AtmPress [m]"]     = _read_scalar_from_tdms(tdms, "Ref. Test Detail", "AtmPress [m]")
        out["KNPSH [m]"]        = _read_scalar_from_tdms(tdms, "Ref. Test Detail", "KNPSH [m]")
        out["WaterTemp [°C]"]   = (_read_scalar_from_tdms(tdms, "Ref. Test Detail", "WaterTemp [°C]") or
                                    _read_scalar_from_tdms(tdms, "Ref. Test Detail", "WaterTemp [C]"))
        out["KVenturi"]         = _read_scalar_from_tdms(tdms, "Ref. Test Detail", "KVenturi")
        return out
    finally:
        try:
            tdms.close()
        except Exception:
            pass


# -------------------- Performance tables (NO units) --------------------
GROUP_RE = re.compile(
    r"^(?P<test>\d+)_(?P<point>\d+)_"
    r"(?P<prefix>PERFORMANCE_PERFORM|NPSH_NPSH|RUNNING_RUNNING)"
    r"_(?:Test_)?(?P<kind>Recorded|Calc|Converted)$"
)
KIND_ORDER = ("Recorded", "Calc", "Converted")

def _normalize_channel_name(ch_name: str) -> str:
    """Mantiene il nome (incluse le unità tra []), normalizzando solo gli spazi."""
    name = (ch_name or "").strip()
    if not name:
        return "—"
    return re.sub(r"\s+", " ", name).strip()

def _mean_all_strict(data):
    if NUMPY_OK:
        try:
            a = np.asarray(data, dtype=float)
        except Exception:
            # Fallback robusto per canali stringa/misti.
            s, c = _nan_sum_and_count(data)
            return (s / c) if c else None
        if a.size == 0:
            return None
        a = a.copy()
        mask = ~np.isfinite(a)
        if mask.any():
            a[mask] = 0.0
        return float(np.mean(a)) if a.size else None
    seq = data if hasattr(data, "__iter__") and not isinstance(data, (str, bytes, bytearray)) else [data]
    total = 0.0
    n = 0
    for v in seq:
        f = _to_float_safe(v)
        if f is not None:
            total += f
        n += 1
    return (total / n) if n else None

def _nan_sum_and_count(a):
    if NUMPY_OK:
        try:
            finite = np.isfinite(a)
        except Exception:
            # Fallback robusto per sequenze non numeriche (es. stringhe con unità/virgole)
            s = 0.0
            c = 0
            try:
                seq = list(a)
            except Exception:
                seq = [a]
            for v in seq:
                f = _to_float_safe(v)
                if f is not None:
                    s += f
                    c += 1
            return s, c
        if not any(finite):
            return 0.0, 0
        s = float(a[finite].sum())
        c = int(finite.sum())
        return s, c
    s = 0.0; c = 0
    for v in a:
        f = _to_float_safe(v)
        if f is not None:
            s += f
            c += 1
    return s, c

def _mean_channel_fast(ch, chunk_size=2_000_000):
    try:
        n = len(ch)
    except Exception:
        try:
            data = ch[:]
        except Exception:
            data = getattr(ch, "data", [])
        return _mean_all_strict(data)

    total = 0.0
    count = 0
    start = 0
    while start < n:
        stop = min(start + chunk_size, n)
        try:
            part = ch[start:stop]
        except Exception:
            try:
                part = ch[:]
            except Exception:
                part = getattr(ch, "data", [])
            start = n
        else:
            start = stop

        if NUMPY_OK:
            try:
                arr = np.asarray(part, dtype=np.float32, order="C")
            except Exception:
                # Fallback robusto: canali stringa (es. "12,34") o mixed types.
                s, c = _nan_sum_and_count(part)
                total += s
                count += c
                continue
        else:
            arr = list(part)

        s, c = _nan_sum_and_count(arr)
        total += s
        count += c

    if count == 0:
        return None
    return total / count

def _collect_perf_points(tdms, test_index: int = 0):
    points = defaultdict(lambda: {"Recorded": [], "Calc": [], "Converted": []})
    for g in tdms.groups():
        m = GROUP_RE.match(g.name or "")
        if not m:
            continue
        if int(m.group("test")) != int(test_index):
            continue
        p = int(m.group("point"))
        k = m.group("kind")
        points[p][k].append(g)
    return dict(points)

def _build_kind_model(groups_by_point: dict):
    """
    Costruisce:
      - columns: lista intestazioni (con eventuali duplicati __2, __3, ...)
      - rows:    lista di tuple con **valori RAW** (float, oppure "" se assente)
    """
    first_seen_order = []
    max_dups = defaultdict(int)

    # Scansione per definire ordine e duplicati massimi
    for p in sorted(groups_by_point.keys()):
        counts_this_point = defaultdict(int)
        for grp in groups_by_point[p]:
            for ch in grp.channels():
                key = _normalize_channel_name(ch.name)
                if not key or key == "—":
                    continue
                counts_this_point[key] += 1
                if key not in first_seen_order:
                    first_seen_order.append(key)
        for key, cnt in counts_this_point.items():
            if cnt > max_dups[key]:
                max_dups[key] = cnt

    # Intestazioni finali con suffissi __2, __3...
    columns = []
    for key in first_seen_order:
        n = max(1, max_dups.get(key, 1))
        for i in range(1, n + 1):
            col = key if i == 1 else f"{key}__{i}"
            columns.append(col)

    # Righe (per ogni point) → **raw float** (niente formattazione qui)
    rows = []
    for p in sorted(groups_by_point.keys()):
        seq = defaultdict(int)
        row_map = {}
        for grp in groups_by_point[p]:
            for ch in grp.channels():
                key = _normalize_channel_name(ch.name)
                if not key or key == "—":
                    continue
                seq[key] += 1
                col = key if seq[key] == 1 else f"{key}__{seq[key]}"
                try:
                    mean_val = _mean_channel_fast(ch)
                except Exception:
                    try:
                        data = ch[:]
                    except Exception:
                        data = getattr(ch, "data", [])
                    mean_val = _mean_all_strict(data)
                row_map[col] = ("" if mean_val is None else mean_val)  # RAW float o vuoto
        # se una colonna non è presente per quel point, metto stringa vuota
        rows.append(tuple(row_map.get(c, "") for c in columns))

    return columns, rows

def read_performance_tables_dynamic(tdms_path: str, test_index: int = 0):
    """
    Ritorna (senza 'units'):
    {
      "Recorded":  {"columns": [...], "rows": [tuple,...]},   # rows con float/""
      "Calc":      {"columns": [...], "rows": [...]},
      "Converted": {"columns": [...], "rows": [...]}
    }
    
    Per "Recorded": usa Perfor_Table_Label da Info_Table se disponibile,
    altrimenti fallback ai nomi dei canali.
    """
    out = {k: {"columns": [], "rows": []} for k in ("Recorded", "Calc", "Converted")}
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return out
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return out
    try:
        points = _collect_perf_points(tdms, test_index=test_index)
        if not points:
            return out
        by_kind = {k: defaultdict(list) for k in ("Recorded", "Calc", "Converted")}
        for p, kinds in points.items():
            for k in ("Recorded", "Calc", "Converted"):
                if kinds[k]:
                    by_kind[k][p].extend(kinds[k])
        
        # Leggi le label personalizzate SOLO per PERFORMANCE (test_index=0)
        # Info_Table e Perfor_Table_Label non sono validi per NPSH/RUNNING
        custom_labels = []
        if test_index == 0:
            custom_labels = read_perfor_table_labels(tdms_path)
        
        for k in ("Recorded", "Calc", "Converted"):
            if by_kind[k]:
                cols, rows = _build_kind_model(by_kind[k])
                
                # Usa custom labels solo per Recorded di PERFORMANCE
                if k == "Recorded" and custom_labels and test_index == 0:
                    # Sostituisci le colonne con le label personalizzate
                    # Se ci sono meno label che colonne, usa le label disponibili
                    # Se ci sono più label che colonne, usa solo quelle necessarie
                    num_cols = len(cols)
                    num_labels = len(custom_labels)
                    
                    if num_labels >= num_cols:
                        # Usa le prime num_cols label
                        cols = custom_labels[:num_cols]
                    else:
                        # Usa tutte le label disponibili, poi fallback ai nomi originali
                        cols = custom_labels + cols[num_labels:]
                
                out[k]["columns"] = cols
                out[k]["rows"]    = rows
        return out
    finally:
        try:
            tdms.close()
        except Exception:
            pass


# -------------------- Curve data — META-ONLY (points deprecati) --------------------
def read_curve_data(tdms_path: str, test_index: int = 0) -> tuple[dict, list[tuple[float, float]]]:
    """
    Restituisce:
      - meta: dict con principali valori contrattuali (stringhe); chiavi:
          capacity, tdh, eff, abs_pow, speed, sg, temp, visc, npsh, liquid
      - points: **DEPRECATO** → sempre lista vuota (le curve ora usano read_performance_tables_dynamic)
    """
    raw = read_contract_and_loop_data(tdms_path) if tdms_path else {}
    meta = {
        "capacity": raw.get("Capacity [m3/h]", "") or "—",
        "tdh":      raw.get("TDH [m]", "") or "—",
        "eff":      raw.get("Efficiency [%]", "") or "—",
        "abs_pow":  raw.get("ABS_Power [kW]", "") or "—",
        "speed":    raw.get("Speed [rpm]", "") or "—",
        "sg":       raw.get("SG Contract", "") or "—",
        "temp":     raw.get("Temperature [°C]", "") or "—",
        "visc":     raw.get("Viscosity [cP]", "") or "—",
        "npsh":     raw.get("NPSH [m]", "") or "—",
        "liquid":   raw.get("Liquid", "") or "—",
    }
    return meta, []  # points non più usati


# -------------------- Power Calc Type (Info_Table) --------------------
def read_power_calc_type(tdms_path: str) -> str:
    """
    Legge il tipo di calcolo potenza dal gruppo Info_Table.
    
    Legge:
      - Power_Calc_Type_Value: indice (0, 1, 2, ...)
      - Power_Calc_Type_Elenco: lista di stringhe
    
    Restituisce la stringa corrispondente all'indice.
    
    Args:
        tdms_path: Percorso del file TDMS
    
    Returns:
        str: Descrizione del tipo di calcolo (es. "Wattmeter", "Torquemeter", ecc.)
             o "—" se non trovato
    """
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return "—"
    
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return "—"
    
    try:
        # Leggi il gruppo Info_Table
        info_group = _get_group_ci(tdms, "Info_Table")
        if not info_group:
            return "—"
        
        # Leggi il canale con l'indice
        value_channel = _get_channel_ci(info_group, "Power_Calc_Type_Value")
        if not value_channel:
            return "—"
        
        # Leggi il canale con l'elenco
        elenco_channel = _get_channel_ci(info_group, "Power_Calc_Type_Elenco")
        if not elenco_channel:
            return "—"
        
        # Leggi il valore dell'indice
        try:
            value_data = value_channel[:]
        except Exception:
            value_data = getattr(value_channel, "data", [])
        
        index_str = _first_nonempty(value_data)
        if not index_str:
            return "—"
        
        # Converti in intero
        try:
            index_value = int(float(str(index_str).replace(",", ".").strip()))
        except Exception:
            return "—"
        
        # Leggi l'elenco
        try:
            elenco_data = elenco_channel[:]
        except Exception:
            elenco_data = getattr(elenco_channel, "data", [])
        
        # Converti in lista di stringhe
        elenco_str = []
        for x in elenco_data:
            s = _first_nonempty([x])
            if s is None:
                s = ""
            elenco_str.append(str(s).strip())
        
        # Restituisci la stringa corrispondente all'indice
        # Gestisce sia 0-based che 1-based come per FSG Order
        n = len(elenco_str)
        if n == 0:
            return "—"
        
        # Prova 0-based
        if 0 <= index_value < n:
            result = elenco_str[index_value]
            return result if result else "—"
        
        # Prova 1-based
        if 1 <= index_value <= n:
            result = elenco_str[index_value - 1]
            return result if result else "—"
        
        return "—"
    
    except Exception:
        return "—"
    
    finally:
        try:
            tdms.close()
        except Exception:
            pass


def read_perfor_table_labels(tdms_path: str) -> list:
    """
    Legge le intestazioni personalizzate dal canale Perfor_Table_Label in Info_Table.
    
    Il canale contiene stringhe nel formato "NOME\r\nUNITA", es:
      "RPM\r\nrpm" → "RPM [rpm]"
      "FLOW\r\nm3/h" → "FLOW [m3/h]"
      "\r\n" → ignorato (campo vuoto)
    
    Args:
        tdms_path: Percorso del file TDMS
    
    Returns:
        list: Lista di intestazioni formattate, o lista vuota se non trovato
    """
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return []
    
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return []
    
    try:
        # Leggi il gruppo Info_Table
        info_group = _get_group_ci(tdms, "Info_Table")
        if not info_group:
            return []
        
        # Leggi il canale Perfor_Table_Label
        label_channel = _get_channel_ci(info_group, "Perfor_Table_Label")
        if not label_channel:
            return []
        
        # Leggi i dati
        try:
            label_data = label_channel[:]
        except Exception:
            label_data = getattr(label_channel, "data", [])
        
        # Processa ogni label
        headers = []
        for raw_label in label_data:
            # Converti in stringa
            label_str = str(raw_label).strip() if raw_label else ""
            
            # Salta campi vuoti
            if not label_str or label_str == "\r\n":
                continue
            
            # Split su \r\n per separare nome e unità
            parts = label_str.split("\r\n")
            
            if len(parts) >= 2:
                name = parts[0].strip()
                unit = parts[1].strip()
                
                # Se il nome contiene già le parentesi quadre (es. "MOTOR EFF [%]")
                # non aggiungere l'unità
                if "[" in name and "]" in name:
                    headers.append(name)
                elif unit:
                    headers.append(f"{name} [{unit}]")
                else:
                    headers.append(name)
            elif len(parts) == 1:
                # Solo nome, nessuna unità
                name = parts[0].strip()
                if name:
                    headers.append(name)
        
        return headers
    
    except Exception:
        return []
    
    finally:
        try:
            tdms.close()
        except Exception:
            pass


def detect_test_types(tdms_path: str) -> list:
    """
    Rileva i tipi di test presenti nel file TDMS analizzando i nomi dei gruppi.
    
    Pattern gruppi:
      - 0_X_PERFORMANCE → "PERFORMANCE"
      - 1_X_NPSH → "NPSH"
      - 2_X_RUNNING → "RUNNING"
    
    Args:
        tdms_path: Percorso del file TDMS
    
    Returns:
        list: Lista dei tipi di test trovati (es. ["PERFORMANCE", "NPSH"])
              Ordine: PERFORMANCE, NPSH, RUNNING (se presenti)
    """
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return []
    
    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return []
    
    try:
        test_types_found = set()
        
        for group in tdms.groups():
            group_name = group.name or ""
            
            # Pattern: NUMERO_NUMERO_TIPO
            # Es: 0_5_PERFORMANCE, 1_3_NPSH, 2_1_RUNNING
            parts = group_name.split("_")
            
            if len(parts) >= 3:
                prefix = parts[0]  # "0", "1", "2"
                suffix = parts[2]  # "PERFORMANCE", "NPSH", "RUNNING"
                
                # Identifica il tipo in base al prefisso
                if prefix == "0" and "PERFORMANCE" in suffix.upper():
                    test_types_found.add("PERFORMANCE")
                elif prefix == "1" and "NPSH" in suffix.upper():
                    test_types_found.add("NPSH")
                elif prefix == "2" and "RUNNING" in suffix.upper():
                    test_types_found.add("RUNNING")
        
        # Restituisci in ordine standard
        result = []
        for test_type in ["PERFORMANCE", "NPSH", "RUNNING"]:
            if test_type in test_types_found:
                result.append(test_type)
        
        return result
    
    except Exception:
        return []
    
    finally:
        try:
            tdms.close()
        except Exception:
            pass
