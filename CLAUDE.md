# CLAUDE.md — Memoria del proyecto Trulab Viajes

> Lee este archivo primero y después `HANDOFF.md`. Con ambos deberías poder retomar el trabajo sin releer el informe original.
> Mantenlo corto y actualizado: los detalles viven en `SPEC.md` y `docs/`.

## Qué es

Reconstrucción con código propio de la app AppSheet **"Trulab viajes"**, el sistema de viáticos de Trulab. Los colaboradores registran los gastos de sus viajes con soporte digital. Financiero audita el saldo (transferido − gastado) y liquida.

**Objetivo:** reemplazar AppSheet con un MVP responsivo (móvil, tablet y escritorio) y con seguridad en el backend. Lo hace **1 desarrollador en 4 semanas**.

## Mapa de documentos

| Archivo | Para qué |
| :--- | :--- |
| `SPEC.md` | **Fuente de verdad:** alcance, roles y permisos (§6), reglas RN-xx (§8), RF y RNF, MVP, **decisiones abiertas DP-xx (§17)** |
| `HANDOFF.md` | Estado actual y próxima tarea; se actualiza en cada sesión |
| `ROADMAP.md` | Fases F1–F10, dependencias, hitos, contingencia |
| `SPRINTS.md` | Tareas por semana con estimación, riesgos, criterios y gates |
| `docs/architecture.md` | Arquitectura y **registro de ADR (§13)** |
| `docs/database-design.md` | Tablas, relaciones, índices, RLS, auditoría, nomenclatura |
| `docs/api-design.md` | Contrato REST, errores, paginación, permisos por endpoint |
| `docs/design-system.md` | Tokens, componentes, layouts mobile-first |
| `docs/user-flows.md` | Flujos F-01 a F-11 y máquina de estados |
| `docs/skills-strategy.md` | Qué skill usar para cada tipo de trabajo |

El informe original de auditoría de AppSheet (*INFORME FINAL PARA PROYECTO TRULAB.md*) **no está en el repo**; todo lo útil se consolidó en `SPEC.md`.

## Stack

- **Frontend:** React 18 + Vite 6 + TypeScript 5.9, Tailwind 3 + shadcn/ui, TanStack Query, React Router, React Hook Form + Zod, Recharts, Lucide.
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (síncrono), Alembic, psycopg 3, WeasyPrint.
- **Datos:** PostgreSQL 16 con RLS; archivos en un bucket privado compatible con S3 o GCS.
- **Runtime del frontend:** Node 24 LTS, estándar del proyecto (**ADR-026**, aprobado el 2026-11-12); versión fijada en `frontend/.nvmrc` (24.22.1), igual que la imagen. Versiones npm exactas.
- **Herramientas:** Docker Compose, GitHub Actions, ruff, mypy, pytest, ESLint, Vitest, Playwright.

## Arquitectura en una frase

Monolito modular: la SPA React habla REST (`/api/v1`) con FastAPI (`routers → services → models`), que usa PostgreSQL y un bucket privado. La autenticación es con Google y una sesión propia (access JWT de 15 min en memoria más refresh rotativo en cookie httpOnly). La autorización va en el service, con RLS como defensa en profundidad.

## Estructura (carpetas raíz creadas en S1-01; el código llega desde S1-03 y S1-05)

```
backend/app/{core,modules/<dominio>,templates/pdf}   backend/{alembic,tests}
frontend/src/{app,components/{ui,layout},features/<dominio>,lib,types}
infra/{docker,db/init}  scripts/etl_appsheet/  docs/
```

Dominios: `auth`, `usuarios`, `cargos`, `catalogos` (tablas maestras proyectos, rubros y células; las administra SUPERADMIN), `legalizaciones`, `gastos`, `pagos`, `reportes`, `indicadores`.

## Roles y módulos

- **Roles** (uno por usuario): `VIAJERO` (solo lo suyo), `ADMIN` (operación interna: aprueba, rechaza y devuelve; gestiona usuarios y cargos; **no** toca dinero), `FINANCIERO` (tesorería: valor transferido, estado financiero, pagos y liquidación; ve todo), `SUPERADMIN` (todo, incluidos los catálogos). Matriz completa en `SPEC.md` §6.
- **Módulos MVP:** Auth, Usuarios, Cargos, Catálogos, Legalizaciones, Gastos, Pagos, PDF, Indicadores. Las notificaciones son opcionales. OCR y Google Chat quedan para el futuro.
- **Estados (DP-13 ✅):** dos dimensiones independientes. `estado` (operativo, AppSheet `Estado`): `PENDIENTE → APROBADO | RECHAZADO`; *devolver* regresa a `PENDIENTE` con comentario; lo cambia solo ADMIN/SUPERADMIN. `estado_financiero` (AppSheet `Estado_P`): `PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO`; lo cambia solo FINANCIERO/SUPERADMIN; `PAGADO`/`PROCESADO` exigen `APROBADO`. `Estado legalizacion` = `[Estado]`, no se almacena.

## Decisiones DEFINITIVAS (resueltas el 2026-11-10 y el 2026-11-11; no reabrir)

Se confirmaron contra la configuración y la estructura real de AppSheet. Solo cambian si el dueño del producto lo decide de forma explícita, y en ese caso se registra un ADR nuevo. Detalle en `SPEC.md` §17.1.

- **DP-01 ✅ Acceso:** solo **Google OAuth con cuentas de Google Workspace de Trulab**. Además, el correo debe existir en Usuarios, estar activo y tener rol; si no, el acceso se deniega. **No hay** registro público, contraseñas, recuperación, restablecimiento ni cambio de contraseña. Las credenciales las gestiona Google Workspace (ADR-006).
- **DP-02 ✅ Proyectos:** `Proyecto` es una **lista cerrada en cada gasto** (`Registro_Gastos`), no en la legalización; el mecanismo (tabla maestra) lo fija DP-14. `Segmentador` **no** son proyectos: es solo el filtro de fechas del dashboard y se reemplaza por `desde`/`hasta` (ADR-017, ADR-018).
- **DP-04 ✅ Valor transferido:** solo **FINANCIERO** lo registra y modifica (SUPERADMIN, para soporte); ADMIN y VIAJERO no. `valor_transferido = recursos_propios ? 0 : valor_asignado (Valor_T)`, calculado y nunca escrito a mano (ADR-019).
- **DP-07 ✅ Estructura real:** las 5 tablas están validadas (`SPEC.md` §18). Los datos del colaborador vienen del usuario autenticado (`LOOKUP(USEREMAIL())`). Hay rubro, CC/NIT, empresa, dos adjuntos y fecha de factura en el gasto, y una sola fecha de legalización en la cabecera (ADR-020).

- **DP-13 ✅ Estados:** `Estado` = Pendiente ⛔ / Aprobado / Rechazado (ADMIN aprueba, rechaza, devuelve); `Estado_P` = Pendiente⌛ / Pagado / Transferido / Procesado (solo FINANCIERO y SUPERADMIN); `Estado legalizacion` = espejo de `Estado`. `Devuelto` y `Cancelado` son extensión futura (ADR-021).
- **DP-14 ✅ Catálogos:** proyectos, rubros y células **no se escriben en el código**: tablas maestras administradas por SUPERADMIN, que se desactivan y no se borran. `Rol` sigue como enum fijo. Para el usuario no cambia nada (lista desplegable); internamente se guarda la referencia a la tabla, no el texto (ADR-022).
- **RN-27 ✅ Sin autoaprobación (definitiva):** nadie aprueba, valida financieramente ni paga una legalización creada por sí mismo; solo SUPERADMIN, con auditoría (ADR-025).
- **DP-15 ✅ Adjuntos:** `soporte` = imagen, `archivo` = PDF; **al menos uno** por gasto para aprobar y liquidar (ADR-023).
- **DP-16 ✅ Fechas:** indicadores siempre sobre `gastos.fecha_factura BETWEEN desde AND hasta`; no hay fechas de viaje (ADR-024).
- **DP-17 ✅ Recursos propios:** lo marca el VIAJERO al crear; transferido = 0 y la empresa reembolsa (ADR-019).
- **DP-18 ✅ ADMIN:** operación interna; no registra valor transferido, no cambia `Estado_P`, no paga ni liquida. Separación de funciones con FINANCIERO (ADR-025).

**No quedan decisiones bloqueantes.** Siguen abiertas, sin bloquear: DP-05 hosting (gate al cerrar la semana 2), DP-06 correos, DP-08 marca, DP-09 folios, DP-10 qué se registra al pagar, DP-12 (recomendación: financiero no edita gastos). Los supuestos de detalle S-01 a S-08 (`SPEC.md` §17.3) se validan en la demo de la semana 2.

## Decisiones clave (ver ADR en `docs/architecture.md` §13)

1. Las transiciones de estado son **acciones** (`POST /legalizaciones/{id}/aprobar|rechazar|devolver` para ADMIN y `POST /legalizaciones/{id}/estado-financiero` para FINANCIERO) que pasan por una única función `transicionar()`, la cual registra el historial en la misma transacción.
2. **El saldo nunca se almacena:** sale de la vista `v_legalizacion_saldos` (`valor_transferido − Σ gastos`). `valor_transferido` es una columna generada a partir de `recursos_propios` y `valor_asignado`.
3. **Recurso ajeno → 404**, sin permiso → 403, estado inválido → 409. Los errores siguen RFC 9457 con `code` estable.
4. **Dinero:** `NUMERIC(14,2)` en BD y *string* en JSON. Moneda COP.
5. **PK UUID** más folio legible (`LG-000001`, `CA-000001`).
6. **Eliminación lógica** (`deleted_at`); los usuarios se desactivan, no se borran.
7. **Soportes** en un bucket privado, validados por *magic bytes*, con máximo de 10 MB y servidos con URL firmada de 5 min.
8. El backend siempre corre en Docker (por WeasyPrint y la paridad con producción).

## Convenciones técnicas

- **Idioma:** dominio, BD, API y UI en **español**. Código de infraestructura y nombres técnicos genéricos en inglés (`router`, `service`, `schemas`).
- **Nombres:** tablas en `snake_case` plural; JSON en `snake_case`; componentes React en `PascalCase`; hooks como `useX`. Más detalle en `docs/database-design.md` §9.
- **Reglas de negocio solo en `services`**; routers delgados; nada de lógica de negocio en componentes React.
- **TDD obligatorio** para reglas RN-xx y permisos. Una prueba parametrizada recorre la matriz RBAC.
- **Migraciones solo con Alembic.** Los tipos TS se generan desde OpenAPI; no se escriben a mano.
- **Git:** rama `main` protegida; ramas `feat/<fase>-<tema>`, `fix/...`; commits convencionales en español (`feat(gastos): subir soporte`).
- **Secretos** solo en `.env` (no versionado); se mantiene `.env.example` al día. Un hook de pre-commit bloquea cualquier `.env`.
- **Formato:** `.editorconfig` (UTF-8, LF, 2 espacios; 4 en Python) y `.gitattributes` (`eol=lf`, por los contenedores Linux). Hooks en `.pre-commit-config.yaml` (genéricos, ruff, mypy); ESLint, Prettier y `tsc` del frontend desde S1-05.
- **Docker local:** `infra/docker-compose.yml`; desde la raíz `docker compose up -d` (gracias a `COMPOSE_FILE` en `.env`) levanta `db`, aplica las migraciones (servicio `migrate`) y arranca `api` y `frontend` (http://localhost:5173; Vite reenvía `/api` a `api:8000`, sin CORS en local). BD en `127.0.0.1:5433` (5432 lo ocupa un PostgreSQL nativo de Windows). Sin MinIO: en local `STORAGE_BACKEND=local`. Detalle en `infra/README.md`.
- **Roles de BD (S1-04):** `postgres` = superusuario de arranque (solo init); `trulab_owner` = dueño de la BD, **no** superusuario, ejecuta Alembic (`DATABASE_URL_MIGRATIONS`); `trulab_app` = la API (`DATABASE_URL`), solo DML por privilegios por defecto, sin DDL ni `BYPASSRLS`. Roles en `infra/db/init/10-roles.sh` (idempotente); extensiones y privilegios en Alembic. La API no recibe credenciales de dueño.
- **Frontend:** comandos con `docker compose exec frontend npm run lint|typecheck|format:check|test|build|gen:api`. Para el editor y pre-commit, `npm ci` en `frontend/` del equipo (el contenedor usa su propio volumen de `node_modules`). `src/types/api.ts` se genera desde OpenAPI (`gen:api`), no se edita. Las llamadas a la API van siempre por `src/lib/api-client.ts`. Detalle en `frontend/README.md`.
- **CI (S1-06):** `.github/workflows/ci.yml` con 4 jobs obligatorios: `pre-commit` (todos los hooks), `backend` (Docker Compose + PostgreSQL real: ruff, mypy, migraciones de ida y vuelta, `alembic check`, pytest completo), `frontend` (Node 24: ESLint, tsc, Prettier, Vitest, build) e `integracion` (Compose completo, humo y contrato: `src/types/api.ts` debe coincidir con el OpenAPI). Actions fijadas por SHA, `permissions: contents: read`, sin secretos (`.env` generado con `scripts/crear_env.py`). Workflows validados con actionlint (hook de pre-commit). Si cambia la API, regenerar los tipos (`gen:api`) o la CI falla.
- **Identidad y auditoría (S1-07):** tablas `usuarios` (correo CITEXT, sin contraseña, `google_sub` para el primer login), `cargos` (folio `CA-000001`), `celulas` (catálogo), `sesiones` (solo SHA-256 del refresh, con `CHECK`) y `auditoria` (`app/core/audit.py`: `registrar()` en la misma transacción, sanea secretos y enmascara la cédula; solo inserción por `REVOKE` y trigger, también para `trulab_owner`). Columnas base con los mixins de `app/core/models.py`; enums en `app/core/enums.py`. `trulab_app` no borra físicamente `usuarios`, `cargos` ni `celulas`. SUPERADMIN inicial: `SUPERADMIN_EMAIL`, creado por `migrate` solo si no hay ninguno activo. Pruebas de BD con el fixture `sesion` (transacción revertida).
- **Migraciones:** `docker compose run --rm migrate alembic revision --autogenerate -m "..."`; modelos en `app/modules/<dominio>/models.py` heredando de `app.core.models.Base` (con `naming_convention`). Las tablas de solo inserción revocan `UPDATE`/`DELETE` a `trulab_app` en su migración. Reglas y comandos en `backend/README.md`.
- **Python local = 3.12** (`.python-version`), en `.venv` creado con `py -3.12 -m venv .venv` e instalado con `requirements-dev.txt`. El equipo también tiene Python 3.15 como predeterminado del sistema: **no usarlo** para el proyecto (sin wheels de PyYAML). Usar siempre `.venv\Scripts\python` y `.venv\Scripts\pre-commit`.
- **Identidad git local:** `John Hernandez <John.Hernandez@trulab.co>`; remote `origin` en GitHub (`johnhernandez-prog/Trulab_Viaticos`).

## Estado actual

**Fase:** **Sprint 1 en curso** (semana 1, F1). Todas las decisiones bloqueantes están resueltas (DP-01, DP-02, DP-04 y DP-07 el 2026-11-10; DP-13 a DP-18 el 2026-11-11). **S1-01 a S1-07 terminadas** (estructura, configuración, Docker Compose, esqueleto del backend: `GET /api/v1/health`, docs en `/api/v1/docs`, problem+json, `X-Request-ID`, logs JSON; y persistencia: Alembic con `naming_convention`, roles `trulab_owner`/`trulab_app` con mínimo privilegio, `citext` y `pgcrypto`; frontend esqueleto con página temporal; CI en GitHub Actions; y modelo de identidad y auditoría con SUPERADMIN inicial); sin auth, endpoints de negocio ni pantallas funcionales todavía. **La documentación está congelada** como baseline de requisitos (commit "docs: finalize requirements, business rules and project decisions"); cambiarla exige decisión del dueño del producto y ADR. El detalle vivo está en `HANDOFF.md`.

## Cómo retomar

1. Lee `HANDOFF.md`: estado, próxima tarea y bloqueos.
2. Abre solo la sección de la semana actual en `SPRINTS.md`.
3. Consulta `SPEC.md` y el `docs/` relevante a la tarea (no todo).
4. Si dudas de una decisión pasada, revisa los ADR y luego usa `claude-mem:mem-search`.
5. Trabaja con la skill indicada en la tarea (`docs/skills-strategy.md`).
6. Al cerrar, actualiza `HANDOFF.md` (`claude-mem:handoff`) y este archivo si cambió una decisión, el stack o el estado.

## Orden recomendado de desarrollo

F1 Base técnica → F2 Auth/RBAC → F3 Usuarios/Cargos → F4 Legalizaciones → F5 Gastos → F6 Pagos → F7 PDF → F8 Dashboard → F9 Pruebas (continuas y cierre) → F10 Producción + ETL. Nunca se empieza un módulo funcional antes de que F2 esté probado.
