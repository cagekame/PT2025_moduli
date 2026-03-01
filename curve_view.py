# curve_view.py
import math
import tkinter as tk
from tkinter import ttk

# matplotlib per il grafico
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.lines import Line2D
    from matplotlib.path import Path
    MPL_OK = True
except Exception:
    MPL_OK = False

# dati dal reader
from tdms_reader import read_performance_tables_dynamic, read_contract_and_loop_data
# format dei dati
from ui_format import fmt_if_number as _fmt_if_number, fmt_num as _fmt_num

# -------------------- UI helper (compattezza) --------------------
KEY_COL_WIDTH = 14
KEY_FONT = ("Segoe UI", 9, "bold")
VAL_FONT = ("Segoe UI", 9)
ROW_PADX = 8
ROW_PADY = 2
INNER_GAP = 4

def _kv(parent, k, v):
    row = tk.Frame(parent, bg="#f0f0f0")
    row.pack(fill="x", padx=ROW_PADX, pady=ROW_PADY)
    tk.Label(row, text=k, width=KEY_COL_WIDTH, anchor="w", bg="#f0f0f0",
             font=KEY_FONT).pack(side="left", padx=(0, INNER_GAP))
    tk.Label(row, text=(v if v else "—"), anchor="w", bg="#f0f0f0",
             font=VAL_FONT).pack(side="left", fill="x", expand=True)


# -------------------- Marker custom: triangolo rettangolo (angolo 90° in alto a destra) --------------------

def _marker_triangle_right_angle_top_right():
    # Vertici: top-left -> top-right (angolo retto) -> bottom-right
    verts = [
        (-0.5,  0.5),  # top-left
        ( 0.5,  0.5),  # top-right  <-- angolo 90°
        ( 0.5, -0.5),  # bottom-right
        (-0.5,  0.5),  # chiusura
    ]
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY]
    return Path(verts, codes)

RIGHT_ANGLE_TR_MARKER = _marker_triangle_right_angle_top_right()


# -------------------- numerica --------------------
def _to_float(x, default=None):
    try:
        if isinstance(x, str):
            x = x.replace(",", ".").strip()
        f = float(x)
        if math.isfinite(f):
            return f
    except Exception:
        pass
    return default

def _dedupe_and_sort_xy(xs, ys):
    """Ordina per x crescente e deduplica x coincidenti mediando i corrispondenti y."""
    pairs = {}
    for x, y in zip(xs, ys):
        try:
            xf = float(x); yf = float(y)
        except Exception:
            continue
        if not (math.isfinite(xf) and math.isfinite(yf)):
            continue
        pairs.setdefault(xf, []).append(yf)
    if not pairs:
        return [], []
    xs_sorted = sorted(pairs.keys())
    ys_sorted = [sum(pairs[x]) / len(pairs[x]) for x in xs_sorted]
    return xs_sorted, ys_sorted


# ---------- Trendline polinomiale cubica (minimi quadrati, senza NumPy) ----------
def _solve_linear_system_4x4(A, b):
    """Risoluzione A x = b (A 4x4) con eliminazione gaussiana + pivoting parziale."""
    M = [list(A[i]) + [b[i]] for i in range(4)]
    for col in range(4):
        pivot_row = max(range(col, 4), key=lambda r: abs(M[r][col]))
        if abs(M[pivot_row][col]) < 1e-12:
            return None
        if pivot_row != col:
            M[col], M[pivot_row] = M[pivot_row], M[col]
        pivot = M[col][col]
        for j in range(col, 5):
            M[col][j] /= pivot
        for r in range(col + 1, 4):
            factor = M[r][col]
            if factor == 0:
                continue
            for j in range(col, 5):
                M[r][j] -= factor * M[col][j]
    x = [0.0] * 4
    for i in range(3, -1, -1):
        s = M[i][4] - sum(M[i][j] * x[j] for j in range(i + 1, 4))
        x[i] = s
    return x

def _poly3_trendline(xs, ys):
    """y = a x^3 + b x^2 + c x + d, con R^2. Ritorna (a, b, c, d, r2) o tutti None."""
    n = len(xs)
    if n < 4:
        return (None, None, None, None, None)
    S0 = float(n)
    S1 = sum(xs)
    S2 = sum(x*x for x in xs)
    S3 = sum(x*x*x for x in xs)
    S4 = sum((x**4) for x in xs)
    S5 = sum((x**5) for x in xs)
    S6 = sum((x**6) for x in xs)

    T0 = sum(ys)
    T1 = sum(x*y for x, y in zip(xs, ys))
    T2 = sum((x*x)*y for x, y in zip(xs, ys))
    T3 = sum((x**3)*y for x, y in zip(xs, ys))

    A = [
        [S6, S5, S4, S3],
        [S5, S4, S3, S2],
        [S4, S3, S2, S1],
        [S3, S2, S1, S0],
    ]
    bvec = [T3, T2, T1, T0]

    coeffs = _solve_linear_system_4x4(A, bvec)
    if coeffs is None:
        return (None, None, None, None, None)
    a, b, c, d = coeffs

    y_mean = T0 / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (a*x**3 + b*x**2 + c*x + d)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    return (a, b, c, d, r2)
# --------------------------------------------------------------------


# -------------------- Colonne EXACT di Converted --------------------
FLOW_NAME  = "FLOW"
TDH_NAME   = "TDH"
EFF_NAME   = "EFF"
POWER_NAME = "POWER"

def _idx_exact_or_dup(columns, base_name):
    """
    Ritorna l'indice della colonna con nome esatto `base_name`.
    Accetta anche eventuali duplicati creati dal reader con suffisso '__2', '__3', ...
    """
    if not columns:
        return None
    for i, c in enumerate(columns):
        if c == base_name:
            return i
    prefix = f"{base_name}__"
    for i, c in enumerate(columns):
        if isinstance(c, str) and c.startswith(prefix):
            return i
    return None

def _get_converted(tdms_path: str, test_index: int = 0):
    perf = read_performance_tables_dynamic(tdms_path, test_index=test_index) or {}
    conv = perf.get("Converted") or {}
    return conv.get("columns") or [], conv.get("rows") or []


# -------------------- Contractual + Rated (stessa fonte del certificato) --------------------
def _read_contractual_meta(tdms_path: str) -> dict:
    """Chiavi UI normalizzate per Rated Point + alcuni campi textual Contractual."""
    raw = read_contract_and_loop_data(tdms_path) or {}
    
    # Helper per cercare chiavi in modo robusto
    def find_key(pattern):
        """Cerca una chiave nel dict raw che contiene il pattern (case-insensitive)."""
        pattern_lower = pattern.lower()
        for k in raw.keys():
            if pattern_lower in k.lower():
                return raw[k]
        return ""
    
    meta = {
        # Rated - cerca con pattern matching robusto
        "capacity": find_key("capacity") or "—",
        "tdh":      find_key("tdh [m") or "—",  # matcha sia "TDH [m]" che "TDH [m³/h]" ecc
        "eff":      find_key("efficiency") or "—",
        "abs_pow":  find_key("abs_power") or find_key("power [k") or "—",
        "speed":    find_key("speed") or "—",
        "sg":       find_key("sg contract") or "—",
        "temp":     find_key("temperature") or "—",
        "visc":     find_key("viscosity") or "—",
        "npsh":     find_key("npsh [m") or "—",
        "liquid":   raw.get("Liquid", "") or "—",
        # Contractual extra
        "fsg_order": raw.get("FSG ORDER", "") or "—",
        "customer":  raw.get("Customer", "") or "—",
        "po":        raw.get("Purchaser Order", "") or "—",
        "end_user":  raw.get("End User", "") or "—",
        "item":      raw.get("Item", "") or "—",
        "pump":      raw.get("Pump", "") or "—",
        "sn":        raw.get("Serial Number_Elenco", "") or "—",
        "imp_draw":  raw.get("Impeller Drawing", "") or "—",
        "imp_mat":   raw.get("Impeller Material", "") or "—",
        "imp_dia":   raw.get("Diam Nominal", "") or "—",
        "specs":     raw.get("Applic. Specs.", "") or "—",
    }
    return meta


# Serie per i grafici (letta come fa la tabella Converted)
def _series_q_h_from_converted(tdms_path: str, test_index: int = 0):
    cols, rows = _get_converted(tdms_path, test_index=test_index)
    if not cols or not rows:
        return [], []
    ix_q = _idx_exact_or_dup(cols, FLOW_NAME)
    ix_h = _idx_exact_or_dup(cols, TDH_NAME)
    if ix_q is None or ix_h is None:
        return [], []
    xs, ys = [], []
    for r in rows:
        q = _to_float(r[ix_q], None)
        h = _to_float(r[ix_h], None)
        if q is None or h is None:
            continue
        if math.isfinite(q) and math.isfinite(h):
            xs.append(q); ys.append(h)
    return xs, ys

def _series_q_eff_from_converted(tdms_path: str, test_index: int = 0):
    cols, rows = _get_converted(tdms_path, test_index=test_index)
    if not cols or not rows:
        return [], []
    ix_q   = _idx_exact_or_dup(cols, FLOW_NAME)
    ix_eff = _idx_exact_or_dup(cols, EFF_NAME)
    if ix_q is None or ix_eff is None:
        return [], []
    xs, ys = [], []
    for r in rows:
        q = _to_float(r[ix_q], None)
        e = _to_float(r[ix_eff], None)
        if q is None or e is None:
            continue
        if math.isfinite(q) and math.isfinite(e):
            xs.append(q); ys.append(e)
    return xs, ys

def _series_q_power_from_converted(tdms_path: str, test_index: int = 0):
    cols, rows = _get_converted(tdms_path, test_index=test_index)
    if not cols or not rows:
        return [], []
    ix_q  = _idx_exact_or_dup(cols, FLOW_NAME)
    ix_pw = _idx_exact_or_dup(cols, POWER_NAME)
    if ix_q is None or ix_pw is None:
        return [], []
    xs, ys = [], []
    for r in rows:
        q = _to_float(r[ix_q], None)
        p = _to_float(r[ix_pw], None)
        if q is None or p is None:
            continue
        if math.isfinite(q) and math.isfinite(p):
            xs.append(q); ys.append(p)
    return xs, ys


# -------------------- Figure matplotlib separate per PDF --------------------
def build_tdh_eff_figure(tdms_path: str, show_points: bool = True,
                         eff_min: float = 0.0, eff_max: float = 100.0,
                         unit_system: str = "Metric"):
    """Genera solo il grafico TDH + Efficiency con unità di misura specificate."""
    if not MPL_OK:
        return None

    try:
        import unit_converter as uc
    except:
        uc = None
        unit_system = "Metric"

    meta = _read_contractual_meta(tdms_path)
    fig = Figure(figsize=(11, 7), dpi=100)
    ax = fig.add_subplot(111)

    xs_raw, ys_raw = _series_q_h_from_converted(tdms_path, test_index=0)
    xs_eff, ys_eff = _series_q_eff_from_converted(tdms_path, test_index=0)

    # Converti i dati se necessario
    if uc and unit_system != "Metric":
        xs_raw = [uc.convert_value(x, 'flow', 'Metric', unit_system) for x in xs_raw]
        ys_raw = [uc.convert_value(y, 'head', 'Metric', unit_system) for y in ys_raw]
        xs_eff = [uc.convert_value(x, 'flow', 'Metric', unit_system) for x in xs_eff]

    has_rated_point = False
    has_bep_point = False
    has_rated_eff_point = False

    rated_q = _to_float(meta.get("capacity", ""), None)
    rated_tdh = _to_float(meta.get("tdh", ""), None)
    rated_eta = _to_float(meta.get("eff", ""), None)
    
    # Converti rated point se necessario
    if uc and unit_system != "Metric":
        if rated_q: rated_q = uc.convert_value(rated_q, 'flow', 'Metric', unit_system)
        if rated_tdh: rated_tdh = uc.convert_value(rated_tdh, 'head', 'Metric', unit_system)

    # TDH scatter
    if xs_raw and ys_raw:
        sc = ax.scatter(xs_raw, ys_raw, s=30, label="_nolegend_")
        sc.set_visible(show_points)

    # TDH trendline
    tdhs_trend = None
    xs, ys = _dedupe_and_sort_xy(xs_raw, ys_raw)
    x_curve = []
    if xs:
        a, b, c, d, r2 = _poly3_trendline(xs, ys)
        if a is not None and len(xs) >= 4:
            xmin, xmax = min(xs), max(xs)
            num = max(50, min(400, 10 * len(xs)))
            x_curve = [xmin + (xmax - xmin) * i / (num - 1) for i in range(num)]
            y_curve = [a*x**3 + b*x**2 + c*x + d for x in x_curve]
            tdhs_trend = ax.plot(x_curve, y_curve, linewidth=1.8, label="TDH")[0]
        else:
            tdhs_trend = ax.plot(xs, ys, linewidth=1.8, label="TDH")[0]

    # Rated TDH point (usa rated_q e rated_tdh già convertiti)
    if rated_q is not None and rated_tdh is not None:
        ax.scatter([rated_q], [rated_tdh], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                   facecolors="none", edgecolors="tab:blue",
                   linewidths=1.6, label="_nolegend_", zorder=10)
        has_rated_point = True

    # Etichette assi con unità dinamiche
    flow_unit = uc.get_unit_label('flow', unit_system) if uc else "m³/h"
    head_unit = uc.get_unit_label('head', unit_system) if uc else "m"
    
    ax.set_ylabel(f"TDH [{head_unit}]")
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    ax.set_xlabel(f"Capacity [{flow_unit}]")
    ax.grid(True, linestyle=":", linewidth=0.8)

    # Efficiency (asse destro)
    eta_line = None
    ax2 = None
    if xs_eff and ys_eff:
        ax2 = ax.twinx()
        ax.set_zorder(2); ax2.set_zorder(1); ax.patch.set_visible(False)
        ax2.set_ylabel("Efficiency [%]")

        eff_sc = ax2.scatter(xs_eff, ys_eff, s=25, marker="o", label="_nolegend_")
        eff_sc.set_visible(show_points)

        if rated_q is not None and rated_eta is not None:
            ax2.scatter([rated_q], [rated_eta], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                        facecolors="none", edgecolors="tab:orange",
                        linewidths=1.6, label="_nolegend_", zorder=10)
            has_rated_eff_point = True

        xe, ye = _dedupe_and_sort_xy(xs_eff, ys_eff)
        if xe:
            ea, eb, ec, ed, er2 = _poly3_trendline(xe, ye)
            e_x = x_curve if x_curve else [
                min(xe) + (max(xe) - min(xe)) * i / (max(50, min(400, 10*len(xe))) - 1)
                for i in range(max(50, min(400, 10*len(xe))))
            ]
            if ea is not None and len(xe) >= 4:
                e_y = [ea*x**3 + eb*x**2 + ec*x + ed for x in e_x]
                eta_line = ax2.plot(e_x, e_y, linewidth=1.8, color="orange", label="Efficiency")[0]
                try:
                    max_i = max(range(len(e_x)), key=lambda k: e_y[k])
                    ax2.scatter([e_x[max_i]], [e_y[max_i]], s=80, marker="D",
                                color="red", edgecolors="red", label="_nolegend_", zorder=10)
                    has_bep_point = True
                except Exception:
                    pass
            else:
                eta_line = ax2.plot(xe, ye, linewidth=1.8, color="orange", label="Efficiency")[0]
        ax2.set_ylim(eff_min, eff_max)

    ax.relim(); ax.autoscale(axis="y")
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(bottom=0, top=ymax * 1.10)

    # Legend
    handles, labels = [], []
    if tdhs_trend: handles.append(tdhs_trend); labels.append("TDH")
    if eta_line: handles.append(eta_line); labels.append("Efficiency")
    if has_rated_point:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:blue", markeredgewidth=1.6))
        labels.append("Rated TDH")
    if has_rated_eff_point:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:orange", markeredgewidth=1.6))
        labels.append("Rated Efficiency")
    if has_bep_point:
        handles.append(Line2D([0],[0], marker="D", linestyle="None", markersize=7,
                               markerfacecolor="red", markeredgecolor="red"))
        labels.append("BEP point")
    if handles:
        ax.legend(handles, labels, loc="lower right")

    fig.tight_layout()
    return fig


def build_power_figure(tdms_path: str, show_points: bool = True, unit_system: str = "Metric"):
    """Genera solo il grafico Power con unità di misura specificate."""
    if not MPL_OK:
        return None

    try:
        import unit_converter as uc
    except:
        uc = None
        unit_system = "Metric"

    fig = Figure(figsize=(11, 7), dpi=100)
    ax = fig.add_subplot(111)

    pxs_raw, pys_raw = _series_q_power_from_converted(tdms_path, test_index=0)
    
    # Converti i dati se necessario
    if uc and unit_system != "Metric":
        pxs_raw = [uc.convert_value(x, 'flow', 'Metric', unit_system) for x in pxs_raw]
        pys_raw = [uc.convert_value(y, 'power', 'Metric', unit_system) for y in pys_raw]
    
    p_line = None
    if pxs_raw and pys_raw:
        pwr_sc = ax.scatter(pxs_raw, pys_raw, s=28, label="_nolegend_")
        pwr_sc.set_visible(show_points)
        pxs, pys = _dedupe_and_sort_xy(pxs_raw, pys_raw)
        if pxs:
            pa, pb, pc, pd, pr2 = _poly3_trendline(pxs, pys)
            if pa is not None and len(pxs) >= 4:
                pxmin, pxmax = min(pxs), max(pxs)
                pnum = max(50, min(400, 10 * len(pxs)))
                px_curve = [pxmin + (pxmax - pxmin) * i / (pnum-1) for i in range(pnum)]
                py_curve = [pa*x**3 + pb*x**2 + pc*x + pd for x in px_curve]
                p_line = ax.plot(px_curve, py_curve, linewidth=1.8, color="black", label="Absorbed Power")[0]
            else:
                p_line = ax.plot(pxs, pys, linewidth=1.8, color="black", label="Absorbed Power")[0]

    # Etichette assi con unità dinamiche
    flow_unit = uc.get_unit_label('flow', unit_system) if uc else "m³/h"
    power_unit = uc.get_unit_label('power', unit_system) if uc else "kW"
    
    ax.set_xlabel(f"Capacity [{flow_unit}]")
    ax.set_ylabel(f"Abs Power [{power_unit}]")
    ax.set_ylim(bottom=0)
    ax.grid(True, linestyle=":", linewidth=0.8)
    ax.relim(); ax.autoscale(axis="y")
    pymin, pymax = ax.get_ylim()
    ax.set_ylim(bottom=0, top=pymax * 1.10)
    if p_line is not None:
        ax.legend([p_line], ["Absorbed Power"], loc="lower right")

    fig.tight_layout()
    return fig


# -------------------- Figura matplotlib (usata sia da UI che da PDF) --------------------
def build_curve_figure(tdms_path: str, show_points: bool = True,
                       eff_min: float = 0.0, eff_max: float = 100.0,
                       unit_system: str = "Metric",
                       return_artists: bool = False):
    """
    Genera e restituisce la Figure matplotlib con i due grafici
    (TDH+Efficiency sopra, Absorbed Power sotto).
    Usata da render_curve_tab (UI).
    Ritorna None se matplotlib non è disponibile o i dati mancano.
    
    Args:
        return_artists: se True, restituisce (fig, artists_dict, ax2) invece di solo fig
                       artists_dict contiene {'tdh': scatter, 'eff': scatter, 'pwr': scatter}
                       ax2 è l'asse Efficiency (per modificare ylim senza rigenerare)
    """
    if not MPL_OK:
        return None if not return_artists else (None, {}, None)

    try:
        import unit_converter as uc
    except:
        uc = None
        unit_system = "Metric"

    meta = _read_contractual_meta(tdms_path)

    fig = Figure(figsize=(9, 11), dpi=100)
    gs  = fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.20)
    ax  = fig.add_subplot(gs[0])
    axp = fig.add_subplot(gs[1], sharex=ax)

    xs_raw, ys_raw = _series_q_h_from_converted(tdms_path, test_index=0)
    xs_eff, ys_eff = _series_q_eff_from_converted(tdms_path, test_index=0)

    # Converti i dati se necessario
    if uc and unit_system != "Metric":
        xs_raw = [uc.convert_value(x, 'flow', 'Metric', unit_system) for x in xs_raw]
        ys_raw = [uc.convert_value(y, 'head', 'Metric', unit_system) for y in ys_raw]
        xs_eff = [uc.convert_value(x, 'flow', 'Metric', unit_system) for x in xs_eff]

    has_rated_point     = False
    has_bep_point       = False
    has_rated_eff_point = False

    rated_q   = _to_float(meta.get("capacity", ""), None)
    rated_tdh = _to_float(meta.get("tdh", ""), None)
    rated_eta = _to_float(meta.get("eff", ""), None)
    
    # Converti rated point se necessario
    if uc and unit_system != "Metric":
        if rated_q: rated_q = uc.convert_value(rated_q, 'flow', 'Metric', unit_system)
        if rated_tdh: rated_tdh = uc.convert_value(rated_tdh, 'head', 'Metric', unit_system)

    # Dizionario per gli artist (se richiesti)
    artists = {}

    # --- TDH ---
    tdh_scatter = None
    if xs_raw and ys_raw:
        sc = ax.scatter(xs_raw, ys_raw, s=30, label="_nolegend_")
        sc.set_visible(show_points)
        tdh_scatter = sc
        if return_artists:
            artists['tdh'] = sc

    tdhs_trend = None
    xs, ys = _dedupe_and_sort_xy(xs_raw, ys_raw)
    x_curve = []; y_curve = []
    if xs:
        a, b, c, d, r2 = _poly3_trendline(xs, ys)
        if a is not None and len(xs) >= 4:
            xmin, xmax = min(xs), max(xs)
            num = max(50, min(400, 10 * len(xs)))
            x_curve = [xmin + (xmax - xmin) * i / (num - 1) for i in range(num)]
            y_curve = [a*x**3 + b*x**2 + c*x + d for x in x_curve]
            tdhs_trend = ax.plot(x_curve, y_curve, linewidth=1.8, label="TDH")[0]
        else:
            tdhs_trend = ax.plot(xs, ys, linewidth=1.8, label="TDH")[0]

    # Rated TDH point (usa rated_q, rated_tdh già convertiti)
    if rated_q is not None and rated_tdh is not None:
        ax.scatter([rated_q], [rated_tdh], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                   facecolors="none", edgecolors="tab:blue",
                   linewidths=1.6, label="_nolegend_", zorder=10)
        has_rated_point = True

    # Etichette assi con unità dinamiche
    flow_unit = uc.get_unit_label('flow', unit_system) if uc else "m³/h"
    head_unit = uc.get_unit_label('head', unit_system) if uc else "m"
    
    ax.set_ylabel(f"TDH [{head_unit}]")
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    ax.grid(True, linestyle=":", linewidth=0.8)

    # --- Efficiency ---
    eta_line = None
    ax2 = None
    eff_scatter = None
    if xs_eff and ys_eff:
        ax2 = ax.twinx()
        ax.set_zorder(2); ax2.set_zorder(1); ax.patch.set_visible(False)
        ax2.set_ylabel("Efficiency [%]")
        ax2.set_ylim(0, 100)

        eff_sc = ax2.scatter(xs_eff, ys_eff, s=25, marker="o", label="_nolegend_")
        eff_sc.set_visible(show_points)
        eff_scatter = eff_sc
        if return_artists:
            artists['eff'] = eff_sc

        if rated_q is not None and rated_eta is not None:
            ax2.scatter([rated_q], [rated_eta], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                        facecolors="none", edgecolors="tab:orange",
                        linewidths=1.6, label="_nolegend_", zorder=10)
            has_rated_eff_point = True

        xe, ye = _dedupe_and_sort_xy(xs_eff, ys_eff)
        if xe:
            ea, eb, ec, ed, er2 = _poly3_trendline(xe, ye)
            e_x = x_curve if x_curve else [
                min(xe) + (max(xe) - min(xe)) * i / (max(50, min(400, 10*len(xe))) - 1)
                for i in range(max(50, min(400, 10*len(xe))))
            ]
            if ea is not None and len(xe) >= 4:
                e_y = [ea*x**3 + eb*x**2 + ec*x + ed for x in e_x]
                eta_line = ax2.plot(e_x, e_y, linewidth=1.8, color="orange", label="Efficiency")[0]
                try:
                    max_i = max(range(len(e_x)), key=lambda k: e_y[k])
                    ax2.scatter([e_x[max_i]], [e_y[max_i]], s=80, marker="D",
                                color="red", edgecolors="red", label="_nolegend_", zorder=10)
                    has_bep_point = True
                except Exception:
                    pass
            else:
                eta_line = ax2.plot(xe, ye, linewidth=1.8, color="orange", label="Efficiency")[0]
        ax2.set_ylim(eff_min, eff_max)

    ax.relim(); ax.autoscale(axis="y")
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(bottom=0, top=ymax * 1.10)

    handles, labels = [], []
    if tdhs_trend is not None:
        handles.append(tdhs_trend); labels.append("TDH")
    if eta_line is not None:
        handles.append(eta_line);   labels.append("Efficiency")
    if has_rated_point:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:blue", markeredgewidth=1.6))
        labels.append("Rated TDH")
    if has_rated_eff_point:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:orange", markeredgewidth=1.6))
        labels.append("Rated Efficiency")
    if has_bep_point:
        handles.append(Line2D([0],[0], marker="D", linestyle="None", markersize=7,
                               markerfacecolor="red", markeredgecolor="red"))
        labels.append("BEP point")
    if handles:
        ax.legend(handles, labels, loc="lower right")

    # --- Power ---
    pxs_raw, pys_raw = _series_q_power_from_converted(tdms_path, test_index=0)
    
    # Converti i dati Power se necessario
    if uc and unit_system != "Metric":
        pxs_raw = [uc.convert_value(x, 'flow', 'Metric', unit_system) for x in pxs_raw]
        pys_raw = [uc.convert_value(y, 'power', 'Metric', unit_system) for y in pys_raw]
    
    p_line = None
    pwr_scatter = None
    if pxs_raw and pys_raw:
        pwr_sc = axp.scatter(pxs_raw, pys_raw, s=28, label="_nolegend_")
        pwr_sc.set_visible(show_points)
        pwr_scatter = pwr_sc
        if return_artists:
            artists['pwr'] = pwr_sc
        pxs, pys = _dedupe_and_sort_xy(pxs_raw, pys_raw)
        if pxs:
            pa, pb, pc, pd, pr2 = _poly3_trendline(pxs, pys)
            if pa is not None and len(pxs) >= 4:
                pxmin, pxmax = min(pxs), max(pxs)
                pnum = max(50, min(400, 10 * len(pxs)))
                px_curve = [pxmin + (pxmax - pxmin) * i / (pnum-1) for i in range(pnum)]
                py_curve = [pa*x**3 + pb*x**2 + pc*x + pd for x in px_curve]
                p_line = axp.plot(px_curve, py_curve, linewidth=1.8, color="black", label="Absorbed Power")[0]
            else:
                p_line = axp.plot(pxs, pys, linewidth=1.8, color="black", label="Absorbed Power")[0]

    power_unit = uc.get_unit_label('power', unit_system) if uc else "kW"
    
    axp.set_xlabel(f"Capacity [{flow_unit}]")
    axp.set_ylabel(f"Abs Power [{power_unit}]")
    axp.set_ylim(bottom=0)
    axp.grid(True, linestyle=":", linewidth=0.8)
    axp.relim(); axp.autoscale(axis="y")
    pymin, pymax = axp.get_ylim()
    axp.set_ylim(bottom=0, top=pymax * 1.10)
    if p_line is not None:
        axp.legend([p_line], ["Absorbed Power"], loc="lower right")

    fig.subplots_adjust(top=0.98)
    
    if return_artists:
        return fig, artists, ax2
    else:
        return fig


# -------------------- Render --------------------
def render_curve_tab(parent, tdms_path: str, acquisizione_id: int = None):
    """
    parent: frame della tab 'Curva'
    tdms_path: percorso TDMS
    acquisizione_id: ID acquisizione per leggere unit_system

    Layout:
    - Colonna sinistra: "Contractual Data" (sopra) e "Rated Point" (sotto)
    - Colonna destra: frame con grafico scrollabile
    """
    # Leggi unit_system dal DB
    try:
        from db import get_unit_system
        unit_system = get_unit_system(acquisizione_id) if acquisizione_id else "Metric"
    except Exception:
        unit_system = "Metric"
    
    # --- GRIGLIA PRINCIPALE: 2 colonne (sx info, dx grafico) e 1 riga ---
    parent.grid_columnconfigure(0, weight=0, minsize=380)
    parent.grid_columnconfigure(1, weight=1)
    parent.grid_rowconfigure(0, weight=1)

    # ====== COLONNA SINISTRA ======
    left_col = tk.Frame(parent, bg="#f0f0f0")
    left_col.grid(row=0, column=0, sticky="nsw", padx=(10, 6), pady=10)
    left_col.grid_columnconfigure(0, weight=1)

    # Leggi dati raw
    raw = read_contract_and_loop_data(tdms_path) or {}
    
    # Helper per convertire valori individuali
    def get_converted_value(key_pattern: str, param_type: str, default="—"):
        """Cerca la chiave nel raw e converte il valore se necessario."""
        value = None
        # Cerca con diverse varianti della chiave (case-insensitive)
        for k in raw.keys():
            if key_pattern.lower() in k.lower():
                value = raw[k]
                break
        
        if not value or value == "":
            return default
        
        # Converti se necessario
        if unit_system != "Metric" and param_type:
            try:
                import unit_converter as uc
                return uc.convert_value(value, param_type, "Metric", unit_system)
            except:
                return value
        return value
    
    meta = {
        # Rated - converti manualmente
        "capacity": get_converted_value("capacity", "flow"),
        "tdh":      get_converted_value("tdh", "head"),
        "eff":      get_converted_value("efficiency", None),
        "abs_pow":  get_converted_value("abs_power", "power") or get_converted_value("power", "power"),
        "speed":    get_converted_value("speed", "speed"),
        "sg":       get_converted_value("sg contract", None),
        "temp":     get_converted_value("temperature", "temp"),
        "visc":     get_converted_value("viscosity", None),
        "npsh":     get_converted_value("npsh", "npsh"),
        "liquid":   raw.get("Liquid", "") or "—",
        # Contractual extra (non cambiano)
        "fsg_order": raw.get("FSG ORDER", "") or "—",
        "customer":  raw.get("Customer", "") or "—",
        "po":        raw.get("Purchaser Order", "") or "—",
        "end_user":  raw.get("End User", "") or "—",
        "item":      raw.get("Item", "") or "—",
        "pump":      raw.get("Pump", "") or "—",
        "sn":        raw.get("Serial Number_Elenco", "") or "—",
        "imp_draw":  raw.get("Impeller Drawing", "") or "—",
        "imp_mat":   raw.get("Impeller Material", "") or "—",
        "imp_dia":   raw.get("Diam Nominal", "") or "—",
        "specs":     raw.get("Applic. Specs.", "") or "—",
    }

    # Contractual Data — due colonne interne per compattezza
    contractual = tk.LabelFrame(left_col, text="Contractual Data", bg="#f0f0f0")
    contractual.grid(row=0, column=0, sticky="new")
    contractual.grid_columnconfigure(0, weight=1)
    contractual.grid_columnconfigure(1, weight=1)

    c1 = tk.Frame(contractual, bg="#f0f0f0"); c1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    c2 = tk.Frame(contractual, bg="#f0f0f0"); c2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    _kv(c1, "FSG ORDER",         meta.get("fsg_order", "—"))
    _kv(c1, "CUSTOMER",          meta.get("customer", "—"))
    _kv(c1, "P.O.",              meta.get("po", "—"))
    _kv(c1, "End User",          meta.get("end_user", "—"))
    _kv(c1, "Item",              meta.get("item", "—"))
    _kv(c1, "Pump",              meta.get("pump", "—"))
    _kv(c1, "S. N.",             meta.get("sn", "—"))
    _kv(c1, "Imp. Draw.",        meta.get("imp_draw", "—"))
    _kv(c1, "Imp. Mat.",         meta.get("imp_mat", "—"))
    _kv(c1, "Imp Dia [mm]",      meta.get("imp_dia", "—"))
    _kv(c1, "Specs",             meta.get("specs", "—"))

    # Rated Point (sotto) con unità dinamiche
    rated = tk.LabelFrame(left_col, text="Rated Point", bg="#f0f0f0")
    rated.grid(row=1, column=0, sticky="new", pady=(6, 0))

    try:
        import unit_converter as uc
        flow_unit = uc.get_unit_label('flow', unit_system)
        head_unit = uc.get_unit_label('head', unit_system)
        power_unit = uc.get_unit_label('power', unit_system)
        temp_unit = uc.get_unit_label('temp', unit_system)
        npsh_unit = uc.get_unit_label('npsh', unit_system)
    except:
        flow_unit = "m³/h"
        head_unit = "m"
        power_unit = "kW"
        temp_unit = "°C"
        npsh_unit = "m"

    _kv(rated, f"Capacity [{flow_unit}]", _fmt_if_number(meta.get("capacity", "—")))
    _kv(rated, f"TDH [{head_unit}]",         _fmt_if_number(meta.get("tdh", "—")))
    _kv(rated, "Efficiency [%]",  _fmt_if_number(meta.get("eff", "—")))
    _kv(rated, f"ABS_Power [{power_unit}]",  _fmt_if_number(meta.get("abs_pow", "—")))
    _kv(rated, "Speed [rpm]",     _fmt_if_number(meta.get("speed", "—")))
    _kv(rated, "SG",              _fmt_if_number(meta.get("sg", "—")))
    _kv(rated, f"Temperature [{temp_unit}]",_fmt_if_number(meta.get("temp", "—")))
    _kv(rated, "Viscosity [cP]",  _fmt_if_number(meta.get("visc", "—")))
    _kv(rated, f"NPSH [{npsh_unit}]",        _fmt_if_number(meta.get("npsh", "—")))
    _kv(rated, "Liquid",          meta.get("liquid", "—"))
    
    # =====================================================
    # Controlli scala efficienza (sotto Rated Point)
    # =====================================================
    eff_scale = tk.LabelFrame(left_col, text="Efficiency Scale", bg="#f0f0f0")
    eff_scale.grid(row=2, column=0, sticky="new", pady=(10, 0))

    # 5 celle in una riga
    eff_scale.grid_columnconfigure(0, weight=0)
    eff_scale.grid_columnconfigure(1, weight=0)
    eff_scale.grid_columnconfigure(2, weight=0)
    eff_scale.grid_columnconfigure(3, weight=0)
    eff_scale.grid_columnconfigure(4, weight=1)  # il bottone può espandere

    # Min
    tk.Label(eff_scale, text="Min [%]", bg="#f0f0f0").grid(
        row=0, column=0, sticky="e", padx=(6, 2), pady=4
    )
    entry_eff_min = tk.Entry(eff_scale, width=6)
    entry_eff_min.grid(
        row=0, column=1, sticky="w", padx=(0, 12), pady=4
    )

    # Max
    tk.Label(eff_scale, text="Max [%]", bg="#f0f0f0").grid(
        row=0, column=2, sticky="e", padx=(6, 2), pady=4
    )
    entry_eff_max = tk.Entry(eff_scale, width=6)
    entry_eff_max.grid(
        row=0, column=3, sticky="w", padx=(0, 12), pady=4
    )

    # Carica impostazioni salvate dal DB
    try:
        from db import curve_settings_get, curve_settings_set as _curve_settings_set
        _saved = curve_settings_get(acquisizione_id) if acquisizione_id is not None else None
        if _saved is None:
            _saved = {"show_points": True, "eff_min": 0.0, "eff_max": 100.0}
        _saved_show   = _saved["show_points"]
        _saved_effmin = _saved["eff_min"]
        _saved_effmax = _saved["eff_max"]
    except Exception:
        _curve_settings_set = None
        _saved_show   = True
        _saved_effmin = 0.0
        _saved_effmax = 100.0

    entry_eff_min.delete(0, "end")
    entry_eff_min.insert(0, str(int(_saved_effmin) if _saved_effmin == int(_saved_effmin) else _saved_effmin))
    entry_eff_max.delete(0, "end")
    entry_eff_max.insert(0, str(int(_saved_effmax) if _saved_effmax == int(_saved_effmax) else _saved_effmax))

    def _save_settings():
        if _curve_settings_set is None or acquisizione_id is None:
            return
        try:
            _curve_settings_set(
                acquisizione_id,
                show_points=bool(show_curve_points_var.get()),
                eff_min=float(entry_eff_min.get()),
                eff_max=float(entry_eff_max.get()),
            )
        except Exception:
            pass

    # Variabili che verranno usate da apply_eff_scale e _toggle_curve_points
    canvas = None
    tdh_points_artist = None
    eff_points_artist = None
    pwr_points_artist = None
    ax2 = None  # asse Efficiency per modifiche veloci senza rigenerare

    # Funzione per rigenerare la figura (usata da Apply e dal rendering iniziale)
    def _regenerate_figure():
        """Rigenera completamente la figura con i parametri correnti."""
        # Leggi i valori correnti
        try:
            current_eff_min = float(entry_eff_min.get())
            current_eff_max = float(entry_eff_max.get())
        except:
            current_eff_min = 0.0
            current_eff_max = 100.0
        
        # Genera la figura
        result = build_curve_figure(
            tdms_path, 
            show_points=bool(show_curve_points_var.get()),
            eff_min=current_eff_min, 
            eff_max=current_eff_max,
            unit_system=unit_system,
            return_artists=True
        )
        
        if result is None or result == (None, {}, None):
            return None, {}, None
        
        return result

    def apply_eff_scale():
        """Applica la nuova scala di efficienza modificando ax2 (veloce) o rigenerando se necessario."""
        nonlocal ax2, canvas, tdh_points_artist, eff_points_artist, pwr_points_artist
        
        try:
            vmin = float(entry_eff_min.get())
            vmax = float(entry_eff_max.get())
            if vmax <= vmin:
                return
            
            # Ottimizzazione: se ax2 esiste, modifica solo ylim (veloce)
            if ax2 is not None:
                ax2.set_ylim(vmin, vmax)
                canvas.draw_idle()
                _save_settings()
            else:
                # Fallback: rigenera tutto (necessario se ax2 non disponibile)
                new_result = _regenerate_figure()
                if new_result is None or new_result == (None, {}, None):
                    return
                
                new_fig, new_artists, new_ax2 = new_result
                
                # Distruggi il canvas vecchio
                for widget in right.winfo_children():
                    widget.destroy()
                
                # Crea nuovo canvas
                canvas = FigureCanvasTkAgg(new_fig, master=right)
                widget = canvas.get_tk_widget()
                widget.pack(fill="both", expand=True, padx=0, pady=0)
                
                # Aggiorna gli artist e ax2
                tdh_points_artist = new_artists.get('tdh')
                eff_points_artist = new_artists.get('eff')
                pwr_points_artist = new_artists.get('pwr')
                ax2 = new_ax2
                
                _save_settings()
        except Exception:
            pass

    # Bottone sulla stessa riga (colonna 4)
    btn_set_eff = tk.Button(eff_scale, text="Apply", command=apply_eff_scale)
    btn_set_eff.grid(row=0, column=4, sticky="e", padx=(10, 6), pady=4)

    # =====================================================
    # Flag: Show curve points
    # =====================================================
    show_curve_points_var = tk.BooleanVar(value=_saved_show)

    chk_show_points = tk.Checkbutton(
        left_col,
        text="Show curve points",
        variable=show_curve_points_var,
        bg="#f0f0f0",
        activebackground="#f0f0f0",
    )
    chk_show_points.grid(row=3, column=0, sticky="w", padx=12, pady=(8, 0))

    # ====== COLONNA DESTRA: GRAFICO SCROLLABILE ======
    right_outer = tk.LabelFrame(parent, text="Curve", bg="#f0f0f0")
    right_outer.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)
    right_outer.grid_columnconfigure(0, weight=1)
    right_outer.grid_rowconfigure(0, weight=1)

    scroll_canvas = tk.Canvas(right_outer, highlightthickness=0, bg="#f0f0f0")
    vbar = ttk.Scrollbar(right_outer, orient="vertical", command=scroll_canvas.yview)
    scroll_canvas.configure(yscrollcommand=vbar.set)
    scroll_canvas.grid(row=0, column=0, sticky="nsew")
    vbar.grid(row=0, column=1, sticky="ns")

    right = tk.Frame(scroll_canvas, bg="#f0f0f0")
    _win_id = scroll_canvas.create_window((0, 0), window=right, anchor="nw")

    def _on_right_configure(_e=None):
        scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
    right.bind("<Configure>", _on_right_configure)

    def _on_canvas_configure(e):
        scroll_canvas.itemconfig(_win_id, width=e.width)
    scroll_canvas.bind("<Configure>", _on_canvas_configure)

    # Scroll con la rotella del mouse (Windows/Linux/Mac)
    def _on_mousewheel(event):
        if event.num == 4:
            scroll_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            scroll_canvas.yview_scroll(1, "units")
        else:
            scroll_canvas.yview_scroll(int(-event.delta / 120), "units")

    scroll_canvas.bind("<MouseWheel>",  _on_mousewheel)
    scroll_canvas.bind("<Button-4>",    _on_mousewheel)
    scroll_canvas.bind("<Button-5>",    _on_mousewheel)

    def _bind_wheel(e):
        scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        scroll_canvas.bind_all("<Button-4>",   _on_mousewheel)
        scroll_canvas.bind_all("<Button-5>",   _on_mousewheel)

    def _unbind_wheel(e):
        scroll_canvas.unbind_all("<MouseWheel>")
        scroll_canvas.unbind_all("<Button-4>")
        scroll_canvas.unbind_all("<Button-5>")

    scroll_canvas.bind("<Enter>", _bind_wheel)
    scroll_canvas.bind("<Leave>", _unbind_wheel)
    right.bind("<Enter>", _bind_wheel)
    right.bind("<Leave>", _unbind_wheel)

    if not MPL_OK:
        tk.Label(
            right,
            text="Matplotlib non disponibile.\nInstalla 'matplotlib' per vedere i grafici.",
            bg="#f0f0f0", justify="left"
        ).pack(anchor="nw", padx=10, pady=10)
        return

    # --- Genera figura iniziale ---
    result = _regenerate_figure()
    
    if result is None or result == (None, {}, None):
        tk.Label(
            right,
            text="Impossibile generare il grafico.",
            bg="#f0f0f0", justify="left"
        ).pack(anchor="nw", padx=10, pady=10)
        return
    
    fig, artists, ax2 = result
    
    # Estrai gli artist per il toggle Show Points
    tdh_points_artist = artists.get('tdh')
    eff_points_artist = artists.get('eff')
    pwr_points_artist = artists.get('pwr')

    # --- render in Tk ---
    canvas = FigureCanvasTkAgg(fig, master=right)
    widget = canvas.get_tk_widget()
    widget.pack(fill="both", expand=True, padx=0, pady=0)
    DESIRED_HEIGHT_PX = 1200
    widget.configure(height=DESIRED_HEIGHT_PX)

    widget.update_idletasks()
    try:
        w_px = right.winfo_width() or widget.winfo_width()
        h_px = widget.winfo_height() or DESIRED_HEIGHT_PX
        if w_px > 0 and h_px > 0:
            fig.set_size_inches(w_px / fig.dpi, h_px / fig.dpi, forward=True)
    except Exception:
        pass

    canvas.draw()

    # Toggle visibilità punti curve
    def _toggle_curve_points(*_):
        show = bool(show_curve_points_var.get())
        try:
            if tdh_points_artist is not None:
                tdh_points_artist.set_visible(show)
            if eff_points_artist is not None:
                eff_points_artist.set_visible(show)
            if pwr_points_artist is not None:
                pwr_points_artist.set_visible(show)
            canvas.draw_idle()
            _save_settings()
        except Exception:
            pass

    show_curve_points_var.trace_add("write", _toggle_curve_points)

    right.update_idletasks()
    scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

    # adattamento LIVE larghezza
    def _resize_to_full_width(_e=None):
        try:
            right.update_idletasks()
            w_px = right.winfo_width()
            h_px = widget.winfo_height()
            if w_px > 0 and h_px > 0:
                fig.set_size_inches(w_px / fig.dpi, h_px / fig.dpi, forward=True)
                canvas.draw_idle()
                scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        except Exception:
            pass

    right.bind("<Configure>", lambda e: _resize_to_full_width())
    scroll_canvas.bind("<Configure>", lambda e: (_on_canvas_configure(e), _resize_to_full_width()))