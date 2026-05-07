# MIGRATION_SPEC — Professor+ : Streamlit → Next.js + FastAPI

> Document de référence pour la migration. **Aucune feature ne doit être perdue.**
> Tout ce qui n'est pas listé ici n'est pas dans le périmètre.

---

## 🚫 Hors périmètre

- Le dossier `Fares_appli/` est **totalement exclu** : pas migré, pas lu, pas déployé.

---

## 🎯 Stack cible

| Couche | Technologie | Hébergement |
|---|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + framer-motion + react-query + lucide-react + Sonner (toasts) | Vercel |
| Backend | FastAPI + scripts Python existants wrappés en services | Railway |
| Auth | Header `X-API-Key` (mono-user) | — |
| DB métier | **Notion** (inchangé) | — |
| Storage | **Google Drive** (inchangé) | — |
| Jobs longs | Pattern fire-and-poll (dict en mémoire FastAPI) | — |

**Palette par défaut** (à valider) : `#1F3A67` (primary) + `#14B8A6` (accent) + sidebar gradient `#1A1F2E → #151922` + Inter.

---

## 📑 Inventaire des 12 pages — mapping vers Next.js + endpoints

### 1. `page_accueil` → `/` (Dashboard)
**Header** : "🎓 Professor+ Admin"  
**Composants** : 4 stats cards (Profs, Familles, À facturer multi-devise CHF/EUR/AED, Net EUR), 3 cards paiements + barre progression, 3 cards historique envois, 2 cards citations (Hadith + Citation du jour), 3 boutons quick actions, info box workflow recommandé.

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
**Composants** : 3 quick-pick mois, date pickers début/fin, time pickers (cachables si jour entier), liste profs hors TutorBird (multiselect avec refresh), résultats par devise.

| Action | Endpoint |
|---|---|
| Charger profs hors TB | `GET /api/notion/profs-hors-tb` |
| Lancer extraction | `POST /api/extract` → `{job_id}` |
| Polling job | `GET /api/jobs/{id}` (logs streamés + progression) |

**Script wrappé** : `extract_tutorbird.run_extraction(...)` + `fetch_notion_profs.run_fetch_notion_profs(...)`  
**Durée** : longue (>30s) → **fire-and-poll obligatoire**

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
**Tabs** : Scanner dates / Supprimer anciennes / Nettoyer doublons

| Action | Endpoint |
|---|---|
| Scanner dates Notion | `GET /api/cleanup/scan-dates` |
| Supprimer anciennes (avec dry-run) | `POST /api/cleanup/delete-old` (body: `{cutoff_date, dry_run}`) |
| Nettoyer doublons | `POST /api/cleanup/duplicates` (body: `{dry_run}`) |

**Script** : `cleanup_notion.run_cleanup_duplicates`, `run_scan_notion_dates`, `run_delete_old_rows`  
**Durée** : longue → fire-and-poll

---

### 5. `page_payment` → `/payment-links` (Liens de paiement) — 2 onglets
**Tab 1** (générer) : 3 quick-pick mois, toggle no-split, checkbox méthodes (Carte/Link/Apple Pay/Google Pay), checkbox impayés n-2, multiselect "On Behalf Of".  
**Tab 2** (régénérer) : multiselect familles.

| Action | Endpoint |
|---|---|
| Générer liens (avec split) | `POST /api/payment-links/create` |
| Générer liens (no-split) | `POST /api/payment-links/create?no_split=true` |
| Régénérer pour familles | `POST /api/payment-links/regenerate` (body: `{families: []}`) |
| Relancer manquants | `POST /api/payment-links/retry-missing` |
| Statut profs Stripe Connect | `GET /api/teachers/stripe-status` |

**Scripts** : `create_payment_links.run_create_payment_links`, `create_payment_links_no_split.run_create_payment_links_no_split`  
**Durée** : longue → fire-and-poll

---

### 6. `page_invoices` → `/invoices` (Génération factures) — 2 onglets
**Tab 1** (générer batch) : radio dossier (nouveau/existant), checkbox copie locale, checkbox impayés n-2 + selectbox mois (n-2 défaut, 6 mois back).  
**Tab 2** (régénérer) : multiselect familles.

| Action | Endpoint |
|---|---|
| Générer factures | `POST /api/invoices/generate` (body: `{folder_mode, include_unpaid_n2, target_month}`) |
| Détecter impayés Notion | `GET /api/invoices/unpaid-detect?year=&month=` |
| Régénérer pour familles | `POST /api/invoices/regenerate` |
| Télécharger ZIP | `GET /api/invoices/{folder_id}/download` |
| Télécharger 1 PDF | `GET /api/invoices/{folder_id}/{family}.pdf` |

**Scripts** : `generate_invoices.run_generate_invoices`, `fetch_unpaid_notion.fetch_unpaid_n2`  
**Durée** : longue → fire-and-poll

---

### 7. `page_send` → `/send-invoices` (Envoi factures) — 4 onglets templates
**Tabs** : 🇫🇷 FR / 🇬🇧 EN / 👩 Carole Tessier / 📌 Multi-mois  
**Composants** : sujet + message, radio toutes/sélection, checkbox test à moi-même, multiselect inclusion/exclusion.

| Action | Endpoint |
|---|---|
| Diagnostic (PDFs/emails dispo) | `GET /api/send/diagnostic?folder=<id>` |
| Test envoi à soi-même | `POST /api/send/test` (body: `{template, subject, body}`) |
| Envoi batch | `POST /api/send/invoices` (body: `{template, subject, body, families, exclude}`) |
| Resync PDFs Drive | `POST /api/storage/resync-drive?folder=<id>` |

**Script** : `send_invoices_email.send_invoices_batch`  
**Durée** : longue → fire-and-poll

---

### 8. `page_reminders` → `/reminders` (Rappels paiement) — flow 4 étapes
**Étapes** : (1) choix dossier → (2) charger impayés Notion → (3) éditer template (3 langues) → (4) envoi.

| Action | Endpoint |
|---|---|
| Charger familles impayées | `GET /api/reminders/unpaid?folder=<id>` |
| Test envoi | `POST /api/reminders/test` |
| Envoi batch | `POST /api/reminders/send` |

**Script** : `send_payment_reminders.send_payment_reminders`  
**Durée** : moyenne → sync ou fire-and-poll selon volume

---

### 9. `page_sync` → `/sync` (Sync Stripe → Notion)
**Inputs** : toggle no-split (défaut true), checkbox "depuis dernier dossier" / date picker.

| Action | Endpoint |
|---|---|
| Sync no-split | `POST /api/sync/stripe-to-notion?mode=no-split` |
| Sync normal (2 phases) | `POST /api/sync/stripe-to-notion?mode=normal` |

**Scripts** : `no_prof_sync_stripe_notion.sync_stripe_to_notion`, `sync_stripe_notion.sync_stripe_to_notion`, `update_notion_prof_pages.run_update_notion_prof_pages`  
**Durée** : longue → fire-and-poll

---

### 10. `page_update` → `/update-notion` (Ajouter lignes Notion) — 3 onglets
**Tab 1** : ajout massif (radio dossier, checkbox skip pages profs).  
**Tab 2** : par famille ou par prof (multiselect).  
**Tab 3** : scan-compare (compare factures Drive vs lignes Notion → liste manquantes).

| Action | Endpoint |
|---|---|
| Ajouter toutes les lignes | `POST /api/update-notion/all` |
| Ajouter par sélection | `POST /api/update-notion/selection` (body: `{by: "family"|"teacher", names: []}`) |
| Scan-compare | `GET /api/update-notion/scan-compare?folder=<id>` |
| Ajouter manquantes | `POST /api/update-notion/add-missing` |

**Script** : `update_notion.run_update_notion`  
**Durée** : longue → fire-and-poll

---

### 11. `page_config` → `/settings` (Configuration) — 5 onglets
**Tab 1 (Profs)** : sous-onglets ajouter/modifier  
**Tab 2 (Familles EUR)** : data editor + ajout manuel  
**Tab 3 (Tarifs spéciaux)** : data editor  
**Tab 4 (Email)** : Gmail + app password  
**Tab 5 (Drive)** : tests connexion + écriture

| Action | Endpoint |
|---|---|
| Liste profs | `GET /api/teachers` |
| Ajouter prof | `POST /api/teachers` |
| Modifier prof | `PATCH /api/teachers/{id}` |
| Supprimer prof | `DELETE /api/teachers/{id}` |
| Familles EUR (CRUD) | `GET/POST/DELETE /api/families-eur` |
| Tarifs spéciaux (CRUD) | `GET/POST/DELETE /api/special-rates` |
| Config email | `GET/PUT /api/settings/email` |
| Test Drive | `GET /api/storage/drive-test` |
| Test écriture Drive | `POST /api/storage/drive-write-test` |
| Taux FX live | `GET /api/fx-rate?from=CHF&to=EUR` |

**Stockage** : `secrets.yaml` + `familles_euros.yaml` + `tarifs_speciaux.yaml` (lus/écrits via `config_loader.py` + `google_drive.py`)

---

### 12. `page_profs` → `/teachers-payroll` (Récap paie profs)
**Header** : "👨‍🏫 Récapitulatif Professeurs — [Mois]"  
**Composants** : header card avec taux FX live + total, 3 cartes metrics, expander par prof (3 metrics + tableau leçons), section envoi (test/global), génération ZIP/PDF combiné.

| Action | Endpoint |
|---|---|
| Récap profs (calculs) | `GET /api/payroll/summary?year=&month=` |
| Télécharger PDF prof | `GET /api/payroll/{teacher}.pdf` |
| Email à 1 prof | `POST /api/payroll/send-one` (body: `{teacher}`) |
| Test à moi-même | `POST /api/payroll/send-test` |
| Envoi à tous | `POST /api/payroll/send-all` |
| Générer ZIP | `GET /api/payroll/zip?year=&month=` |
| Générer PDF combiné | `GET /api/payroll/combined.pdf?year=&month=` |

**Scripts** : `recap_profs.calculate_prof_recap`, `recap_profs.fetch_fx_rate`, `generate_prof_pdfs.run_generate_prof_summary_pdf`  
**Durée** : longue → fire-and-poll pour ZIP/PDF combiné

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
| update_notion | `services/notion.py::add_lessons` | long | async job |
| update_notion_prof_pages | `services/notion.py::update_prof_pages` | long | async job |
| cleanup_notion | `services/notion.py::cleanup` | long | async job |
| recap_profs + generate_prof_pdfs | `services/payroll.py` | long | async job |
| google_drive + storage_manager | `services/storage.py` | court | sync |
| config_loader | `services/config.py` | court | sync |
| quotes_data | `services/quotes.py` | court | sync |
| generate_refresh_token | utilitaire CLI, **pas exposé en API** | — | — |

---

## 🔑 Configuration & secrets (depuis secrets.yaml actuel)

À transférer en variables d'environnement Railway :
- `STRIPE_SECRET_KEY` (+ `STRIPE_PUBLISHABLE_KEY`)
- `NOTION_TOKEN`
- `NOTION_PAYMENTS_DB_ID` (Paiements – Base Centrale)
- `NOTION_PROFS_HORS_TB_DB_ID`
- `NOTION_TEACHERS_PAGES_PARENT_ID`
- `GMAIL_USER` + `GMAIL_APP_PASSWORD`
- `TUTORBIRD_API_KEY` (ou cookies session)
- `GOOGLE_SERVICE_ACCOUNT_JSON` (base64 du JSON actuel)
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `API_KEY` (pour auth header X-API-Key)
- `FRONTEND_ORIGIN` (CORS)

À garder dans Drive (lus dynamiquement) :
- `secrets.yaml` (teachers, no_prof_secret)
- `familles_euros.yaml`
- `tarifs_speciaux.yaml`

---

## 🏗️ Pattern jobs longs (fire-and-poll)

```
POST /api/extract                  → 202 Accepted, body: {job_id: "abc123"}
                                   (lance la tâche en BackgroundTasks FastAPI)

GET /api/jobs/abc123               → 200 OK, body: {
                                       status: "running" | "done" | "error",
                                       progress: 0.42,
                                       logs: ["Extraction prof X...", "..."],
                                       result: { ... } // si done
                                     }
```

Côté frontend : composant `<JobRunner endpoint=... onComplete=... />` qui poll toutes les 2s et affiche un terminal style + barre de progression. Réutilisé partout.

---

## 🎨 Composants frontend partagés à créer

- `<PageHeader title subtitle icon breadcrumbs />`
- `<StatsCard label value icon trend />`
- `<TerminalLog logs />` (fond noir, monospace, auto-scroll)
- `<JobRunner endpoint payload onComplete />` (fire-and-poll universel)
- `<EmptyState icon title description action />`
- `<WorkflowStepper steps activeStep />`
- `<ActivityTimeline items />`
- `<DataTable columns rows searchable filterable />` (shadcn)
- `<ConfirmDialog />` (avant actions destructives)
- `<CurrencyAmount value currency />` (gère EUR/CHF/AED)
- `<TeacherCard teacher />`
- `<FamilyCard family />`
- `<InvoicePreview pdfUrl />`

---

## 🗺️ Routing Next.js (App Router)

```
app/
├── layout.tsx              → AppLayout (sidebar + topbar)
├── page.tsx                → Dashboard (page_accueil)
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
│   ├── teachers/page.tsx
│   ├── families-eur/page.tsx
│   ├── special-rates/page.tsx
│   ├── email/page.tsx
│   └── drive/page.tsx
└── teachers-payroll/page.tsx
```

---

## 📦 Arborescence cible du projet

```
professor_plus_V9 - Copie_Claude_ia/    ← repo actuel (on garde Streamlit en backup)
├── app.py                              ← Streamlit (laissé en place tant que la migration n'est pas validée)
├── pages/                              ← Streamlit pages (idem)
├── scripts/                            ← scripts métier (réutilisés tels quels par le backend)
├── config/                             ← YAML configs (lus par les deux apps)
├── data/                               ← données extraites
├── Factures/                           ← PDFs locaux
│
├── backend/                            ← NOUVEAU
│   ├── app/
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routes/
│   │   ├── services/                   ← wrappers vers ../scripts/*.py
│   │   ├── jobs/                       ← gestion fire-and-poll
│   │   └── core/config.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
│
├── frontend/                           ← NOUVEAU
│   ├── app/                            ← Next.js App Router
│   ├── components/
│   ├── lib/
│   ├── package.json
│   ├── tailwind.config.ts
│   └── next.config.js
│
├── docker-compose.yml                  ← dev local front + back
├── .gitignore                          ← exclut Fares_appli/, .venv, node_modules
├── MIGRATION_SPEC.md                   ← ce document
└── README.md

🚫 Fares_appli/                          ← IGNORÉ TOTALEMENT
```

---

## ✅ Plan de migration par étapes (par commit)

1. ✅ Inventaire complet (ce document)
2. Scaffold backend FastAPI (squelette + 1 endpoint test `/api/health`)
3. Scaffold frontend Next.js + shadcn/ui + design system + composants partagés
4. **PoC bout-en-bout** : page Extract + endpoint `/api/extract` + JobRunner (valide fire-and-poll)
5. Page Settings (CRUD profs/familles/tarifs/email/drive)
6. Page Dashboard (lecture seule, juste des metrics)
7. Page Invoices + Payment Links (les 2 plus gros services)
8. Pages Send + Reminders + Sync + Update + Cleanup + Twint
9. Page Teachers Payroll
10. Tests locaux + docker-compose
11. Déploiement Vercel + Railway
12. Phase de comparaison avec Streamlit (1-2 semaines)
13. Archivage Streamlit dans `_legacy/` quand validé
