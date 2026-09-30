# MovaPay POS

Monorepo con el API multi-tenant (`backend/`, FastAPI + Postgres + Redis) y el
POS offline-first (`frontend/`, SvelteKit PWA).

## Todo junto (Docker)

```bash
docker compose up --build
```

- App: http://localhost:4173
- API / docs: http://localhost:8000/docs

La API aplica las migraciones al arrancar. Puertos configurables con
`WEB_PORT` y `API_PORT`.

## Desarrollo

```bash
# 1. Infra + API (ver backend/AGENTS.md para Windows)
cd backend
docker compose up -d
alembic upgrade head
fastapi dev src/main.py            # http://localhost:8000

# 2. Frontend
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

## Cómo se conectan

- El front llama rutas relativas (`/v1/...`). Vite (`dev` y `preview`) las
  reenvía a `API_PROXY_TARGET` (por defecto `http://localhost:8000`): mismo
  origen para el navegador, sin CORS, y el SSE del dashboard pasa sin buffer.
- Si el front se sirve desde otro origen, definir `VITE_API_BASE_URL` en el
  front y añadir ese origen a `CORS_ORIGINS` en el backend.
- El tenant viaja en el header `X-Tenant-Id`. En la pantalla de inicio se elige
  un tenant existente o se crea uno nuevo.
- Dinero: el API usa decimales como string (`"3.50"`); el front opera en
  centavos enteros (`src/lib/money.ts`).
- Ventas: una línea por producto con `quantity`. Pago con
  `outcome: approved | declined | timeout`; `timeout` deja la venta en
  `created` ("pago sin resolver") y el POS permite reintentar sobre la misma
  venta.
- Offline: las ventas se guardan en IndexedDB y se sincronizan al volver la
  conexión (`POST /v1/sales` + `/pay approved`), guardando el id remoto para
  no duplicar si el `/pay` falla.
