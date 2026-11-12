# infra/

Infraestructura: Docker Compose, Dockerfiles y configuración de despliegue.

```
infra/
├── docker-compose.yml      # entorno local (S1-02)
├── db/
│   └── init/
│       └── 10-roles.sh     # roles trulab_owner y trulab_app (S1-04)
└── docker/
    ├── backend.Dockerfile  # Python 3.12 + librerías de WeasyPrint; etapa `dev`
    └── frontend.Dockerfile # Node 24 LTS + Vite dev server; etapa `dev`
```

## Entorno local

1. Copiar `/.env.example` a `/.env` y completar las tres contraseñas (`POSTGRES_PASSWORD`, `OWNER_DB_PASSWORD`, `APP_DB_PASSWORD`, distintas) y ponerlas también en `DATABASE_URL_MIGRATIONS` y `DATABASE_URL`.
2. Desde la **raíz** del repositorio (el `.env` define `COMPOSE_FILE`):

| Comando | Qué levanta |
| :--- | :--- |
| `docker compose up -d` | PostgreSQL 16 (`db`) en `127.0.0.1:5433` (5433 para no chocar con un PostgreSQL nativo de Windows), las migraciones (`migrate`, se ejecuta y termina), la API (`api`, FastAPI con recarga) en `127.0.0.1:8000` y el frontend (`frontend`, Vite con HMR) en `127.0.0.1:5173` |
| `docker compose ps` | Estado y salud de los servicios |
| `docker compose down` | Detiene todo; los datos siguen en los volúmenes |
| `docker compose down -v` | Detiene y **borra** los volúmenes (BD incluida) |

Ya no hay perfiles: `api` y `frontend` salieron del perfil `app` en S1-03 y S1-05. La SPA llama a `/api/v1` en su propia origen y Vite reenvía `/api` a `http://api:8000` por la red interna (sin CORS en local; `frontend/README.md`).

**`node_modules` del frontend** vive en el volumen `frontend-node-modules` (binarios de Linux). Al cambiar dependencias: `docker compose exec frontend npm install <paquete>@<versión>` o, si el lock cambió en otra rama, `docker compose run --rm frontend npm ci`.

**Volúmenes:** `pgdata` (BD), `api-storage` (soportes en desarrollo) y `frontend-node-modules`. **Red:** `trulab-viajes`.

## Base de datos: roles y permisos (S1-04)

Tres roles, con el principio de mínimo privilegio (`docs/database-design.md` §6):

| Rol | Atributos | Qué puede hacer | Lo usa |
| :--- | :--- | :--- | :--- |
| `postgres` | superusuario | Todo. Solo para inicializar el volumen y administrar | Imagen oficial (`POSTGRES_USER`) |
| `trulab_owner` | `LOGIN`, sin `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION` ni `BYPASSRLS` | Dueño de la BD `trulab_viajes` y del esquema `public`; crea extensiones *trusted* (`citext`, `pgcrypto`) y todo el esquema | Alembic (servicio `migrate`) |
| `trulab_app` | `LOGIN`, sin ningún atributo privilegiado | `CONNECT`, `USAGE` en `public` y `SELECT, INSERT, UPDATE, DELETE` en las tablas que crea `trulab_owner` (`USAGE, SELECT` en sus secuencias). Sin DDL, `TRUNCATE`, `REFERENCES` ni `TRIGGER`; no lee `alembic_version`. Queda sujeto a RLS | La API (`DATABASE_URL`) |

`PUBLIC` no tiene `CONNECT` sobre la BD ni `USAGE`/`CREATE` sobre `public`.

**Quién hace qué:**
- `infra/db/init/10-roles.sh` (superusuario): crea los roles si no existen, reaplica atributos y contraseñas, hace a `trulab_owner` dueño de la BD y concede `CONNECT` a `trulab_app`. Los roles no van en Alembic porque son objetos del clúster y llevan contraseñas.
- La migración inicial de Alembic (`trulab_owner`): extensiones, privilegios del esquema y privilegios por defecto. Se niega a correr si el rol `trulab_app` no existe o si no la ejecuta el dueño de la BD.

El script se ejecuta solo al crear el volumen. **Para reaplicarlo** (volumen existente, contraseña cambiada o volumen creado antes de S1-04):

```
docker compose exec db bash /docker-entrypoint-initdb.d/10-roles.sh
```

En Git Bash, anteponer `MSYS_NO_PATHCONV=1` (si no, Git Bash convierte la ruta a una de Windows). En PowerShell funciona tal cual.

Un volumen creado antes de S1-04 tiene a `trulab_owner` como superusuario de arranque. Lo más simple es recrearlo (`docker compose down -v` y `docker compose up -d`; borra los datos locales).

**Producción (F10, DP-05):** en un PostgreSQL gestionado, el administrador del proveedor ejecuta el SQL equivalente a `10-roles.sh` una vez; las migraciones corren con `trulab_owner` antes de arrancar la API, y la API solo recibe las credenciales de `trulab_app`.

**MinIO:** no se incluye. Sus imágenes oficiales ya no están disponibles en registros públicos; en local se usa `STORAGE_BACKEND=local`. El almacenamiento de producción se decide con DP-05.

## Producción

Se define en **F10**, según el hosting de DP-05.
