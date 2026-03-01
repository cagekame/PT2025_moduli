# pdf_report.py

import os
import re
import sys
import tempfile
import subprocess
from datetime import date
from tkinter import filedialog, messagebox

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from io import BytesIO

from tdms_reader import (
    read_contract_and_loop_data,
    read_performance_tables_dynamic,
    read_tdms_fields,
)

from ui_format import fmt_if_number, fmt_seq, clean_header_brackets, DASH

# Curve matplotlib (opzionale: se non disponibile si salta silenziosamente)

# --- DB: recupero checked_by / engineering_user direttamente dal DB usando n_collaudo ---
try:
    from db import connect as _db_connect
except Exception:  # pragma: no cover
    _db_connect = None


# -------------------------
# Utility
# -------------------------
_BAD_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
_UNIT_IN_BRACKETS_RE = re.compile(r"^(?P<name>.+?)\s*\[(?P<unit>.+?)\]\s*$")


def _safe(x):
    return "" if x is None else str(x)


def _sanitize_filename(name: str) -> str:
    name = _BAD_CHARS_RE.sub("-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _split_name_unit(colname: str) -> tuple[str, str]:
    """
    "Capacity [m3/h]" -> ("Capacity", "m3/h")
    altrimenti -> (colname, "")
    """
    s = _safe(colname).strip()
    if not s:
        return "", ""
    m = _UNIT_IN_BRACKETS_RE.match(s)
    if not m:
        return s, ""
    return m.group("name").strip(), m.group("unit").strip()


def _open_file_default_app(path: str):
    """Apre un file col visualizzatore predefinito del sistema."""
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
        return
    subprocess.Popen(["xdg-open", path])


def _get_signers_from_db_by_collaudo(n_collaudo: str) -> tuple[str, str]:
    """
    Recupera (checked_by, engineering_user) dalla tabella acquisizioni usando n_collaudo.
    Se il DB non è disponibile o non trova record, ritorna ("", "").
    """
    nc = _safe(n_collaudo).strip()
    if not nc or _db_connect is None:
        return "", ""

    try:
        with _db_connect() as conn:
            row = conn.execute(
                """
                SELECT checked_by, engineering_user
                FROM acquisizioni
                WHERE n_collaudo = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (nc,)
            ).fetchone()
            if not row:
                return "", ""
            return (row[0] or "", row[1] or "")
    except Exception:
        return "", ""


# -------------------------
# Styles / page params
# -------------------------
_PAGE_W, _PAGE_H = landscape(A4)
_MARG_L = 8 * mm
_MARG_R = 8 * mm
_MARG_T = 6 * mm
_MARG_B = 6 * mm

_styles = getSampleStyleSheet()

P = {
    "hdr_logo": ParagraphStyle("hdr_logo", parent=_styles["Normal"], fontName="Helvetica-Bold", fontSize=12, leading=12),
    "hdr_mid": ParagraphStyle("hdr_mid", parent=_styles["Normal"], fontName="Helvetica-Oblique", fontSize=9, leading=9, alignment=1),
    "hdr_right": ParagraphStyle("hdr_right", parent=_styles["Normal"], fontName="Helvetica", fontSize=10, leading=10, alignment=2),
    "sub": ParagraphStyle("sub", parent=_styles["Normal"], fontName="Helvetica", fontSize=8.3, leading=8.3, alignment=1),
    "tiny": ParagraphStyle("tiny", parent=_styles["Normal"], fontName="Helvetica", fontSize=7.2, leading=8),
    "tiny_center": ParagraphStyle("tiny_center", parent=_styles["Normal"], fontName="Helvetica", fontSize=5.5, leading=7, alignment=1),
    "th": ParagraphStyle("th", parent=_styles["Normal"], fontName="Helvetica", fontSize=7, leading=8, alignment=1),
    "foot": ParagraphStyle("foot", parent=_styles["Normal"], fontName="Helvetica", fontSize=8, leading=8, alignment=0),
    "foot_right": ParagraphStyle("foot_right", parent=_styles["Normal"], fontName="Helvetica", fontSize=8, leading=8, alignment=2),
}


# -------------------------
# Mini builder tabelle KV
# -------------------------
def _kv_table(kv_pairs, col_widths, font_size=7.2, hpad=2, vpad=1.5):
    """
    kv_pairs: lista (label, value)
    Applica fmt_if_number ai value per avere numeri puliti e DASH per vuoti.
    """
    data = []
    for k, v in kv_pairs:
        val = fmt_if_number(v, dash=DASH)
        data.append([
            Paragraph(f"<b>{_safe(k)}</b>", P["tiny"]),
            Paragraph(_safe(val), P["tiny"]),
        ])

    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEFTPADDING", (0, 0), (-1, -1), hpad),
        ("RIGHTPADDING", (0, 0), (-1, -1), hpad),
        ("TOPPADDING", (0, 0), (-1, -1), vpad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), vpad),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# -------------------------
# PDF core
# -------------------------
def generate_pdf_report_like_standard(
    *,
    pdf_path: str,
    values_tuple,
    meta_dict: dict,
    change_date: str,
    username: str,
    note_collaudo: str,
    note_ingegneria: str,
    acquisizione_id: int = None,
):
    """
    Replica layout standard + riempie campi da TDMS via tdms_reader.
    """
    v = list(values_tuple) if values_tuple else [""] * 10
    while len(v) < 10:
        v.append("")

    job        = _safe(v[0]).strip()
    n_collaudo = _safe(v[1]).strip()
    matricola  = _safe(v[2]).strip()
    tipo_pompa = _safe(v[3]).strip()
    data_file  = _safe(v[4]).strip()

    tdms_path = _safe(meta_dict.get("_FilePath", "")).strip()
    
    # Leggi unit_system dal DB
    try:
        from db import get_unit_system as _get_unit_system
        unit_system = _get_unit_system(acquisizione_id) if acquisizione_id else "Metric"
    except Exception:
        unit_system = "Metric"

    # TDMS read
    contract = read_contract_and_loop_data(tdms_path) if tdms_path else {}
    perf = read_performance_tables_dynamic(tdms_path, test_index=0) if tdms_path else {"Recorded": {}, "Calc": {}, "Converted": {}}
    
    # Helper per convertire valori individuali dal contract
    def get_contract_value(key_pattern: str, param_type: str = None):
        """Cerca la chiave nel contract e converte il valore se necessario."""
        value = None
        # Cerca con diverse varianti della chiave (case-insensitive)
        for k in contract.keys():
            if key_pattern.lower() in k.lower():
                value = contract[k]
                break
        
        if not value or value == "":
            return ""
        
        # Converti se necessario
        if unit_system != "Metric" and param_type:
            try:
                import unit_converter as uc
                return uc.convert_value(value, param_type, "Metric", unit_system)
            except:
                return value
        return value
    
    # Applica conversioni se unit_system != Metric (solo per tabelle)
    if unit_system != "Metric":
        try:
            import unit_converter as uc
            # Converti tabelle Calc e Converted
            calc_cols, calc_rows = perf.get("Calc", {}).get("columns", []), perf.get("Calc", {}).get("rows", [])
            conv_cols, conv_rows = perf.get("Converted", {}).get("columns", []), perf.get("Converted", {}).get("rows", [])
            calc_cols, calc_rows = uc.convert_performance_table(calc_cols, calc_rows, "Metric", unit_system)
            conv_cols, conv_rows = uc.convert_performance_table(conv_cols, conv_rows, "Metric", unit_system)
            perf["Calc"] = {"columns": calc_cols, "rows": calc_rows}
            perf["Converted"] = {"columns": conv_cols, "rows": conv_rows}
        except Exception:
            pass  # se conversione fallisce, usa dati originali

    # Numero certificato preferibilmente da TDMS
    tdms_fields = read_tdms_fields(tdms_path) if tdms_path else {}
    cert_num = tdms_fields.get("n_collaudo", "") or n_collaudo or DASH

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=landscape(A4),
        leftMargin=_MARG_L,
        rightMargin=_MARG_R,
        topMargin=_MARG_T,
        bottomMargin=_MARG_B,
        title=f"{cert_num} - {job}",
        author=_safe(username),
    )

    story = []

    # -------------------------
    # HEADER (3 colonne)
    # -------------------------
    system_id = contract.get("FSG ORDER", "") or f"{job}-{matricola}"
    unit_label = "SI (Metric)" if unit_system == "Metric" else "U.S. Customary"
    left_cell = Paragraph("FLOWSERVE", P["hdr_logo"])
    center_cell = Paragraph(f"ENGINEERING USE ONLY&nbsp;&nbsp;&nbsp;&nbsp;U.M. System : {unit_label}", P["hdr_mid"])
    right_cell = Paragraph(
        f"<b>Test Certificate num.</b>&nbsp;&nbsp;{_safe(cert_num)}<br/>"
        f"<b>{_safe(system_id)}</b>",
        P["hdr_right"]
    )
    header = Table(
        [[left_cell, center_cell, right_cell]],
        colWidths=[50*mm, 160*mm, (_PAGE_W - 2*_MARG_L - 210*mm)]
    )
    header.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.9, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(header)

    # Riga grigia: Contractual Data | System ID | Loop Details
    sub = Table(
        [[
            Paragraph("<i>Rated Point</i>", P["sub"]),
            Paragraph("<i>Contractual Data</i>", P["sub"]),
            Paragraph("<i>Loop Details</i>", P["sub"])
        ]],
        colWidths=[70*mm, (_PAGE_W - 2*_MARG_L - 140*mm), 70*mm]
    )
    sub.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.9, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#efefef")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sub)

    # -------------------------
    # BLOCCO SUPERIORE 3 COLONNE
    # -------------------------
    # Etichette dinamiche basate su unit_system
    try:
        import unit_converter as uc
        flow_unit = uc.get_unit_label('flow', unit_system)
        head_unit = uc.get_unit_label('head', unit_system)
        power_unit = uc.get_unit_label('power', unit_system)
        temp_unit = uc.get_unit_label('temp', unit_system)
        npsh_unit = uc.get_unit_label('npsh', unit_system)
    except:
        flow_unit, head_unit, power_unit, temp_unit, npsh_unit = "m³/h", "m", "kW", "°C", "m"
    
    contractual_kv = [
        (f"Capacity [{flow_unit}]",  get_contract_value("capacity", "flow")),
        (f"TDH [{head_unit}]",       get_contract_value("tdh", "head")),
        ("Efficiency",               get_contract_value("efficiency")),
        (f"ABS_Power [{power_unit}]", get_contract_value("abs_power", "power") or get_contract_value("power", "power")),
        ("Speed [rpm]",              get_contract_value("speed")),
        ("SG",                       get_contract_value("sg contract")),
        (f"Temperature [{temp_unit}]", get_contract_value("temperature", "temp")),
        ("Viscosity [cP]",           get_contract_value("viscosity")),
        (f"NPSH [{npsh_unit}]",      get_contract_value("npsh", "npsh")),
        ("Liquid",                   get_contract_value("liquid")),
    ]

    order_kv = [
        ("FSG ORDER",            contract.get("FSG ORDER", job)),
        ("CUSTOMER",             contract.get("Customer", "")),
        ("P.O.",                 contract.get("Purchaser Order", "")),
        ("End User",             contract.get("End User", "")),
        ("Item",                 contract.get("Item", "")),
        ("Pump",                 contract.get("Pump", "") or tipo_pompa),
        ("S. N.",                contract.get("Serial Number_Elenco", "") or matricola),
        ("Imp. Draw.",           contract.get("Impeller Drawing", "")),
        ("Imp. Mat.",            contract.get("Impeller Material", "")),
        ("Imp Dia [mm]",         contract.get("Diam Nominal", "")),
        ("Specs",                contract.get("Applic. Specs.", "")),
    ]

    loop_kv = [
        ("Test performed with :", ""),
        ("CALIBRATED MOTOR (num.)", ""),
        ("FLOWMETER", ""),
        ("Suction [Inch]",       contract.get("Suction [Inch]", "")),
        ("Discharge [Inch]",     contract.get("Discharge [Inch]", "")),
        ("Wattmeter Const.",     contract.get("Wattmeter Const.", "")),
        ("AtmPress [m]",         contract.get("AtmPress [m]", "")),
        ("KNPSH [m]",            contract.get("KNPSH [m]", "")),
        ("WaterTemp [°C]",       contract.get("WaterTemp [°C]", "")),
        ("Kventuri",             contract.get("KVenturi", "")),
        ("PVap",                 ""),
    ]

    t_contractual = _kv_table(contractual_kv, col_widths=[38*mm, 25*mm])

    mid_w = (_PAGE_W - 2*_MARG_L - 140*mm)
    label_w = 30*mm
    value_w = max(10*mm, mid_w - label_w)
    t_order = _kv_table(order_kv, col_widths=[label_w, value_w])

    t_loop = _kv_table(loop_kv, col_widths=[45*mm, 22*mm])

    top3 = Table(
        [[t_contractual, t_order, t_loop]],
        colWidths=[70*mm, (_PAGE_W - 2*_MARG_L - 140*mm), 70*mm]
    )
    top3.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.9, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(top3)

    # -------------------------
    # TABELLONE DATI (colonne+righe TDMS) - con paginazione automatica
    # -------------------------
    rec = perf.get("Recorded", {}) or {}
    cal = perf.get("Calc", {}) or {}
    con = perf.get("Converted", {}) or {}

    rec_cols = rec.get("columns", []) or []
    cal_cols = cal.get("columns", []) or []
    con_cols = con.get("columns", []) or []

    rec_rows = rec.get("rows", []) or []
    cal_rows = cal.get("rows", []) or []
    con_rows = con.get("rows", []) or []

    all_cols = list(rec_cols) + list(cal_cols) + list(con_cols)

    col_names = []
    col_units = []
    for c in all_cols:
        name, unit = _split_name_unit(c)
        col_names.append(clean_header_brackets(name))
        col_units.append(unit)

    n_rows = max(len(rec_rows), len(cal_rows), len(con_rows), 1)

    def _row_at(rows, i, width):
        if i < len(rows):
            r = list(rows[i])
        else:
            r = [""] * width
        r = r[:width] + [""] * max(0, width - len(r))
        return fmt_seq(r, dash=DASH)

    # Righe intestazione (nome + unità) + tutte le righe dati
    hdr_row_names = [Paragraph(f"<b>{_safe(x)}</b>", P["tiny_center"]) for x in col_names]
    hdr_row_units = [Paragraph(_safe(u), P["tiny_center"]) for u in col_units]

    all_data_rows = []
    for i in range(n_rows):
        row = []
        row.extend(_row_at(rec_rows, i, len(rec_cols)))
        row.extend(_row_at(cal_rows, i, len(cal_cols)))
        row.extend(_row_at(con_rows, i, len(con_cols)))
        all_data_rows.append(row)

    # -------------------------
    # LARGHEZZE DINAMICHE tabellone + header 3 sezioni
    # -------------------------
    available_w = _PAGE_W - 2*_MARG_L

    n_rec = len(rec_cols)
    n_cal = len(cal_cols)
    n_con = len(con_cols)

    total_cols = n_rec + n_cal + n_con
    if total_cols <= 0:
        total_cols = 1
        n_rec = 1
        n_cal = 0
        n_con = 0

    base_w = available_w / total_cols
    col_widths = ([base_w] * n_rec) + ([base_w] * n_cal) + ([base_w] * n_con)

    w_rec = max(base_w * n_rec, 8 * mm)
    w_cal = max(base_w * n_cal, 8 * mm)
    w_con = max(base_w * n_con, 8 * mm)

    s = w_rec + w_cal + w_con
    scale = (available_w / s) if s > 0 else 1.0
    w_rec *= scale
    w_cal *= scale
    w_con *= scale

    # -------------------------
    # Calcolo righe per pagina
    # Pagina A4 landscape = 210mm di altezza.
    # Spazio fisso (header+sub+top3+spacer+big_hdr+2 righe intestazione+footer+bottom):
    #   ~110mm. Rimangono ~100mm per le righe dati.
    # Ogni riga dati: fontsize 6.7pt + padding 2*1.2pt = 9.1pt ≈ 3.21mm
    # Con margine di sicurezza usiamo MAX_ROWS_PER_PAGE = 22
    # -------------------------
    MAX_ROWS_PER_PAGE = 22

    chunks = []
    for start in range(0, max(len(all_data_rows), 1), MAX_ROWS_PER_PAGE):
        chunks.append(all_data_rows[start:start + MAX_ROWS_PER_PAGE])
    total_pages = len(chunks)

    test_date  = data_file or date.today().strftime("%d/%m/%Y")
    issue_date = date.today().strftime("%d/%m/%Y")

    from reportlab.platypus import PageBreak

    for page_idx, chunk in enumerate(chunks):
        page_num = page_idx + 1

        # Dalla pagina 2 in poi: ripeti header, sub e top3
        if page_idx > 0:
            story.append(PageBreak())
            story.append(header)
            story.append(sub)
            story.append(top3)

        # Header tabella sezioni
        story.append(Spacer(1, 3))
        big_hdr = Table(
            [[
                Paragraph("<b><i>Recorded Data</i></b>", P["th"]),
                Paragraph("<b><i>Calculated Values</i></b>", P["th"]),
                Paragraph("<b><i>Values Converted to contractual RPM &amp; S.G.</i></b>", P["th"]),
            ]],
            colWidths=[w_rec, w_cal, w_con]
        )
        big_hdr.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.9, colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#efefef")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(big_hdr)

        # Tabella dati (2 righe intestazione + righe del chunk)
        data = [hdr_row_names, hdr_row_units] + chunk

        big_table = Table(data, colWidths=col_widths)
        big_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#f5f5f5")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.7),
            ("TOPPADDING", (0, 0), (-1, -1), 1.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),
        ]))
        story.append(big_table)

        # Footer con numero pagina corretto
        story.append(Spacer(1, 4))
        footer = Table(
            [[
                Paragraph(f"<b>Test Date :</b>&nbsp;{_safe(test_date)}", P["foot"]),
                Paragraph(f"<b>Date of Issue :</b>&nbsp;{_safe(issue_date)}", P["foot"]),
                Paragraph(f"<b>Page</b>&nbsp;{page_num} of {total_pages}", P["foot_right"]),
            ]],
            colWidths=[120*mm, 120*mm, (_PAGE_W - 2*_MARG_L - 240*mm)]
        )
        footer.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.9, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(footer)

    # -------------------------
    # BLOCCO FINALE
    # Riga 1 (altezza fissa): Brg.Temp | Operator | Engineering | Quality Control
    # Riga 2 (espandibile):   Notes (intestazione + contenuto a tutta larghezza)
    # -------------------------
    combined_notes = []
    if (note_collaudo or "").strip():
        combined_notes.append("NOTE COLLAUDO:\n" + note_collaudo.strip())
    if (note_ingegneria or "").strip():
        combined_notes.append("NOTE INGEGNERIA:\n" + note_ingegneria.strip())
    notes_final = "\n\n".join(combined_notes).strip()

    checked_by_db, engineering_user_db = _get_signers_from_db_by_collaudo(cert_num)

    op_val  = _safe(checked_by_db).strip()      or DASH
    eng_val = _safe(engineering_user_db).strip() or DASH
    qc_val  = DASH

    total_w = _PAGE_W - 2 * _MARG_L
    brg_value = "DE [°C]  __   &nbsp;&nbsp;NDE [°C]  __   &nbsp;&nbsp;AmbTemp [°C]  __"

    # --- Riga Brg. Temperature ---
    brg_label_w = 38 * mm
    brg_value_w = total_w - brg_label_w
    brg_row = Table(
        [[
            Paragraph("<b>Brg. Temperature</b>", P["tiny"]),
            Paragraph(brg_value, P["tiny"]),
        ]],
        colWidths=[brg_label_w, brg_value_w],
    )
    brg_row.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.9, colors.black),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(brg_row)

    # --- Riga firme: Operator | Engineering | Quality Control ---
    col_w = total_w / 6  # 6 celle: 3 label + 3 valore
    signers_row = Table(
        [[
            Paragraph("<b>Operator :</b>", P["tiny"]),
            Paragraph(op_val, P["tiny"]),
            Paragraph("<b>Engineering :</b>", P["tiny"]),
            Paragraph(eng_val, P["tiny"]),
            Paragraph("<b>Quality Control :</b>", P["tiny"]),
            Paragraph(qc_val, P["tiny"]),
        ]],
        colWidths=[col_w] * 6,
    )
    signers_row.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.9, colors.black),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(signers_row)

    # --- Riga notes (si espande) ---
    notes_html = _safe(notes_final).replace("\n", "<br/>") if notes_final else "&nbsp;"
    notes_row = Table(
        [
            [Paragraph("<b>Notes</b>", P["tiny"])],
            [Paragraph(notes_html, P["tiny"])],
        ],
        colWidths=[total_w],
    )
    notes_row.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.9, colors.black),
        ("BACKGROUND",    (0, 0), (0, 0),   colors.HexColor("#f5f5f5")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(notes_row)

    # -------------------------
    # PAGINE CURVE (due pagine: TDH+Eff, Power)
    # -------------------------
    if tdms_path:
        try:
            from reportlab.platypus import PageBreak
            from curve_view import build_tdh_eff_figure, build_power_figure

            # Leggi impostazioni salvate + unit_system
            try:
                from db import curve_settings_get as _curve_settings_get, get_unit_system as _get_unit_system
                cs = _curve_settings_get(acquisizione_id) if acquisizione_id is not None else None
                if cs is None:
                    cs = {"show_points": True, "eff_min": 0.0, "eff_max": 100.0}
                unit_system = _get_unit_system(acquisizione_id) if acquisizione_id is not None else "Metric"
            except Exception:
                cs = {"show_points": True, "eff_min": 0.0, "eff_max": 100.0}
                unit_system = "Metric"

            def add_curve_page(curve_fig, title="Curve"):
                if curve_fig is None:
                    return
                buf = BytesIO()
                curve_fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
                buf.seek(0)

                avail_w = _PAGE_W - 2 * _MARG_L
                avail_h = _PAGE_H - _MARG_T - _MARG_B - 20 * mm

                img_w_pt = curve_fig.get_figwidth() * 72
                img_h_pt = curve_fig.get_figheight() * 72

                scale = min(avail_w / img_w_pt, avail_h / img_h_pt)
                draw_w = img_w_pt * scale
                draw_h = img_h_pt * scale

                story.append(PageBreak())

                # Header con unit_system dinamico
                unit_label = "SI (Metric)" if unit_system == "Metric" else "U.S. Customary"
                curve_hdr = Table(
                    [[
                        Paragraph("FLOWSERVE", P["hdr_logo"]),
                        Paragraph(f"ENGINEERING USE ONLY&nbsp;&nbsp;&nbsp;&nbsp;U.M. System : {unit_label}", P["hdr_mid"]),
                        Paragraph(
                            f"<b>Test Certificate num.</b>&nbsp;&nbsp;{_safe(cert_num)}<br/>"
                            f"<b>{_safe(system_id)}</b>",
                            P["hdr_right"]
                        ),
                    ]],
                    colWidths=[50*mm, 160*mm, (_PAGE_W - 2*_MARG_L - 210*mm)]
                )
                curve_hdr.setStyle(TableStyle([
                    ("GRID",          (0, 0), (-1, -1), 0.9, colors.black),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
                    ("TOPPADDING",    (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(curve_hdr)
                story.append(Spacer(1, 4))

                # Immagine con bordo
                img = Image(buf, width=draw_w, height=draw_h)
                img_frame = Table([[img]], colWidths=[draw_w])
                img_frame.setStyle(TableStyle([
                    ("BOX",           (0, 0), (-1, -1), 0.9, colors.black),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                    ("TOPPADDING",    (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                img_frame.hAlign = "CENTER"
                story.append(img_frame)

                try:
                    import matplotlib
                    matplotlib.pyplot.close(curve_fig)
                except Exception:
                    pass

            # Pagina 1: TDH + Efficiency
            tdh_fig = build_tdh_eff_figure(
                tdms_path,
                show_points=cs["show_points"],
                eff_min=cs["eff_min"],
                eff_max=cs["eff_max"],
                unit_system=unit_system,
            )
            add_curve_page(tdh_fig, "TDH + Efficiency")

            # Pagina 2: Power
            pwr_fig = build_power_figure(
                tdms_path,
                show_points=cs["show_points"],
                unit_system=unit_system
            )
            add_curve_page(pwr_fig, "Absorbed Power")

        except Exception:
            pass  # se le curve falliscono, il PDF continua senza

    doc.build(story)


# -------------------------
# NEW: Preview helper (TEMP + open)
# -------------------------
def preview_pdf_report(
    parent,
    *,
    meta_dict: dict,
    values_tuple,
    change_date: str,
    username: str,
    note_collaudatore_get,
    note_ingegneria_get,
):
    """
    ✅ PREVIEW:
    - Genera un PDF temporaneo in %TEMP%
    - Lo apre nel viewer di default
    - L'utente può salvarlo dal viewer (Salva con nome...)
    """
    tdms_path      = _safe(meta_dict.get("_FilePath", "")).strip()
    acquisizione_id = meta_dict.get("id")

    job = _safe(values_tuple[0]).strip() if values_tuple and len(values_tuple) > 0 else "JOB"
    n_collaudo = _safe(values_tuple[1]).strip() if values_tuple and len(values_tuple) > 1 else "COLLAUDO"

    fname = _sanitize_filename(f"{n_collaudo} - {job}.pdf")
    pdf_path = os.path.join(tempfile.gettempdir(), fname)

    try:
        note_coll = note_collaudatore_get(tdms_path) or ""
        note_ing  = note_ingegneria_get(tdms_path) or ""

        generate_pdf_report_like_standard(
            pdf_path=pdf_path,
            values_tuple=values_tuple,
            meta_dict=meta_dict,
            change_date=change_date,
            username=username,
            note_collaudo=note_coll,
            note_ingegneria=note_ing,
            acquisizione_id=acquisizione_id,
        )

        _open_file_default_app(pdf_path)
        return pdf_path

    except Exception as e:
        messagebox.showerror("Anteprima PDF", f"Impossibile generare/aprire il PDF:\n{e}")
        return None


# -------------------------
# (Vecchio) Salva con nome... - lo lasciamo, può tornare utile
# -------------------------
def generate_and_save_pdf_interactive(
    parent,
    *,
    meta_dict: dict,
    values_tuple,
    change_date: str,
    username: str,
    note_collaudatore_get,
    note_ingegneria_get,
):
    """
    Apre Salva con nome... e genera PDF:
      - A4 ORIZZONTALE
      - dati presi dal TDMS via tdms_reader
      - formattazione numeri/placeholder con ui_format
      - nome suggerito "N° COLLAUDO - JOB.pdf"
    """
    job = _safe(values_tuple[0]).strip() if values_tuple and len(values_tuple) > 0 else "JOB"
    n_collaudo = _safe(values_tuple[1]).strip() if values_tuple and len(values_tuple) > 1 else "COLLAUDO"
    suggested = _sanitize_filename(f"{n_collaudo} - {job}.pdf")

    pdf_path = filedialog.asksaveasfilename(
        parent=parent,
        title="Salva certificato PDF",
        defaultextension=".pdf",
        initialfile=suggested,
        filetypes=[("PDF", "*.pdf")],
    )
    if not pdf_path:
        return None

    try:
        tdms_path       = _safe(meta_dict.get("_FilePath", ""))
        acquisizione_id = meta_dict.get("id")

        note_coll = note_collaudatore_get(tdms_path) or ""
        note_ing  = note_ingegneria_get(tdms_path) or ""

        generate_pdf_report_like_standard(
            pdf_path=pdf_path,
            values_tuple=values_tuple,
            meta_dict=meta_dict,
            change_date=change_date,
            username=username,
            note_collaudo=note_coll,
            note_ingegneria=note_ing,
            acquisizione_id=acquisizione_id,
        )
        messagebox.showinfo("PDF creato", f"PDF generato correttamente:\n{pdf_path}")
        return pdf_path
    except Exception as e:
        messagebox.showerror("Errore PDF", f"Impossibile generare il PDF:\n{e}")
        return None
