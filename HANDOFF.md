# HANDOFF — Trulab Viajes

> Documento vivo para retomar entre sesiones. Se actualiza al final de **cada** sesión (skill `claude-mem:handoff`).
> Formato: se sobrescriben las secciones de estado. El historial se acumula al final (lo más reciente arriba).

## Estado actual

| Campo | Valor |
| :--- | :--- |
| Fase | **Sprint 1 en curso** (semana 1 · F1 base técnica). Documentación congelada (baseline `62b91cf`) |
| Semana del sprint | Semana 1: **S1-01 ✅, S1-02 ✅ y S1-03 ✅ terminadas**; S1-04 a S1-13 pendientes |
| Código | Esqueleto del backend FastAPI (health, errores, request id, logs) en Docker; sin lógica de negocio ni frontend |
| Repositorio | `main` = `origin/main` = `62b91cf` (baseline publicado en GitHub). S1-01 a S1-03 están en la rama **`feat/f1-estructura-monorepo`** (sin push ni merge) |
| Última actualización | 2026-11-11 |

## Última actividad

**S1-03 · Backend esqueleto.** FastAPI mínimo y operativo dentro del contenedor `api`:
- `app/main.py` con `create_app()`; `core/config.py` (pydantic-settings; `DATABASE_URL` obligatoria), `core/db.py` (engine síncrono creado al primer uso, `get_db`, `bd_disponible`), `core/errors.py` (problem+json RFC 9457 y base `ErrorDominio`), `core/middleware.py` (`X-Request-ID` y log de acceso), `core/logs.py` (JSON con `request_id`), `core/health.py` (`GET /api/v1/health`).
- `requirements.txt` (FastAPI 0.115.4, uvicorn 0.32.0, Pydantic 2.9.2, pydantic-settings 2.6.1, SQLAlchemy 2.0.36, psycopg 3.2.3), `requirements-dev.txt` (pytest, httpx, ruff 0.6.9, mypy 1.13.0) y `pyproject.toml` (configuración de ruff, mypy strict y pytest).
- 13 pruebas (`tests/`): health contra PostgreSQL real y con BD caída, documentación, problem+json (404, 405, 409 de dominio, 422, 500 sin filtrar detalles), `X-Request-ID` y formato de logs.
- Compose: **`api` sale del perfil `app`** y arranca con `docker compose up -d`; `frontend` sigue en el perfil hasta S1-05.
- pre-commit: se agrega **mypy** (`mirrors-mypy` v1.13.0, con las mismas versiones de dependencias que `requirements*.txt`).

**Decisiones técnicas de S1-03:**
- **Documentación en `/api/v1/docs` y `/api/v1/openapi.json`**, no en la raíz: `docs/api-design.md` §1 fija el contrato OpenAPI bajo el prefijo versionado. Se desactiva con `ENV=production` (y ReDoc no se publica).
- **Health `200`/`503`:** `{status, version, db}` como dice `docs/api-design.md` §2; con la BD caída responde 503 para que el healthcheck de Docker marque la API como no sana. Conexión con `connect_timeout=3`.
- **Engine perezoso:** importar la app no abre conexiones; la primera consulta crea el engine (con `pool_pre_ping`).
- **`X-Request-ID`:** se conserva el del cliente solo si cumple `^[A-Za-z0-9._-]{1,128}$`; si no, se genera un UUID. Va en todas las respuestas, también en los 500, y en cada línea de log.
- **Logs:** JSON en stdout con la librería estándar (sin dependencias nuevas). El access log de uvicorn se reemplaza por uno propio con `request_id` y duración; solo se registran método y ruta (sin query string, RNF-09).
- **Errores:** códigos estables de `docs/api-design.md` §7 por estado HTTP; se agrega `METODO_NO_PERMITIDO` (405), que el contrato no listaba. El 500 no expone detalles; el traceback va solo al log.
- **`core/logs.py`** (no `logging.py`) para no tapar el módulo estándar `logging`; `health` vive en `core/` porque no es un dominio de negocio.
- **`DATABASE_URL` hasta S1-04:** el rol `trulab_app` aún no existe; en el `.env` local se apunta a `trulab_owner` (anotado en `.env.example`).
- **Fuera de alcance, a propósito:** Alembic y roles de BD (S1-04), `SET LOCAL` de RLS (S1-09), auth (S1-08), CORS (cuando la SPA llame a la API), modelos y módulos de dominio.

**Validaciones de S1-03 (con un `.env` temporal, luego eliminado):** `docker compose build api` correcto; `docker compose up -d` deja `db` y `api` *healthy*; desde Windows, `GET /api/v1/health` → 200 `{"status":"ok","version":"0.1.0","db":"ok"}` con `X-Request-ID`; `/api/v1/docs` → Swagger UI; `/api/v1/openapi.json` → OpenAPI 3.1 con `/api/v1/health`; `/docs` y `/openapi.json` en la raíz → 404 problem+json. Con la BD detenida, health → 503, y se recupera solo al volver la BD. La recarga automática detectó cambios en archivos montados desde Windows. En el contenedor: `ruff check`, `ruff format --check`, `mypy` strict y **13/13 pruebas** en verde (queda un `DeprecationWarning` de anyio dentro de Starlette, ajeno al proyecto). `pre-commit run --all-files`: todo en verde, incluido mypy. Entorno de prueba limpiado (`down -v`).

**S1-02 · Docker Compose local.** Archivos nuevos: `infra/docker-compose.yml`, `infra/docker/backend.Dockerfile`, `infra/docker/frontend.Dockerfile` y `.dockerignore`. Modificados: `.env.example` (bloque de Compose y puertos) e `infra/README.md` (instrucciones de uso).

- **Servicios:** `db` (PostgreSQL 16.4, healthcheck `pg_isready`), `api` (FastAPI con `uvicorn --reload`, código montado desde `backend/`, healthcheck a `/api/v1/health`) y `frontend` (Vite dev server, código montado desde `frontend/`). **Red** `trulab-viajes`; **volúmenes** `pgdata`, `api-storage` y `frontend-node-modules`.
- **Uso:** desde la raíz, `docker compose up -d` (solo `db`) o `docker compose --profile app up -d` (todo). Requiere `.env` copiado de `.env.example` con `POSTGRES_PASSWORD`. Detalle en `infra/README.md`.

**Decisiones técnicas de S1-02:**
- **Compose en `infra/` + `COMPOSE_FILE` en `.env`:** la arquitectura ubica el compose en `infra/` y a la vez pide que `docker compose up` levante todo. Con `COMPOSE_FILE=infra/docker-compose.yml` en el `.env` raíz se cumplen las dos cosas (probado: la interpolación toma el `.env` raíz). Sin esa variable: `docker compose --env-file .env -f infra/docker-compose.yml ...`.
- **`api` y `frontend` en el perfil `app`:** su código no existe todavía; si arrancaran por defecto, `docker compose up` fallaría. **S1-03 debe quitar el perfil de `api` y S1-05 el de `frontend`.**
- **Contratos para las tareas siguientes:** el Dockerfile del backend instala dependencias desde **`backend/requirements.txt` y `backend/requirements-dev.txt`** (este incluye `-r requirements.txt`) y arranca `app.main:app`; el del frontend usa **`frontend/package.json` y `package-lock.json`** y `npm run dev`. S1-03 y S1-05 deben respetarlos o ajustar el Dockerfile.
- **MinIO no se incluye:** sus imágenes oficiales ya no están disponibles públicamente (`minio/minio` no existe en Docker Hub; `quay.io/minio` devuelve 401). La arquitectura lo marca como opcional y admite el sistema de archivos en local (`SPEC.md` §14, `docs/architecture.md` §12), así que se usa `STORAGE_BACKEND=local` sobre el volumen `api-storage`. Si en F5 hace falta un emulador S3 local, se elige con un ADR (otra tecnología).
- **BD en el puerto 5433 del host:** en este equipo corre un PostgreSQL nativo de Windows (servicio `postgres.exe`) en 5432. Configurable con `POSTGRES_HOST_PORT`; dentro de la red Docker sigue siendo `db:5432` (lo que usa `DATABASE_URL`).
- **Seguridad:** todos los puertos se publican solo en `127.0.0.1`. La BD recibe solo sus tres variables (no el `.env` completo); la API recibe el `.env`. Si falta `POSTGRES_PASSWORD`, Compose se detiene con un mensaje claro. `.dockerignore` deja fuera `.git`, `.venv`, docs, `.env*` y `node_modules`. Las imágenes corren con usuario sin privilegios (`app` uid 1000, `node`).
- **Windows:** recarga por *polling* (`WATCHFILES_FORCE_POLLING`, `CHOKIDAR_USEPOLLING`), porque los volúmenes montados desde Windows no emiten eventos de archivos; `node_modules` en volumen para no mezclar binarios de Windows y Linux.
- **Versiones fijadas:** `postgres:16.4`, `python:3.12.7-slim-bookworm`, `node:20.18.0-bookworm-slim` (verificadas en el registro). La imagen del backend incluye Pango y HarfBuzz para WeasyPrint (ADR-010).
- **El PostgreSQL 16 de Docker no crea todavía roles ni extensiones:** `trulab_app`, `citext` y `pgcrypto` son de S1-04.

**Validaciones ejecutadas (con un `.env` temporal, luego eliminado):**
- `docker compose config`: válido con y sin el perfil `app`; sin `POSTGRES_PASSWORD` falla con el mensaje esperado.
- `docker compose up -d`: `db` *healthy*; `PostgreSQL 16.4` responde; accesible desde Windows en `127.0.0.1:5433` y desde la red interna como `db:5432`.
- Persistencia: un dato escrito sobrevivió a `down` + `up`.
- `backend.Dockerfile --target base`: construye; Python 3.12.7, usuario `app`, `libpango`, `libpangoft2` y `libharfbuzz-subset` presentes.
- Etapas `dev` de backend y frontend: se detienen en el `COPY` de los archivos de S1-03 y S1-05 (esperado).
- `pre-commit run --all-files`: todo en verde.
- Limpieza: `docker compose down -v`, imagen de prueba borrada, `.env` temporal eliminado.

**S1-01 · Estructura del monorepo.** Se crearon las carpetas raíz `backend/`, `frontend/`, `infra/`, `scripts/` y `scripts/etl_appsheet/` (cada una con un README que dice qué tarea la llena) y la configuración base: `.gitignore`, `.editorconfig`, `.gitattributes`, `.env.example` y `.pre-commit-config.yaml`. No se escribió código de aplicación ni se tocaron requisitos, reglas, arquitectura, roadmap ni sprints.

**Decisiones técnicas de S1-01:**
- `.gitattributes` con `eol=lf`: el equipo está en Windows (`core.autocrlf=true`) y el backend corre en contenedores Linux; un CRLF rompe scripts. Los documentos ya estaban en LF en el índice, así que no cambió ninguno.
- pre-commit con hooks genéricos, `ruff` y `ruff-format` (sobre `backend/` y `scripts/`) y un hook local que **bloquea cualquier `.env`**. ESLint/Prettier y mypy se agregan cuando existan sus dependencias (S1-03, S1-05); CI los corre igual (S1-06).
- `.env.example` documenta todas las variables previstas, agrupadas por la tarea que las usa, sin secretos. Separa `trulab_owner` (migraciones) de `trulab_app` (API, sin `BYPASSRLS`).
- `scripts/etl_appsheet/input/` y `output/` están ignorados: contendrán datos personales (RNF-09).
- **Validación:** YAML de pre-commit válido; sin CRLF, sin espacios al final y con salto de línea final en los archivos nuevos; `.env` y `.env.local` ignorados y `.env.example` versionado.

**Entorno de desarrollo con Python 3.12 (complemento de S1-01 y P-5):**
- Instalado **Python 3.12.10** con `winget install --id Python.Python.3.12 -e --scope user` y las opciones `InstallAllUsers=0 PrependPath=0 Include_launcher=0 AssociateFiles=0 Shortcuts=0`, en `C:\Users\famil\AppData\Local\Programs\Python\Python312\python.exe`. **Python 3.15 se conserva** y sigue siendo el predeterminado del sistema y del `py` launcher; 3.12 se usa con `py -3.12`.
- Entorno virtual: `py -3.12 -m venv .venv` (en la raíz, ignorado por git) con `pre-commit==3.8.0` desde `requirements-dev.txt`.
- Archivos nuevos: `.python-version` (`3.12`) y `requirements-dev.txt`. En `.pre-commit-config.yaml`: `default_language_version: python: python3.12` e instrucciones de instalación con el venv.
- `pre-commit install` dejó el hook en `.git/hooks/pre-commit`. `pre-commit run --all-files`: **todos los hooks pasan** (los de JSON, TOML, ruff y `.env` se omiten porque aún no hay archivos de ese tipo); no hubo que corregir nada. Los entornos de los hooks se crearon con Python 3.12.10. El bloqueo de `.env` se probó con un archivo temporal (falla como debe) y el archivo se eliminó.

### Sesión anterior

Análisis funcional definitivo (DP-13 a DP-18), confirmación de RN-27 y DP-14, documentación congelada y publicada en GitHub (`62b91cf`).

## Trabajo completado

- [x] Hito 0: documentación base (commit `7db3188`)
- [x] **DP-01 ✅** Acceso solo con Google Workspace de Trulab, validado contra Usuarios y rol; sin contraseñas (ADR-006)
- [x] **DP-02 ✅** Proyecto = lista cerrada en cada gasto; Segmentador = filtro de fechas (ADR-017, ADR-018)
- [x] **DP-04 ✅** Solo FINANCIERO registra el valor transferido; regla de recursos propios (ADR-019)
- [x] **DP-07 ✅** Estructura real de las 5 tablas (ADR-020)
- [x] **DP-13 ✅** Dos dimensiones de estado + espejo (ADR-021)
- [x] **DP-14 ✅** Tablas maestras `proyectos`, `rubros`, `celulas` administradas por SUPERADMIN (ADR-022, reemplaza el mecanismo de ADR-017)
- [x] **DP-15 ✅** `soporte` = imagen, `archivo` = PDF, al menos uno (ADR-023)
- [x] **DP-16 ✅** Indicadores sobre `fecha_factura` (ADR-024)
- [x] **DP-17 ✅** Recursos propios lo marca el viajero al crear (ADR-019)
- [x] **DP-18 ✅** ADMIN = operación; FINANCIERO = tesorería (ADR-025)
- [x] **RN-27 ✅** Sin autoaprobación, definitiva (solo SUPERADMIN, con auditoría)
- [x] **DP-14 ✅** Confirmada definitivamente por el negocio
- [x] Memoria del proyecto actualizada
- [x] Rama renombrada a `main` y commit final de documentación
- [x] Baseline publicado en GitHub (`origin/main` = `62b91cf`)
- [x] **S1-01** Estructura del monorepo y configuración base (rama `feat/f1-estructura-monorepo`)
- [x] Entorno local con Python 3.12 (`.venv`), `pre-commit install` y `pre-commit run --all-files` en verde
- [x] **S1-02** Docker Compose local: PostgreSQL 16, API y frontend (perfil `app`), red y volúmenes
- [x] **S1-03** Backend esqueleto: FastAPI, config, db, health, problem+json, X-Request-ID, logs JSON; 13 pruebas

## Trabajo pendiente

- [ ] Integrar `feat/f1-estructura-monorepo` en `main` (push + PR o merge, cuando el usuario lo indique)
- [ ] Proteger `main` en GitHub (*Settings → Branches*; lo hace el usuario)
- [ ] Sprint 1: S1-04 a S1-13
- [ ] Semana 0, tareas aún abiertas: P-2 (exportación de **datos** y soportes de AppSheet; ahora también alimenta los catálogos iniciales), P-3 (OAuth Client ID de Google Workspace), P-4 (logo y paleta), P-5 (entorno de desarrollo)
- [ ] Validar los supuestos S-01 a S-08, salvo S-06 que ya es RN-27 (`SPEC.md` §17.3), con ADMIN y FINANCIERO, a más tardar en la demo de la semana 2
- [ ] Semanas 2 a 4

## Próxima tarea sugerida

**S1-04** · Alembic con `naming_convention`, roles de BD `trulab_owner`/`trulab_app` y extensiones `citext` y `pgcrypto` (2 h, depende de S1-03; skill `engineering:architecture`). Al crear `trulab_app`, devolver `DATABASE_URL` del `.env` local a ese rol y quitar la nota de `.env.example`. Alternativa: **S1-05** (frontend esqueleto), que solo depende de S1-01. En paralelo, sin bloquear al desarrollador:
1. Solicitar a un administrador de Google Workspace el **OAuth Client ID** (P-3). Mientras tanto se usa el login de desarrollo local (R1.1).
2. Solicitar la **exportación de datos** de AppSheet (P-2), incluidos los valores distintos de Proyecto, Rubro y Célula.
3. Decidir **DP-05** (hosting) antes de cerrar la semana 2.

## Decisiones

### Resueltas: definitivas, no reabrir (detalle en `SPEC.md` §17.1)

| ID | Resolución | ADR |
| :--- | :--- | :--- |
| DP-01 ✅ | Solo Google OAuth con Google Workspace de Trulab. Acceso solo si el correo está en Usuarios, activo y con rol. Sin registro público ni gestión de contraseñas | ADR-006 |
| DP-02 ✅ | Proyecto = lista cerrada en `gastos` (no en la legalización). Segmentador = filtro `desde`/`hasta`, no se migra | ADR-017, ADR-018 |
| DP-03 ✅ | Absorbida por DP-13: *Devolver* regresa a `PENDIENTE` con comentario | ADR-021 |
| DP-04 ✅ | Solo FINANCIERO (y SUPERADMIN) registra o modifica el valor transferido. `valor_transferido = recursos_propios ? 0 : Valor_T` | ADR-019 |
| DP-07 ✅ | Estructura real validada: Cargos, Usuarios, Crear_legalizacion, Registro_Gastos, Segmentador | ADR-020 |
| DP-13 ✅ | `estado` = PENDIENTE / APROBADO / RECHAZADO (ADMIN); `estado_financiero` = PENDIENTE / TRANSFERIDO / PAGADO / PROCESADO (FINANCIERO); `Estado legalizacion` = espejo | ADR-021 |
| DP-14 ✅ | Catálogos `proyectos`, `rubros`, `celulas` en tablas maestras, administradas por SUPERADMIN | ADR-022 |
| DP-15 ✅ | `soporte` (imagen) o `archivo` (PDF); al menos uno por gasto | ADR-023 |
| DP-16 ✅ | Indicadores sobre `gastos.fecha_factura`; sin fechas de viaje | ADR-024 |
| DP-17 ✅ | Recursos propios: lo marca el VIAJERO al crear; transferido = 0, la empresa reembolsa | ADR-019 |
| DP-18 ✅ | ADMIN aprueba, rechaza, devuelve y revisa; no toca valor transferido, `Estado_P`, pagos ni liquidación | ADR-025 |
| RN-27 ✅ | Nadie aprueba, valida financieramente ni paga una legalización creada por sí mismo; solo SUPERADMIN (soporte, contingencia, administración, pruebas controladas), con auditoría | ADR-025 |

### Abiertas, no bloqueantes (detalle en `SPEC.md` §17.2)

| ID | Tema | Cuándo |
| :--- | :--- | :--- |
| DP-05 | Hosting y almacenamiento | Gate de la semana 2 |
| DP-06 | Correos en el MVP | F6 (opcional) |
| DP-08 | Paleta y logo | UI (hay tokens provisionales) |
| DP-09 | Formato de folios / IDs históricos de AppSheet | F3 |
| DP-10 | Qué se registra al pagar (la semántica del signo ya la respalda DP-17) | F6 |
| DP-11 | Solo COP | — |
| DP-12 | Financiero no edita gastos ajenos | F5 |

## Riesgos conocidos

1. **Calendario ajustado:** déficit de unas 20 h en las semanas 1 y 2 (`SPRINTS.md`, resumen de capacidad). Plan B: una semana 5 de holgura.
2. **Alcance nuevo sin estimar** (por instrucción, el plan no se re-estimó): administración de catálogos para SUPERADMIN (RF-016, F-03b), segunda dimensión de estado (`estado_financiero`) y tres acciones de ADMIN en lugar de dos. Estimación informal: +6 a 8 h repartidas entre S2-04, S2-05, S2-10 y S3-01. Agrava el riesgo 1.
3. **Supuestos S-01 a S-08 por validar** (S-06 ya es la regla definitiva RN-27) (`SPEC.md` §17.3), en especial la semántica y el orden de `Estado_P` (S-03), devolver desde `APROBADO` (S-01) y la ausencia de un paso "enviar" (S-02): ADMIN podría aprobar mientras el viajero aún carga gastos.
4. **Datos históricos inconsistentes** con las reglas nuevas: `Estado_P` `Pagado` con `Estado` distinto de `Aprobado`, valores de catálogo con grafías distintas, PDF guardados en `Soporte`. El ETL los reporta; hay que decidir con el negocio antes del corte.
5. **Migración de soportes** desde AppSheet o Google Drive: volumen y permisos desconocidos (P-2). Dos adjuntos por gasto.
6. **Dependencia externa** para el OAuth Client ID (admin de Google Workspace).
7. **WeasyPrint en Windows:** mitigado ejecutando el backend en Docker.
8. **Datos personales:** la cédula (usuarios y legalizaciones) exige un manejo cuidadoso (RNF-09).
9. **Dos Pythons en el equipo:** 3.15 es el predeterminado del sistema y no sirve para el proyecto (sin wheels de PyYAML). *Mitigación:* `.python-version`, `.venv` con 3.12 y `default_language_version` en pre-commit; ejecutar siempre desde `.venv`. Docker Desktop ya funciona (necesario para S1-02 y S1-03).
9. **Hosting (DP-05)** sin decidir: bloquea la infraestructura de la semana 3 si no se resuelve en el gate de la semana 2.

## Diferencias entre el informe original y la app real (resueltas en la documentación)

- El proyecto estaba en la legalización → realmente está **en el gasto** (lista cerrada, ahora tabla maestra).
- `Segmentador` como "clasificación" → realmente es **solo un filtro de fechas**, que se aplica sobre la **fecha de factura**.
- Login con JWT y contraseña bcrypt → realmente es **solo Google Workspace**, sin contraseñas.
- `fecha_inicio`/`fecha_fin` → realmente solo hay **`Fecha legalizacion`**; no se agregan fechas de viaje.
- Un estado `BORRADOR → LEGALIZADA → PAGADA` → realmente hay **dos**: operativo (Pendiente/Aprobado/Rechazado, ADMIN) y financiero (Pendiente/Transferido/Pagado/Procesado, FINANCIERO), más un espejo.
- ADMIN pagaba y devolvía → realmente ADMIN es **operación** (aprueba, rechaza, devuelve) y no toca dinero.
- Gasto con `descripcion` y un soporte → realmente tiene **rubro, concepto, CC_Nit, empresa, observaciones, Soporte (imagen) y Archivo (PDF)**, con al menos uno de los dos.
- Usuario sin cédula ni célula → realmente tiene **cédula y célula**.
- Valor transferido manual → realmente se **calcula a partir de Recursos propios** (que marca el viajero) y `Valor_T` (que registra FINANCIERO).

---

## Historial de sesiones

### 2026-11-11 · Sesión 4: inicio del Sprint 1, S1-01
- Verificado `main` = `origin/main` = `62b91cf`.
- S1-01: carpetas `backend/`, `frontend/`, `infra/`, `scripts/etl_appsheet/` con README; `.gitignore`, `.editorconfig`, `.gitattributes`, `.env.example`, `.pre-commit-config.yaml`. Commit en `feat/f1-estructura-monorepo`.
- `pre-commit` no ejecutado por falta de Python 3.12/Docker; validación manual equivalente sobre los archivos nuevos.
- Se detuvo tras S1-01 a pedido del usuario.
- Corrección del entorno: Python 3.12.10 instalado junto a 3.15 (sin tocarlo), `.venv` con 3.12, `.python-version`, `requirements-dev.txt`, pre-commit fijado a 3.12. `pre-commit run --all-files` en verde. Commit en la misma rama; sin merge ni push.
- S1-02: Docker Compose en `infra/` (db PostgreSQL 16.4; api y frontend en el perfil `app`), Dockerfiles de desarrollo, `.dockerignore`. MinIO descartado (imágenes no disponibles); BD en el puerto 5433 del host por un PostgreSQL nativo en 5432. Validado con un `.env` temporal; entorno de prueba limpiado. Commit en la misma rama; sin merge ni push.
- S1-03: esqueleto FastAPI (`app/main.py`, `core/` config, db, errors, middleware, logs, health), requirements y pyproject, 13 pruebas, `api` fuera del perfil `app`, mypy en pre-commit. Validado en Docker con PostgreSQL real. Commit en la misma rama; sin merge ni push.

### 2026-11-11 · Sesión 3: análisis funcional definitivo (DP-13 a DP-18)
- Resueltas DP-13, DP-14, DP-15, DP-16, DP-17 y DP-18; DP-03 absorbida por DP-13. Nuevos ADR-021 a ADR-025; ADR-017 queda reemplazado en su mecanismo por ADR-022; ADR-019 incluye DP-17.
- Reglas reescritas: RN-03, RN-05, RN-06, RN-07, RN-09, RN-10, RN-13, RN-16, RN-18. Reglas nuevas: RN-20 a RN-27. RF-016 (catálogos) nuevo; RF-005, RF-006, RF-007, RF-010, RF-013 y RF-015 ajustados. Supuestos S-01 a S-08 en `SPEC.md` §17.3.
- Modelo de datos: `estado` + `estado_financiero` con `CHECK` de coherencia, tablas `proyectos`/`rubros`/`celulas`, `soporte_id`/`archivo_id`, nuevos eventos (`APROBAR`, `RECHAZAR`, `CAMBIAR_ESTADO_FINANCIERO`), mapeo de estados con emojis para el ETL.
- API: acciones `aprobar`, `rechazar`, `devolver` (ADMIN) y `estado-financiero` (FINANCIERO); endpoints de catálogos para SUPERADMIN; indicadores sobre `fecha_factura`.
- Documentos: `SPEC.md` (v0.3), `CLAUDE.md`, `HANDOFF.md`, `docs/database-design.md`, `docs/architecture.md`, `docs/api-design.md`, `docs/user-flows.md`, `docs/design-system.md`; en `ROADMAP.md` y `SPRINTS.md` solo marcas de estado de las decisiones y una nota de terminología (sin cambios en tareas ni estimaciones).
- Validación con el negocio: RN-27 pasa de supuesto (S-06) a regla definitiva; DP-14 confirmada (tablas maestras, cambio solo interno). Documentación congelada.
- Rama `master` renombrada a `main`; commit "docs: finalize requirements, business rules and project decisions". Sin push.
- El proyecto queda listo para iniciar oficialmente el Sprint 1.

### 2026-11-10 · Sesión 2: resolución de decisiones principales
- Resueltas DP-01, DP-02, DP-04 y DP-07 con evidencia de la configuración y la estructura real de AppSheet. Registradas como definitivas (ADR-006 y ADR-017 a ADR-020).
- Nuevas reglas de negocio: RN-14 a RN-19. RF-002 eliminado; RF-015 agregado.
- Modelo de datos ajustado: `rubro`/`proyecto` en gastos, `recursos_propios` + `valor_asignado` + `valor_transferido` generado, instantánea del colaborador, cédula y célula.
- Nuevas preguntas abiertas DP-13 a DP-18 (resueltas en la sesión 3). La planificación no cambió.

### 2026-11-10 · Sesión 1: inicialización y documentación base
- Git inicializado, identidad local `John.Hernandez@trulab.co`, remote `origin` configurado (repositorio remoto vacío).
- Generada toda la documentación estratégica a partir del informe. Sin código.
- Revisión de consistencia: unificado el plazo de DP-05 (antes de cerrar la semana 2), DP-07 apunta a F4 y F10, aclarada la nota ¹ de RBAC (editar vs eliminar).
- Commit local del hito 0 (`7db3188`).
