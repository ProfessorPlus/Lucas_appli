"""
📄 Generate Invoices
Génération des factures PDF (basé sur generate_invoice_auto.py)
VERSION CLOUD - Compatible Streamlit Cloud avec Google Drive
"""

import os
import json
import re
import traceback
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Import du storage manager pour compatibilité cloud
try:
    from scripts.storage_manager import save_invoice_folder, load_json
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False

# ---------- CONSTANTES PDF ----------
BRAND_BLUE = colors.Color(0.121, 0.227, 0.404)
BRAND_GREEN = colors.Color(0.133, 0.545, 0.133)
FONT_SANS, FONT_BOLD = "Helvetica", "Helvetica-Bold"
LEFT = RIGHT = 20 * mm
TOP = 48 * mm
BOTTOM = 24 * mm
TAGLINE_LEFT = "Soutien scolaire\nsur-mesure"

MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

STATUTS_NON_FACTURES = ["AbsentNotice"]


# ---------- NORMALISATION ----------
def normalize(s):
    """Normalise un nom : minuscules, sans accents, espaces propres"""
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    if "," in s:
        p = [x.strip() for x in s.split(",", 1)]
        if len(p) == 2:
            s = f"{p[1]} {p[0]}"
    return s.strip()


def clean_str(s):
    """Nettoie une chaîne pour nom de fichier en conservant les lettres accentuées translittérées."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-zA-Z0-9_\- ]", "", s).strip()


def parse_dt(date_str):
    """Parse une date DD.MM.YYYY"""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except:
        return datetime.min


# ---------- TOTAL COMPACT (comme l'original) ----------
class TotalTight(Flowable):
    def __init__(self, text, fontName=FONT_BOLD, fontSize=16, color=BRAND_BLUE, spacing=-1.0):
        Flowable.__init__(self)
        self.text = text
        self.fontName = fontName
        self.fontSize = fontSize
        self.color = color
        self.spacing = spacing
        self.width = sum(pdfmetrics.stringWidth(ch, fontName, fontSize) + spacing for ch in text)
        self.height = fontSize + 2

    def wrap(self, *args):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont(self.fontName, self.fontSize)
        c.setFillColor(self.color)
        x = 0
        for ch in self.text:
            c.drawString(x, 0, ch)
            x += pdfmetrics.stringWidth(ch, self.fontName, self.fontSize) + self.spacing
        c.restoreState()


# ---------- BOUTON (comme l'original) ----------
class PayButton(Flowable):
    def __init__(self, label="Cliquez ici pour payer en ligne", url="https://example.com"):
        Flowable.__init__(self)
        self.label = label
        self.url = url
        self.w = 55 * mm
        self.h = 11 * mm

    def wrap(self, *args):
        return (self.w, self.h)

    def draw(self):
        c = self.canv
        c.saveState()

        c.setFillColor(BRAND_BLUE)
        c.roundRect(0, 0, self.w, self.h, 5 * mm, fill=1, stroke=0)

        full = self.label
        before = "Cliquez "
        word = "ici"

        c.setFillColor(colors.white)
        c.setFont(FONT_SANS, 8.7)

        w_before = c.stringWidth(before, FONT_SANS, 8.7)
        w_word = c.stringWidth(word, FONT_SANS, 8.7)
        w_full = c.stringWidth(full, FONT_SANS, 8.7)

        x = (self.w - w_full) / 2
        y = (self.h - 9) / 2 + 2

        c.drawString(x, y, full)

        # Souligner "ici"
        underline_y = y - 1.2
        c.saveState()
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.0)
        c.line(x + w_before, underline_y, x + w_before + w_word, underline_y)
        c.restoreState()

        c.linkURL(self.url, (0, 0, self.w, self.h), relative=1)
        c.restoreState()


# ---------- COMPTEUR FACTURES ----------
def _next_invoice_number(counter_root, invoice_date):
    os.makedirs(counter_root, exist_ok=True)
    month_dir = os.path.join(counter_root, f"invoice_counters_{invoice_date:%y_%m}")
    os.makedirs(month_dir, exist_ok=True)
    counter_file = os.path.join(month_dir, "invoice_counter.txt")

    if os.path.exists(counter_file):
        try:
            counter = int(open(counter_file, "r", encoding="utf-8").read().strip())
        except:
            counter = 0
    else:
        counter = 0

    counter += 1
    with open(counter_file, "w", encoding="utf-8") as f:
        f.write(str(counter))

    seq_number = 10000 + (counter - 1)
    return f"{invoice_date:%y-%m}-{seq_number}"


def _build_invoice_pdf(output_path, items, total_due_display, pay_link_url,
                       parent_name, logo_path, counter_root, today, is_notion_custom=False,
                       previous_items=None, previous_month_label=None):
    """
    Génère un PDF de facture.
    
    Args:
        output_path: chemin du fichier PDF
        items: liste de {"date": datetime, "description": str, "amount": float}
        total_due_display: "123.45 CHF"
        pay_link_url: URL du lien de paiement
        parent_name: nom du parent
        logo_path: chemin du logo
        counter_root: dossier des compteurs de factures
        today: datetime du jour
    """
    currency = total_due_display.split()[-1] if " " in total_due_display else "CHF"
    
    def draw_header(canvas, doc_inner):
        w, h = A4
        x_left = LEFT
        x_right = w - RIGHT
        y_top = h - TOP + 16 * mm

        if logo_path and os.path.exists(logo_path):
            img = ImageReader(logo_path)
            canvas.drawImage(img, x_left, y_top - 26*mm, width=36*mm, height=36*mm, preserveAspectRatio=True)

        canvas.setFillColor(BRAND_BLUE)
        canvas.setFont(FONT_BOLD, 27)
        title = "FACTURE"
        tw = canvas.stringWidth(title, FONT_BOLD, 27)
        canvas.drawString(x_right - tw, y_top - 6 * mm, title)

    def draw_footer(canvas, doc):
        w, h = A4
        bar_h = 12 * mm
        y = 12 * mm

        canvas.setFillColor(BRAND_BLUE)
        canvas.rect(LEFT, y, w - LEFT - RIGHT, bar_h, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_BOLD, 11)
        tagline = "" if is_notion_custom else "Soutien scolaire sur-mesure"
        if tagline:
            canvas.drawString(LEFT + 5 * mm, y + bar_h/2 - 4, tagline)

        canvas.setFont(FONT_SANS, 10)
        txt = "Facture"
        tw = canvas.stringWidth(txt, FONT_SANS, 10)
        canvas.drawString(w - RIGHT - tw - 5*mm, y + bar_h/2 - 4, txt)

    def on_page(canvas, d):
        draw_header(canvas, d)
        draw_footer(canvas, d)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
    )

    flow = []

    # Styles
    st_sub = ParagraphStyle(name="sub", fontName=FONT_BOLD, fontSize=11, leading=13)
    st_facturer = ParagraphStyle(name="facturer", fontName=FONT_SANS, fontSize=12, leading=14)
    st_label = ParagraphStyle(name="label", fontName=FONT_BOLD, fontSize=10, alignment=TA_RIGHT)
    st_value = ParagraphStyle(name="value", fontName=FONT_SANS, fontSize=10, alignment=TA_RIGHT)
    st_header = ParagraphStyle(name="th", fontName=FONT_BOLD, fontSize=12, alignment=TA_CENTER, textColor=colors.white)

    date_str = today.strftime("%d.%m.%Y")
    inv_number = _next_invoice_number(counter_root, today)

    # BANDEAU HAUT
    if is_notion_custom:
        # Carole / Notion custom : pas de tagline, adresse OCTOPUS dans "Facturer à"
        left_band = Paragraph("", st_sub)  # Vide à gauche
        st_addr_mid = ParagraphStyle(name="addr_mid", fontName=FONT_SANS, fontSize=9, leading=12)
        middle_band = Paragraph(
            "<b>Facturer à :</b><br/>"
            "OCTOPUS SARL<br/>"
            "C/o CATS BUSINESS CENTER<br/>"
            "28 bd Princesse Charlotte<br/>"
            "98 000 MONACO",
            st_addr_mid,
        )
    else:
        tagline_text = TAGLINE_LEFT
        left_band = Paragraph(tagline_text.replace("\n", "<br/>"), st_sub)
        middle_band = Paragraph(f"<b>Facturer à :</b><br/>{parent_name}", st_facturer)

    avail = A4[0] - LEFT - RIGHT
    left_w = 58 * mm
    mid_w = 54 * mm
    right_w = avail - left_w - mid_w

    right_band = Table(
        [
            [Paragraph("Date :", st_label), "", Paragraph(date_str, st_value)],
            [Paragraph("Facture n°:", st_label), "", Paragraph(inv_number, st_value)],
        ],
        colWidths=[26*mm, 4*mm, right_w - 30*mm],
    )

    header_row = Table([[left_band, middle_band, right_band]],
                       colWidths=[left_w, mid_w, right_w])
    flow.append(header_row)
    flow.append(Spacer(1, 10 * mm))

    # TABLEAU
    if is_notion_custom:
        # Custom Carole : pas de colonne Date, pas de détail cours, juste Package
        data_tbl = [
            [
                Paragraph("Description", st_header),
                Paragraph("Frais", st_header),
            ]
        ]

        # Ligne unique : 1 Package FORMATION Anglais / Professionnel
        st_package = ParagraphStyle(name="pkg", fontName=FONT_BOLD, fontSize=10)
        st_package_frais = ParagraphStyle(name="pkgf", fontName=FONT_BOLD, fontSize=10, alignment=TA_CENTER, textColor=BRAND_BLUE)
        data_tbl.append([
            Paragraph("1 Package FORMATION Anglais", st_package),
            Paragraph("Professionnel", st_package_frais),
        ])
        
        # Ajouter les cours impayés des mois précédents (notion custom)
        if previous_items:
            separator_label = previous_month_label or "mois précédent(s)"
            st_separator_nc = ParagraphStyle(
                name="sep_nc", fontName=FONT_BOLD, fontSize=9,
                textColor=colors.Color(0.8, 0.2, 0.1), alignment=TA_CENTER,
            )
            sep_text = f"⚠ Rappel — Cours non encore réglés — {separator_label}"
            data_tbl.append([
                Paragraph(sep_text, st_separator_nc),
                Paragraph("", st_separator_nc),
            ])
            for prev_item in previous_items:
                desc_cell = prev_item["description"]
                amt_cell = f'{prev_item["amount"]:.2f} {currency}'
                data_tbl.append([
                    Paragraph(desc_cell, ParagraphStyle(name="c2", fontName=FONT_SANS, fontSize=10)),
                    Paragraph(amt_cell, ParagraphStyle(name="r2", fontName=FONT_BOLD, fontSize=10, alignment=TA_CENTER, textColor=BRAND_GREEN)),
                ])
        
        col_widths_tbl = [avail * 0.7, avail * 0.3]
    else:
        data_tbl = [
            [
                Paragraph("Date", st_header),
                Paragraph("Description", st_header),
                Paragraph("Frais", st_header),
            ]
        ]

    if not is_notion_custom:
        for item in items:
            date_cell = item["date"].strftime("%d.%m.%Y") if item["date"] != datetime.min else ""
            desc_cell = item["description"]
            amt = float(item["amount"])
            amount_cell = f"{amt:.2f} {currency}"
            data_tbl.append([date_cell, desc_cell, amount_cell])
        
        # Ajouter les cours impayés des mois précédents
        if previous_items:
            separator_label = previous_month_label or "mois précédent(s)"
            st_separator = ParagraphStyle(
                name="sep", fontName=FONT_BOLD, fontSize=9,
                textColor=colors.Color(0.8, 0.2, 0.1), alignment=TA_CENTER,
            )
            sep_text = f"⚠ Rappel — Cours non encore réglés — {separator_label}"
            prev_separator_row_idx = len(data_tbl)
            data_tbl.append([
                "",
                Paragraph(sep_text, st_separator),
                "",
            ])
            for prev_item in previous_items:
                date_cell = prev_item["date"].strftime("%d.%m.%Y") if prev_item["date"] != datetime.min else ""
                desc_cell = prev_item["description"]
                amt = float(prev_item["amount"])
                amount_cell = f"{amt:.2f} {currency}"
                data_tbl.append([date_cell, desc_cell, amount_cell])

    if is_notion_custom:
        tbl = Table(data_tbl, colWidths=col_widths_tbl, repeatRows=1)
    else:
        tbl = Table(data_tbl, colWidths=[30*mm, avail - 60*mm, 30*mm], repeatRows=1)

    tbl_style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),

        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 14),

        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),

        ("LINEBELOW", (0, 1), (-1, -1), 0.35, colors.lightgrey),
    ]
    
    if is_notion_custom:
        # 2 colonnes : Description (LEFT), Frais (CENTER sous le header)
        tbl_style_cmds.append(("ALIGN", (0, 1), (0, -1), "LEFT"))
        tbl_style_cmds.append(("ALIGN", (1, 1), (1, -1), "CENTER"))
    else:
        # 3 colonnes : Date (CENTER), Description (LEFT), Frais (RIGHT)
        tbl_style_cmds.append(("ALIGN", (0, 1), (0, -1), "CENTER"))
        tbl_style_cmds.append(("ALIGN", (1, 1), (1, -1), "LEFT"))
        tbl_style_cmds.append(("ALIGN", (2, 1), (2, -1), "RIGHT"))

    # Style the separator row if previous items were added
    if previous_items and not is_notion_custom and 'prev_separator_row_idx' in dir():
        pass  # prev_separator_row_idx is a local variable
    if previous_items:
        # Find the separator row index — it's after current items + header
        if is_notion_custom:
            sep_idx = 2  # header(0) + package(1) → separator at 2
        else:
            sep_idx = 1 + len(items)  # 1 for header row
        tbl_style_cmds.append(("BACKGROUND", (0, sep_idx), (-1, sep_idx), colors.Color(1.0, 0.95, 0.93)))
        tbl_style_cmds.append(("TOPPADDING", (0, sep_idx), (-1, sep_idx), 12))
        tbl_style_cmds.append(("BOTTOMPADDING", (0, sep_idx), (-1, sep_idx), 12))
        tbl_style_cmds.append(("LINEABOVE", (0, sep_idx), (-1, sep_idx), 1.0, colors.Color(0.8, 0.2, 0.1)))

    tbl.setStyle(TableStyle(tbl_style_cmds))

    flow.append(tbl)
    
    # Note si facture combinée
    if previous_items:
        st_note = ParagraphStyle(name="note", fontName=FONT_SANS, fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
        flow.append(Spacer(1, 3 * mm))
        flow.append(Paragraph(
            "Cette facture combine les cours du mois en cours et les cours des mois précédents non encore réglés.",
            st_note
        ))
        flow.append(Spacer(1, 12 * mm))
    else:
        flow.append(Spacer(1, 18 * mm))

    # TOTAL + BOUTON
    total_para = TotalTight(f"Total dû : {total_due_display}", spacing=-1.0)

    stack = Table(
        [
            [total_para],
            [PayButton(label="Cliquez ici pour payer en ligne", url=pay_link_url)],
        ],
        colWidths=[55 * mm],
        hAlign="RIGHT",
    )

    stack.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (0, 1), (0, 1), "CENTER"),
        ("TOPPADDING", (0, 0), (0, 0), 6),
    ]))

    flow.append(stack)

    # BUILD PDF
    try:
        doc.build(flow, onFirstPage=on_page, onLaterPages=on_page)
    except Exception as build_err:
        print(f"❌ Erreur génération PDF {output_path}: {build_err}")
        traceback.print_exc()
        # Supprimer le fichier partiel s'il existe
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def run_generate_invoices(data, secrets, familles_euros, data_dir, base_dir, logo_path=None, callback=None, target_folder_path=None, force_new_folder=False, previous_unpaid_data=None, previous_month_label=None):
    """
    Génère les factures PDF.
    
    Args:
        data: Données extraites de TutorBird
        secrets: Configuration YAML
        familles_euros: Liste des familles en EUR
        data_dir: Dossier des données (pour payment_links_output.json)
        base_dir: Dossier racine du projet
        logo_path: Chemin vers le logo (optionnel)
        callback: Fonction callback(progress, message)
        target_folder_path: Chemin vers le dossier cible (optionnel, pour régénération)
        force_new_folder: Force la création d'un nouveau dossier
        previous_unpaid_data: dict {family_id: {"lessons": [...], ...}} des mois précédents impayés.
                              Les leçons sont ajoutées en section "Rappel" dans le PDF avec le détail.
        previous_month_label: str label pour la section rappel (ex: "Janvier 2026")
    
    Returns:
        dict: {"success": bool, "invoices": int, "links_found": int, "generated_files": list, ...}
    """
    
    if not REPORTLAB_AVAILABLE:
        return {"success": False, "error": "Module reportlab non installé. pip install reportlab"}
    
    def update(progress, message):
        if callback:
            callback(progress, message)
    
    try:
        TEACHERS = secrets.get("teachers", {})
        TEACHER_MAP = {normalize(tid): tid for tid in TEACHERS.keys()}
        
        # Règles spéciales de mapping
        if "Ricardo Hounsinou" in TEACHERS:
            TEACHER_MAP[normalize("Ricardo H")] = "Ricardo Hounsinou"
        if "Ricardo HOUNSINOU" in TEACHERS:
            TEACHER_MAP[normalize("Ricardo H")] = "Ricardo HOUNSINOU"
        
        # Table de correspondance teacher names
        TEACHER_ALIAS = {
            normalize("Ricardo H"): normalize("Ricardo Hounsinou"),
            normalize("Bruno Lamaison"): normalize("Bruno Lamaison"),
            normalize("lamaison bruno"): normalize("Bruno Lamaison"),
        }
        
        # Matching EUR
        manual_names = [normalize(n) for n in familles_euros]
        families_in_euros = set()
        
        for fam_id, fam in data.items():
            parent_name = fam.get("parent_name") or fam.get("family_name") or ""
            norm_parent = normalize(parent_name)
            
            for eur_name in manual_names:
                ratio = SequenceMatcher(None, norm_parent, eur_name).ratio()
                if ratio > 0.70:
                    families_in_euros.add(fam_id)
                    break
        
        # Charger liens Stripe (local ou Drive)
        links_map = {}
        links_list = None
        
        # Essayer storage_manager d'abord (supporte Drive)
        if STORAGE_AVAILABLE:
            links_list = load_json("payment_links_output.json", "data", default=None)
        
        # Fallback fichier local
        if links_list is None:
            links_path = os.path.join(data_dir, "payment_links_output.json")
            if os.path.exists(links_path):
                with open(links_path, "r", encoding="utf-8") as f:
                    links_list = json.load(f)
        
        if links_list:
            for e in links_list:
                key = (e["family_id"], normalize(e["teacher"]))
                links_map[key] = e["payment_link"]
                # Mode no-split : stocker aussi avec clé spéciale famille-only
                if e.get("mode") == "no_split":
                    links_map[(e["family_id"], "__no_split__")] = e["payment_link"]
        
        today = datetime.today()
        year_str = today.strftime("%Y")
        month_str = MONTHS_FR[today.month - 1]
        
        # Dossiers — sur Streamlit Cloud, le repo est read-only, utiliser /tmp/
        try:
            from scripts.config_loader import is_streamlit_cloud as _is_cloud_check
            _on_cloud = _is_cloud_check()
        except Exception:
            _on_cloud = not os.access(base_dir, os.W_OK)
        
        if _on_cloud:
            invoice_root = "/tmp/Factures"
            counter_root = "/tmp/invoice_counters"
        else:
            invoice_root = os.path.join(base_dir, "Factures")
            counter_root = os.path.join(base_dir, "invoice_counters")
        
        # Utiliser le dossier cible si spécifié
        if target_folder_path and os.path.exists(target_folder_path):
            month_folder_path = target_folder_path
            update(5, f"📁 Régénération dans : {os.path.basename(target_folder_path)}")
        else:
            base_month_folder_name = f"{month_str} {year_str} - {today.strftime('%d-%m-%Y')}"
            month_folder_name = base_month_folder_name
            month_folder_path = os.path.join(invoice_root, year_str, month_folder_name)
            if force_new_folder or os.path.exists(month_folder_path):
                month_folder_name = f"{base_month_folder_name} {today.strftime('%Hh%M')}"
                month_folder_path = os.path.join(invoice_root, year_str, month_folder_name)
            os.makedirs(month_folder_path, exist_ok=True)
            update(5, f"📁 Génération dans : {month_folder_name}")
        
        # Stats
        factures_generees = 0
        liens_trouves = 0
        liens_manquants = []
        cours_non_factures = 0
        generated_files = []
        
        # Détecter si mode no-split actif (au moins un lien no_split existe)
        is_no_split_mode = any(
            e.get("mode") == "no_split" for e in (links_list or [])
        )
        
        print(f"🔍 DEBUG: links_list={'None' if links_list is None else len(links_list)}, links_map={len(links_map)}, is_no_split_mode={is_no_split_mode}")
        print(f"🔍 DEBUG: data families={len(data)}, STORAGE_AVAILABLE={STORAGE_AVAILABLE}")
        if links_map:
            sample_keys = list(links_map.keys())[:3]
            print(f"🔍 DEBUG: sample link keys: {sample_keys}")
        
        total_families = len(data)
        current = 0
        
        for fam_id, fam in data.items():
            current += 1
            progress = int(current / total_families * 90)
            
            lessons = fam.get("lessons", [])
            if not lessons:
                continue
            
            parent_name = fam.get("parent_name") or fam.get("family_name") or "Parent"
            update(progress, f"📄 {parent_name} ({current}/{total_families})")
            
            currency = "EUR" if fam_id in families_in_euros else "CHF"
            # Prioriser la devise définie dans les données (ex: profs hors TutorBird via Notion)
            fam_currency = (fam.get("currency") or "").upper()
            if fam_currency in ("EUR", "CHF"):
                currency = fam_currency
            
            # Filtrer les absences
            lessons_filtered = []
            for L in lessons:
                attendance = L.get("attendance_status", "")
                if attendance in STATUTS_NON_FACTURES:
                    cours_non_factures += 1
                    continue
                lessons_filtered.append(L)
            
            if not lessons_filtered:
                continue
            
            fam_folder = clean_str(parent_name.replace(" ", "_"))
            fam_base_dir = os.path.join(month_folder_path, fam_folder)
            os.makedirs(fam_base_dir, exist_ok=True)
            
            # Nettoyer les anciens PDFs dans le sous-dossier (évite doublons lors de régénération)
            if target_folder_path:  # seulement lors de régénération dans un dossier existant
                for _old_pdf in os.listdir(fam_base_dir):
                    if _old_pdf.lower().endswith('.pdf'):
                        _old_path = os.path.join(fam_base_dir, _old_pdf)
                        try:
                            os.remove(_old_path)
                            print(f"   🗑️ Ancien PDF supprimé: {_old_pdf}")
                        except Exception:
                            pass
            
            # ===========================
            # MODE NO-SPLIT : une seule facture par famille
            # ===========================
            if is_no_split_mode:
                lessons_sorted = sorted(lessons_filtered, key=lambda x: parse_dt(x.get("date", "")))
                
                items = []
                total_due = 0.0
                
                for L in lessons_sorted:
                    d = parse_dt(L.get("date", ""))
                    student = L.get("student", "")
                    teacher = L.get("teacher", "Professeur")
                    duration = L.get("duration_min", "")
                    desc = f"Cours avec {teacher} pour {student} ({duration} min)"
                    amt = float(L.get("amount", 0) or 0)
                    total_due += amt
                    items.append({"date": d, "description": desc, "amount": amt})
                
                if total_due <= 0:
                    continue
                
                # Construire les items impayés des mois précédents pour cette famille
                prev_items_for_fam = []
                if previous_unpaid_data:
                    prev_fam = previous_unpaid_data.get(fam_id)
                    if prev_fam:
                        prev_lessons = prev_fam.get("lessons", [])
                        prev_lessons_filtered = [
                            L for L in prev_lessons
                            if L.get("attendance_status") not in STATUTS_NON_FACTURES
                        ]
                        prev_lessons_sorted = sorted(prev_lessons_filtered, key=lambda x: parse_dt(x.get("date", "")))
                        for L in prev_lessons_sorted:
                            d = parse_dt(L.get("date", ""))
                            student = L.get("student", "")
                            teacher = L.get("teacher", "Professeur")
                            duration = L.get("duration_min", "")
                            desc = f"Cours avec {teacher} pour {student} ({duration} min)"
                            amt = float(L.get("amount", 0) or 0)
                            total_due += amt
                            prev_items_for_fam.append({"date": d, "description": desc, "amount": amt})
                
                total_due_display = f"{total_due:.2f} {currency}"
                
                # Lien no-split
                no_split_key = (fam_id, "__no_split__")
                pay_link_url = links_map.get(no_split_key)
                
                if pay_link_url:
                    liens_trouves += 1
                else:
                    pay_link_url = "https://example.com"
                    liens_manquants.append(f"{parent_name} (no-split)")
                
                filename = f"Facture_{year_str}-{today.strftime('%m-%d')}_{clean_str(parent_name.replace(' ', '_'))}.pdf"
                output_path = os.path.join(fam_base_dir, filename)
                
                # Générer le PDF
                # Facture spéciale OCTOPUS uniquement pour Carole Tessier
                is_notion_custom = (
                    fam.get("source") == "notion_hors_tb"
                    and normalize(parent_name) == normalize("Carole Tessier")
                )
                _build_invoice_pdf(
                    output_path, items, total_due_display, pay_link_url,
                    parent_name, logo_path, counter_root, today,
                    is_notion_custom=is_notion_custom,
                    previous_items=prev_items_for_fam if prev_items_for_fam else None,
                    previous_month_label=previous_month_label,
                )
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    factures_generees += 1
                    generated_files.append(output_path)
                    print(f"   ✅ PDF créé: {output_path} ({os.path.getsize(output_path)} bytes)")
                else:
                    print(f"   ❌ PDF non créé pour {parent_name}: {output_path}")
                    print(f"      exists={os.path.exists(output_path)}, fam_base_dir exists={os.path.exists(fam_base_dir)}")
            
            # ===========================
            # MODE NORMAL : une facture par famille/prof
            # ===========================
            else:
                # Regrouper par prof
                by_teacher = {}
                for L in lessons_filtered:
                    prof_tb = L.get("teacher") or "Professeur"
                    prof_normalized = normalize(prof_tb)
                    yaml_name = TEACHER_MAP.get(prof_normalized, prof_tb)
                    by_teacher.setdefault((prof_tb, yaml_name), []).append(L)
                
                for (teacher_display, teacher_yaml), lessons_list in by_teacher.items():
                    lessons_sorted = sorted(lessons_list, key=lambda x: parse_dt(x.get("date", "")))
                    
                    items = []
                    total_due = 0.0
                    
                    for L in lessons_sorted:
                        d = parse_dt(L.get("date", ""))
                        student = L.get("student", "")
                        duration = L.get("duration_min", "")
                        desc = f"Cours avec {teacher_display} pour {student} ({duration} min)"
                        amt = float(L.get("amount", 0) or 0)
                        total_due += amt
                        items.append({"date": d, "description": desc, "amount": amt})
                    
                    if total_due <= 0:
                        continue
                    
                    # Chercher lien paiement
                    pay_link_url = None
                    teacher_norm = normalize(teacher_display)
                    teacher_search = TEACHER_ALIAS.get(teacher_norm, teacher_norm)
                    
                    # Essai 1
                    key1 = (fam_id, teacher_search)
                    if key1 in links_map:
                        pay_link_url = links_map[key1]
                    
                    # Essai 2
                    if not pay_link_url:
                        key2 = (fam_id, normalize(teacher_yaml))
                        if key2 in links_map:
                            pay_link_url = links_map[key2]
                    
                    # Essai 3
                    if not pay_link_url:
                        key3 = (fam_id, teacher_norm)
                        if key3 in links_map:
                            pay_link_url = links_map[key3]
                    
                    # Essai 4: recherche approximative
                    if not pay_link_url:
                        for (link_fam, link_teacher), link_url in links_map.items():
                            if link_fam == fam_id:
                                if SequenceMatcher(None, teacher_search, link_teacher).ratio() > 0.8:
                                    pay_link_url = link_url
                                    break
                                if SequenceMatcher(None, teacher_norm, link_teacher).ratio() > 0.8:
                                    pay_link_url = link_url
                                    break
                    
                    # Essai 5: fallback mode no-split
                    if not pay_link_url:
                        no_split_key = (fam_id, "__no_split__")
                        if no_split_key in links_map:
                            pay_link_url = links_map[no_split_key]
                    
                    if pay_link_url:
                        liens_trouves += 1
                    else:
                        pay_link_url = "https://example.com"
                        liens_manquants.append(f"{parent_name} / {teacher_display}")
                    
                    # Construire les items impayés des mois précédents pour cette famille/prof
                    prev_items_for_teacher = []
                    if previous_unpaid_data:
                        prev_fam = previous_unpaid_data.get(fam_id)
                        if prev_fam:
                            for pL in prev_fam.get("lessons", []):
                                if pL.get("attendance_status") in STATUTS_NON_FACTURES:
                                    continue
                                prev_teacher = pL.get("teacher") or ""
                                if normalize(prev_teacher) == normalize(teacher_display) or normalize(prev_teacher) == normalize(teacher_yaml):
                                    d = parse_dt(pL.get("date", ""))
                                    student = pL.get("student", "")
                                    duration = pL.get("duration_min", "")
                                    desc = f"Cours avec {prev_teacher} pour {student} ({duration} min)"
                                    amt = float(pL.get("amount", 0) or 0)
                                    total_due += amt
                                    prev_items_for_teacher.append({"date": d, "description": desc, "amount": amt})
                            prev_items_for_teacher.sort(key=lambda x: x["date"])
                    
                    total_due_display = f"{total_due:.2f} {currency}"
                    
                    teacher_clean = clean_str(teacher_display.replace(" ", "_"))
                    filename = f"Facture_{year_str}-{today.strftime('%m-%d')}_{teacher_clean}.pdf"
                    output_path = os.path.join(fam_base_dir, filename)
                    
                    # Générer le PDF
                    _build_invoice_pdf(
                        output_path, items, total_due_display, pay_link_url,
                        parent_name, logo_path, counter_root, today,
                        previous_items=prev_items_for_teacher if prev_items_for_teacher else None,
                        previous_month_label=previous_month_label,
                    )
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        factures_generees += 1
                        generated_files.append(output_path)
                    else:
                        print(f"⚠️ PDF non créé pour {parent_name}/{teacher_display}: {output_path}")
                
        # ===============================
        # UPLOAD VERS GOOGLE DRIVE (si cloud)
        # ===============================
        drive_saved = False
        print(f"🔍 DEBUG UPLOAD: STORAGE_AVAILABLE={STORAGE_AVAILABLE}, factures_generees={factures_generees}, month_folder_path={month_folder_path}")
        
        # Lister les fichiers dans le dossier pour vérifier qu'ils existent
        if os.path.exists(month_folder_path):
            for dirpath, dirnames, filenames in os.walk(month_folder_path):
                for fn in filenames:
                    fp = os.path.join(dirpath, fn)
                    print(f"   📄 Fichier local: {fp} ({os.path.getsize(fp)} bytes)")
        else:
            print(f"   ❌ DOSSIER N'EXISTE PAS: {month_folder_path}")
        
        if STORAGE_AVAILABLE and factures_generees > 0:
            update(95, "☁️ Upload vers Google Drive...")
            try:
                result = save_invoice_folder(month_folder_path)
                print(f"🔍 DEBUG UPLOAD result: {result}")
                if result.get("success"):
                    drive_saved = True
                    uploaded_count = result.get("uploaded", 0)
                    update(98, f"☁️ {uploaded_count} fichiers uploadés sur Drive")
                else:
                    print(f"❌ Upload Drive échoué: {result}")
            except Exception as e:
                print(f"⚠️ Erreur upload Drive: {e}")
                import traceback
                traceback.print_exc()
        
        update(100, "✅ Terminé !")
        
        return {
            "success": True,
            "invoices": factures_generees,
            "links_found": liens_trouves,
            "links_missing": liens_manquants,
            "absences": cours_non_factures,
            "folder": month_folder_path,
            "generated_files": generated_files,
            "drive_saved": drive_saved
        }
        
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}