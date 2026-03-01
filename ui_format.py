import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterable, List, Union

DASH = "—"  # segnaposto UI per valori non disponibili

# ---------------------------
# Numeri e placeholder
# ---------------------------
def fmt_num(x) -> str:
    try:
        d = Decimal(str(x))
        q = d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        _ = float(q)
    except (InvalidOperation, ValueError, TypeError):
        return ""
    s = format(q, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s

def fmt_if_number(value, dash: str = DASH) -> str:
    if value is None:
        return dash
    s = str(value).strip()
    if s in ("", dash):
        return dash
    out = fmt_num(s.replace(",", "."))
    return out if out != "" else s

def fmt_seq(seq, dash: str = DASH) -> List[str]:
    try:
        return [fmt_if_number(v, dash=dash) for v in seq]
    except Exception:
        return [fmt_if_number(seq, dash=dash)]

# ---------------------------
# Pulizia intestazioni generica
# ---------------------------
def clean_header_brackets(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = s.strip(" -|/:,")
    return s

def _normalize_key(s: str) -> str:
    return re.sub(r"\s{2,}", " ", str(s).upper().strip())

def _key_for_match(text: str) -> str:
    s = re.sub(r"\[[^\]]*\]", "", str(text))
    return _normalize_key(s)

# ---------------------------
# Unità per Calculated / Converted (Metric e US)
# ---------------------------
_UNIT_MAP = {
    "calculated": {
        "Metric": {
            "FLOW": "m3/h",
            "KIN SUCT.": "m",
            "KIN DISCH.": "m",
            "TDH": "m",
            "POWER": "kW",
        },
        "US": {
            "FLOW": "GPM",
            "KIN SUCT.": "ft",
            "KIN DISCH.": "ft",
            "TDH": "ft",
            "POWER": "HP",
        },
    },
    "converted": {
        "Metric": {
            "FLOW": "m3/h",
            "TDH": "m",
            "POWER": "kW",
            "EFF": "%",
        },
        "US": {
            "FLOW": "GPM",
            "TDH": "ft",
            "POWER": "HP",
            "EFF": "%",
        },
    },
}

def add_units_to_header(header: str, table_kind: str, unit_system: str = "Metric") -> str:
    if header is None:
        return ""
    kind = (table_kind or "").strip().lower()
    if kind not in _UNIT_MAP:
        return str(header).strip()
    
    # Cerca nell'unit_system specificato
    unit_map_for_system = _UNIT_MAP[kind].get(unit_system, {})
    key = _key_for_match(header)
    unit = unit_map_for_system.get(key)
    return f"{str(header).strip()} {unit}" if unit else str(header).strip()

def add_units_to_headers(headers: Union[Iterable[str], str], table_kind: str, unit_system: str = "Metric") -> Union[List[str], str]:
    try:
        return [add_units_to_header(h, table_kind, unit_system) for h in headers]  # type: ignore[arg-type]
    except TypeError:
        return add_units_to_header(headers, table_kind, unit_system)               # type: ignore[arg-type]

# ---------------------------
# Router per certificate_view
# ---------------------------
def normalize_headers(headers: Union[Iterable[str], str], table_kind_or_title: str, unit_system: str = "Metric") -> Union[List[str], str]:
    """
    - 'Calculated...' / 'Converted...' -> aggiunge unità
    - fallback -> nessuna pulizia speciale
    """
    if headers is None:
        return []

    kind = (table_kind_or_title or "").strip().lower()

    if "calculated" in kind:
        return add_units_to_headers(headers, "calculated", unit_system)
    if "converted" in kind or "coverted" in kind:
        return add_units_to_headers(headers, "converted", unit_system)

    # fallback: restituisce i nomi così come sono
    return headers

