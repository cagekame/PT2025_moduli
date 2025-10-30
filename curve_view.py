# curve_view.py
import math
import tkinter as tk
from tkinter import ttk

# matplotlib per il grafico
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPL_OK = True
except Exception:
    MPL_OK = False

# dati centralizzati dal reader (points: (TDH, Flow))
from tdms_reader import read_curve_data


def _kv(parent, k, v):
    row = tk.Frame(parent, bg="#f0f0f0")
    row.pack(fill="x", padx=8, pady=2)
    tk.Label(row, text=k, width=18, anchor="w", bg="#f0f0f0",
             font=("Segoe UI", 10, "bold")).pack(side="left")
    tk.Label(row, text=(v if v else "—"), anchor="w", bg="#f0f0f0",
             font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)


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


def render_curve_tab(parent, tdms_path: str):
    """
    parent: frame della tab 'Curva' creata nel modulo certificato.
    tdms_path: percorso TDMS (stringa, può essere vuota).
    """
    parent.grid_columnconfigure(0, weight=0)  # sinistra fissa
    parent.grid_columnconfigure(1, weight=1)  # destra elastica
    parent.grid_rowconfigure(0, weight=1)

    left = tk.LabelFrame(parent, text="Contractual Data", bg="#f0f0f0")
    left.grid(row=0, column=0, sticky="nsw", padx=(10, 8), pady=10)

    right = tk.LabelFrame(parent, text="Curva (x = Capacity [m³/h], y = TDH [m])", bg="#f0f0f0")
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 10), pady=10)
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(0, weight=1)

    # meta + punti (points: (TDH, Flow))
    meta, points = read_curve_data(tdms_path, test_index=0)

    _kv(left, "Capacity [m³/h]", meta.get("capacity", "—"))
    _kv(left, "TDH [m]",         meta.get("tdh", "—"))
    _kv(left, "Efficiency [%]",  meta.get("eff", "—"))
    _kv(left, "ABS_Power [kW]",  meta.get("abs_pow", "—"))
    _kv(left, "Speed [rpm]",     meta.get("speed", "—"))
    _kv(left, "SG",              meta.get("sg", "—"))
    _kv(left, "Temperature [°C]", meta.get("temp", "—"))
    _kv(left, "Viscosity [cP]",  meta.get("visc", "—"))
    _kv(left, "NPSH [m]",        meta.get("npsh", "—"))
    _kv(left, "Liquid",          meta.get("liquid", "—"))

    if not MPL_OK:
        tk.Label(
            right,
            text="Matplotlib non disponibile.\nInstalla 'matplotlib' per vedere il grafico.",
            bg="#f0f0f0", justify="left"
        ).grid(row=0, column=0, sticky="nw", padx=10, pady=10)
        return

    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)

    # Punti: inverti (Flow, TDH) per asse X/Y
    xs_raw, ys_raw = [], []
    if points:
        xs_raw = [p[1] for p in points]  # Flow/Capacity (X, >0)
        ys_raw = [p[0] for p in points]  # TDH (Y, >=0)
        ax.scatter(xs_raw, ys_raw, s=30, label="Converted points")

    # Ordina/deduplica per trendline
    xs, ys = _dedupe_and_sort_xy(xs_raw, ys_raw)

    # Trendline polinomiale cubica
    a, b, c, d, r2 = _poly3_trendline(xs, ys)
    if a is not None and xs:
        xmin, xmax = min(xs), max(xs)
        num = max(50, min(400, 10 * len(xs)))
        x_curve = [xmin + (xmax - xmin) * i / (num - 1) for i in range(num)]
        y_curve = [a*x**3 + b*x**2 + c*x + d for x in x_curve]
        ax.plot(x_curve, y_curve, linewidth=1.8,
                label=f"Trendline (y = {a:.3g} x³ + {b:.3g} x² + {c:.3g} x + {d:.3g}, R² = {r2:.3f})")

    # Punto contrattuale: x=Capacity, y=TDH
    try:
        cx = float(str(meta.get("capacity", "")).replace(",", "."))
        cy = float(str(meta.get("tdh", "")).replace(",", "."))
        if math.isfinite(cx) and math.isfinite(cy):
            ax.scatter([cx], [cy], marker="*", s=120, label="Contractual", zorder=3)
    except Exception:
        pass

    ax.set_xlabel("Capacity [m³/h]")
    ax.set_ylabel("TDH [m]")

    # === Limiti degli assi richiesti ===
    # Y (TDH) parte sempre da 0
    ax.set_ylim(bottom=0)
    # X (Flow/Capacity) mostra solo x >= 0
    ax.set_xlim(left=0)

    ax.grid(True, linestyle=":", linewidth=0.8)
    ax.legend(loc="best")

    canvas = FigureCanvasTkAgg(fig, master=right)
    canvas.draw()
    canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
