# AGENTS.md

API multi-tenant de productos y ventas: FastAPI + SQLAlchemy async + Postgres + Redis, en MVC.

## Layout

- `src/models/` — **Model**: ORM SQLAlchemy. `enums.py` tiene el vocabulario de dominio.
- `src/routers/` — **HTTP + lógica**: un archivo por recurso, con el `APIRouter`, los schemas Pydantic **y** la lógica de negocio, separados en tres secciones dentro del mismo módulo: `Lógica`, `Schemas`, `Endpoints`.

Los endpoints usan el nombre de la ruta (`list_sales`, `create_sale`, `get_sale`) y las funciones de persistencia usan un verbo de dominio (`fetch_sales`, `insert_sale`, `fetch_sale`) para no chocar con ellos. `dashboard.py` no tiene colisión, así que conserva sus nombres.

Consecuencia aceptada: `src/workers/outbox.py` importa `..routers.dashboard`, así que el worker carga FastAPI y Pydantic sin necesitarlos. No cuesta nada en runtime (mismo proceso, FastAPI ya está cargado), pero es una dependencia del worker hacia la capa HTTP. Por eso `compute_from_db`, `today_bounds` y `cache_key` son contrato: renombrarlos rompe el worker.
Infraestructura aparte: `config.py`, `database.py`, `cache.py`, `deps.py`, `events.py`, `workers/outbox.py`.

## Entorno

- Windows + OneDrive. Venv en `venv/` (Python 3.14.6): usa `venv/Scripts/python.exe` o activa con `venv/Scripts/activate` / `activate.ps1`. No hay `bin/`.
- Deps con pin `==` en `requirements.txt`, que es un dump de `pip freeze` (incluye transitive como `agent-detector`). Para añadir algo: edita el archivo, `venv/Scripts/python.exe -m pip install -r requirements.txt`, y re-pinea con `pip freeze --exclude pip > requirements.txt`. No hay `pyproject.toml`: el proyecto no es instalable.
- `sqlalchemy[asyncio]` (y por tanto `greenlet`) es obligatorio para el engine async. Si ves `ModuleNotFoundError: No module named 'greenlet'`, no está instalado.

## Run

```bash
venv/Scripts/fastapi.exe dev src/main.py          # reload incluido
venv/Scripts/python.exe -m uvicorn src.main:app --reload
```

**En Windows `--reload` no es opcional**: sin él uvicorn elige `ProactorEventLoop` y psycopg en modo async falla con `InterfaceError: Psycopg cannot use the 'ProactorEventLoop'`. Con reload cae al `SelectorEventLoop`. Es contraintuitivo (reload parece opcional, pero es lo que arregla el loop) y no produce ningún aviso en el log de arranque: el error sale del worker, no del servidor.

Infraestructura:

```bash
docker compose up -d
venv/Scripts/alembic.exe upgrade head
```

**El volumen de Postgres va en `/var/lib/postgresql`**, no en `/var/lib/postgresql/data`: PG18 movió `PGDATA` a `/var/lib/postgresql/18/docker`, y con la ruta antigua el contenedor aborta al arrancar.

Para probar la migración sin base de datos: `alembic upgrade head --sql` y `alembic downgrade a9bc2f43f378:base --sql`. Las revisiones viven en `migrations/versions/`, no en `alembic/versions/` (`script_location` en `alembic.ini` apunta a `migrations`).

## Verificación

**No hay pytest, ruff ni mypy instalados, ni config para ellos.** No inventes ni reportes esos comandos. Verificar es: `docker compose up -d`, `alembic upgrade head`, arrancar la app, y `curl` contra los endpoints. `GET /health` reporta Postgres y Redis por separado.

## Aislamiento por tenant

- Sin usuarios ni sesiones: el tenant viaja en el header **`X-Tenant-Id`** (obligatorio, UUID; si falta o no parsea, 422). Lo resuelve `get_tenant_id` en `deps.py`.
- **`tenant_id` nunca se acepta en el body**: los schemas Pydantic de entrada no tienen ese campo y sale siempre de la dependencia.
- El filtro por tenant va **en el `WHERE`** de cada query, nunca en un `if` posterior. Un recurso de otro tenant devuelve **404 y no 403**, para no revelar que existe.
- `POST /v1/tenants` es el único endpoint sin header (crea el tenant).
- CORS: `CORS_ORIGINS` (coma-separado). Hay que permitir explícitamente `X-Tenant-Id`: es un header no simple y sin él el preflight falla. En dev el front usa el proxy de Vite (mismo origen) y no depende de CORS.

## Reglas de venta que no se negocian

- Una venta nace **`created`**. `SALES.status` es `NOT NULL DEFAULT 'created'`.
- El enum persistido es **`created | approved | declined`**. Ya no existe `unknown` ni el campo `idempotency_key`.
- `POST /v1/sales/{id}/pay` recibe `outcome: created | approved | declined | timeout`.
  - `approved` / `declined` escriben el estado y son **terminales**: una vez escritos, ningún reporte posterior los reinterpreta. La respuesta trae `applied: false`.
  - `created` y `timeout` son **no-ops**: no escriben, no generan evento y el dashboard no se mueve. `timeout` (se tardó o falló la red) **no se persiste nunca**.
  - Consecuencia: `created` significa "pago sin resolver" e incluye lo que dio timeout. No se distinguen, y es intencional.
- El `price` de `sales_products` es un **snapshot** del precio **unitario** al vender, no una referencia al producto.
- Cada línea lleva **`quantity`** (≥ 1, default 1). La PK de `SALES_PRODUCTS` es `(sale_id, product_id)`, así que un producto va **una sola vez** por venta: `SaleCreate` rechaza productos repetidos con 422. El total de línea es `price * quantity`, tanto en `sale_total` como en el subquery de `compute_from_db`.
- `price` es `Numeric(12,2)` ↔ `Decimal`. En JSON un `Decimal` sale como **string** (`"10.50"`), no como número. No esperes `float` en ningún sitio.

## Outbox y reactividad (dashboard)

- **Toda** transición inserta su fila en `sales_outbox` en la misma transacción que el cambio: incluido el `created` inicial (`create_sale`). Sin ese evento, la orden nueva no se vería en el dashboard hasta que otro cambio disparara un recálculo.
- Cada fila lleva un **`payload` JSONB con el snapshot de la venta**. El evento se autodescribe a propósito: si el worker releyera la venta, un evento viejo de `created` publicaría el `approved` actual y mentiría. Reprocesar un evento da siempre la verdad histórica.
- `src/workers/outbox.py` es un `asyncio.Task` dentro del mismo proceso (arrancado en el `lifespan`), no un servicio aparte. Nunca muere por un fallo puntual: loguea y reintenta.
- El transporte del wakeup es un **Redis Stream** con consumer group, no `LISTEN/NOTIFY`: NOTIFY tiene un tope duro de 8000 bytes por payload, no tiene consumer group y pierde despertares. El stream además es compatible con Dragonfly.
- La tabla `sales_outbox` es la fuente de verdad; el stream solo reduce la latencia. El poll cada `OUTBOX_POLL_SECONDS` cubre la ventana entre el commit y el `XADD`. Entrega *at-least-once*, y `processed_at` + `FOR UPDATE SKIP LOCKED` la hacen idempotente y permiten varios workers.
- El agregado se recalcula **una vez por tenant por ciclo**, aunque el lote traiga varios eventos de ese tenant; el SSE publica **un frame por venta**.
- **En la publicación el tenant sale siempre del propio evento** (`event.tenant_id`), nunca de una variable del bucle: agrupar mal ahí manda la venta de un tenant al stream de otro.
- El agregado es **derivado**: Redis es caché, Postgres la verdad. El total de cada venta se calcula con un subquery sobre `sales_products`, no con una columna desnormalizada. Clave `dashboard:today:{tenant_id}:{YYYY-MM-DD}`.
- **`total_sales = sum(counts.values())`**, nunca acumulado en paralelo: por construcción no puede desviarse de la suma por estado, ni aunque el outbox entregue el mismo evento dos veces.
- "Hoy" es el **día UTC** calendario. El dashboard es **eventualmente consistente**: tras un `/pay` el agregado tarda un instante (wakeup del stream, o hasta `OUTBOX_POLL_SECONDS`). Un test debe esperar a que converja, no leer al instante.
- SSE en `GET /v1/dashboard/stream`: `snapshot` (el agregado del día) al conectar, luego un frame `sale` por venta con su estado, y `: ping` de heartbeat cada 15 s.

## Caché

Redis es una aceleración, **nunca la única copia**. Todos los helpers de `src/cache.py` capturan excepciones y degradan en silencio: con Redis caído la API sigue respondiendo contra Postgres. `SCAN` para invalidar por prefijo, nunca `KEYS`. Al escribir se invalida el prefijo del tenant.

## Convenciones

- FastAPI 0.142 / Starlette 1.7: `@app.on_event` está **deprecado**, usa `lifespan=` en `FastAPI()`. Y `status.HTTP_422_UNPROCESSABLE_ENTITY` está deprecado → `HTTP_422_UNPROCESSABLE_CONTENT`.
- `include_router` en 0.142 crea un `_IncludedRouter` perezoso: las rutas no aparecen en `app.routes` con `path`, se ven en `app.openapi()`. Para enumerar rutas usa el esquema OpenAPI.
- Parámetros de query: `limit: LIMIT = 50` con `LIMIT = Annotated[int, Query(ge=1, le=200)]`. **No** escribas `limit: int = LIMIT`: deja el objeto `Query` como default y rompe el esquema con un warning.
- Pydantic v2: `ConfigDict`, `Field`, `field_validator` + `@classmethod`, `model_validate`, `model_dump`. Nada de `class Config`, `parse_obj` ni `.dict()`.
- SQLAlchemy 2.1 async: `await session.execute(select(...))`, `async_sessionmaker`, `with_for_update(skip_locked=True)`.
- Nombres de columna: se respetan los del esquema original, incluidas las rarezas `update_at` (no `updated_at`) y `delete_at`. `delete_at` existe pero no hay endpoints `DELETE`.
- Las **tablas van en MAYÚSCULAS** (`__tablename__ = "SALES"`), y por eso en SQL crudo hay que entrecomillarlas: `ALTER TABLE "SALES"`. El enum también: `"SALES_STATUS"`. Postgres pliega a minúsculas lo que no lleva comillas, y `ALTER TYPE SALES_STATUS` sin comillas no encuentra al tipo real.

## Dos trampas de SQLAlchemy que ya muerden

1. `ENUM(SalesStatus, ...)` sin `values_callable` usa los **nombres** del enum (`CREATED`) como labels en Postgres en vez de los valores (`created`), y revienta con `LookupError: 'created' is not among the defined enum values`. Está arreglado en `models/enums.py`; si tocas el enum, mantén el `values_callable`.
2. Pasar los **strings** (`ENUM('created', 'approved', ...)`) en vez de la clase hace que SQLAlchemy devuelva el valor crudo y no convierta a `SalesStatus`: todo `.value` revienta con `'str' object has no attribute 'value'`. Y un `GROUP BY` sobre una columna suelta **siempre** devuelve el valor crudo, no el miembro, aunque la clase esté registrada: por eso `compute_from_db` normaliza con `getattr(status, "value", status)`.

## Notas de Git Bash en Windows

- El CLI de Docker **no está en el PATH**: `export PATH="$PATH:/c/Users/alurr/AppData/Local/Programs/DockerDesktop/resources/bin"`.
- `docker exec <cont> <cmd> /ruta/...` **mala la ruta**: MSYS la convierte a `C:/Program Files/Git/var/...`. Usa `MSYS_NO_PATHCONV=1`.
- Varios uvicorn pueden quedar escuchando en el mismo puerto y las requests se reparten entre procesos con código viejo, dando 500 intermitentes que no se reproducen por curl. `netstat -ano | grep LISTENING` para verlo y matar los PIDs sobrantes.
