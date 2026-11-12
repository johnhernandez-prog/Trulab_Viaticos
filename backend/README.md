# backend/

API FastAPI (Python 3.12) de Trulab Viajes. Se ejecuta siempre en Docker (ADR-016).

```
backend/
├── app/
│   ├── main.py        # create_app(): middlewares, manejadores de error y routers
│   ├── core/
│   │   ├── config.py      # Settings (variables de entorno)
│   │   ├── db.py          # engine SQLAlchemy síncrono, get_db, bd_disponible
│   │   ├── errors.py      # RFC 9457 problem+json, ErrorDominio
│   │   ├── health.py      # GET /api/v1/health
│   │   ├── logs.py        # logs JSON con request_id
│   │   ├── middleware.py  # X-Request-ID y registro de acceso
│   │   └── models.py      # Base declarativa con la naming_convention (S1-04)
│   └── modules/       # un paquete por dominio: router → service → models (desde S1-07)
├── alembic/           # migraciones (S1-04)
│   ├── env.py             # conexión con trulab_owner y descubrimiento automático de modelos
│   ├── script.py.mako     # plantilla de migraciones nuevas
│   └── versions/          # AAAAMMDD_HHMM_<descripcion>.py
├── alembic.ini
├── tests/
├── pyproject.toml     # configuración de ruff, mypy y pytest
├── requirements.txt       # dependencias de ejecución (versiones exactas)
└── requirements-dev.txt   # + pruebas y calidad (incluye requirements.txt)
```

Pendiente en tareas siguientes: módulos de dominio (desde S1-07), `templates/pdf/` (F7).

## Uso (desde la raíz del repositorio)

```
docker compose up -d                          # db + migraciones + api (http://127.0.0.1:8000)
docker compose exec api python -m pytest      # pruebas como trulab_app (omite las de migraciones)
docker compose run --rm migrate python -m pytest   # todas, también las que necesitan trulab_owner
docker compose exec api ruff check .
docker compose exec api mypy app tests alembic
```

- Salud: `GET /api/v1/health` → `{status, version, db}` (503 si la BD no responde).
- Documentación: `/api/v1/docs` (Swagger UI) y `/api/v1/openapi.json`. Se desactivan con `ENV=production`.
- Para agregar una dependencia: editar `requirements.txt` (o `-dev`) y `docker compose build api`. Si es de tipado para mypy, sincronizar también `additional_dependencies` en `/.pre-commit-config.yaml`.

## Migraciones (Alembic)

**Reglas:**
- El esquema cambia **solo** con migraciones de Alembic; nunca a mano.
- Las migraciones las ejecuta **`trulab_owner`** (`DATABASE_URL_MIGRATIONS`), el dueño de la BD. La API usa **`trulab_app`** (`DATABASE_URL`), que no puede crear ni alterar objetos. El contenedor `api` no recibe `DATABASE_URL_MIGRATIONS`.
- `docker compose up -d` aplica las pendientes: el servicio `migrate` ejecuta `alembic upgrade head` y la API arranca solo si terminó bien.
- Los modelos van en `app/modules/<dominio>/models.py` y heredan de `app.core.models.Base`. `alembic/env.py` los importa solo: no hay que registrarlos.
- Los nombres de constraints e índices salen de la `naming_convention` (`docs/database-design.md` §9): no se escriben a mano. Los `CheckConstraint` sí llevan `name="regla"` y quedan como `ck_<tabla>__<regla>`.
- Cada tabla nueva que crea `trulab_owner` le da a `trulab_app` **solo** `SELECT, INSERT, UPDATE, DELETE` (y `USAGE, SELECT` sobre sus secuencias) por los privilegios por defecto de la migración inicial. Las tablas de solo inserción (`auditoria`, `legalizacion_eventos`) deben ejecutar `REVOKE UPDATE, DELETE ... FROM trulab_app` en su migración. Las políticas RLS (`... TO trulab_app`) se crean también en migraciones (S2-03).
- Una migración publicada (en `main`) no se edita: se corrige con otra nueva. Siempre se escribe `downgrade()`.
- Revisar siempre lo que genera `--autogenerate` (no detecta, entre otros, cambios de nombre de columnas ni `CHECK`). Datos, vistas, funciones, RLS y privilegios van con `op.execute(...)`.

**Comandos** (desde la raíz; los archivos nuevos aparecen en `backend/alembic/versions/`):

| Comando | Para qué |
| :--- | :--- |
| `docker compose run --rm migrate alembic revision --autogenerate -m "crear cargos usuarios"` | Nueva migración a partir de los modelos (queda formateada con ruff) |
| `docker compose run --rm migrate alembic revision -m "vista saldos"` | Nueva migración vacía (SQL manual) |
| `docker compose run --rm migrate alembic upgrade head` | Aplicar las pendientes (también lo hace `docker compose up -d`) |
| `docker compose run --rm migrate alembic downgrade -1` | Revertir la última |
| `docker compose run --rm migrate alembic current` / `history` | Versión actual / historial |
| `docker compose run --rm migrate alembic check` | Falla si los modelos tienen cambios sin migración |
| `docker compose run --rm migrate alembic upgrade head --sql` | Ver el SQL sin aplicarlo (revisión antes de producción) |

**Antes de hacer commit de una migración:** `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` y `alembic check` deben pasar, junto con `python -m pytest` en `migrate`. Si dos ramas crean migraciones en paralelo, quedan dos cabezas (la prueba `test_historial_de_migraciones_lineal` falla): se resuelve con `alembic merge heads -m "unir ramas"`.
