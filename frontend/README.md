# Professor+ Frontend (Next.js 15)

Dashboard admin moderne. Remplace progressivement l'app Streamlit en gardant la
fonctionnalité 1-pour-1.

## Stack
- Next.js 15 (App Router)
- TypeScript + Tailwind CSS
- shadcn/ui pattern (composants locaux)
- framer-motion (animations subtiles)
- @tanstack/react-query (state)
- lucide-react (icônes)
- sonner (toasts)

## Quick start

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

→ http://localhost:3000

## Pages

- `/` — Dashboard accueil
- `/showcase` — **Catalogue de tous les composants** (à valider visuellement avant migration)
- `/extract`, `/payment-links`, `/invoices`, `/send-invoices`, `/reminders`, `/sync`,
  `/update-notion`, `/cleanup`, `/twint`, `/teachers-payroll`, `/settings/*` — pages de
  l'app, à migrer

## Design tokens

Tous les couleurs sont dans `app/globals.css` (CSS variables HSL) +
`tailwind.config.ts` (Tailwind tokens). **Ne jamais hardcoder de hex en dur** —
toujours `bg-primary`, `text-muted-foreground`, etc.

## Backend

Le frontend appelle `${BACKEND_URL}/api/*` via les rewrites Next.js.
Auth : header `X-API-Key`.
