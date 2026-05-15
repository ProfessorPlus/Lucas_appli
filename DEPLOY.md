# Déploiement — Vercel (frontend) + Railway (backend)

Le webhook Stripe reste sur **Render** (séparé, déjà déployé).

```
            ┌─────────────────────────────┐
            │ Browser                     │
            └──────────────┬──────────────┘
                           │ HTTPS
                ┌──────────▼──────────┐
                │ Vercel              │  frontend/  (Next.js)
                │ professorplus.vercel│
                └──────────┬──────────┘
                           │ /api/backend/* rewrite
                ┌──────────▼──────────┐
                │ Railway             │  Dockerfile racine (FastAPI)
                │ X.up.railway.app    │  ── lit configs depuis Drive
                └──────┬─────────┬────┘
                       │         │
                ┌──────▼──┐   ┌──▼─────────┐
                │ Notion  │   │ Stripe API │
                │ Drive   │   └────────────┘
                │ Gmail   │
                │ TutorBird│
                └──────────┘

   (En parallèle, déjà existant — ne change pas)
   ┌────────────┐
   │ Render     │  stripe-webhook-professorplus
   │ webhooks   │  ── reçoit charge.succeeded → marque Notion payé
   └────────────┘
```

---

## 0. Pré-requis

- Compte GitHub : ton repo `ProfessorPlus/Lucas_appli` est déjà push (branche `migration-nextjs`)
- Compte Railway : https://railway.app — gratuit jusqu'à 5$/mois de credits
- Compte Vercel : https://vercel.com — gratuit pour projets perso
- Le fichier `google_service_account.json.json` (à la racine du projet) → **on va le copier en base64 dans une variable Railway**

---

## 1. Backend → Railway

### 1.1 Crée le projet

1. Va sur https://railway.app/new
2. **"Deploy from GitHub repo"** → choisis `Lucas_appli`
3. **Branch** : `migration-nextjs`
4. Railway détecte automatiquement le `Dockerfile` à la racine + `railway.toml`
5. Clique **"Deploy"** — le premier build prend ~5 min

### 1.2 Configure les variables d'environnement

Va dans **Variables** de ton service Railway et ajoute :

#### Secrets indispensables

| Variable | Valeur | Comment l'obtenir |
|---|---|---|
| `API_KEY` | une chaîne longue aléatoire | `python -c "import secrets; print(secrets.token_urlsafe(32))"` — **mémorise-la, tu l'utiliseras côté Vercel** |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | (long base64) | Voir 1.3 ci-dessous |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | `19Kco_Tu_gZxVgzWuQb5gvB7-7Z3LS-8E` | C'est l'ID de ton dossier `Professor_Plus_Data` sur Drive (le récupère depuis l'URL) |
| `FRONTEND_ORIGIN` | `https://<TON-PROJET>.vercel.app` | Tu le mettras après avoir déployé Vercel (étape 2) |

#### Optionnel mais utile

| Variable | Valeur par défaut |
|---|---|
| `JOBS_RETENTION_HOURS` | `24` |

⚠️ **Tu n'as PAS besoin** de remettre `STRIPE_SECRET_KEY`, `NOTION_TOKEN`, `GMAIL_*`, `TUTORBIRD_*` ici → ces clés sont déjà dans ton `secrets.yaml` sur Drive, le backend les charge automatiquement.

### 1.3 Générer le base64 du service account

Sur ton Mac/PC, dans un terminal au dossier du projet :

**Windows PowerShell :**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("google_service_account.json.json")) | Set-Clipboard
```
(le base64 est maintenant dans le presse-papier — paste dans Railway)

**Mac/Linux :**
```bash
base64 -w 0 google_service_account.json.json | pbcopy
```

Dans Railway → variable `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` → colle la valeur.

### 1.4 Vérifie le déploiement

1. Une fois redéployé, Railway donne une URL : `https://professor-plus-backend-production.up.railway.app` (ou similaire)
2. **Test santé** : ouvre `<URL>/api/health` → doit afficher `{"status":"ok"}`
3. **Test auth** : ouvre `<URL>/api/settings/teachers` → doit afficher `{"detail":"Invalid or missing X-API-Key header"}` (signe que l'auth marche)
4. **Test data** : avec `curl` :
   ```bash
   curl -H "X-API-Key: <ta-API_KEY>" <URL>/api/settings/teachers
   ```
   → doit te lister tes 13 profs

Si ça plante :
- Railway → Deployments → clique sur le dernier deploy → **Logs** : tu verras la stacktrace
- Vérifie les variables d'env (notamment le base64 — il ne doit pas contenir de saut de ligne)

---

## 2. Frontend → Vercel

### 2.1 Crée le projet

1. Va sur https://vercel.com/new
2. **"Import Git Repository"** → choisis `Lucas_appli`
3. **Configure Project** :
   - **Framework Preset** : Next.js (auto-détecté)
   - **Root Directory** : `frontend` ← important !
   - **Production Branch** : `migration-nextjs` (Settings → Git après création)

### 2.2 Variables d'environnement

Ajoute dans **Environment Variables** :

| Variable | Valeur | Notes |
|---|---|---|
| `BACKEND_URL` | `https://professor-plus-backend-production.up.railway.app` | L'URL Railway de l'étape 1 |
| `NEXT_PUBLIC_API_KEY` | (la même `API_KEY` qu'au 1.2) | Même valeur exacte |

⚠️ `NEXT_PUBLIC_*` est exposé au browser — c'est OK car l'API key sert juste à gate-keep ton API mono-user, pas à protéger des secrets sensibles.

### 2.3 Deploy

Clique **"Deploy"**. Premier build ~2 min. Vercel te donne une URL :
`https://lucas-appli.vercel.app` (ou similaire avec ton compte)

### 2.4 Retourne mettre à jour Railway

Maintenant que tu as l'URL Vercel, **retourne dans Railway** → Variables :
- `FRONTEND_ORIGIN` = `https://<TA-URL>.vercel.app`

Railway redémarrera tout seul. Le CORS sera alors correct.

---

## 3. Vérifications après déploiement

Ouvre `https://<TON-VERCEL>.vercel.app` dans ton navigateur :

| Page | Devrait afficher |
|---|---|
| `/` (Dashboard) | 13 profs, 27 familles, CA d'avril |
| `/settings/teachers` | Liste des 13 profs avec leurs taux |
| `/settings/families-eur` | 13 familles EUR |
| `/extract` | Le formulaire d'extraction TutorBird |
| `/edit-invoice` | L'éditeur de facture avec ton dossier "Mai 2026" dans la liste |
| `/teachers-payroll` | 3 490,94 € de total (excluant Imane) |

Si une page affiche "Impossible de charger…" → ouvre la console navigateur (F12) et regarde l'onglet **Network** : tu verras quelle API échoue. Le plus probable :
- **401** : `NEXT_PUBLIC_API_KEY` ≠ `API_KEY` côté Railway → vérifie qu'elles sont identiques
- **CORS error** : `FRONTEND_ORIGIN` côté Railway pas exactement = URL Vercel → recopie sans le `/` final

---

## 4. Coûts attendus

| Service | Plan | Coût |
|---|---|---|
| Vercel | Hobby | 0 € (frontend 100% gratuit pour usage perso) |
| Railway | Pay-as-you-go | ~3-5 € / mois (un seul worker FastAPI + très peu de RAM) |
| Render (webhook, déjà actif) | Free | 0 € |
| **Total nouveau** | | **~5 € / mois** |

---

## 5. Que faire de l'app Streamlit actuelle ?

**Pour l'instant : laisse-la tourner en parallèle.**

- Ton Streamlit Cloud continue d'écrire sur Drive
- Le nouveau Next.js sur Vercel/Railway lit la même source Drive
- → Les deux apps voient les mêmes données

Test croisé pendant 1-2 mois :
- Fais le workflow complet (extract → payment links → invoices → send) sur le nouveau Next.js
- Vérifie que Streamlit affiche les mêmes chiffres
- Quand tu es 100% confiant → tu peux archiver/retirer Streamlit Cloud

---

## 6. Update du code après déploiement

Une fois Vercel + Railway connectés à `migration-nextjs` :
- **Tout push sur cette branche déploie automatiquement** (Vercel ET Railway)
- Si tu fais un `git push` avec une modif backend → Railway rebuilt en ~2 min
- Si tu fais un push avec une modif frontend → Vercel rebuilt en ~1 min

Pour déployer à partir d'une autre branche, change le réglage "Production Branch" dans les Settings de chaque service.

---

## 7. Webhook Render

Le webhook Stripe → Render reste **inchangé**. Pour rappel :
- URL Stripe configurée pour pointer sur Render
- Render lit/écrit Notion (pas via le backend Next.js)
- → Aucune modif à faire ici

Si tu veux investiguer les "en échec" : voir analyse dans la conversation Claude.
