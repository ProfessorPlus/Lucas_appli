"""
📄 Generate Prof PDFs - Design Lovable
Reproduit fidèlement le design de la fiche de paie Lovable.
"""

import os
import io
import math
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import requests
from functools import lru_cache
from datetime import date as _date
import calendar as _calendar

# ===========================
# FX
# ===========================
FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
ECB_SDMX_URL = "https://data-api.ecb.europa.eu/service/data/EXR/M.CHF.EUR.SP00.E"
FALLBACK_CHF_EUR = 0.94


@lru_cache(maxsize=36)
def _fetch_chf_eur_rate(target_year=None, target_month=None):
    if target_year and target_month:
        prev_y, prev_m = target_year, target_month
    else:
        today = _date.today()
        prev_y, prev_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    last_day = _calendar.monthrange(prev_y, prev_m)[1]
    sd = f"{prev_y:04d}-{prev_m:02d}-01"
    ed = f"{prev_y:04d}-{prev_m:02d}-{last_day:02d}"
    ml = f"{prev_y:04d}-{prev_m:02d}"
    try:
        r = requests.get(f"{FRANKFURTER_URL}/{sd}..{ed}", params={"base": "CHF", "symbols": "EUR"}, timeout=15)
        r.raise_for_status()
        rates = r.json().get("rates", {})
        if rates:
            vals = [d["EUR"] for d in rates.values() if "EUR" in d]
            if vals:
                return round(sum(vals) / len(vals), 6), f"Moyenne {ml} ({len(vals)}j)"
    except Exception:
        pass
    try:
        hd = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"}
        r = requests.get(ECB_SDMX_URL, params={"startPeriod": sd, "endPeriod": ed}, headers=hd, timeout=10)
        r.raise_for_status()
        d = r.json()
        s = d["dataSets"][0]["series"]
        obs = s[next(iter(s.keys()))].get("observations", {})
        if obs:
            v = float(obs[str(max(int(k) for k in obs.keys()))][0])
            return round(2.0 - v, 6), f"ECB {ml}"
    except Exception:
        pass
    return FALLBACK_CHF_EUR, "Taux de secours"


def require_chf_to_eur_factor(extraction_end_date=None):
    target_year = None
    target_month = None
    if extraction_end_date:
        try:
            if isinstance(extraction_end_date, str):
                from datetime import datetime as _dt
                d = _dt.strptime(extraction_end_date.strip()[:10], "%Y-%m-%d").date()
            elif isinstance(extraction_end_date, _date):
                d = extraction_end_date
            else:
                d = extraction_end_date.date() if hasattr(extraction_end_date, 'date') else None
            if d:
                target_year = d.year
                target_month = d.month
        except Exception:
            pass
    rate, source = _fetch_chf_eur_rate(target_year, target_month)
    return rate, source, rate


# ===========================
# FONTS
# ===========================
def _init_fonts():
    paths = [
        ("Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("SansBd", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for name, path in paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass
    try:
        pdfmetrics.getFont("Sans")
        return "Sans", "SansBd"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


F, FB = _init_fonts()

# ===========================
# COLORS (matching Lovable)
# ===========================
NAVY = colors.HexColor("#1F3A67")
NAVY_DARK = colors.HexColor("#162D52")
GREEN = colors.HexColor("#059669")
CARD_BG = colors.HexColor("#F7F8FA")
CARD_BORDER = colors.HexColor("#E5E7EB")
ROW_ALT = colors.HexColor("#F9FAFB")
ROW_BORDER = colors.HexColor("#E5E7EB")
TXT = colors.HexColor("#1F2937")
TXT_MID = colors.HexColor("#6B7280")
TXT_LIGHT = colors.HexColor("#9CA3AF")
WHITE = colors.white

# ===========================
# LAYOUT
# ===========================
PW, PH = A4  # 595.27 x 841.89
MX = 50  # horizontal margin
MY_TOP = 45
MY_BOT = 35
CW = PW - 2 * MX  # content width ~495


def _rrect(c, x, y, w, h, r=6, fill=None, stroke=None, sw=0.75):
    """Rounded rect helper."""
    p = c.beginPath()
    p.roundRect(x, y, w, h, r)
    if fill:
        c.setFillColor(fill)
    if stroke:
        c.setStrokeColor(stroke)
        c.setLineWidth(sw)
    else:
        c.setStrokeColor(fill or WHITE)
        c.setLineWidth(0)
    c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)


def _circle(c, cx, cy, r, fill):
    """Filled circle."""
    c.setFillColor(fill)
    c.circle(cx, cy, r, fill=1, stroke=0)


# ===========================
# PAGE BUILDER
# ===========================

def _build_page(c, teacher_name, data, mois_label, logo_path, fx_rate, fx_source):
    """Draw one complete teacher recap, spanning multiple pages if needed."""
    
    total_eur_raw = data.get("eur", 0) + data.get("chf_as_eur", 0)
    total_hours = data.get("total_hours", 0)
    nb_lessons = data.get("nb_lessons", 0)
    details = data.get("details", [])
    
    # Utiliser la somme des montants détaillés (déjà arrondis) pour cohérence
    total_eur_from_details = sum(d.get("amount_eur", 0) for d in details)
    total_eur = total_eur_from_details if details else total_eur_raw
    
    sorted_d = sorted(details, key=lambda d: d["date"])
    
    rh = 28  # row height (compact)
    cols = [90, 150, 70, 100, 85]  # Date, Élève, Durée, Taux, Montant
    tw = sum(cols)
    tx0 = MX + (CW - tw) / 2
    
    # Calculate how many rows fit on first page vs continuation pages
    first_page_table_start_y = PH - MY_TOP - 58 - 30 - 62 - 30 - 28 - rh  # after header+cards+section title+table header
    continuation_table_start_y = PH - MY_TOP - 30  # just top margin + small padding
    footer_reserve = 80  # space for total row + footer
    
    rows_first_page = max(1, int((first_page_table_start_y - MY_BOT - footer_reserve) / rh))
    rows_per_cont_page = max(1, int((continuation_table_start_y - MY_BOT - footer_reserve) / rh))
    
    # Determine pages needed
    total_rows = len(sorted_d)
    if total_rows <= rows_first_page:
        pages_needed = 1
    else:
        remaining_after_first = total_rows - rows_first_page
        pages_needed = 1 + math.ceil(remaining_after_first / rows_per_cont_page)
    
    row_idx = 0  # current row index in sorted_d
    tot_min = 0
    tot_amt = 0.0
    
    for page_num in range(pages_needed):
        if page_num > 0:
            c.showPage()
        
        y = PH - MY_TOP
        
        # ─────────────────────────────
        # HEADER (first page only)
        # ─────────────────────────────
        if page_num == 0:
            # Logo
            logo_size = 44
            logo_x = MX
            logo_y = y - logo_size
            if logo_path and os.path.exists(logo_path):
                try:
                    c.drawImage(logo_path, logo_x, logo_y, width=logo_size, height=logo_size, preserveAspectRatio=True, mask='auto')
                except Exception:
                    _circle(c, MX + 22, y - 22, 22, NAVY)
                    c.setFillColor(WHITE)
                    c.setFont(FB, 16)
                    c.drawCentredString(MX + 22, y - 28, "P+")
            else:
                _circle(c, MX + 22, y - 22, 22, NAVY)
                c.setFillColor(WHITE)
                c.setFont(FB, 16)
                c.drawCentredString(MX + 22, y - 28, "P+")
            
            # "Professor+" title
            tx = MX + logo_size + 14
            c.setFillColor(TXT)
            c.setFont(FB, 20)
            c.drawString(tx, y - 18, "Professor+")
            
            # Subtitle
            c.setFillColor(TXT_LIGHT)
            c.setFont(F, 9)
            c.drawString(tx, y - 34, "Soutien scolaire personnalisé")
            
            # Right side: "Détail de paie"
            c.setFillColor(NAVY)
            c.setFont(FB, 24)
            c.drawRightString(PW - MX, y - 16, "Détail de paie")
            
            # "Période : ..."
            c.setFillColor(TXT_MID)
            c.setFont(F, 10)
            c.drawRightString(PW - MX, y - 36, f"Période : {mois_label}")
            
            y -= 58
            
            # Separator line
            c.setStrokeColor(CARD_BORDER)
            c.setLineWidth(0.75)
            c.line(MX, y, PW - MX, y)
            
            y -= 30
            
            # ─────────────────────────────
            # METRIC CARDS
            # ─────────────────────────────
            gap = 10
            card1_w = CW * 0.34
            card4_w = CW * 0.24
            remaining_w = CW - card1_w - card4_w - 3 * gap
            card_sm = remaining_w / 2
            card_h = 62
            
            cards = [
                (card1_w, "PROFESSEUR", teacher_name, TXT, 13),
                (card_sm, "LEÇONS", str(nb_lessons), NAVY, 22),
                (card_sm, "HEURES", f"{total_hours:.1f}h", NAVY, 22),
                (card4_w, "TOTAL", f"{total_eur:,.2f} €", GREEN, 18),
            ]
            
            cx = MX
            for w, label, val, vc, fs in cards:
                _rrect(c, cx, y - card_h, w, card_h, r=8, fill=CARD_BG, stroke=CARD_BORDER)
                c.setFillColor(TXT_LIGHT)
                c.setFont(FB, 7)
                c.drawString(cx + 14, y - 18, label)
                c.setFillColor(vc)
                actual_fs = fs
                if len(val) > 20 and fs > 11:
                    actual_fs = 11
                if label == "PROFESSEUR":
                    max_text_w = w - 28
                    text_w = c.stringWidth(val, FB, actual_fs)
                    if text_w > max_text_w:
                        words = val.split()
                        line1 = ""
                        line2 = ""
                        for word in words:
                            test = (line1 + " " + word).strip()
                            if c.stringWidth(test, FB, actual_fs) <= max_text_w:
                                line1 = test
                            else:
                                line2 = (line2 + " " + word).strip()
                        c.setFont(FB, actual_fs)
                        c.drawString(cx + 14, y - card_h + 28, line1)
                        c.drawString(cx + 14, y - card_h + 12, line2)
                    else:
                        c.setFont(FB, actual_fs)
                        c.drawString(cx + 14, y - card_h + 18, val)
                else:
                    c.setFont(FB, actual_fs)
                    c.drawString(cx + 14, y - card_h + 18, val)
                cx += w + gap
            
            y -= card_h + 30
            
            # ─────────────────────────────
            # SECTION TITLE: "Détail des leçons"
            # ─────────────────────────────
            c.setFillColor(NAVY)
            c.setFont(FB, 14)
            c.drawString(MX, y, "Détail des leçons")
            title_w = c.stringWidth("Détail des leçons", FB, 14)
            c.setStrokeColor(NAVY)
            c.setLineWidth(2)
            c.line(MX, y - 5, MX + title_w, y - 5)
            y -= 28
        else:
            # Continuation page: just "Détail des leçons (suite)" + page number
            c.setFillColor(TXT_LIGHT)
            c.setFont(F, 9)
            c.drawRightString(PW - MX, y - 10, f"{teacher_name} — {mois_label} — Page {page_num + 1}/{pages_needed}")
            y -= 30
        
        # ─────────────────────────────
        # TABLE HEADER (every page)
        # ─────────────────────────────
        _rrect(c, tx0, y - rh, tw, rh, r=5, fill=NAVY)
        hdrs = ["Date", "Élève", "Durée", "Taux horaire", "Montant"]
        c.setFillColor(WHITE)
        c.setFont(FB, 9)
        hx = tx0
        for i, h in enumerate(hdrs):
            if i == len(hdrs) - 1:
                c.drawRightString(hx + cols[i] - 12, y - rh + 10, h)
            else:
                c.drawString(hx + 12, y - rh + 10, h)
            hx += cols[i]
        y -= rh
        
        # ─────────────────────────────
        # DATA ROWS (for this page)
        # ─────────────────────────────
        if page_num == 0:
            rows_this_page = rows_first_page
        else:
            rows_this_page = rows_per_cont_page
        
        rows_drawn = 0
        while row_idx < total_rows and rows_drawn < rows_this_page:
            d = sorted_d[row_idx]
            
            # Alternating background
            bg = ROW_ALT if row_idx % 2 == 0 else WHITE
            c.setFillColor(bg)
            c.rect(tx0, y - rh, tw, rh, fill=1, stroke=0)
            
            # Bottom border
            c.setStrokeColor(ROW_BORDER)
            c.setLineWidth(0.5)
            c.line(tx0, y - rh, tx0 + tw, y - rh)
            
            rx = tx0
            ry = y - rh + 10
            
            # Date
            c.setFillColor(TXT)
            c.setFont(F, 9)
            c.drawString(rx + 12, ry, d["date"])
            rx += cols[0]
            
            # Élève
            student = d.get("student", "")
            if "," in student:
                parts = [p.strip() for p in student.split(",")]
                student = " ".join(parts)
            if len(student) > 22:
                student = student[:20] + "…"
            c.drawString(rx + 12, ry, student)
            rx += cols[1]
            
            # Durée
            dur = d.get("duration_min", 0)
            tot_min += dur
            c.drawString(rx + 12, ry, f"{dur} min")
            rx += cols[2]
            
            # Taux horaire
            rate = d.get("rate", 0)
            cur = d.get("currency", "")
            if "CHF" in cur:
                taux = f"{rate:,.2f} CHF/h"
            else:
                taux = f"{rate:,.2f} €/h"
            c.drawString(rx + 12, ry, taux)
            rx += cols[3]
            
            # Montant
            amt = d.get("amount_eur", 0)
            tot_amt += amt
            c.setFont(FB, 9)
            c.drawRightString(rx + cols[4] - 12, ry, f"{amt:,.2f} €")
            
            y -= rh
            row_idx += 1
            rows_drawn += 1
        
        # ─────────────────────────────
        # TOTAL ROW + FOOTER (last page only)
        # ─────────────────────────────
        is_last_page = (page_num == pages_needed - 1)
        
        if is_last_page:
            trh = 34
            left_w = cols[0] + cols[1] + cols[2]
            _rrect(c, tx0, y - trh, left_w, trh, r=0, fill=NAVY)
            right_w = tw - left_w
            c.setFillColor(CARD_BG)
            c.rect(tx0 + left_w, y - trh, right_w, trh, fill=1, stroke=0)
            
            c.setFillColor(WHITE)
            c.setFont(FB, 11)
            c.drawString(tx0 + 12, y - trh + 12, "TOTAL")
            
            h, m = divmod(tot_min, 60)
            dur_str = f"{h}h{m:02d}" if m else f"{h}h"
            c.drawString(tx0 + cols[0] + cols[1] + 12, y - trh + 12, dur_str)
            
            c.setFillColor(GREEN)
            c.setFont(FB, 15)
            c.drawRightString(tx0 + tw - 12, y - trh + 10, f"{tot_amt:,.2f} €")
            
            y -= trh
            
            # Footer
            fy = MY_BOT + 8
            c.setStrokeColor(CARD_BORDER)
            c.setLineWidth(0.5)
            c.line(MX, fy + 12, PW - MX, fy + 12)
            
            c.setFillColor(TXT_LIGHT)
            c.setFont(F, 7)
            c.drawString(MX, fy, f"Taux de change appliqué : 1 CHF = {fx_rate} EUR (source: {fx_source})")
            c.drawRightString(PW - MX, fy, "Généré automatiquement — Professor+")


# ===========================
# PUBLIC API
# ===========================

def generate_single_pdf_to_bytes(teacher_name, data, mois_label, logo_path=None, extraction_end_date=None):
    rate, source, _ = require_chf_to_eur_factor(extraction_end_date)
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=A4)
    _build_page(cv, teacher_name, data, mois_label, logo_path, rate, source)
    cv.save()
    buf.seek(0)
    return buf.getvalue()


def generate_all_pdfs_as_zip(teacher_recaps, mois_label, logo_path=None, exclude_owner="Parisi Lucas", extraction_end_date=None):
    import zipfile
    rate, source, _ = require_chf_to_eur_factor(extraction_end_date)
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for tname in sorted(teacher_recaps.keys()):
            if tname == exclude_owner:
                continue
            d = teacher_recaps[tname]
            if d["nb_lessons"] == 0:
                continue
            buf = io.BytesIO()
            cv = canvas.Canvas(buf, pagesize=A4)
            _build_page(cv, tname, d, mois_label, logo_path, rate, source)
            cv.save()
            buf.seek(0)
            safe = tname.replace(" ", "_")
            zf.writestr(f"Paie_{safe}_{mois_label.replace(' ', '_')}.pdf", buf.getvalue())
    zbuf.seek(0)
    return zbuf.getvalue()


def generate_all_pdfs_to_bytes(teacher_recaps, mois_label, logo_path=None, exclude_owner="Parisi Lucas", extraction_end_date=None):
    rate, source, _ = require_chf_to_eur_factor(extraction_end_date)
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=A4)
    first = True
    for tname in sorted(teacher_recaps.keys()):
        if tname == exclude_owner:
            continue
        d = teacher_recaps[tname]
        if d["nb_lessons"] == 0:
            continue
        if not first:
            cv.showPage()
        first = False
        _build_page(cv, tname, d, mois_label, logo_path, rate, source)
    if not first:
        cv.save()
        buf.seek(0)
        return buf.getvalue()
    return None