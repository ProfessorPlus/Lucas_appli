# MIGRATION_SPEC — Professor+ : Streamlit → Next.js + FastAPI

> Document de référence pour la migration. **Aucune feature ne doit être perdue.**
> Tout ce qui n'est pas listé ici n'est pas dans le périmètre.

---

## 🚫 Hors périmètre

- Le dossier `Fares_appli/` est **totalement exclu** : pas migré, pas lu, pas déployé.
- Le script `generate_refresh_token.py` reste un utilitaire CLI, pas exposé en API.

---

## 🎯 Stack cible

| Couche | Technologie | Hébergement |
|---|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + framer-motion + react-query + lucide-react + Sonner (toasts) | Vercel |
| Backend principal | FastAPI + scripts Python existants wrappés en services | Railway |
| **Webhook Stripe** | FastAPI minimal (sync_engine.py + server.py) — service séparé | **Render** (ou Railway séparé) |
| Auth | Header `X-API-Key` (mono-user) | — |
| DB métier | **Notion** (inchangé) | — |
| Storage | **Google Drive** (inchangé via OAuth) | — |
| Jobs longs | Pattern fire-and-poll (SQLite local pour persistance) | — |

---

## ⚠️ Comportements critiques à préserver (à lire AVANT de coder)

Ces comportements ont été débuggés sur plusieurs mois en production. Les ignorer = recréer des bugs résolus.

### A. **Multi-devise — calcul leçon par leçon**
Les familles peuvent **mélanger plusieurs devises** dans leurs leçons (ex: famille TutorBird CHF fusionnée avec un prof Notion EUR). Donc :
- Chaque leçon a un champ `source` qui peut valoir `"notion_hors_tb"` (ou absent si TutorBird)
- Chaque leçon Notion a un champ `notion_devise_client` (EUR, CHF, AED)
- `amounts_by_currency` doit être calculé **leçon par leçon**, pas famille par famille
- Pour une leçon TutorBird (sans `source`) : CHF par défaut, EUR si la famille est dans `familles_euros.yaml`
- Pour une leçon Notion : devise = `notion_devise_client`
- AED → EUR via **peg USD** (1 USD = 3.6725 AED) puis Frankfurter USD/EUR
- CHF → EUR via Frankfurter CHF/EUR

### B. **Fusion TutorBird + Notion hors TutorBird**
Quand on extrait, les familles "Profs hors TutorBird" (Notion) sont fusionnées dans les familles TutorBird existantes :
1. Match exact par `family_id` (rare, Notion utilise `notion_<famille>`)
2. **Match par nom normalisé avec mots triés alphabétiquement** : `"Fatou Thiam"` == `"Thiam Fatou"` après normalisation (lowercase, sans accents, mots triés)
3. Si pas de match → ajout comme nouvelle famille (`source: "notion_hors_tb"`, `currency: notion`)
4. Quand fusion : devise Notion **prime** sur TutorBird (tous les fields family-level), MAIS chaque leçon garde son `source` original
5. Index `tb_name_index` (nom_normalisé → fam_id) pour le lookup

### C. **n-2 impayés consolidés**
Quand on inclut les impayés des mois précédents dans la facture du mois courant :
1. Lecture depuis Notion "Paiements Centrale" : `Payé != true` AND `Invoice date > X mois back`
2. Persistance via `st.session_state["_previous_unpaid_data"]` **+ fallback `payment_links_output.json` sur Drive**
3. Format : `{family_id: {amount: float, hours: float, dates: [datetime, ...]}}`
4. Utilisé dans 3 endroits :
   - **Payment links** : montant Stripe = montant courant + montants n-2 cumulés
   - **Invoices** : section "Rappel" dans le PDF avec séparateur visuel + leçons des mois précédents
   - **Update Notion** : ligne unique avec heures totales (courant + n-2) et plage de dates étendue
5. Métadata Stripe : `includes_previous_months: "true"` quand cumulé

### D. **Stripe SDK v15 compatibility**
La SDK v15 a changé le format des objets metadata :
- `dict(charge.metadata)` → **CRASH** avec `KeyError: 0`
- Utiliser `charge.metadata.to_dict()` ou itérer manuellement par clés
- S'applique à tous les services qui touchent Stripe (webhooks Render + sync depuis app)

### E. **Matching Stripe ↔ Notion : invoice_date est PRÉFÉRENTIEL**
Quand on régénère un lien Stripe, l'invoice_date change (date du jour) mais la ligne Notion garde son ancienne invoice_date :
1. Critère de matching : prof + élève + montant + (invoice_date en **préférence**)
2. Si rows trouvées avec invoice_date exacte → prendre celle-là
3. Sinon → fallback sans contrainte de date
4. `parent_name` récupéré depuis PaymentLink API si absent du PaymentIntent
5. Log : `ℹ️ Pas de match date exacte (X), fallback sans date`

### F. **Email — priorité templates et détection**
Ordre de priorité strict : **Multi-mois > Carole > Anglais > Français**
- Détection Carole : `"carole" in name.lower() AND "tessier" in name.lower()` — **purement par nom** (pas dépendant de `source` ou `family_id`)
- Détection EN : `language in {"anglais", "english", "en"}` (lu depuis data extraite, fallback `fr`)
- Détection Multi-mois : `family_id in _multimonth_ids` (depuis `_previous_unpaid_data` OR `payment_links_output.json` avec `includes_previous_months: "true"`)
- Aperçu par tab : compteur `(N)` + liste des familles concernées dans chaque onglet

### G. **Matching PDF ↔ famille pour pièces jointes**
Bug historique : Pisanello recevait le PDF de Diallo (similarité textuelle 0.714 fortuite). Donc :
- Utiliser **`names_match` strict** : seuil SequenceMatcher 0.82 + ≥2 mots en commun + permutation autorisée (mots triés)
- Sélectionner le **meilleur** match (max score), pas le premier qui passe le seuil
- Match exact (après normalisation) = score forcé à 1.0 (priorité absolue)
- Fallback PDF à la racine du dossier : exiger **TOUS** les mots significatifs du parent

### H. **Filter `attendance_status == "AbsentNotice"`**
Les leçons avec `attendance_status == "AbsentNotice"` sont **exclues** de tous les calculs (factures, recap profs, lignes Notion). Ne JAMAIS les compter.

---

## 🎨 Palette Professor+

### Mode Clair — Couleurs principales

| Token | HSL | HEX | Rôle |
|---|---|---|---|
| `--primary` | 219 54% 26% | `#1F3A67` | Bleu marine — boutons, accents |
| `--accent` | 168 80% 40% | `#14B8A6` | Turquoise — highlights, Stripe badge |
| `--background` | 210 20% 98% | `#F7F9FA` | Fond général (blanc cassé) |
| `--foreground` | 222 47% 11% | `#0F1B2D` | Texte principal |

### Cartes & surfaces

| Token | HSL | HEX | Rôle |
|---|---|---|---|
| `--card` | 0 0% 100% | `#FFFFFF` | Fond des cards |
| `--secondary` | 210 18% 95% | `#EEF1F4` | Fond secondaire / badges |
| `--muted` | 210 18% 95% | `#EEF1F4` | Zones atténuées |
| `--muted-foreground` | 215 16% 47% | `#697080` | Texte gris discret |
| `--border` | 214 20% 90% | `#DDE3EC` | Séparateurs |

### États sémantiques

| Token | HSL | HEX | Rôle |
|---|---|---|---|
| `--success` | 142 71% 45% | `#29C76F` | ✅ Succès (vert) |
| `--warning` | 38 92% 50% | `#F59E0B` | ⚠️ Warning (orange) |
| `--info` | 199 89% 48% | `#0EA5E9` | ℹ️ Info (bleu ciel) |
| `--destructive` | 0 84% 60% | `#F35454` | ❌ Erreur (rouge) |

### Sidebar (fond sombre fixe — même en mode clair)

| Token | HSL | HEX | Rôle |
|---|---|---|---|
| `--sidebar-background` | 225 25% 14% | `#1A1F2E` | Fond principal sidebar |
| `--sidebar-accent` | 225 20% 20% | `#282E3F` | Hover / item actif |
| `--sidebar-border` | 225 20% 22% | `#2C3347` | Séparateur sidebar |
| `--sidebar-primary` | 168 80% 40% | `#14B8A6` | Turquoise actif sidebar |
| `--sidebar-foreground` | 210 20% 80% | `#BAC4D0` | Texte sidebar |

### Mode Sombre

| Token | HSL | HEX |
|---|---|---|
| `--background` | 225 25% 8% | `#0E111A` |
| `--card` | 225 25% 12% | `#151A27` |
| `--primary` | 168 80% 40% | `#14B8A6` (turquoise devient primaire) |
| `--sidebar-background` | 225 30% 7% | `#0B0E17` |

### Couleurs supplémentaires utilisées dans les composants

| Usage | HEX |
|---|---|
| Émeraude (payé, connecté) | `#10B981` |
| Ambre (retard, warning) | `#F59E0B` |
| Bleu (extraction) | `#3B82F6` |
| Violet (factures) | `#8B5CF6` |
| Cyan (emails) | `#06B6D4` |
| Orange (rappels) | `#F97316` |
| Terminal bg | `#0D1117` (GitHub dark) |
| Sidebar dégradé | `#1A1F2E → #151922` |

---

## 📑 Inventaire des 12 pages — mapping vers Next.js + endpoints

### 1. `page_accueil` → `/` (Dashboard)
**Header** : "🎓 Professor+ Admin"  
**Composants** : 4 stats cards, 3 cards paiements + barre progression, 3 cards historique envois, 2 cards citations (Hadith + Citation du jour), 3 boutons quick actions, info box workflow recommandé.

**4 metrics principales** :
- 👨‍🏫 Nombre de profs (TutorBird + Notion hors TB)
- 👪 Nombre de familles
- 💰 À facturer (multi-devise : `1,321.80 AED + 6,445.00 CHF + 3,658.32 EUR`)
- 💶 Net EUR (CA EUR − Profs EUR, après conversion taux Frankfurter)

**3 cards paiements** (sélectionnable par dossier facture) :
- `% payé` (nb factures payées / nb total)
- `montant payé / total dû` par devise
- Barre de progression

**3 cards historique envois** (sélectionnable par dossier) :
- Nb factures envoyées (avec date dernier envoi)
- Nb rappels envoyés
- Nb relances en attente

**Quick actions** (3 boutons) :
- 🚀 Workflow complet : Extract → Payment Links → Invoices → Send
- 📥 Lancer extraction du mois en cours
- 💸 Voir paie profs

**Info box workflow recommandé** :
1. Extraire les leçons (TutorBird + Notion hors TB)
2. Créer les liens de paiement (option : inclure impayés n-2)
3. Générer les factures PDF
4. Envoyer les factures par email (4 templates selon famille)
5. Sync Stripe → Notion (auto via webhook Render)
6. Envoyer les rappels (J+10, J+20, J+30)
7. Récapitulatif paie profs + envoi PDFs

| Donnée | Endpoint API |
|---|---|
| 4 metrics globales | `GET /api/dashboard/summary` |
| 3 metrics paiements | `GET /api/dashboard/payments?folder=<id>` |
| 3 metrics envois | `GET /api/dashboard/emails?folder=<id>` |
| Citation + Hadith | `GET /api/quotes/random` |
| Liste dossiers factures (selectbox) | `GET /api/invoice-folders` |

---

### 2. `page_extract` → `/extract` (Extraction TutorBird)
**Header** : "📥 Extraction TutorBird"  
**Composants détaillés** :
- 3 quick-pick : mois courant, mois précédent, mois en cours (M)
- Date pickers début/fin avec time pickers (00:00 → 23:59 par défaut)
- Checkbox "Journée entière" qui cache les time pickers
- Section "Profs hors TutorBird (Notion)" avec :
  - Bouton "Rafraîchir depuis Notion"
  - Tableau : Famille | Prof | Élève | Heures | Taux client (avec devise) | Taux prof | Total client (avec devise)
  - Multiselect "Profs hors TutorBird à inclure" (par défaut tous)
  - Total filtré : `1,037 EUR + 1,322 AED`

**Résultats post-extraction** :
- 📁 N familles | 📚 N leçons | 💰 Total multi-devise (calculé leçon par leçon — voir critique A)
- 📋 N prof(s) hors TutorBird ajouté(s)
- 💶 Net : N € (CA X € − Profs Y €)
- Expander "🔍 Détail par famille" : tableau Famille | EUR | CHF | AED | Note (marquée EUR si dans `familles_euros.yaml`)

**Sauvegarde** : `full_output_tb_SIMPLE.json` (Drive + cache /tmp), `full_output_tb_YYYY-MM.json` (archive Drive), `teacher_emails.json`

| Action | Endpoint |
|---|---|
| Charger profs hors TB | `GET /api/notion/profs-hors-tb` |
| Lancer extraction | `POST /api/extract` → `{job_id}` |
| Polling job | `GET /api/jobs/{id}` |
| Détail post-extraction | `GET /api/extract/last-summary` |

**Scripts** : `extract_tutorbird.run_extraction(...)` + `fetch_notion_profs.run_fetch_notion_profs(...)`  
**Durée** : longue → fire-and-poll obligatoire

---

### 3. `page_twint` → `/twint` (Activation Twint)
**Header** : "⚡ Activation Twint"  
**Composants** : multiselect comptes, statuts par compte (active/pending/aucun Connect).

| Action | Endpoint |
|---|---|
| Vérifier statut | `GET /api/twint/status` |
| Activer Twint | `POST /api/twint/activate` (body: `{account_ids: []}`) |

**Script** : `activate_twint.get_twint_status` (à étendre pour activation)  
**Durée** : moyenne — sync OK

---

### 4. `page_cleanup` → `/cleanup` (Nettoyage Notion) — 3 onglets

| Action | Endpoint |
|---|---|
| Scanner dates Notion | `GET /api/cleanup/scan-dates` |
| Supprimer anciennes (avec dry-run) | `POST /api/cleanup/delete-old` (body: `{cutoff_date, dry_run}`) |
| Nettoyer doublons | `POST /api/cleanup/duplicates` (body: `{dry_run}`) |

**Script** : `cleanup_notion.run_cleanup_duplicates`, `run_scan_notion_dates`, `run_delete_old_rows`  
**Durée** : longue → fire-and-poll

---

### 5. `page_payment` → `/payment-links` (Liens de paiement) — 2 onglets

**Métadata Stripe injectée dans `payment_intent_data.metadata`** (cruciale pour matching webhook) :
`family_name` (legacy), `family_id`, `parent_name`, `parent_email`, `currency` (chf/eur/aed), `teacher` (séparés `/`), `student` (séparés `&`), `invoice_date`, `includes_previous_months` (`"true"` si n-2), `previous_amount`, `previous_months`.

**Output sauvé sur Drive** : `payment_links_output.json` (source de vérité pour invoices, send, sync) :
```json
[
  {
    "family_id": "fml_xxx",
    "parent_name": "Calabresi Aurélie",
    "amount": 315.0,
    "currency": "eur",
    "payment_link": "https://buy.stripe.com/...",
    "stripe_payment_link_id": "plink_...",
    "includes_previous_months": "true",
    "previous_amount": 60.0,
    "metadata": { ... }
  }
]
```

**AED currency support** : Stripe accepte AED en paiement direct ; conversion AED → EUR via USD peg pour calculs internes ; affichage dans la devise originale.

**Désactivation des anciens liens** : régénération → `payment_links.update(id, active=False)` avant création nouveau.

| Action | Endpoint |
|---|---|
| Générer liens (avec split) | `POST /api/payment-links/create` |
| Générer liens (no-split) | `POST /api/payment-links/create?no_split=true` |
| Régénérer pour familles | `POST /api/payment-links/regenerate` (body: `{families, deactivate_old: true}`) |
| Relancer manquants | `POST /api/payment-links/retry-missing` |
| Statut profs Stripe Connect | `GET /api/teachers/stripe-status` |
| Détecter impayés n-2 | `GET /api/payment-links/unpaid-detect?year=&month=` |
| Lister liens existants | `GET /api/payment-links/list?folder=<id>` |

**Scripts** : `create_payment_links.run_create_payment_links`, `create_payment_links_no_split.run_create_payment_links_no_split`  
**Durée** : longue → fire-and-poll

---

### 6. `page_invoices` → `/invoices` (Génération factures) — 2 onglets

**Format des PDFs** :
- Nom : `Facture_YYYY-MM-DD_Family_Name.pdf` (date du jour)
- Sous-dossier par famille : `Calabresi_Aurelie/`, `Tessier_Carole/`...
- Format heures : `"22h45"` (pas `"22.8h"`)
- Classes ReportLab custom : `TotalTight`, `PayButton`
- Bouton "Payer en ligne" embed link Stripe
- Filtrer `AbsentNotice` (voir critique H)

**Cas spécial Carole Tessier (OCTOPUS SARL)** :
- Adresse Monaco au lieu de Suisse
- Format "package" (montant global, pas leçon par leçon)
- Détection : par nom uniquement (`"carole" in name AND "tessier" in name`)
- Détails heures depuis Notion (`details_heures`)

**Multi-mois (n-2 consolidés)** :
- PDF unique avec leçons du mois courant en haut
- Section "Rappel" avec séparateur visuel + leçons des mois précédents impayés
- Total cumulé en bas avec montant Stripe = `lessons_amount + prev_amount`

**AED support** : devise affichée comme "AED" dans le total ; pas de conversion (la facture reste en AED) ; Stripe link en AED.

**Régénération dans dossier existant** :
- `target_folder_path` fourni → ne crée pas de nouveau dossier
- **Cleanup local** : supprime les anciens PDFs du sous-dossier famille AVANT création
- Sur Drive : si PDF inexistant par nom exact (date différente), cherche d'autres PDFs dans le sous-dossier et les remplace (Service Account quota issue)

| Action | Endpoint |
|---|---|
| Générer factures | `POST /api/invoices/generate` (body: `{folder_mode, include_unpaid_n2, target_month, copy_local}`) |
| Détecter impayés Notion | `GET /api/invoices/unpaid-detect?year=&month=` |
| Régénérer pour familles | `POST /api/invoices/regenerate` (body: `{families, target_folder_id, cleanup_old}`) |
| Télécharger ZIP | `GET /api/invoices/{folder_id}/download` |
| Télécharger 1 PDF | `GET /api/invoices/{folder_id}/{family}.pdf` |
| Lister dossiers factures | `GET /api/invoice-folders` |

**Scripts** : `generate_invoices.run_generate_invoices`, `fetch_unpaid_notion.fetch_unpaid_n2`  
**Durée** : longue → fire-and-poll

---

### 7. `page_send` → `/send-invoices` (Envoi factures) — 4 onglets templates
**Tabs** : 🇫🇷 FR / 🇬🇧 EN / 👩 Carole Tessier / 📌 Multi-mois

**Aperçu par onglet** : `(N)` dans titre + liste des familles concernées sous le tab.

**Logique de sélection template** (voir critique F) — ordre strict : Multi-mois > Carole > EN > FR.

**Templates par défaut** (surcharge possible) :
- FR : "Facture(s) - Soutien scolaire - {month} {year}"
- EN : "Invoice(s) - Tutoring - {month} {year}"
- Carole : "Invoice {month} {year} - OCTOPUS SARL"
- Multi-mois : "Facture(s) - Soutien scolaire - {month} {year} (incluant cours non réglés)"

**Pièces jointes PDF** : matching strict (voir critique G), meilleur match max score, fallback racine si pas de sous-dossier.

| Action | Endpoint |
|---|---|
| Diagnostic (PDFs/emails) | `GET /api/send/diagnostic?folder=<id>` |
| Aperçu par template | `GET /api/send/preview?folder=<id>` (renvoie `{fr, en, carole, multi}`) |
| Test envoi à soi-même | `POST /api/send/test` |
| Envoi batch | `POST /api/send/invoices` (body: `{templates, families, exclude}`) |
| Resync PDFs Drive | `POST /api/storage/resync-drive?folder=<id>` |

**Script** : `send_invoices_email.send_invoices_batch`  
**Durée** : longue → fire-and-poll

---

### 8. `page_reminders` → `/reminders` (Rappels paiement) — flow 4 étapes
**Étapes** : (1) choix dossier → (2) charger impayés Notion → (3) éditer template (3 langues) → (4) envoi.

**3 templates** : FR, EN, Carole (mêmes règles que Send).

**Logique automatique** (`should_send_automatic_reminder`) : `Invoice date` > 10 jours AND `Payé != true` AND pas de rappel dans les 7 derniers jours. Stocke "Last reminder" dans Notion.

**Pièces jointes PDF** : même logique strict que Send.

| Action | Endpoint |
|---|---|
| Charger familles impayées | `GET /api/reminders/unpaid?folder=<id>` |
| Aperçu par template | `GET /api/reminders/preview?folder=<id>` |
| Test envoi | `POST /api/reminders/test` |
| Envoi batch | `POST /api/reminders/send` |
| Auto-detect candidats | `GET /api/reminders/auto-candidates` |

**Script** : `send_payment_reminders.send_payment_reminders`  
**Durée** : moyenne → fire-and-poll

---

### 9. `page_sync` → `/sync` (Sync Stripe → Notion)

**⚠️ CRITIQUE — DEUX services de sync différents** :

**A. Sync manuel depuis l'app** (`/sync` page) : parcourt charges Stripe période donnée + match lignes Notion (critique E) + marque payé.

**B. Webhook Stripe automatique sur Render** (service séparé) :
- URL : `https://professorplus-webhook.onrender.com/stripe-webhook`
- Événements : `charge.succeeded`, `charge.refunded`, `charge.failed`
- Vérification signature Stripe (`STRIPE_WEBHOOK_SECRET`)
- Compatibility Stripe SDK v15 (critique D)
- Fallback `parent_name` depuis PaymentLink API si absent
- Fichiers : `sync_engine.py` (split) + `no_prof_sync_stripe_notion.py` (no-split)
- Stack : FastAPI minimal + `requirements.txt` + `server.py`
- **Déploiement séparé** du backend principal

**Critères de matching** : prof + élève + montant + invoice_date (préférentiel, critique E).

| Action | Endpoint |
|---|---|
| Sync no-split (manuel) | `POST /api/sync/stripe-to-notion?mode=no-split` |
| Sync normal 2 phases | `POST /api/sync/stripe-to-notion?mode=normal` |
| Voir derniers logs webhook | `GET /api/sync/webhook-logs` |
| Status webhook | `GET /api/sync/webhook-status` |

**Scripts** : `no_prof_sync_stripe_notion.sync_stripe_to_notion`, `sync_stripe_notion.sync_stripe_to_notion`, `update_notion_prof_pages.run_update_notion_prof_pages`  
**Durée** : longue → fire-and-poll

---

### 10. `page_update` → `/update-notion` (Ajouter lignes Notion) — 3 onglets
**Tab 1** : ajout massif. **Tab 2** : par famille ou par prof. **Tab 3** : scan-compare.

**Données ajoutées par ligne Notion** : Famille, Profs (multi), Élèves (multi), Montant dû, Devise, Heures (`"X.Xh"`), Date cours range, Invoice date, Stripe link, Stripe payment link ID, Status payé.

**Cas n-2 consolidés** (critique C) :
- `additional_amounts: {family_id: {amount, hours, dates}}`
- Montant final = montant Stripe (depuis `payment_links_output.json`) si dispo, sinon `lessons_amount + prev_amount`
- Heures totales = courantes + n-2
- Plage de dates étendue : `min(toutes_dates) → max(toutes_dates)`
- Filter `AbsentNotice` (critique H)

**Devise** : `family.currency` (Notion prime sur TB) ; override EUR si famille dans `familles_euros.yaml` ; sinon CHF par défaut.

**Scan-compare (Tab 3)** : lit PDFs Drive + lignes Notion du mois → familles avec PDF mais sans ligne = "Manquantes". Bouton "Ajouter manquantes".

| Action | Endpoint |
|---|---|
| Ajouter toutes les lignes | `POST /api/update-notion/all` (body: `{folder_id, skip_prof_pages}`) |
| Ajouter par sélection | `POST /api/update-notion/selection` (body: `{by, names}`) |
| Scan-compare | `GET /api/update-notion/scan-compare?folder=<id>` |
| Ajouter manquantes | `POST /api/update-notion/add-missing` |
| Charger impayés n-2 | `GET /api/update-notion/unpaid-data?year=&month=` |

**Script** : `update_notion.run_update_notion`  
**Durée** : longue → fire-and-poll

---

### 11. `page_config` → `/settings` (Configuration) — 5 onglets

**Tab 1 — Profs** (10 CHF + N Notion EUR/AED) : nom, email, taux horaire, devise, % part prof (split), Stripe Connect Account ID. Status Connect : ✅ active / ⚠️ pending / ❌ aucun. Bouton "Tester Stripe Connect".

**Tab 2 — Familles EUR** : `familles_euros.yaml` sur Drive
```yaml
euros:
  - "Calabresi Aurélie"
  - "Briere Pierre"
  - "Tessier Carole"
```

**Tab 3 — Tarifs spéciaux** : `{parent_name, student_name, hourly_rate, currency, language}` → `tarifs_speciaux.yaml`.

**Tab 4 — Email** : `gmail_email` + `gmail_app_password` + test envoi.

**Tab 5 — Drive** : test lecture, test écriture, Service Account Email, Drive Root Folder ID, refresh OAuth token.

**FX Rate live** (footer) : Frankfurter CHF/EUR + AED/USD + USD/EUR.

| Action | Endpoint |
|---|---|
| Profs (CRUD) | `GET/POST/PATCH/DELETE /api/teachers[/{id}]` |
| Statut Stripe Connect prof | `GET /api/teachers/{id}/stripe-status` |
| Familles EUR (CRUD) | `GET/POST/DELETE /api/families-eur` |
| Tarifs spéciaux (CRUD) | `GET/POST/DELETE /api/special-rates` |
| Config email | `GET/PUT /api/settings/email` |
| Test Drive lecture | `GET /api/storage/drive-test` |
| Test écriture Drive | `POST /api/storage/drive-write-test` |
| Refresh OAuth token | `POST /api/storage/drive-refresh-token` |
| Taux FX live | `GET /api/fx-rate?from=CHF&to=EUR` |
| Status Frankfurter | `GET /api/fx-rate/status` |

---

### 12. `page_profs` → `/teachers-payroll` (Récap paie profs)
**Header** : "👨‍🏫 Récapitulatif Professeurs — [Mois]"

**Header card** : Total à verser EUR + Taux FX live + source + Date d'extraction + Période + Bouton "Auto CHF".

**3 cartes metrics** : Total profs EUR | Total CHF (converti EUR) | Total AED (via USD peg).

**Expander par prof** : 3 metrics (nb leçons, total brut, total payé) + tableau leçons (Date | Élève | Famille | Durée | Montant client | Taux prof | Montant prof | Devise) + boutons "Email à ce prof" / "Test à moi-même".

**Auto CHF** : checkbox + input cible EUR (ex: 1500 €) → calcul taux CHF = `montant_eur / chf_eur_rate × heures` → MAJ taux affichés.

**Frankfurter — chaîne de fallback** :
1. Frankfurter API (`https://api.frankfurter.app`)
2. ECB (XML)
3. Taux hardcodé
4. Footer PDF : "FX source: Frankfurter (CHF/EUR=1.0712, AED/USD=3.6725 peg, USD/EUR=0.9234)"

**Conversion par leçon** :
- EUR → direct
- CHF → × `taux CHF/EUR`
- AED → × `peg USD/AED` → × `taux USD/EUR`
- Tarifs spéciaux par devise depuis `tarifs_speciaux.yaml`

**PDFs profs** : metric cards en haut + tableau styled + footer FX + pagination >15 leçons + format `"22h45"` + header logo.

**ZIP / PDF combiné** : ZIP = 1 PDF/prof ; PDF combiné = tous les profs en un seul.

| Action | Endpoint |
|---|---|
| Récap profs | `GET /api/payroll/summary?year=&month=&auto_chf_target=` |
| PDF prof | `GET /api/payroll/{teacher}.pdf?year=&month=` |
| Email à 1 prof | `POST /api/payroll/send-one` |
| Test à moi-même | `POST /api/payroll/send-test` |
| Envoi à tous | `POST /api/payroll/send-all` |
| ZIP | `GET /api/payroll/zip?year=&month=` |
| PDF combiné | `GET /api/payroll/combined.pdf?year=&month=` |
| Taux FX courant + source | `GET /api/payroll/fx-status` |

**Scripts** : `recap_profs.calculate_prof_recap`, `recap_profs.fetch_fx_rate`, `recap_profs.fetch_chf_eur_rate`, `recap_profs.compute_teacher_recap`, `generate_prof_pdfs.run_generate_prof_summary_pdf`  
**Durée** : longue → fire-and-poll

---

## 🔧 Mapping scripts → services backend

| Script | Service backend | Durée | Pattern |
|---|---|---|---|
| extract_tutorbird | `services/tutorbird.py` | long | async job |
| fetch_notion_profs | `services/notion.py::fetch_profs_hors_tb` | moyen | sync |
| fetch_unpaid_notion | `services/notion.py::unpaid_n2` | moyen | sync |
| create_payment_links | `services/stripe.py::create_links` | long | async job |
| create_payment_links_no_split | `services/stripe.py::create_links_no_split` | long | async job |
| activate_twint | `services/stripe.py::twint` | moyen | sync |
| generate_invoices | `services/invoices.py::generate` | long | async job |
| send_invoices_email | `services/email.py::send_invoices` | long | async job |
| send_payment_reminders | `services/email.py::send_reminders` | moyen | sync ou async |
| sync_stripe_notion | `services/sync.py::stripe_to_notion` | long | async job |
| no_prof_sync_stripe_notion | `services/sync.py::stripe_to_notion_no_split` | long | async job |
| **sync_engine + server (Render)** | **service séparé Render** | continu (webhook) | event-driven |
| update_notion | `services/notion.py::add_lessons` | long | async job |
| update_notion_prof_pages | `services/notion.py::update_prof_pages` | long | async job |
| cleanup_notion | `services/notion.py::cleanup` | long | async job |
| recap_profs + generate_prof_pdfs | `services/payroll.py` | long | async job |
| google_drive + storage_manager | `services/storage.py` | court | sync |
| config_loader | `services/config.py` | court | sync |
| quotes_data | `services/quotes.py` | court | sync |
| generate_refresh_token | utilitaire CLI, **pas exposé en API** | — | — |

---

## 🗄️ Stockage — Source of truth pour chaque fichier

| Fichier | Type | Localisation | Lu par | Écrit par |
|---|---|---|---|---|
| `secrets.yaml` | Config sensible | Drive (lu dyn) + cache /tmp | tous services | settings page |
| `familles_euros.yaml` | Config | Drive | extract, invoices, payment_links, payroll | settings |
| `tarifs_speciaux.yaml` | Config | Drive | invoices, payroll | settings |
| `full_output_tb_SIMPLE.json` | Données | Drive + cache /tmp | invoices, payment_links, payroll, send, reminders | extract |
| `full_output_tb_YYYY-MM.json` | Archive | Drive | rechargement historique | extract |
| `payment_links_output.json` | Liens Stripe | Drive + cache /tmp | invoices, send (multi), update_notion, sync | payment_links |
| `teacher_emails.json` | Emails profs | Drive + cache /tmp | payroll, send | extract |
| Factures PDFs | Sortie | Drive (`Factures/YYYY/Mois YYYY - DD-MM HHhMM/<Famille>/Facture_*.pdf`) + local | send, reminders | invoices |
| PDFs paie profs | Sortie | Drive (`Paie profs/YYYY/Mois YYYY/Recap_*.pdf`) + local | (envoi email) | payroll |

**Variables d'environnement Railway** :
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` (sur Render)
- `NOTION_TOKEN`, `NOTION_PAYMENTS_DB_ID`, `NOTION_PROFS_HORS_TB_DB_ID`, `NOTION_TEACHERS_PAGES_PARENT_ID`
- `GMAIL_USER`, `GMAIL_APP_PASSWORD`
- `TUTORBIRD_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (base64), `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `FRANKFURTER_API_URL` (default `https://api.frankfurter.app`)
- `OPENAI_API_KEY` (citations)
- `API_KEY` (auth `X-API-Key`)
- `FRONTEND_ORIGIN` (CORS)

---

## 🏗️ Pattern jobs longs (fire-and-poll)

**Persistance** : SQLite local (pas dict mémoire) pour survivre aux redéploiements Railway.

```
POST /api/extract                  → 202 Accepted, {job_id: "abc123"}
                                     (BackgroundTasks FastAPI + persiste SQLite)

GET /api/jobs/abc123               → 200 OK, {
                                       status: "running" | "done" | "error",
                                       progress: 0.42,
                                       logs: ["...", "..."],
                                       result: { ... } // si done
                                     }
```

**Streaming logs** : Server-Sent Events (`/api/jobs/{id}/stream`) en plus du polling 2s.

**Cleanup** : jobs > 24h supprimés auto.

Frontend : composant `<JobRunner>` (poll 2s + SSE), terminal style + barre progression. Réutilisable.

---

## 🎨 Composants frontend partagés à créer

`<PageHeader>`, `<StatsCard>`, `<TerminalLog>` (fond `#0D1117`), `<JobRunner>` (poll + SSE), `<EmptyState>`, `<WorkflowStepper>`, `<ActivityTimeline>`, `<DataTable>` (shadcn), `<ConfirmDialog>`, `<CurrencyAmount>` (EUR/CHF/AED), `<TeacherCard>`, `<FamilyCard>`, `<InvoicePreview>`, `<TemplatePreview>`, `<MultiCurrencyTotal>`, `<NetCalculation>`, `<FXRateBadge>`.

---

## 🗺️ Routing Next.js (App Router)

```
app/
├── layout.tsx              → AppLayout
├── page.tsx                → Dashboard
├── extract/page.tsx
├── twint/page.tsx
├── cleanup/page.tsx
├── payment-links/page.tsx
├── invoices/page.tsx
├── send-invoices/page.tsx
├── reminders/page.tsx
├── sync/page.tsx
├── update-notion/page.tsx
├── settings/
│   ├── page.tsx            → redirect /settings/teachers
│   ├── teachers/page.tsx
│   ├── families-eur/page.tsx
│   ├── special-rates/page.tsx
│   ├── email/page.tsx
│   └── drive/page.tsx
├── teachers-payroll/page.tsx
└── showcase/page.tsx       → design system preview (interne)
```

---

## 📦 Arborescence cible du projet

```
professor_plus_V9 - Copie_Claude_ia/
├── app.py                              ← Streamlit (gardé en backup)
├── pages/                              ← Streamlit pages
├── scripts/                            ← scripts métier (réutilisés par backend)
├── config/, data/, Factures/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routes/
│   │   ├── services/                   ← wrappers vers ../scripts/*.py
│   │   ├── jobs/                       ← fire-and-poll + SQLite
│   │   └── core/config.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
│
├── webhook/                            ← service séparé Render
│   ├── sync_engine.py
│   ├── server.py
│   ├── requirements.txt
│   └── render.yaml
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── package.json
│   ├── tailwind.config.ts
│   └── next.config.js
│
├── docker-compose.yml
├── .gitignore                          ← exclut Fares_appli/, .venv, node_modules
├── MIGRATION_SPEC.md
└── README.md

🚫 Fares_appli/                          ← IGNORÉ TOTALEMENT
```

---

## 🧪 Stratégie de tests & validation

### Tests backend (pytest)
Services critiques : extract, invoices, payment_links, sync. Mocks Notion/Stripe/TutorBird. Fixtures multi-devise.

### Tests intégration
Pipeline complet extract → payment_links → invoices → send (faux SMTP). AED + multi-mois + Carole.

### Phase de comparaison Streamlit ↔ Next.js (1-2 mois en parallèle)
- [ ] Extraction : `full_output_tb_SIMPLE.json` byte-à-byte
- [ ] Payment links : `payment_links_output.json` byte-à-byte
- [ ] PDFs factures : visuel 10 familles random
- [ ] PDFs Carole : OCTOPUS SARL + adresse Monaco
- [ ] PDFs multi-mois : section "Rappel" + montant cumulé
- [ ] Emails : 1 test/template (FR, EN, Carole, Multi)
- [ ] Sync Stripe → Notion : paiement test, vérifier matching dans les 2 apps
- [ ] Webhook Render : checker logs
- [ ] Recap profs : montants EUR à l'euro près
- [ ] PDFs paie profs : FX footer + tableau leçons

### Critères Go/No-Go pour archiver Streamlit
- ✅ 1 mois prod sur Next.js sans bug bloquant
- ✅ Emails clients identiques aux versions Streamlit
- ✅ Pas de désynchronisation Stripe ↔ Notion
- ✅ FX rates cohérents (fallback chain ECB → hardcoded testée)
- ✅ Service Account Drive quota OK (replace au lieu de create)

---

## ✅ Plan de migration par étapes (par commit)

1. ✅ Inventaire complet (ce document)
2. Scaffold backend FastAPI (squelette + `/api/health`) + SQLite jobs
3. Scaffold webhook Render (séparé) + déploiement initial
4. Scaffold frontend Next.js + shadcn + design system + composants partagés
5. **PoC bout-en-bout** : page Extract + endpoint `/api/extract` + JobRunner + SSE
6. Page Settings (CRUD profs/familles EUR/tarifs/email/drive)
7. Page Dashboard (multi-currency)
8. Page Payment Links (n-2 + AED + désactivation anciens liens)
9. Page Invoices (Carole + multi-mois + cleanup local + replace Drive)
10. Page Send + Reminders (4 templates + aperçu par tab + matching strict)
11. Page Sync (manuel + ping webhook Render)
12. Page Update Notion (additional_amounts {amount, hours, dates})
13. Page Cleanup + Twint
14. Page Teachers Payroll (Auto CHF + Frankfurter fallback)
15. Tests locaux + docker-compose
16. Déploiement Vercel + Railway + Render
17. **Phase de comparaison avec Streamlit (1-2 mois)**
18. Archivage Streamlit dans `_legacy/` quand validé

---

## 🐛 Bugs historiques à NE PAS recréer

À tester explicitement après migration :

1. **Pisanello recevait le PDF de Diallo** : matching fortuit 0.714 → `names_match` strict + meilleur match
2. **Aseelah PDF 0 bytes** : génération PDF échoue silencieusement pour AED → vérifier
3. **Stripe SDK v15 KeyError: 0** : `dict(metadata)` → `metadata.to_dict()`
4. **Calabresi sync échoue** : invoice_date différente entre régénération et Notion → préférentiel
5. **Service Account quota** : ne peut pas créer, seulement update → replace logic
6. **Carole compte en EUR avec montant gonflé** : fusion CHF+EUR sans conversion → calcul leçon par leçon avec `source` flag
7. **Multimonth template jamais appliqué** : signature fonction n'acceptait pas le param → vérifier
8. **n-2 ligne Notion incomplète** : seul montant ajouté → dict `{amount, hours, dates}`
9. **Régénération facture crée doublon Drive** : nom différent (date du jour) → cleanup local + replace Drive
10. **Templates email anglais absents pour rappels** : seul Carole + FR supportés → ajouter EN
