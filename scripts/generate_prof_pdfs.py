"""
📄 Generate Prof PDFs
Génère un PDF par professeur avec le détail des leçons et montants en euros.
Peut aussi générer un PDF combiné (tous les profs dans un seul fichier).
"""

import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# --- FX (CHF -> EUR) via ECB SDMX API ---
# Series: EXR.M.CHF.EUR.SP00.E (monthly end-of-period)
# Business rule: factor = 2 - value
# No hardcoded fallback: if the API fails or returns no value, we raise.

import requests
from functools import lru_cache
from datetime import date as _date, datetime as _datetime

ECB_SDMX_URL = "https://data-api.ecb.europa.eu/service/data/EXR/M.CHF.EUR.SP00.E"


def _to_date(d):
    """Accepts date/datetime or ISO string (YYYY-MM or YYYY-MM-DD) and returns a date."""
    if d is None:
        return None
    if isinstance(d, _date) and not isinstance(d, _datetime):
        return d
    if isinstance(d, _datetime):
        return d.date()
    if isinstance(d, str):
        s = d.strip()
        if len(s) == 7:
            s = s + "-01"
        return _datetime.strptime(s, "%Y-%m-%d").date()
    raise TypeError(f"Unsupported date type: {type(d)}")


def _month_start_end(y: int, m: int) -> tuple[str, str]:
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-31"


@lru_cache(maxsize=36)
def fetch_chf_eur_monthly_value(y: int, m: int) -> float:
    start, end = _month_start_end(y, m)
    headers = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"}

    r = requests.get(
        ECB_SDMX_URL,
        params={"startPeriod": start, "endPeriod": end},
        headers=headers,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    series = data["dataSets"][0]["series"]
    first_key = next(iter(series.keys()))
    obs = series[first_key].get("observations", {})
    if not obs:
        raise RuntimeError(f"Aucune observation FX trouvée pour {y:04d}-{m:02d} (EXR.M.CHF.EUR.SP00.E).")

    last_idx = max(int(k) for k in obs.keys())
    value = obs[str(last_idx)][0]
    return float(value)


def require_chf_to_eur_factor(extraction_end_date):
    """
    Returns (factor, month_label, raw_value) using month of extraction_end_date.
    Raises RuntimeError if date missing or API returns no value.
    """
    d = _to_date(extraction_end_date)
    if d is None:
        raise RuntimeError(
            "Aucune valeur API trouvée de conversion : extraction_end_date manquante. "
            "Impossible de calculer le taux CHF→EUR."
        )
    raw = fetch_chf_eur_monthly_value(d.year, d.month)
    factor = round(2.0 - raw, 6)
    month_label = f"{d.year:04d}-{d.month:02d}"
    return factor, month_label, raw


HEADER_BG = colors.HexColor("#1F3A67")
ROW_ALT = colors.HexColor("#f5f5f5")
BORDER_COLOR = colors.HexColor("#bdbdbd")
ACCENT = colors.HexColor("#1F3A67")


def _build_styles():
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontSize=20, spaceAfter=4, textColor=ACCENT,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=11, spaceAfter=4, textColor=colors.HexColor("#424242"),
    )
    header_style = ParagraphStyle(
        "TableHeader", parent=styles["Normal"],
        fontSize=9, textColor=colors.white, alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"],
        fontSize=8.5, alignment=TA_CENTER,
    )
    cell_left = ParagraphStyle(
        "CellLeft", parent=styles["Normal"],
        fontSize=8.5, alignment=TA_LEFT,
    )
    cell_right = ParagraphStyle(
        "CellRight", parent=styles["Normal"],
        fontSize=8.5, alignment=TA_RIGHT,
    )
    total_style = ParagraphStyle(
        "TotalCell", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica-Bold", alignment=TA_RIGHT,
        textColor=ACCENT,
    )
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#9e9e9e"),
    )
    
    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "header": header_style,
        "cell": cell_style,
        "cell_left": cell_left,
        "cell_right": cell_right,
        "total": total_style,
        "footer": footer_style,
    }


def _build_teacher_story(teacher_name, data, mois_label, logo_path, styles, chf_to_eur_factor, fx_month_label, fx_raw_value):
    """Builds the reportlab story (list of flowables) for one teacher."""
    story = []

    # Logo + Title header
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=35*mm, height=35*mm)
            logo.hAlign = "LEFT"
            
            header_data = [[
                logo,
                Paragraph("Professor+<br/><font size=10>Détail de paie</font>", styles["title"])
            ]]
            header_table = Table(header_data, colWidths=[40*mm, 120*mm])
            header_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(header_table)
        except Exception:
            story.append(Paragraph("Professor+", styles["title"]))
    else:
        story.append(Paragraph("Professor+", styles["title"]))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(f"Période : {mois_label}", styles["subtitle"]))
    story.append(Spacer(1, 6*mm))

    # Teacher info box
    total_eur = data["eur"] + data["chf_as_eur"]
    total_hours = data.get("total_hours", 0)

    info_data = [
        [Paragraph("<b>Professeur</b>", styles["cell_left"]),
         Paragraph(teacher_name, styles["cell_left"])],
        [Paragraph("<b>Nombre de leçons</b>", styles["cell_left"]),
         Paragraph(str(data["nb_lessons"]), styles["cell_left"])],
        [Paragraph("<b>Heures totales</b>", styles["cell_left"]),
         Paragraph(f"{total_hours:.1f}h", styles["cell_left"])],
        [Paragraph("<b>Familles EUR</b>", styles["cell_left"]),
         Paragraph(f"{data['eur']:.2f} €", styles["cell_left"])],
        [Paragraph("<b>Familles CHF→EUR</b>", styles["cell_left"]),
         Paragraph(f"{data['chf_as_eur']:.2f} €", styles["cell_left"])],
        [Paragraph("<b>TOTAL À PAYER</b>", styles["cell_left"]),
         Paragraph(f"<b>{total_eur:.2f} €</b>",
                   ParagraphStyle("TotalInline", parent=styles["cell_left"],
                                  fontSize=11, textColor=ACCENT, fontName="Helvetica-Bold"))],
    ]
    info_table = Table(info_data, colWidths=[55*mm, 80*mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8eaf6")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER_COLOR),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8*mm))

    # Lessons table
    headers = ["Date", "Élève", "Durée", "Taux", "Devise", "Montant €"]
    header_row = [Paragraph(h, styles["header"]) for h in headers]

    sorted_details = sorted(data["details"], key=lambda x: x["date"])
    rows = [header_row]
    for d in sorted_details:
        rows.append([
            Paragraph(d["date"], styles["cell"]),
            Paragraph(d["student"], styles["cell_left"]),
            Paragraph(f"{d['duration_min']} min", styles["cell"]),
            Paragraph(f"{d['rate']}", styles["cell"]),
            Paragraph(d["currency"], styles["cell"]),
            Paragraph(f"{d['amount_eur']:.2f} €", styles["cell_right"]),
        ])

    # Total row
    rows.append([
        Paragraph("", styles["cell"]),
        Paragraph("", styles["cell"]),
        Paragraph("", styles["cell"]),
        Paragraph("", styles["cell"]),
        Paragraph("<b>TOTAL</b>", ParagraphStyle("t", parent=styles["cell"], fontName="Helvetica-Bold")),
        Paragraph(f"<b>{total_eur:.2f} €</b>", styles["total"]),
    ])

    col_widths = [22*mm, 52*mm, 18*mm, 18*mm, 25*mm, 25*mm]
    lesson_table = Table(rows, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8eaf6")),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, HEADER_BG),
    ]
    for i in range(1, len(rows) - 1):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))

    lesson_table.setStyle(TableStyle(style_cmds))
    story.append(lesson_table)

    # Footer
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph(
        f"Taux de conversion (mois {fx_month_label}) : 1 CHF = {chf_to_eur_factor} EUR  (règle: 2 - {fx_raw_value})  |  ★ = tarif spécial",
        styles["footer"]
    ))
    story.append(Paragraph("Généré automatiquement — Professor+", styles["footer"]))

    return story


def generate_single_pdf(teacher_name, data, mois_label, output_path, logo_path=None, extraction_end_date=None):
    """Génère un PDF pour un seul prof."""
    styles = _build_styles()
    
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    
    chf_to_eur_factor, fx_month_label, fx_raw_value = require_chf_to_eur_factor(extraction_end_date)
    story = _build_teacher_story(teacher_name, data, mois_label, logo_path, styles, chf_to_eur_factor, fx_month_label, fx_raw_value)
    doc.build(story)
    return output_path


def generate_single_pdf_to_bytes(teacher_name, data, mois_label, logo_path=None, extraction_end_date=None):
    """Génère un PDF pour un seul prof, retourne les bytes."""
    styles = _build_styles()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    
    chf_to_eur_factor, fx_month_label, fx_raw_value = require_chf_to_eur_factor(extraction_end_date)
    story = _build_teacher_story(teacher_name, data, mois_label, logo_path, styles, chf_to_eur_factor, fx_month_label, fx_raw_value)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_all_pdfs_as_zip(teacher_recaps, mois_label, logo_path=None, exclude_owner="Parisi Lucas", extraction_end_date=None):
    """
    Génère un ZIP contenant un PDF distinct par prof.
    
    Returns:
        bytes: contenu du ZIP
    """
    import zipfile
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for tname in sorted(teacher_recaps.keys()):
            if tname == exclude_owner:
                continue
            data = teacher_recaps[tname]
            if data["nb_lessons"] == 0:
                continue
            
            pdf_bytes = generate_single_pdf_to_bytes(tname, data, mois_label, logo_path, extraction_end_date=extraction_end_date)
            safe_name = tname.replace(" ", "_")
            filename = f"Paie_{safe_name}_{mois_label.replace(' ', '_')}.pdf"
            zf.writestr(filename, pdf_bytes)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def generate_combined_pdf(teacher_recaps, mois_label, output_path, logo_path=None, exclude_owner="Parisi Lucas", extraction_end_date=None):
    """
    Génère un PDF combiné avec tous les profs (un prof par page).
    
    Args:
        teacher_recaps: dict {teacher_name: data}
        mois_label: "Février 2026"
        output_path: chemin du PDF de sortie
        logo_path: chemin du logo
        exclude_owner: nom du propriétaire à exclure
    
    Returns:
        str: chemin du PDF généré
    """
    styles = _build_styles()
    
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    
    chf_to_eur_factor, fx_month_label, fx_raw_value = require_chf_to_eur_factor(extraction_end_date)

    combined_story = []
    first = True
    
    for tname in sorted(teacher_recaps.keys()):
        if tname == exclude_owner:
            continue
        data = teacher_recaps[tname]
        if data["nb_lessons"] == 0:
            continue
        
        if not first:
            combined_story.append(PageBreak())
        first = False
        
        combined_story.extend(
            _build_teacher_story(tname, data, mois_label, logo_path, styles, chf_to_eur_factor, fx_month_label, fx_raw_value)
        )
    
    if combined_story:
        doc.build(combined_story)
        return output_path
    return None


def generate_all_pdfs_to_bytes(teacher_recaps, mois_label, logo_path=None, exclude_owner="Parisi Lucas", extraction_end_date=None):
    """
    Génère un PDF combiné en mémoire (bytes) pour téléchargement Streamlit.
    
    Returns:
        bytes: contenu du PDF
    """
    styles = _build_styles()
    
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    
    chf_to_eur_factor, fx_month_label, fx_raw_value = require_chf_to_eur_factor(extraction_end_date)

    combined_story = []
    first = True
    
    for tname in sorted(teacher_recaps.keys()):
        if tname == exclude_owner:
            continue
        data = teacher_recaps[tname]
        if data["nb_lessons"] == 0:
            continue
        
        if not first:
            combined_story.append(PageBreak())
        first = False
        
        combined_story.extend(
            _build_teacher_story(tname, data, mois_label, logo_path, styles, chf_to_eur_factor, fx_month_label, fx_raw_value)
        )
    
    if combined_story:
        doc.build(combined_story)
        buffer.seek(0)
        return buffer.getvalue()
    return None