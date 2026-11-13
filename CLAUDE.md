# CLAUDE.md — Memoria del proyecto Trulab Viajes

> Lee este archivo primero y después `HANDOFF.md`. Con ambos deberías poder retomar el trabajo sin releer el informe original.
> Mantenlo corto y actualizado: los detalles viven en `SPEC.md` y `docs/`.

## Qué es

Reconstrucción con código propio de dos sistemas que se **fusionan**: la app AppSheet **"Trulab viajes"** (legalización de gastos con soporte digital) y la app Google Apps Script **"Solicitud de tiquetes y gastos de viaje"** (solicitud previa con tarifas y PDF firmado). La entidad única es el **viático** (`VT-000001`), con etapas `SOLICITUD` y `LEGALIZACION`. Financiero audita el saldo (transferido − gastado) y liquida.

**Objetivo:** reemplazar AppSheet y Apps Script con un MVP responsivo (móvil, tablet y escritorio) y con seguridad en el backend. Lo hace **1 desarrollador en 4 semanas + una semana 5 de holgura (activada el 2026-11-12)**.

## Mapa de documentos

| Archivo | Para qué |
| :--- | :--- |
| `SPEC.md` | **Fuente de verdad (v0.4):** alcance, roles y permisos (§6), reglas RN-xx (§8), RF y RNF, MVP, **decisiones DP-xx (§17)** |
| `HANDOFF.md` | Estado actual y próxima tarea; se actualiza en cada sesión |
| `ROADMAP.md` | Fases F1–F10, dependencias, hitos, contingencia |
| `SPRINTS.md` | Tareas por semana con estimación, riesgos, criterios y gates |
| `docs/architecture.md` | Arquitectura y **registro de ADR (§13)** |
| `docs/database-design.md` | Tablas, relaciones, índices, RLS, auditoría, nomenclatura |
| `docs/api-design.md` | Contrato REST, errores, paginación, permisos por endpoint |
| `docs/design-system.md` | Tokens, componentes, layouts mobile-first |
| `docs/user-flows.md` | Flujos F-01 a F-11 y máquina de estados |
| `docs/skills-strategy.md` | Qué skill usar para cada tipo de trabajo |

El informe original de auditoría de AppSheet (*INFORME FINAL PARA PROYECTO TRULAB.md*) y los 10 archivos de Apps Script (`calcularGastos.html`, `javaScript.html`, `Codigo.gs`…) **no están en el repo**; todo lo útil se consolidó en `SPEC.md` §18. Las tarifas reales de `calcularGastos.html` hay que extraerlas (P-7) antes del seed.

## Stack

- **Frontend:** React 18 + Vite 6 + TypeScript 5.9, Tailwind 3 + shadcn/ui, TanStack Query, React Router, React Hook Form + Zod, Recharts, Lucide.
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (síncrono), Alembic, psycopg 3, WeasyPrint.
- **Seguridad:** `argon2-cffi` (Argon2id, contraseñas de operativos), `google-auth` (solo SUPERADMIN), PyJWT.
- **Datos y nube (AWS, ADR-028):** PostgreSQL 16 con RLS (**Amazon RDS** en staging/producción); archivos en **Amazon S3** privado y correo con **Amazon SES** (`boto3`); cómputo en ECS Fargate o App Runner (DP-21). GCP descartado. En local: `STORAGE_BACKEND=local`, `MAIL_BACKEND=log`.
- **Runtime del frontend:** Node 24 LTS, estándar del proyecto (**ADR-026**, aprobado el 2026-11-12); versión fijada en `frontend/.nvmrc` (24.22.1), igual que la imagen. Versiones npm exactas.
- **Herramientas:** Docker Compose, GitHub Actions, ruff, mypy, pytest, ESLint, Vitest, Playwright.

## Arquitectura en una frase

Monolito modular: la SPA React habla REST (`/api/v1`) con FastAPI (`routers → services → models`), que usa PostgreSQL y un bucket privado. La autenticación es **híbrida** (ADR-027): usuario y contraseña (Argon2id) para VIAJERO/ADMIN/FINANCIERO y Google `@trulab.co` solo para SUPERADMIN, con una sesión propia (access JWT de 15 min en memoria más refresh rotativo en cookie httpOnly). La autorización va en el service, con RLS como defensa en profundidad.

## Estructura (carpetas raíz creadas en S1-01; el código llega desde S1-03 y S1-05)

```
backend/app/{core,modules/<dominio>,templates/pdf}   backend/{alembic,tests}
frontend/src/{app,components/{ui,layout},features/<dominio>,lib,types}
infra/{docker,db/init}  scripts/etl_appsheet/  docs/
```

Dominios: `auth`, `usuarios`, `cargos`, `archivos` (metadatos de S3), `auditoria` (consulta), `catalogos` (tablas maestras proyectos, rubros, células y **tarifas de viáticos**; las administra SUPERADMIN), `viaticos` (antes `legalizaciones`; solicitud, trayectos y cálculo tarifario), `gastos`, `pagos`, `reportes`, `indicadores`.

## Roles y módulos

- **Roles** (uno por usuario): `VIAJERO` (solo lo suyo; empleado o **prestador de servicios**), `ADMIN` (operación interna: aprueba, rechaza y devuelve; gestiona usuarios operativos y cargos; **no** toca dinero), `FINANCIERO` (tesorería: valor asignado/transferido, estado financiero, pagos y liquidación; ve todo), `SUPERADMIN` (todo, incluidos catálogos y tarifas; crea o promueve a otros SUPERADMIN). Matriz completa en `SPEC.md` §6.
- **Módulos MVP:** Auth (híbrida + recuperación de contraseña), Usuarios, Cargos, Catálogos, **Tarifas de viáticos**, **Viáticos (solicitud + legalización)**, Gastos, Pagos, PDF (**solicitud con firma y legalización**), Indicadores. Las notificaciones de estado son opcionales (el correo de restablecimiento no). OCR, Google Chat y Asana quedan para el futuro.
- **Modalidades y etapas (DP-19 ✅):** `CON_SOLICITUD` (nace en etapa `SOLICITUD`; con la solicitud `APROBADO` —y `TRANSFERIDO` si pidió gastos de viaje— el dueño *habilita la legalización* sobre el mismo `VT-`, y `estado` vuelve a `PENDIENTE`) y `LEGALIZACION_DIRECTA` (nace en etapa `LEGALIZACION`; recursos propios solo aquí).
- **Estados (DP-13 ✅), sobre ambas etapas:** `estado` (operativo, AppSheet `Estado`): `PENDIENTE → APROBADO | RECHAZADO`; *devolver* regresa a `PENDIENTE` con comentario; lo cambia solo ADMIN/SUPERADMIN. `estado_financiero` (AppSheet `Estado_P`): `PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO`; lo cambia solo FINANCIERO/SUPERADMIN; `PAGADO`/`PROCESADO` exigen `APROBADO` y etapa `LEGALIZACION`. `Estado legalizacion` = `[Estado]`, no se almacena.

## Decisiones DEFINITIVAS (SPEC v0.4, última revisión 2026-11-12; no reabrir)

Se confirmaron contra la configuración real de AppSheet y de Apps Script. Solo cambian si el dueño del producto lo decide de forma explícita, y en ese caso se registra un ADR nuevo. **El 2026-11-12 el dueño del producto reemplazó DP-01 y cerró DP-05** (documentación descongelada temporalmente y vuelta a congelar). Detalle en `SPEC.md` §17.1.

- **DP-01 ✅ Acceso híbrido (reemplaza la versión del 2026-11-10; ADR-027):** dominio corporativo **`@trulab.co`**. `VIAJERO`, `ADMIN`, `FINANCIERO` (incluidos **prestadores de servicios sin correo corporativo**, por la no subordinación laboral): **usuario y contraseña** (Argon2id), recuperación por correo (token de un solo uso, 15–30 min, hash SHA-256) y cambio obligatorio de la contraseña temporal; **no** usan Google. `SUPERADMIN`: **solo Google OAuth `@trulab.co`**, sin contraseña (`CHECK` en la BD). SUPERADMIN inicial: **John Hernandez, `john.hernandez@trulab.co`** (`SUPERADMIN_EMAIL`); cualquier SUPERADMIN activo crea o promueve a otros; **nunca** se desactiva ni degrada al último. RN-12 y RN-15 reescritas; RF-002 reactivado.
- **DP-02 ✅ Proyectos:** se eligen en cada gasto (y en la cabecera de la solicitud); `Segmentador` = filtro `desde`/`hasta` (ADR-017, ADR-018). **Esquema híbrido (ADR-031):** catálogo `proyectos` + opción "Otro" con nombre escrito (`proyecto_otro`); exactamente uno de los dos (`CHECK`).
- **DP-04 ✅ Valor transferido:** solo **FINANCIERO** (y SUPERADMIN) registra `valor_asignado`; `valor_transferido = recursos_propios ? 0 : valor_asignado`, calculado (ADR-019). El `presupuesto_solicitado` es solo referencia sugerida.
- **DP-05 ✅ AWS (ADR-028):** RDS PostgreSQL 16, S3 (URLs prefirmadas de 5 min), SES y ECS Fargate o App Runner (DP-21 abierta). GCP descartado.
- **DP-07 ✅ Estructura real de AppSheet:** 5 tablas validadas (`SPEC.md` §18; ADR-020).
- **DP-13 ✅ Estados:** `Estado` (ADMIN), `Estado_P` (FINANCIERO), espejo (ADR-021).
- **DP-14 ✅ Catálogos:** proyectos, rubros y células en tablas maestras de SUPERADMIN, sin valores en el código (ADR-022).
- **DP-15 ✅ Adjuntos:** `soporte` = imagen, `archivo` = PDF, al menos uno por gasto (ADR-023).
- **DP-16 ✅ Fechas:** indicadores sobre `gastos.fecha_factura`; las fechas de viaje (`viatico_trayectos`) no son base de indicadores (ADR-024).
- **DP-17 ✅ Recursos propios:** lo marca el VIAJERO al crear (solo `LEGALIZACION_DIRECTA`); transferido = 0 y la empresa reembolsa.
- **DP-18 ✅ ADMIN:** operación interna; no toca dinero (ADR-025).
- **DP-19 ✅ Entidad unificada (ADR-029):** `viaticos` con folio `VT-000001` (reemplaza `legalizaciones`/`LG-`); modalidades `CON_SOLICITUD` y `LEGALIZACION_DIRECTA`; etapas `SOLICITUD` y `LEGALIZACION`; `viatico_trayectos` (1–5), `viatico_eventos`, vista `v_viatico_saldos`. Fuera: Google Sheets (`PROYECTOS`, `CorreosExternos`) y Asana (post-MVP).
- **DP-20 ✅ Tarifas (ADR-030):** tabla `tarifas_viaticos` por ciudad y tipo de vinculación (empleado/prestador), 6 conceptos, administrada por SUPERADMIN; seed de 22 destinos desde `calcularGastos.html`. Cálculo: `gasto_diario = alimentación + trans_interno + otros`; `subtotal = gasto_diario × días`; `presupuesto = Σ(subtotal + aeropuerto + intermunicipal)`; el solicitante no edita importes. Prestador + proyecto con `exige_formato_prestador` → adjunta formato en vez de calcular.
- **RN-27 ✅ Sin autoaprobación (definitiva, en toda etapa):** nadie aprueba, valida financieramente ni liquida un viático creado por sí mismo; solo SUPERADMIN, con auditoría (ADR-025).

**No quedan decisiones bloqueantes.** Siguen abiertas, sin bloquear: DP-06 correos de estado, DP-08 marca, DP-09 folios históricos, DP-10 qué se registra al pagar, DP-12 (recomendación: financiero no edita gastos), **DP-21** ECS Fargate vs App Runner. Supuestos S-01 a S-14 (`SPEC.md` §17.3) se validan en la demo de la semana 2.

## Decisiones clave (ver ADR en `docs/architecture.md` §13)

1. Las transiciones son **acciones** (`POST /viaticos/{id}/aprobar|rechazar|devolver|gestionar-tiquetes` para ADMIN, `POST /viaticos/{id}/estado-financiero` y `PATCH …/valor-asignado` para FINANCIERO, `POST …/habilitar-legalizacion` para el dueño) que pasan por una única función `transicionar()`, la cual registra el historial (`viatico_eventos`) en la misma transacción.
2. **El saldo nunca se almacena:** sale de la vista `v_viatico_saldos` (`valor_transferido − Σ gastos`). `valor_transferido` es una columna generada a partir de `recursos_propios` y `valor_asignado`. **El presupuesto tarifario lo calcula solo el servidor** (función pura; el cliente nunca envía importes).
3. **Recurso ajeno → 404**, sin permiso → 403, estado inválido → 409. Los errores siguen RFC 9457 con `code` estable.
4. **Dinero:** `NUMERIC(14,2)` en BD y *string* en JSON. Moneda COP.
5. **PK UUID** más folio legible (`VT-000001`, `CA-000001`); el `VT-` no cambia de la solicitud a la legalización.
6. **Eliminación lógica** (`deleted_at`); los usuarios se desactivan, no se borran.
7. **Archivos** (soportes, firmas, formatos de prestador) en un bucket **S3** privado, validados por *magic bytes*, máximo 10 MB, servidos con URL prefirmada de 5 min.
8. **Contraseñas** solo para operativos (Argon2id); respuestas de login que no revelan si el usuario existe; tokens de recuperación solo como hash; `password_hash` nunca sale por la API ni a logs.
9. El backend siempre corre en Docker (por WeasyPrint y la paridad con producción).

## Convenciones técnicas

- **Idioma:** dominio, BD, API y UI en **español**. Código de infraestructura y nombres técnicos genéricos en inglés (`router`, `service`, `schemas`).
- **Nombres:** tablas en `snake_case` plural; JSON en `snake_case`; componentes React en `PascalCase`; hooks como `useX`. Más detalle en `docs/database-design.md` §9.
- **Reglas de negocio solo en `services`**; routers delgados; nada de lógica de negocio en componentes React.
- **TDD obligatorio** para reglas RN-xx y permisos. Una prueba parametrizada recorre la matriz RBAC.
- **Migraciones solo con Alembic.** Los tipos TS se generan desde OpenAPI; no se escriben a mano.
- **Git:** rama `main` protegida; ramas `feat/<fase>-<tema>`, `fix/...`; commits convencionales en español (`feat(gastos): subir soporte`).
- **Secretos** solo en `.env` (no versionado) o, en AWS, en Secrets Manager/Parameter Store y rol de IAM de la tarea; se mantiene `.env.example` al día. Un hook de pre-commit bloquea cualquier `.env`.
- **Formato:** `.editorconfig` (UTF-8, LF, 2 espacios; 4 en Python) y `.gitattributes` (`eol=lf`, por los contenedores Linux). Hooks en `.pre-commit-config.yaml` (genéricos, ruff, mypy); ESLint, Prettier y `tsc` del frontend desde S1-05.
- **Docker local:** `infra/docker-compose.yml`; desde la raíz `docker compose up -d` (gracias a `COMPOSE_FILE` en `.env`) levanta `db`, aplica las migraciones (servicio `migrate`) y arranca `api` y `frontend` (http://localhost:5173; Vite reenvía `/api` a `api:8000`, sin CORS en local). BD en `127.0.0.1:5433` (5432 lo ocupa un PostgreSQL nativo de Windows). Sin MinIO: en local `STORAGE_BACKEND=local`. Detalle en `infra/README.md`.
- **Roles de BD (S1-04):** `postgres` = superusuario de arranque (solo init); `trulab_owner` = dueño de la BD, **no** superusuario, ejecuta Alembic (`DATABASE_URL_MIGRATIONS`); `trulab_app` = la API (`DATABASE_URL`), solo DML por privilegios por defecto, sin DDL ni `BYPASSRLS`. Roles en `infra/db/init/10-roles.sh` (idempotente); extensiones y privilegios en Alembic. La API no recibe credenciales de dueño.
- **Frontend:** comandos con `docker compose exec frontend npm run lint|typecheck|format:check|test|build|gen:api`. Para el editor y pre-commit, `npm ci` en `frontend/` del equipo (el contenedor usa su propio volumen de `node_modules`). `src/types/api.ts` se genera desde OpenAPI (`gen:api`), no se edita. Las llamadas a la API van siempre por `src/lib/api-client.ts`. Detalle en `frontend/README.md`.
- **CI (S1-06):** `.github/workflows/ci.yml` con 4 jobs obligatorios: `pre-commit` (todos los hooks), `backend` (Docker Compose + PostgreSQL real: ruff, mypy, migraciones de ida y vuelta, `alembic check`, pytest completo), `frontend` (Node 24: ESLint, tsc, Prettier, Vitest, build) e `integracion` (Compose completo, humo y contrato: `src/types/api.ts` debe coincidir con el OpenAPI). Actions fijadas por SHA, `permissions: contents: read`, sin secretos (`.env` generado con `scripts/crear_env.py`). Workflows validados con actionlint (hook de pre-commit). Si cambia la API, regenerar los tipos (`gen:api`) o la CI falla.
- **Identidad y auditoría (S1-07):** tablas `usuarios` (correo CITEXT, credenciales por rol desde S1-07b, `google_sub` para el primer login del SUPERADMIN), `cargos` (folio `CA-000001`), `celulas` (catálogo), `sesiones` (solo SHA-256 del refresh, con `CHECK`) y `auditoria` (`app/core/audit.py`: `registrar()` en la misma transacción, sanea secretos y enmascara la cédula; solo inserción por `REVOKE` y trigger, también para `trulab_owner`). Columnas base con los mixins de `app/core/models.py`; enums en `app/core/enums.py`. `trulab_app` no borra físicamente `usuarios`, `cargos` ni `celulas`. SUPERADMIN inicial: `SUPERADMIN_EMAIL=john.hernandez@trulab.co`, creado por `migrate` solo si no hay ninguno activo (sin contraseña; audita `SUPERADMIN_ASIGNADO`).
- **Credenciales (S1-07b):** `usuarios.username` (CITEXT, minúsculas), `password_hash` (Argon2id PHC), `debe_cambiar_password`, `intentos_fallidos`/`bloqueado_hasta`, `es_prestador_servicios`, `fecha_nacimiento`, con `CHECK` por rol (operativo ⇒ username + hash; SUPERADMIN ⇒ sin hash; `google_sub` solo SUPERADMIN). `tokens_recuperacion_password` (SHA-256, sin `DELETE` para la app). Fábrica de pruebas con `HASH_FICTICIO`. `Settings` valida `MAIL_BACKEND`/SES/S3 y el TTL de 15–30 min. Datos de tarifas en `backend/app/modules/catalogos/datos/tarifas_viaticos.csv`. Pruebas de BD con el fixture `sesion` (transacción revertida).
- **Auth (S1-08):** primitivas en `app/core/security.py` (Argon2id, JWT, tokens opacos), correo en `app/core/mail.py` (`MAIL_BACKEND=log|ses`), límite por IP en `app/core/rate_limit.py`, reglas en `app/modules/auth/service.py`. Las rutas se protegen con `UsuarioActual` (`app/modules/auth/dependencias.py`), que lee usuario y sesión de la BD en cada petición y bloquea si hay cambio de contraseña pendiente. `JWT_SECRET` obligatorio (lo genera `scripts/crear_env.py`). Pruebas HTTP con la fixture `api` (sesión revertida, `Buzon`, Google falso). Detalle en `backend/README.md`.
- **Migraciones:** `docker compose run --rm migrate alembic revision --autogenerate -m "..."`; modelos en `app/modules/<dominio>/models.py` heredando de `app.core.models.Base` (con `naming_convention`). Las tablas de solo inserción revocan `UPDATE`/`DELETE` a `trulab_app` en su migración. Reglas y comandos en `backend/README.md`.
- **Python local = 3.12** (`.python-version`), en `.venv` creado con `py -3.12 -m venv .venv` e instalado con `requirements-dev.txt`. El equipo también tiene Python 3.15 como predeterminado del sistema: **no usarlo** para el proyecto (sin wheels de PyYAML). Usar siempre `.venv\Scripts\python` y `.venv\Scripts\pre-commit`.
- **Identidad git local:** `John Hernandez <John.Hernandez@trulab.co>`; remote `origin` en GitHub (`johnhernandez-prog/Trulab_Viaticos`).

## Estado actual

**Fase:** **Semana 1 cerrada (gate cumplido el 2026-11-13); semana 2 en curso** (F4/F5). **S1-01 a S1-13 terminadas** (S1-12 pasa a la semana 5) (estructura, Docker Compose, backend esqueleto, Alembic y roles de BD, frontend esqueleto, CI, modelo de identidad y auditoría con SUPERADMIN inicial, credenciales por rol y tokens de recuperación, y **auth híbrida en el backend**). Matriz RBAC (S1-09), API de cargos, usuarios y auditoría (S1-10) y UI de acceso y AppShell (S1-11); los módulos de negocio son marcadores hasta la semana 2.

**2026-11-12: documentación actualizada a SPEC v0.4** por decisión del dueño del producto (solo documentos y `.env.example`, **sin código ni migraciones**): acceso híbrido (ADR-027, reemplaza ADR-006), AWS (ADR-028, cierra DP-05), entidad unificada `viaticos` con solicitud y legalización (ADR-029, DP-19) y tarifas por tipo de vinculación (ADR-030, DP-20). `SPRINTS.md` se replanificó con **S1-07b**, S1-08 redefinida, semana 2 nueva y la **semana 5 de holgura activada**. La documentación vuelve a estar congelada con este nuevo baseline; el detalle vivo está en `HANDOFF.md`.

**S1-07b y S1-08 terminadas** (2026-11-12): credenciales por rol, tokens de recuperación, tarifas oficiales como datos y auth híbrida (`/auth/login`, `google`, `dev/login` solo local, `refresh`, `logout`, `password/forgot|reset|change`, `/me`).

**S1-09 terminada** (2026-11-13): matriz RBAC en `app/core/permissions.py` (enum `Permiso` de 24 permisos, `MATRIZ` inmutable), `require_permission()` (403 `SIN_PERMISO`), `permisos` en `/me` (vacía con cambio de contraseña pendiente) y `SET LOCAL app.usuario_id/app.rol` por transacción (`fijar_contexto_rls`).

**S1-10 terminada** (2026-11-13): API de `/cargos` (CRUD, folio `CA-`, borrado lógico, `409 EN_USO`), `/usuarios` (contraseña temporal por correo, SUPERADMIN con `@trulab.co`, promoción/degradación, último SUPERADMIN protegido, revocación de sesiones, `409 ACCION_SOBRE_SI_MISMO`) y `GET /auditoria`; paginación en `app/core/paginacion.py` y errores comunes en `app/core/errors.py`.

**S1-11 terminada** (2026-11-13): login dual (usuario/contraseña, Google GIS si hay `VITE_GOOGLE_CLIENT_ID`, acceso de desarrollo solo en `DEV`), olvidé/restablecer/cambiar contraseña (con el cambio obligatorio), `AuthProvider` (recuperación silenciosa, renovación antes de vencer, token en memoria), guardas por sesión y permiso, y AppShell responsivo con menú por permisos (`components/layout/navegacion.ts`). Formularios con React Hook Form + Zod.

**S1-13 terminada** (2026-11-13): semana 1 cerrada. ADMIN conserva `tarifas:leer` (decisión del dueño del producto; F-11 actualizada).

**S2-02 terminada** (2026-11-13): migración `2c36be2a3312` con `proyectos`, `rubros`, `tarifas_viaticos` (seed de 44 filas leído del CSV), `archivos`, `viaticos` (`VT-`, `valor_transferido` generado), `viatico_trayectos`, `viatico_eventos` (solo inserción con trigger), `gastos` y `v_viatico_saldos`; modelos en `app/modules/{catalogos,archivos,viaticos,gastos}/models.py` y enums en `app/core/enums.py`.

**S2-01 terminada** (2026-11-13): API de `/catalogos` (selectores activos para V F A S; administración con `uso` informativo, crear, editar, activar/desactivar sin `DELETE`, solo SUPERADMIN) y `/catalogos/tarifas-viaticos` (lectura F A S; gestión solo SUPERADMIN, dinero como string con `app/core/types.py::Dinero`, ADR-012). Auditoría `CATALOGO_*`/`TARIFA_*`. **641 pruebas** en verde.

**S2-03 terminada** (2026-11-13): RLS real sobre `viaticos`, `viatico_trayectos`, `viatico_eventos`, `gastos` y `archivos` (migración `7d7db0ebc91e`), política `ver_propios_o_privilegiado` por tabla (`FOR ALL TO trulab_app`; sin `FORCE`, decisión documentada en `docs/database-design.md` §6 para no bloquear a `trulab_owner`); `NULLIF(..., '')` ante los GUC vacíos de PostgreSQL. **663 pruebas** en verde (22 nuevas en `tests/test_rls.py`, con aislamiento por SQL directo y por HTTP). **Próxima: S2-04 (servicio de cálculo tarifario, RN-29/RN-30, y `POST /viaticos/calcular-presupuesto`)**.

## Cómo retomar

1. Lee `HANDOFF.md`: estado, próxima tarea y bloqueos.
2. Abre solo la sección de la semana actual en `SPRINTS.md`.
3. Consulta `SPEC.md` y el `docs/` relevante a la tarea (no todo).
4. Si dudas de una decisión pasada, revisa los ADR (hasta ADR-030) y luego usa `claude-mem:mem-search`.
5. Trabaja con la skill indicada en la tarea (`docs/skills-strategy.md`).
6. Al cerrar, actualiza `HANDOFF.md` (`claude-mem:handoff`) y este archivo si cambió una decisión, el stack o el estado.

## Orden recomendado de desarrollo

F1 Base técnica → F2 Auth/RBAC → F3 Usuarios/Cargos → F4 Legalizaciones → F5 Gastos → F6 Pagos → F7 PDF → F8 Dashboard → F9 Pruebas (continuas y cierre) → F10 Producción + ETL. Nunca se empieza un módulo funcional antes de que F2 esté probado.
