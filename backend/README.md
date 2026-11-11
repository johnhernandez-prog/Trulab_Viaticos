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
│   │   └── middleware.py  # X-Request-ID y registro de acceso
│   └── modules/       # un paquete por dominio: router → service → models (desde S1-07)
├── tests/
├── pyproject.toml     # configuración de ruff, mypy y pytest
├── requirements.txt       # dependencias de ejecución (versiones exactas)
└── requirements-dev.txt   # + pruebas y calidad (incluye requirements.txt)
```

Pendiente en tareas siguientes: `alembic/` (S1-04), módulos de dominio (desde S1-07), `templates/pdf/` (F7).

## Uso (desde la raíz del repositorio)

```
docker compose up -d                          # db + api (http://127.0.0.1:8000)
docker compose exec api python -m pytest      # pruebas (PostgreSQL real)
docker compose exec api ruff check .
docker compose exec api mypy app tests
```

- Salud: `GET /api/v1/health` → `{status, version, db}` (503 si la BD no responde).
- Documentación: `/api/v1/docs` (Swagger UI) y `/api/v1/openapi.json`. Se desactivan con `ENV=production`.
- Para agregar una dependencia: editar `requirements.txt` (o `-dev`) y `docker compose build api`. Si es de tipado para mypy, sincronizar también `additional_dependencies` en `/.pre-commit-config.yaml`.
