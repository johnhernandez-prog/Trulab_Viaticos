# infra/

Infraestructura: Docker Compose, Dockerfiles y configuración de despliegue.

```
infra/
├── docker-compose.yml      # entorno local (S1-02)
└── docker/
    ├── backend.Dockerfile  # Python 3.12 + librerías de WeasyPrint; etapa `dev`
    └── frontend.Dockerfile # Node 20 + Vite dev server; etapa `dev`
```

## Entorno local

1. Copiar `/.env.example` a `/.env` y completar al menos `POSTGRES_PASSWORD`.
2. Desde la **raíz** del repositorio (el `.env` define `COMPOSE_FILE`):

| Comando | Qué levanta |
| :--- | :--- |
| `docker compose up -d` | PostgreSQL 16 (`db`), en `127.0.0.1:5433` (5433 para no chocar con un PostgreSQL nativo de Windows) |
| `docker compose --profile app up -d` | `db` + `api` (FastAPI con recarga, `:8000`) + `frontend` (Vite, `:5173`) |
| `docker compose ps` | Estado y salud de los servicios |
| `docker compose down` | Detiene todo; los datos siguen en los volúmenes |
| `docker compose down -v` | Detiene y **borra** los volúmenes (BD incluida) |

`api` y `frontend` están en el perfil `app` hasta que exista su código: S1-03 (backend) y S1-05 (frontend) quitan el perfil.

**Volúmenes:** `pgdata` (BD), `api-storage` (soportes en desarrollo) y `frontend-node-modules`. **Red:** `trulab-viajes`.

**MinIO:** no se incluye. Sus imágenes oficiales ya no están disponibles en registros públicos; en local se usa `STORAGE_BACKEND=local`. El almacenamiento de producción se decide con DP-05.

## Producción

Se define en **F10**, según el hosting de DP-05.
