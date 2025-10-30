# tdms_reader.py
"""
Lettura TDMS riutilizzabile.
- Mantiene le unità di misura nel NOME canale (es. "Capacity [m3/h]") senza rimuoverle.
- Nessun array 'units' nelle tabelle: solo 'columns' e 'rows'.

Espone:
- NPTDMS_OK : bool
- read_tdms_fields(tdms_path) -> {"n_collaudo": str, "tipo_pompa": str}
- read_scalar_string(tdms_path, group, channel) -> str
- read_contract_and_loop_data(tdms_path) -> dict[str,str]
- read_performance_tables_dynamic(tdms_path, test_index=0) -> dict
"""

import os
import re
import math
import re as _re
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

def read_contract_and_loop_data(tdms_path: str) -> dict:
    """
    Ritorna un dict con i principali campi per Contractual / Test Param / Pump Type / Test Detail.
    Le unità sono parte del nome canale, non vengono rimosse.
    """
    out = {
        # Contract data
        "Capacity [m3/h]": "", "TDH [m]": "", "Efficiency [%]": "", "ABS_Power [kW]": "",
        "Speed [rpm]": "", "SG Contract": "", "Temperature [°C]": "", "Viscosity [cP]": "",
        "NPSH [m]": "", "Liquid": "",
        # Test param
        "Customer": "", "Purchaser Order": "", "End User": "", "Applic. Specs.": "",
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
    r"(?P<prefix>PERFORMANCE_PERFORM)"
    r"_(?:Test_)?(?P<kind>Recorded|Calc|Converted)$"
)
KIND_ORDER = ("Recorded", "Calc", "Converted")

def _normalize_channel_name(ch_name: str) -> str:
    """Mantiene il nome (incluse le unità tra []), normalizzando solo gli spazi."""
    name = (ch_name or "").strip()
    if not name:
        return "—"
    return re.sub(r"\s+", " ", name).strip()

def _fmt_num(x):
    try:
        d = Decimal(str(x))
    except Exception:
        return ""
    try:
        q = d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return ""
    try:
        if not math.isfinite(float(q)):
            return ""
    except Exception:
        return ""
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s

def _mean_all_strict(data):
    if NUMPY_OK:
        try:
            a = np.asarray(data, dtype=float)
        except Exception:
            return 0.0
        if a.size == 0:
            return 0.0
        a = a.copy()
        mask = ~np.isfinite(a)
        if mask.any():
            a[mask] = 0.0
        return float(np.mean(a))
    seq = data if hasattr(data, "__iter__") and not isinstance(data, (str, bytes, bytearray)) else [data]
    total = 0.0
    n = 0
    for v in seq:
        try:
            f = float(v)
        except Exception:
            f = 0.0
        if math.isfinite(f):
            total += f
        n += 1
    return (total / n) if n else 0.0

def _nan_sum_and_count(a):
    if NUMPY_OK:
        try:
            finite = np.isfinite(a)
        except Exception:
            try:
                import numpy as _np
                a = _np.asarray(list(a), dtype=float)
                finite = _np.isfinite(a)
            except Exception:
                return 0.0, 0
        if not any(finite):
            return 0.0, 0
        s = float(a[finite].sum())
        c = int(finite.sum())
        return s, c
    s = 0.0; c = 0
    for v in a:
        try:
            f = float(v)
        except Exception:
            continue
        if math.isfinite(f):
            s += f; c += 1
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
                import numpy as _np
                arr = _np.array([], dtype=_np.float32)
        else:
            arr = list(part)

        s, c = _nan_sum_and_count(arr)
        total += s
        count += c

    if count == 0:
        return 0.0
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
    """Costruisce columns (nomi canale, duplicati con __2, __3...) e rows (medie)."""
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

    # Righe (per ogni point)
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
                row_map[col] = _fmt_num(mean_val)
        rows.append(tuple(row_map.get(c, "") for c in columns))

    return columns, rows

def read_performance_tables_dynamic(tdms_path: str, test_index: int = 0):
    """
    Ritorna (senza 'units'):
    {
      "Recorded":  {"columns": [...], "rows": [tuple,...]},
      "Calc":      {"columns": [...], "rows": [...]},
      "Converted": {"columns": [...], "rows": [...]}
    }
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
        for k in ("Recorded", "Calc", "Converted"):
            if by_kind[k]:
                cols, rows = _build_kind_model(by_kind[k])
                out[k]["columns"] = cols
                out[k]["rows"]    = rows
        return out
    finally:
        try:
            tdms.close()
        except Exception:
            pass
            
# -------------------- Curve data (Contractual + punti Converted) --------------------
def _clean_name_for_curve(s: str) -> str:
    if not s:
        return ""
    s = _re.sub(r"\[[^\]]*\]", "", s)         # rimuovi eventuali unità tra [ ]
    s = _re.sub(r"\s+", " ", s).strip()       # normalizza spazi
    return s

def _tag_curve_channel(ch) -> str | None:
    """
    Riconosce il canale come 'flow' (y) o 'tdh' (x) in modo robusto.
    Esempi accettati (case-insensitive):
      - flow/capacity/q   -> 'flow'
      - tdh/head/h        -> 'tdh'
    """
    name = _clean_name_for_curve(getattr(ch, "name", "") or "").lower()
    if not name:
        return None
    if name.startswith("flow") or name.startswith("capacity") or name == "q" or name.startswith("q "):
        return "flow"
    if name.startswith("tdh") or name.startswith("head") or name == "h" or name.startswith("h "):
        return "tdh"
    return None

def read_curve_data(tdms_path: str, test_index: int = 0) -> tuple[dict, list[tuple[float, float]]]:
    """
    Restituisce:
      - meta: dict con principali valori contrattuali (stringhe); chiavi:
          capacity, tdh, eff, abs_pow, speed, sg, temp, visc, npsh, liquid
      - points: lista di (x=TDH [m], y=Flow [m3/h]) in float, calcolati come media per point dai gruppi Converted.
    Se il file non è valido/leggibile, points = [] e meta contiene '—' o stringhe vuote.
    """
    # meta dalle funzioni già esistenti (riuso)
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

    points: list[tuple[float, float]] = []
    if not (tdms_path and os.path.exists(tdms_path) and NPTDMS_OK):
        return meta, points

    try:
        tdms = TdmsFile.open(tdms_path)
    except Exception:
        return meta, points

    try:
        # Scansiona i gruppi PERFORMANCE del test richiesto e prende SOLO i Converted
        per_point: dict[int, dict[str, float]] = {}
        for g in tdms.groups():
            m = GROUP_RE.match(g.name or "")
            if not m:
                continue
            if int(m.group("test")) != int(test_index):
                continue
            if (m.group("kind") or "").lower() != "converted":
                continue

            p = int(m.group("point"))
            acc = per_point.setdefault(p, {})
            # media dei canali utili
            for ch in g.channels():
                tag = _tag_curve_channel(ch)
                if not tag:
                    continue
                try:
                    acc[tag] = float(_mean_channel_fast(ch))
                except Exception:
                    pass

        # compone i punti solo se entrambi presenti e finiti
        for p in sorted(per_point.keys()):
            acc = per_point[p]
            if "flow" in acc and "tdh" in acc and math.isfinite(acc["flow"]) and math.isfinite(acc["tdh"]):
                points.append((float(acc["tdh"]), float(acc["flow"])))  # (x=TDH, y=Flow)

        return meta, points
    finally:
        try:
            tdms.close()
        except Exception:
            pass

