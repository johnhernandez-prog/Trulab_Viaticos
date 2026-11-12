# backend/

API FastAPI (Python 3.12) de Trulab Viajes. Se ejecuta siempre en Docker (ADR-016).

```
backend/
├── app/
│   ├── main.py        # create_app(): middlewares, manejadores de error y routers
│   ├── core/
│   │   ├── audit.py       # modelo `auditoria` + registrar() (solo inserción, S1-07)
│   │   ├── config.py      # Settings (variables de entorno)
│   │   ├── db.py          # engine SQLAlchemy síncrono, get_db, bd_disponible
│   │   ├── errors.py      # RFC 9457 problem+json, ErrorDominio
│   │   ├── health.py      # GET /api/v1/health
│   │   ├── logs.py        # logs JSON con request_id
│   │   ├── middleware.py  # X-Request-ID y registro de acceso
│   │   ├── enums.py       # enums fijos del sistema (Rol)
│   │   └── models.py      # Base (naming_convention) y mixins de columnas base
│   └── modules/       # un paquete por dominio: router → service → models
│       ├── auth/          # models: sesiones (refresh tokens; endpoints en S1-08)
│       ├── cargos/        # models: cargos (folio CA-000001)
│       ├── catalogos/     # models: celulas (proyectos y rubros llegan con los gastos)
│       └── usuarios/      # models (credenciales por rol, ADR-027), service (SUPERADMIN inicial), seed
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

Pendiente en tareas siguientes: routers y services de los dominios (desde S1-08), `templates/pdf/` (F7).

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
- Los modelos van en `app/modules/<dominio>/models.py` y heredan de `app.core.models.Base`. `alembic/env.py` los importa solo: no hay que registrarlos. Los transversales de `app/core` (hoy `audit.py`) se listan en `MODELOS_CORE` de `env.py`.
- **Columnas base** con los mixins de `app/core/models.py`: `ConId` (UUID `gen_random_uuid()`), `ConMarcasDeTiempo` (`created_at`, `updated_at`), `ConAutores` (`created_by`/`updated_by` → `usuarios`, con índice), `ConBorradoLogico` (`deleted_at`) y `ConMigradoDe` (ETL). Todo `datetime` es `TIMESTAMPTZ`.
- **FK circulares** (una tabla referencia a `usuarios` en `created_by` y `usuarios` la referencia a ella): la FK de `usuarios` lleva `use_alter=True` y la migración la crea al final con `op.create_foreign_key`. `--autogenerate` no ordena bien estos casos: revisar el orden de `create_table`.
- **Defaults con `nextval()`** (folios): `alembic check` los omite (`_comparar_default` en `env.py`), porque compararlos consumiría la secuencia y siempre parecerían cambiados.
- Los nombres de constraints e índices salen de la `naming_convention` (`docs/database-design.md` §9): no se escriben a mano. Los `CheckConstraint` sí llevan `name="regla"` y quedan como `ck_<tabla>__<regla>`.
- Cada tabla nueva que crea `trulab_owner` le da a `trulab_app` **solo** `SELECT, INSERT, UPDATE, DELETE` (y `USAGE, SELECT` sobre sus secuencias) por los privilegios por defecto de la migración inicial. Las tablas de solo inserción (`auditoria`, `viatico_eventos`) deben ejecutar `REVOKE UPDATE, DELETE ... FROM trulab_app` en su migración. Las políticas RLS (`... TO trulab_app`) se crean también en migraciones (S2-03).
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

## SUPERADMIN inicial

`docker compose up -d` lo crea a través del servicio `migrate` (después de `alembic upgrade head`) con `python -m app.modules.usuarios.seed`, a partir de `SUPERADMIN_EMAIL` (y `SUPERADMIN_NOMBRE`):

- Vacío: no hace nada. Debe ser del dominio `GOOGLE_WORKSPACE_DOMAIN`; si no, `migrate` termina con código 1 y la API no arranca.
- **Solo actúa si no hay ningún SUPERADMIN activo.** La variable no sirve para crear superadministradores adicionales; los demás se gestionan desde la app (S1-10).
- Si el correo ya existe, lo promueve a SUPERADMIN y lo reactiva (recuperación de acceso); al promoverlo le **quita la contraseña** (el SUPERADMIN entra solo con Google, ADR-027). Crear y promover quedan en `auditoria` (`USUARIO_CREAR` o `ROL_CAMBIAR`, más `SUPERADMIN_ASIGNADO`) con `origen = seed` y sin actor.
- En `.env.example` el valor es el del creador del sistema: `SUPERADMIN_EMAIL=john.hernandez@trulab.co`, `SUPERADMIN_NOMBRE=John Hernandez`. El código no tiene ese valor por defecto.
- Se conecta como `trulab_app` (crear un usuario es una operación de la aplicación). El correo no va al log.
- A mano: `docker compose run --rm migrate python -m app.modules.usuarios.seed`.

## Credenciales por rol (S1-07b, ADR-027)

La BD garantiza el acceso híbrido con `CHECK` en `usuarios`:

| Regla | Constraint |
| :--- | :--- |
| Operativo (VIAJERO/ADMIN/FINANCIERO) ⇒ `password_hash` obligatorio; SUPERADMIN ⇒ sin contraseña | `ck_usuarios__password_segun_rol` |
| `password_hash` solo en formato PHC de Argon2id (`$argon2id$…`): nunca una contraseña en claro | `ck_usuarios__password_argon2id` |
| Operativo ⇒ `username` obligatorio, en minúsculas `^[a-z0-9._-]{3,40}$` (CITEXT único) | `ck_usuarios__username_operativo`, `ck_usuarios__username_formato` |
| Solo SUPERADMIN puede tener `google_sub` | `ck_usuarios__google_solo_superadmin` |
| SUPERADMIN nunca tiene cambio de contraseña pendiente | `ck_usuarios__superadmin_sin_cambio_password` |

Un cambio de rol debe ajustar las credenciales en la misma operación. `tokens_recuperacion_password` guarda solo el SHA-256 del token (`CHECK` de 64 hex) y `trulab_app` no tiene `DELETE`: se invalidan con `used_at`. En pruebas, `tests/fabricas.py::crear_usuario` da a los operativos un `username` y un hash Argon2id ficticio (`HASH_FICTICIO`).

`Settings` (`app/core/config.py`) rechaza al arrancar: `MAIL_BACKEND=log` fuera de `ENV=local`, `MAIL_BACKEND=ses` sin `AWS_SES_SENDER`, `STORAGE_BACKEND=s3` sin `AWS_S3_BUCKET` y `PASSWORD_RESET_TTL_MINUTES` fuera de 15–30.
