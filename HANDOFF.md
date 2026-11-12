# HANDOFF — Trulab Viajes

> Documento vivo para retomar entre sesiones. Se actualiza al final de **cada** sesión (skill `claude-mem:handoff`).
> Formato: se sobrescriben las secciones de estado. El historial se acumula al final (lo más reciente arriba).

## Estado actual

| Campo | Valor |
| :--- | :--- |
| Fase | **Sprint 1 en curso** (semana 1 · F1 base técnica). Documentación congelada (baseline `62b91cf`) |
| Semana del sprint | Semana 1: **S1-01 ✅ a S1-07 ✅ terminadas**; S1-08 a S1-13 pendientes |
| Código | Esqueleto del backend FastAPI (health, errores, request id, logs) en Docker, con Alembic, roles `trulab_owner`/`trulab_app` y extensiones `citext`/`pgcrypto`; frontend esqueleto (React 18, Vite, TS, Tailwind, shadcn/ui, React Router, TanStack Query) con página temporal; CI en GitHub Actions (4 jobs); modelo de identidad y auditoría (`usuarios`, `cargos`, `celulas`, `sesiones`, `auditoria`) y SUPERADMIN inicial; sin auth, endpoints de negocio ni pantallas funcionales |
| Repositorio | `main` = `origin/main` = `62b91cf` (baseline publicado en GitHub). S1-01 a S1-07 están en la rama **`feat/f1-estructura-monorepo`** (sin push ni merge) |
| Última actualización | 2026-11-12 |

## Última actividad

**S1-07 · Modelo de identidad y auditoría.** Migración `20261112_1433_identidad_y_auditoria` (`a154d56e054d`) con 5 tablas, sus modelos SQLAlchemy y el SUPERADMIN inicial. Sin endpoints, sin login ni matriz de permisos.

**Modelo:**

| Tabla | Modelo | Contenido |
| :--- | :--- | :--- |
| `usuarios` | `app/modules/usuarios/models.py` | Columnas base + `nombre_completo`, `correo` (**CITEXT**, único, `CHECK` de formato), `cedula` (única entre no eliminados, parcial), `celula_id` → `celulas`, `rol` (`CHECK` con los 4 roles), `cargo_id` → `cargos`, `activo` (por defecto `true`), `google_sub` (único, nulo hasta el primer login), `ultimo_acceso`. **Sin contraseña** (DP-01, RN-15) |
| `cargos` | `app/modules/cargos/models.py` | Columnas base + `folio` **CA-000001** desde `seq_folio_cargos` (RN-04; la secuencia pertenece a la columna), `nombre` (único sin distinguir mayúsculas entre no eliminados: se puede recrear uno eliminado), `descripcion` |
| `celulas` | `app/modules/catalogos/models.py` | Catálogo (DP-14): `nombre` único sin distinguir mayúsculas, `activo`, `orden`, autores, `migrado_de`; sin `deleted_at` (se desactiva). Estructura común `ConCatalogo`, reutilizable para `proyectos` y `rubros`. **Sin valores en el código**: llegan de la exportación de AppSheet (P-2) o de la administración (RF-016) |
| `sesiones` | `app/modules/auth/models.py` | `usuario_id` (FK `CASCADE`), `token_hash` (único; **`CHECK` de 64 hexadecimales**, así que un refresh token en claro no puede guardarse), `expires_at` (> `created_at`), `revoked_at`, `ip` (INET), `user_agent` |
| `auditoria` | `app/core/audit.py` | `id` BIGINT identity, `usuario_id` (actor, FK `SET NULL`), `accion` (`CHECK` de formato), `entidad`, `entidad_id`, `datos` JSONB (objeto), `ip`, `user_agent`, `created_at` |

- **Columnas base** como mixins en `app/core/models.py` (`ConId`, `ConMarcasDeTiempo`, `ConAutores`, `ConBorradoLogico`, `ConMigradoDe`); todo `datetime` es `TIMESTAMPTZ`. Todas las FK llevan índice; `UNIQUE (migrado_de)` parcial en las tablas que migra el ETL.
- **Enums del sistema** en `app/core/enums.py` (`Rol`). Las acciones de auditoría en `AccionAuditoria`.
- **Ciclo de FK** `usuarios` ↔ `cargos`/`celulas` (`created_by` en ambas direcciones): `use_alter=True` en el modelo y FK creadas al final de la migración.
- **Privilegios de `trulab_app`** (más estrictos que los por defecto): `usuarios`, `cargos` y `celulas` sin `DELETE` (se desactivan o se eliminan lógicamente); `auditoria` solo `INSERT, SELECT`; `sesiones` DML completo.
- **SUPERADMIN inicial:** `app/modules/usuarios/service.py` (`asegurar_superadmin_inicial`) y el comando `python -m app.modules.usuarios.seed`, que el servicio `migrate` ejecuta tras `alembic upgrade head`. Variables nuevas: `SUPERADMIN_NOMBRE` y, en `Settings`, `google_workspace_domain`, `superadmin_email` y `superadmin_nombre`.
- `alembic/env.py`: importa los modelos de `app/core` (`MODELOS_CORE`) y omite en `alembic check` los defaults con `nextval()`.
- **64 pruebas nuevas en el backend** (de 28 a 92): `test_modelo_identidad.py` (restricciones, unicidad, folios, privilegios, sesiones), `test_auditoria.py` (saneamiento, inserción, solo inserción para `trulab_app`), `test_superadmin_inicial.py` (todas las ramas del seed y del comando) y 5 más en `test_migraciones.py` con `trulab_owner` (trigger de solo inserción, purga con `SET NULL`, privilegios). Fixture `sesion` (transacción revertida) y `tests/fabricas.py`.

**Estrategia de auditoría** (docs/database-design.md §7):
1. **Columnas base** en todas las tablas: `created_at/updated_at` y `created_by/updated_by` (las fija el service con el usuario autenticado desde S1-10; `NULL` = sistema o ETL).
2. **`auditoria`** para seguridad y administración. `registrar(session, accion, entidad, entidad_id, usuario_id=..., datos=..., ip=..., user_agent=...)` agrega la fila a la **misma transacción** que el cambio. `datos` se sanea: **rechaza** claves de secretos (`token`, `refresh_token`, `id_token`, `token_hash`, `password`, `cookie`, `authorization`…, en cualquier nivel) y **enmascara** la cédula (`******4050`).
3. **Solo inserción, en dos capas:** `trulab_app` no tiene `UPDATE`/`DELETE`, y el trigger `tg_auditoria__solo_insercion` (más `tg_auditoria__sin_truncate`) rechaza `UPDATE`, `DELETE` y `TRUNCATE` **para cualquier rol**, incluido `trulab_owner`. Única excepción: el `SET NULL` de `usuario_id` que hace la FK si se purga un usuario.
4. `legalizacion_eventos` (historial funcional) llega con F4.

**Estrategia para Google Workspace** (se implementa en S1-08; el modelo ya está listo):
- `POST /auth/google` verifica el ID token de Google (firma, `aud` = `GOOGLE_CLIENT_ID`, `iss`, vencimiento, `email_verified`) y exige `hd` = `GOOGLE_WORKSPACE_DOMAIN` (RN-12).
- Busca el usuario por `correo` (CITEXT: sin distinguir mayúsculas). Si no existe, está inactivo o no tiene rol: **403** y `auditoria` `ACCESO_DENEGADO` (sin token, solo el motivo y el correo).
- **Primer login:** fija `google_sub` (único). En los siguientes se exige que el `sub` coincida: si la cuenta de Google se recreó con el mismo correo, se deniega hasta que un administrador lo revise. Actualiza `ultimo_acceso`.
- **Sesión propia** (ADR-005): access JWT de 15 min en memoria; refresh opaco aleatorio en cookie httpOnly, del que en `sesiones` solo se guarda el SHA-256 (el `CHECK` lo garantiza). Rotación en cada `/auth/refresh` (revoca la anterior con `revoked_at` y crea otra); logout, desactivación y cambio de rol revocan las sesiones del usuario.
- Sin contraseñas ni autorregistro: los usuarios los crean ADMIN o SUPERADMIN (S1-10); el primero, el seed.

**Decisiones técnicas de S1-07:**
- **`celulas` entra en S1-07** porque `usuarios.celula_id` es FK a ella (§2.2, §3). Solo la tabla y su modelo; `proyectos` y `rubros` llegan con `gastos`, y la API de catálogos con S2-05.
- **Modelo de auditoría en `app/core/audit.py`** (donde lo ubica `docs/architecture.md` §3), no en un dominio: es transversal.
- **SUPERADMIN inicial solo si no hay ninguno activo** (y no en cada arranque): la variable de entorno no sirve para crear superadministradores adicionales; si todos quedaran inactivos, el seed recupera el acceso (promueve y reactiva) y lo audita. El comando falla si el correo no es del dominio, así que `migrate` y la API no arrancan con una configuración inválida.
- **El seed usa `trulab_app`**, no `trulab_owner`: crear un usuario es una operación de la app y respeta sus privilegios.
- **Sin `DELETE` físico para la app** en `usuarios`, `cargos` y `celulas`: la eliminación lógica queda garantizada también en la BD.
- **Trigger de solo inserción** además del `REVOKE`: protege la auditoría también frente a `trulab_owner` (ETL o errores manuales).
- **`updated_at` con `onupdate` del ORM** (el documento admite ORM o trigger): más simple y visible en el modelo.
- **`entidad` NOT NULL** en `auditoria` (por ejemplo `auth` para `ACCESO_DENEGADO`), para poder consultar por entidad.

**Validaciones de S1-07 (con un `.env` generado por `scripts/crear_env.py`, luego eliminado):**
- `alembic upgrade head` aplica `a154d56e054d`; `alembic check`: "No new upgrade operations detected"; `downgrade -1` → `upgrade head` → `check` en verde (la secuencia se borra con la tabla).
- BD: 5 tablas de `trulab_owner`, secuencias `seq_folio_cargos` y `auditoria_id_seq`; privilegios de `trulab_app`: `auditoria` {INSERT, SELECT}, `usuarios`/`cargos`/`celulas` {INSERT, SELECT, UPDATE}, `sesiones` {DELETE, INSERT, SELECT, UPDATE}.
- Seed de punta a punta con `SUPERADMIN_EMAIL`: primera vez `CREADO` (con `USUARIO_CREAR` en `auditoria`, sin actor), segunda vez `YA_HAY_SUPERADMIN`; con un correo de otro dominio, `migrate` termina con código 1.
- Pruebas: **92/92** en `migrate`; en `api`, 83 pasan y 9 se omiten (necesitan `trulab_owner`). Las pruebas no dejan datos (transacciones revertidas). Frontend: 17/17.
- `ruff check`, `ruff format --check` y `mypy` strict (`app tests alembic`) en verde. ESLint, tsc y Prettier del frontend en verde.
- **CI completa ejecutada en local** (pasos `run:` de `ci.yml`): `backend`, `frontend` e `integracion` en verde (incluye migraciones de ida y vuelta desde cero, `alembic check`, 92 pruebas y el contrato OpenAPI sin cambios). `pre-commit` falló la primera vez con "files were modified by this hook" porque se editó `backend/README.md` mientras corría (no era un error de formato); repetido sin ediciones en paralelo: en verde.
- `pre-commit run --all-files`: en verde.
- Limpieza: `docker compose down -v` y `.env` eliminado.

**S1-06 · Integración continua (GitHub Actions).** Workflow `.github/workflows/ci.yml` (`CI`), con cuatro jobs que deben pasar todos:

| Job | Qué valida | Cómo |
| :--- | :--- | :--- |
| `pre-commit` | Los mismos hooks que en local: genéricos, ruff, ruff-format, mypy, actionlint, Prettier, ESLint y tsc | Python de `.python-version`, Node de `frontend/.nvmrc`, `npm ci` del frontend y `pre-commit run --all-files --show-diff-on-failure` |
| `backend` | Imagen Docker del backend; ruff, `ruff format --check` y mypy strict dentro del contenedor; migraciones (`alembic check`, `downgrade base`, `upgrade head`, `alembic check`); **pytest completo** (28, sin omitidas, también las que usan `trulab_owner`); `/health` con `trulab_app` | Docker Compose (`db` + `migrate` + `api`) con PostgreSQL 16.4 real y los roles creados por `10-roles.sh`, igual que en local |
| `frontend` | ESLint, `tsc -b`, Prettier, Vitest (17) y build de producción | Node 24 en el runner (`frontend/.nvmrc`), `npm ci` |
| `integracion` (necesita `backend` y `frontend`) | Construye todas las imágenes y levanta el entorno completo; humo de la SPA, del respaldo de rutas, del proxy `/api` y de `openapi.json`; **contrato**: regenera `src/types/api.ts` desde la API real y falla si difiere del versionado | `docker compose up -d --wait`, `curl`, `npm run gen:api` y `git diff --exit-code` |

- **Disparadores:** `push` a `main`, `feat/**` y `fix/**`; `pull_request` hacia `main`; `workflow_dispatch`. `concurrency` por flujo, evento y rama, con `cancel-in-progress` (un push nuevo cancela el anterior de la misma rama sin cancelar la ejecución del PR).
- **Seguridad:** `permissions: contents: read`; actions oficiales **fijadas por SHA** con su versión en comentario (`checkout` v7.0.1, `setup-python` v7.1.0, `setup-node` v7.1.0, `cache` v6.1.0); sin secretos (el `.env` de CI se genera con contraseñas aleatorias en cada job); `timeout-minutes` en todos los jobs.
- **Fallo ante errores:** cada paso corre con `bash -eo pipefail`; cualquier comando con código distinto de 0 detiene el job y la pipeline. Si falla, se vuelcan los logs de los contenedores; el entorno se baja siempre (`down -v`).
- **Archivos nuevos:** `.github/workflows/ci.yml`, `scripts/crear_env.py` (crea `.env` desde `.env.example` con contraseñas aleatorias; lo usan la CI y el equipo) y `frontend/.nvmrc` (`24.22.1`).
- **pre-commit:** nuevo hook **actionlint** v1.7.12 (valida los workflows).
- **ADR-026** (Node 24 LTS como runtime estándar, aprobado por el dueño del producto el 2026-11-12) en `docs/architecture.md` §13, y P-5 de `SPRINTS.md` actualizada. Son los únicos cambios a documentos del baseline, por decisión explícita del dueño.
- Documentación: `scripts/README.md`, `infra/README.md` (paso 1 con `crear_env.py`), este archivo y `CLAUDE.md`.

**Decisiones técnicas de S1-06:**
- **El backend se valida en Docker Compose, no con un servicio `postgres` de GitHub ni con Python del runner.** Así la CI ejecuta exactamente los comandos de local (ADR-016), usa la imagen real (WeasyPrint/Pango incluidos), prueba `10-roles.sh`, el servicio `migrate` y los roles con mínimo privilegio, y no duplica configuración. El costo es construir la imagen en cada ejecución (unos segundos con caché; sin caché de capas entre ejecuciones por ahora).
- **`pytest` del backend corre en el contenedor `migrate`**, que tiene `DATABASE_URL` (trulab_app) y `DATABASE_URL_MIGRATIONS` (trulab_owner): se ejecutan las 28 pruebas, ninguna omitida.
- **Ida y vuelta de migraciones en CI:** la BD es efímera, así que `downgrade base` → `upgrade head` es seguro aquí (en local se evita porque borraría datos).
- **Contrato frontend ↔ backend en `integracion`:** si un cambio de la API no regenera `src/types/api.ts`, la CI falla con un mensaje que indica el comando.
- **Hooks y jobs se solapan a propósito:** ruff, mypy, ESLint y tsc corren en `pre-commit` (con las mismas versiones que el desarrollador) y también en `backend`/`frontend` (con las versiones de la imagen y del lock). El costo es bajo y cada job queda autocontenido y legible.
- **`chmod -R a+rwX`** sobre el código en los jobs de Docker: en el runner el código pertenece a otro uid y los contenedores corren como uid 1000 (cachés de ruff, mypy y pytest; `gen:api`). El runner es efímero.
- **actionlint como hook de pre-commit** (compilado con Go por pre-commit) en lugar de solo en CI: los errores de workflow se detectan antes del push.

**Validaciones de S1-06:**
- `actionlint` 1.7.12 (imagen Docker oficial, con shellcheck): sin hallazgos. Hook de pre-commit `actionlint`: en verde.
- **Pipeline ejecutada en local:** un script lee `ci.yml` y ejecuta los pasos `run:` de cada job tal como están escritos (Git Bash con `-eo pipefail`, `.env` borrado al empezar cada job; los pasos `uses:` se cubren con el `.venv` de Python 3.12 y Node 24 del equipo). `act` no se usó: sus contenedores no comparten las rutas de Windows que necesitan los volúmenes de Compose.
  - Primera pasada: `pre-commit` **falló** porque `ruff-format` corrigió `scripts/crear_env.py` y mostró el diff (`--show-diff-on-failure`). Prueba real de que la pipeline se detiene ante un error de formato. Corregido.
  - `backend`: OK (imágenes, `up --wait`, ruff, mypy, migraciones de ida y vuelta, `alembic check`, **28/28 pruebas**, `/health` con `trulab_app`).
  - `frontend`: OK (ESLint, tsc, Prettier, **17/17 pruebas**, build).
  - `integracion`: OK (entorno completo *healthy*, SPA, rutas, proxy `/api`, `openapi.json`, tipos al día).
  - Segunda pasada de `pre-commit`: OK (17 hooks, incluido actionlint).
- `docker compose up -d --wait` (con y sin lista de servicios) espera a que `migrate` termine con 0 y a que el resto esté *healthy*; devuelve error si algo falla.
- Pendiente de comprobar en GitHub: la primera ejecución real ocurrirá con el primer push o PR (no se hizo push, por instrucción).

**S1-05 · Frontend esqueleto.** SPA operativa en el contenedor `frontend` (http://localhost:5173):
- **Stack con versiones exactas:** React 18.3.1, Vite 6.4.5, TypeScript 5.9.3 (strict, `noUncheckedIndexedAccess`), Tailwind 3.4.19 + `tailwindcss-animate`, shadcn/ui (`components.json`, Radix Slot, CVA, `tailwind-merge` 2), React Router 7.18.5 (modo librería), TanStack Query 5.105.0, Lucide, Inter variable (`@fontsource-variable/inter`). Calidad: ESLint 10.13 (flat config con reglas de tipos, `react-hooks` 7 y `react-refresh`), Prettier 3.9.10, Vitest 3.2.7 + Testing Library + jsdom, `openapi-typescript` 7.13.
- **Estructura** por funcionalidad (`docs/architecture.md` §2): `src/app` (App con providers, `rutas.tsx`, `ErrorRuta`, `NoEncontradoPage`), `components/ui` (`Button`, `Skeleton`), `components/layout` (`AppShell` mínimo: encabezado de 56 px, salto al contenido, márgenes `px-4/6/8`, máximo 1440 px, *safe area*), `features/inicio` (página principal **temporal** y tarjeta "Estado de la API"), `lib` (`api-client`, `query-client`, `env`, `utils`), `types/api.ts` (**generado** desde OpenAPI) y `test/`.
- **Rutas:** `/` (inicio) y `*` (no encontrada) dentro de `AppShell`, con `errorElement`.
- **Comunicación con la API:** `apiClient` (JSON, `credentials: "include"`, problem+json → `ApiError` con `status`, `code`, `requestId` y `errors[]`; sin red → `SIN_CONEXION`). QueryClient sin reintentos en 4xx. La tarjeta de inicio consulta `GET /api/v1/health` con los estados cargando, error con "Reintentar" y datos (un 503 se muestra como "Sin conexión" en la BD).
- **Tokens del design system** (`docs/design-system.md` §2) como variables CSS HSL en `src/index.css` (`primary`, `secondary`, `muted`, `border`, `input`, `ring`, `success`, `warning`, `destructive`, `info` y sus `-subtle`), expuestos en `tailwind.config.ts`.
- **Docker:** imagen `node:24.22.1-bookworm-slim`; `frontend` **sale del perfil `app`** (`docker compose up -d` levanta todo); `API_PROXY_TARGET=http://api:8000`; `VITE_API_BASE_URL=/api/v1`; healthcheck con `fetch`.
- **pre-commit:** hooks locales de Prettier, ESLint y `tsc` (con `frontend/node_modules` del equipo).
- `.env.example`: `VITE_API_BASE_URL=/api/v1` y nota de que todo `VITE_*` es público.
- **17 pruebas** (Vitest): `api-client` (URL, cookies, cuerpo JSON, problem+json, sin conexión, error no JSON, 204), `query-client` (política de reintentos) y `rutas` (inicio con API ok, BD caída, sin API con "Reintentar", ruta desconocida).
- Documentación: `frontend/README.md` (arquitectura, estructura, variables y comandos), `infra/README.md`, este archivo y `CLAUDE.md`.

**Decisiones técnicas de S1-05:**
- **Node 24 LTS en la imagen del frontend** (antes `node:20.18.0`). Node 20 llegó a fin de soporte en abril de 2026, ESLint 9 ya no tiene soporte y ESLint 10 exige Node ≥ 20.19. Node 24 es la misma versión del equipo (24.22.1), así que la imagen y los hooks locales usan el mismo runtime. `SPRINTS.md` (P-5) dice "Node 20 LTS": no se tocó porque es parte del baseline; **queda para que el dueño lo confirme** (o se registre un ADR).
- **Líneas mayores elegidas por compatibilidad, no por ser las más nuevas:** React 18 (fijado por la arquitectura, ADR-002), Vite 6 (sigue recibiendo parches; Vite 7+ no aporta nada al esqueleto), Tailwind 3 (tokens HSL en formato shadcn, tal como los describe el design system; Tailwind 4 cambia a configuración en CSS y OKLCH), TypeScript 5.9 (typescript-eslint aún no admite TS 6+). Todas las versiones son exactas y tienen al menos 14 días; `jest-dom` 6.10 se evitó porque está marcada como *deprecated*.
- **Misma origen con el proxy de Vite** (`/api` → `api:8000`) en lugar de CORS. Evita CORS en local, deja la cookie de refresh (S1-08) como de primera parte con `SameSite=Strict` y no cambia el backend. CORS solo hará falta si en producción la SPA y la API quedan en orígenes distintos (DP-05).
- **Tipos generados desde OpenAPI y versionados** (`src/types/api.ts`, excluido de ESLint y Prettier). Se regeneran con `docker compose exec frontend npm run gen:api`.
- **React Router en modo librería** (`createBrowserRouter` + tabla `rutas.tsx`), no en modo framework: la SPA es estática y no hay SSR.
- **Inter empaquetada** (sin Google Fonts ni CDN): no hay peticiones a terceros y funciona sin conexión al CDN.
- **Fuera de alcance, a propósito:** login con Google, AuthProvider y guardas (S1-08, S1-11), AppShell responsivo con BottomBar/Sidebar y menú por rol (S1-11), pantallas de negocio, React Hook Form, Zod y Recharts (se instalan cuando se usen), formatos COP y fechas (con la primera pantalla que los muestre) y CORS en la API.

**Validaciones de S1-05 (con un `.env` temporal, luego eliminado):**
- `docker compose build frontend` correcto. `docker compose up -d` desde cero levanta `db`, `migrate` (termina con 0), `api` y `frontend`, todos *healthy*, sin perfiles.
- Desde Windows: `http://127.0.0.1:5173/` → 200 HTML; `/legalizaciones/123` → 200 (respaldo de rutas del cliente); `http://127.0.0.1:5173/api/v1/health` → 200 `{"status":"ok","version":"0.1.0","db":"ok"}` con `X-Request-ID` a través del proxy; `/api/v1/docs` → 200 por el proxy.
- **Navegador:** Edge *headless* ejecutó la SPA. El DOM muestra "Estado de la API · Disponible · Conectada · 0.1.0" y `/no-existe` muestra "Página no encontrada". Capturas a 1280 px y a 360 px sin desbordamiento horizontal.
- HMR: un cambio en un archivo montado desde Windows generó `hmr update` (polling).
- `npm run gen:api` generó `src/types/api.ts` desde la API real.
- En el contenedor (Node 24.22.1): `lint` (0 advertencias), `typecheck`, `format:check`, **17/17 pruebas** y `build` (JS 311,7 kB, 100,9 kB gzip) en verde. En Windows (`npm ci` en `frontend/`): lo mismo, en verde.
- `pre-commit run --all-files`: todo en verde, incluidos los 3 hooks nuevos. El hook de ESLint se probó con un archivo con `any`: falla como debe (el archivo se eliminó).
- Limpieza: `docker compose down -v`, `.env` temporal y `dist/` eliminados.

**S1-04 · Persistencia: Alembic, roles y extensiones.**
- **Alembic** en `backend/`: `alembic.ini` (archivos `AAAAMMDD_HHMM_<descripcion>`, hooks de ruff), `alembic/env.py` (conexión solo con `DATABASE_URL_MIGRATIONS`, `compare_type`, `compare_server_default`, una transacción por migración, modo `--sql`, descubrimiento automático de `app/modules/<dominio>/models.py`) y `alembic/script.py.mako` (tipado para mypy strict).
- **`app/core/models.py`:** `Base` con la `naming_convention` de `docs/database-design.md` §9 (`pk_<tabla>`, `ix_/uq_<tabla>__<columnas>`, `fk_<tabla>__<columna>__<tabla_ref>`, `ck_<tabla>__<regla>`).
- **Migración inicial** `20261112_1000_base_extensiones_y_privilegios` (`3f1c9a7e5b20`): verifica que existe `trulab_app` y que la ejecuta el dueño de la BD; crea `citext` y `pgcrypto`; `REVOKE ALL ON SCHEMA public FROM PUBLIC`; `USAGE` a `trulab_app`; privilegios por defecto (solo DML en tablas y `USAGE, SELECT` en secuencias); `trulab_app` sin acceso a `alembic_version`. Con `downgrade()` completo. Sin tablas de negocio.
- **Roles:** `infra/db/init/10-roles.sh` (montado en `docker-entrypoint-initdb.d`, idempotente y re-ejecutable): crea `trulab_owner` y `trulab_app` sin atributos privilegiados, sincroniza contraseñas, hace a `trulab_owner` dueño de la BD, `REVOKE ALL ON DATABASE ... FROM PUBLIC` y `CONNECT` a `trulab_app`.
- **Compose:** `POSTGRES_USER` pasa a `postgres` (superusuario de arranque); nuevo servicio **`migrate`** (`alembic upgrade head`) del que depende `api` (`service_completed_successfully`); `api` recibe `DATABASE_URL_MIGRATIONS=""` (solo conoce a `trulab_app`).
- **`.env.example`:** `OWNER_DB_USER`/`OWNER_DB_PASSWORD`, `POSTGRES_USER=postgres` y **`DATABASE_URL` definitiva con `trulab_app`** (se quitó la nota provisional de S1-03).
- `alembic==1.13.3` en `requirements.txt` y en el hook de mypy; `known-third-party = ["alembic"]` en ruff (la carpeta `backend/alembic/` confundía a isort).
- **15 pruebas nuevas** (28 en total): `test_bd_rol_app.py` (la API es `trulab_app`, sin atributos privilegiados, no es dueña, no hace DDL, no lee `alembic_version`, extensiones instaladas y usables), `test_migraciones.py` (una sola cabeza, BD en `head`, `trulab_owner` no es superusuario, tablas nuevas con solo DML para `trulab_app`, `PUBLIC` sin acceso) y `test_naming_convention.py`.
- Documentación: `backend/README.md` (sección **Migraciones**: reglas y comandos), `infra/README.md` (roles y permisos), este archivo y `CLAUDE.md`.

**Decisiones técnicas de S1-04:**
- **Tres roles, no dos:** `postgres` (superusuario de arranque, solo inicializa), `trulab_owner` (dueño, **sin** ser superusuario) y `trulab_app`. Antes `trulab_owner` era el superusuario de la imagen; con mínimo privilegio, quien migra no debe poder saltarse RLS ni crear roles. Las extensiones `citext` y `pgcrypto` son *trusted* en PG 13+, así que el dueño de la BD las crea sin superusuario (también funciona así en PostgreSQL gestionado).
- **Roles fuera de Alembic, lo demás dentro:** los roles son del clúster y llevan contraseñas, así que van en un script de arranque idempotente. Extensiones, privilegios del esquema y privilegios por defecto son de la BD y van versionados en Alembic (reproducibles en producción).
- **Privilegios por defecto en la migración** (no en el script): así `alembic_version`, creada antes, no queda accesible para la API, y cada tabla futura hereda solo DML. Las tablas de solo inserción revocarán `UPDATE`/`DELETE` en su migración (`docs/database-design.md` §7).
- **Guardas en la migración inicial:** se niega a correr si no existe `trulab_app` o si quien la ejecuta no es el dueño de la BD (por ejemplo, `postgres`); si no, los privilegios por defecto no se aplicarían a las tablas.
- **Servicio `migrate`** en Compose: `docker compose up -d` deja la BD en `head` antes de arrancar la API; es el patrón previsto para producción ("migraciones como paso previo al arranque", `docs/architecture.md` §12). También es el contenedor para crear migraciones y correr las pruebas que necesitan `trulab_owner`.
- **La API no recibe credenciales de dueño** (`DATABASE_URL_MIGRATIONS=""` en el servicio `api`). Por eso las pruebas de `test_migraciones.py` que necesitan `trulab_owner` se omiten en `api` y corren en `migrate`.
- **El rol `trulab_app` va literal en las migraciones** (no como constante): una migración es una foto fija.
- **Alembic 1.13.3** (de la misma época que SQLAlchemy 2.0.36). Revisiones con id hexadecimal de Alembic y nombre de archivo con fecha.
- **No se tocó `docs/`** (baseline congelado): lo implementado es coherente con `docs/database-design.md` §6, §9 y §10 y `docs/architecture.md` §12. El superusuario de arranque y el servicio `migrate` son detalles de implementación local, registrados aquí y en `infra/README.md`.

**Validaciones de S1-04 (con un `.env` temporal de contraseñas aleatorias, luego eliminado):**
- `docker compose build api migrate` correcto; `docker compose up -d` desde cero: el script de roles corre en el init, `migrate` aplica `3f1c9a7e5b20` y termina con 0, `db` y `api` *healthy*.
- BD: `citext 1.6` y `pgcrypto 1.3` instaladas; `trulab_owner` y `trulab_app` con `rolsuper`, `rolcreaterole`, `rolcreatedb` y `rolbypassrls` en `false`; dueño de la BD = `trulab_owner`; ACL de la BD `{trulab_owner=CTc, trulab_app=c}`; ACL de `public` `{pg_database_owner=UC, trulab_app=U}`; privilegios por defecto `trulab_app=arwd` (tablas) y `trulab_app=rU` (secuencias); `alembic_version` = `3f1c9a7e5b20`.
- La API usa `trulab_app` (`DATABASE_URL`) y no ve `DATABASE_URL_MIGRATIONS`. Desde Windows: `/api/v1/health` → 200 `{"status":"ok","version":"0.1.0","db":"ok"}` con `X-Request-ID`; `/api/v1/docs` → 200 HTML; `/api/v1/openapi.json` → OpenAPI 3.1.0 con `/api/v1/health` (contrato sin cambios).
- Repetibilidad: `10-roles.sh` dos veces más sobre el volumen existente sin errores; `upgrade head` sin cambios; `downgrade base` (deja solo `plpgsql`, sin privilegios por defecto y el esquema como en PG 16) → `upgrade head` → `alembic check` ("No new upgrade operations detected").
- Guardas: migrar como `trulab_app` → *permission denied*; como `postgres` → "Las migraciones las ejecuta el dueño de la BD (trulab_owner), no postgres"; sin URL → `RuntimeError` con instrucciones.
- `alembic revision --autogenerate` genera `AAAAMMDD_HHMM_<slug>.py` formateado y limpio (ruff + mypy en verde); el archivo de prueba se eliminó.
- Pruebas: **28/28 en `migrate`**; en `api`, 24 pasan y 4 se omiten (necesitan `trulab_owner`). Queda el `DeprecationWarning` de anyio ya conocido. `ruff check`, `ruff format --check` y `mypy` strict (`app tests alembic`) en verde. `pre-commit run --all-files` en verde.
- Limpieza: `docker compose down -v` y `.env` temporal eliminado.

**Nota para Git Bash:** `docker compose exec db bash /docker-entrypoint-initdb.d/10-roles.sh` necesita `MSYS_NO_PATHCONV=1` (Git Bash reescribe la ruta). En PowerShell funciona tal cual.

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
- [x] **S1-04** Alembic con `naming_convention`, roles `trulab_owner`/`trulab_app` con mínimo privilegio, extensiones `citext`/`pgcrypto`, servicio `migrate`; 28 pruebas
- [x] **S1-05** Frontend esqueleto: Vite, React 18, TS, Tailwind, shadcn/ui, tokens, React Router, TanStack Query, `apiClient`, tipos desde OpenAPI; contenedor `frontend` sin perfil (Node 24); 17 pruebas
- [x] **S1-06** CI en GitHub Actions: `pre-commit`, `backend` (Docker + PostgreSQL), `frontend` (Node 24) e `integracion` (Compose completo + contrato OpenAPI); actionlint; ADR-026
- [x] **S1-07** Modelos y migración de `usuarios`, `cargos`, `celulas`, `sesiones` y `auditoria` (solo inserción con trigger); SUPERADMIN inicial por `SUPERADMIN_EMAIL`; 92 pruebas de backend

## Trabajo pendiente

- [ ] Integrar `feat/f1-estructura-monorepo` en `main` (push + PR o merge, cuando el usuario lo indique)
- [ ] Proteger `main` en GitHub (*Settings → Branches*; lo hace el usuario)
- [ ] Sprint 1: S1-08 a S1-13
- [x] Node 24 LTS aprobado por el dueño del producto como estándar (2026-11-12, ADR-026)
- [ ] Primera ejecución de la CI en GitHub (requiere push/PR) y proteger `main` con los 4 checks
- [ ] Semana 0, tareas aún abiertas: P-2 (exportación de **datos** y soportes de AppSheet; ahora también alimenta los catálogos iniciales), P-3 (OAuth Client ID de Google Workspace), P-4 (logo y paleta), P-5 (entorno de desarrollo)
- [ ] Validar los supuestos S-01 a S-08, salvo S-06 que ya es RN-27 (`SPEC.md` §17.3), con ADMIN y FINANCIERO, a más tardar en la demo de la semana 2
- [ ] Semanas 2 a 4

## Próxima tarea sugerida

**S1-08** · Auth: `/auth/google` (verificación del ID token y `hd`), JWT de acceso, refresh rotativo en cookie, `/auth/refresh`, `/auth/logout`, `/me` (5 h; depende de S1-07 ✅ y de **P-3**, el OAuth Client ID; mientras llega, el login de desarrollo solo con `ENV=local`, R1.1; skills `agent-skills:security-and-hardening`, `agent-skills:test-driven-development`). Sigue la estrategia de Google Workspace de S1-07. Necesitará dependencias nuevas (`google-auth`, `PyJWT`) y la variable `JWT_SECRET`. Pendiente con el usuario: push y PR para la primera ejecución real de la CI y proteger `main` con los 4 checks. En paralelo, sin bloquear al desarrollador:
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
