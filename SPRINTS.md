# SPRINTS — Plan detallado (4 semanas + semana 5 de holgura)

> Fuente: `ROADMAP.md`. Supuestos: 1 desarrollador full-stack, 5 días por semana, unas 6 h productivas al día (alrededor de 30 h por semana).
> **Replanificado el 2026-11-12** por los cambios aprobados (SPEC v0.4): acceso híbrido (ADR-027), AWS (ADR-028), entidad unificada `viaticos` con solicitud y tarifas (ADR-029, ADR-030). Las tareas S1-01 a S1-07 ya están terminadas y no cambian. La **semana 5 de holgura queda activada formalmente**.
> Las estimaciones van en horas (h). Si una semana supera su capacidad, se aplica el recorte de `ROADMAP.md` (contingencia).
> Las skills se nombran como se invocan en Claude Code (detalle en `docs/skills-strategy.md`).
> **Regla de puerta:** no se empieza la semana siguiente sin cumplir su *Gate de salida*. Si falta algo, se termina primero o se recorta de forma explícita (registrándolo en `HANDOFF.md`).
> **Terminología (SPEC v0.4).** La entidad es el **viático** (`VT-000001`) con dos etapas, `SOLICITUD` y `LEGALIZACION`; "legalizar" se lee **aprobar** (ADMIN) en la etapa que corresponda; *pagar* → **cambiar estado financiero** (FINANCIERO); `LEGALIZADA` → `APROBADO`; "listas cerradas" → **tablas de catálogo** (DP-14 ✅) y **tarifas** (DP-20 ✅). Donde una tarea antigua dice "legalización", léase "viático" (`docs/user-flows.md`).

---

## Semana 0 · Preparación (antes de empezar; no consume capacidad de desarrollo)

| # | Tarea | Responsable |
| :- | :--- | :--- |
| P-1 | ✅ DP-01, DP-02, DP-04 y DP-07 resueltas (2026-11-10); ✅ DP-13 a DP-18 resueltas (2026-11-11). **No quedan decisiones bloqueantes** (`SPEC.md` §17.1) | Dueño del producto |
| P-2 | Exportar desde AppSheet los **datos** de las 5 tablas en CSV y los soportes (imágenes y PDF), y confirmar dónde se guardan. La estructura ya está validada (DP-07 ✅) | Dueño del producto / admin AppSheet |
| P-3 | Crear el proyecto en Google Cloud Console y el **OAuth Client ID** (web) con los orígenes local y de producción. **Solo lo usa el login de SUPERADMIN** (ADR-027); ya no bloquea a los demás roles | Admin de Google Workspace |
| P-4 | Entregar el logo y la paleta corporativa (DP-08) | Comunicaciones |
| P-5 | Instalar Docker Desktop, Node 24 LTS (ADR-026; antes Node 20), Python 3.12 y el CLI `gh` en el equipo de desarrollo | Desarrollador |
| P-6 | **AWS:** cuenta y entorno staging; verificar en **Amazon SES** la identidad del remitente (`AWS_SES_SENDER`) y salir del *sandbox* de SES; crear bucket S3 privado y RDS (DP-05 ✅, ADR-028). Elegir ECS Fargate o App Runner (DP-21) | Dueño del producto / desarrollador |
| P-7 | ✅ *Valores entregados el 2026-11-12* (`backend/app/modules/catalogos/datos/tarifas_viaticos.csv`; `P-CONEXI-002` exige formato). Pendiente: la hoja `PROYECTOS`. **Tarifas:** entregar `calcularGastos.html` y extraer las dos tablas (empleado y prestador, 22 destinos × 6 conceptos) a un CSV validado por el dueño del producto (seed de `tarifas_viaticos`). También `javaScript.html` (proyectos que exigen formato de prestador, p. ej. `P-CONEXI-002`) y la hoja `PROYECTOS` | Dueño del producto / desarrollador |
| P-8 | Confirmar para cada usuario operativo actual: `username`, correo de contacto y si es **prestador de servicios** (insumo de S1-10 y del ETL) | Dueño del producto |

---

## Semana 1 · Fases F1, F2 y F3: base técnica, seguridad, usuarios y cargos

**Objetivo:** un esqueleto desplegable localmente donde los operativos entran con usuario y contraseña (con recuperación por correo), el SUPERADMIN entra con Google, y un ADMIN gestiona usuarios y cargos, con permisos probados.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S1-01 | Estructura del monorepo (`backend/`, `frontend/`, `infra/`, `scripts/`), `.gitignore`, `.editorconfig`, `.env.example`, pre-commit | 2 h | — | `agent-skills:incremental-implementation`, `agent-skills:git-workflow-and-versioning` |
| S1-02 | `docker-compose.yml`: postgres 16, api (con recarga), frontend y minio opcional | 3 h | S1-01 | `agent-skills:ci-cd-and-automation` |
| S1-03 | Backend esqueleto: FastAPI, `core/config`, `core/db`, `/health`, manejo de errores problem+json, `X-Request-ID`, logs estructurados | 4 h | S1-02 | `agent-skills:api-and-interface-design`, `agent-skills:build` |
| S1-04 | Alembic con `naming_convention`, roles de BD `trulab_owner`/`trulab_app`, extensiones `citext` y `pgcrypto` | 2 h | S1-03 | `engineering:architecture` |
| S1-05 | Frontend esqueleto: Vite, React, TS, Tailwind, shadcn/ui, tokens del design-system, React Router, TanStack Query, `apiClient` | 4 h | S1-01 | `agent-skills:frontend-ui-engineering`, `design:design-system` |
| S1-06 | CI en GitHub Actions: ruff, mypy, pytest (con Postgres de servicio), eslint, tsc y build | 2 h | S1-03, S1-05 | `agent-skills:ci-cd-and-automation` |
| S1-07 | ✅ Migración `cargos` y `usuarios` + `sesiones` + `auditoria`; seed del primer SUPERADMIN por variable de entorno | 2 h | S1-04 | `agent-skills:test-driven-development` |
| **S1-07b** | ✅ **Migración correctiva de identidad (ADR-027):** `usuarios` + `username` (CITEXT único), `password_hash` (con `CHECK` por rol), `debe_cambiar_password`, `password_cambiada_at`, `intentos_fallidos`, `bloqueado_hasta`, `es_prestador_servicios`, `fecha_nacimiento` y `CHECK`s de `username` y `google_sub`; crear `tokens_recuperacion_password` (hash SHA-256 con `CHECK` de 64 hex); acciones nuevas de auditoría; `SUPERADMIN_EMAIL`/`SUPERADMIN_NOMBRE` por defecto de John Hernandez. **Sin** `firma_archivo_id` (llega con `archivos`, S2-02) | 2 h | S1-07 | `agent-skills:test-driven-development`, `engineering:system-design` |
| **S1-08** | ✅ **Auth híbrida (ADR-027):** `POST /auth/login` (usuario/contraseña, Argon2id, bloqueo, respuesta genérica), `forgot`/`reset`/`change` de contraseña (correo por `Mailer`: Amazon SES en AWS, log en local; cambio obligatorio de la temporal), JWT de acceso + refresh rotativo en cookie, `/auth/refresh`, `/auth/logout`, `/me`, y `POST /auth/google` **restringido a SUPERADMIN** (verificación del ID token, `hd`) | 6 h | S1-07b (Google: P-3) | `agent-skills:security-and-hardening`, `agent-skills:test-driven-development` |
| **S1-09** | ✅ `core/permissions.py`: matriz RBAC, `require_permission`, `permisos` en `/me`, `SET LOCAL` de RLS por transacción, prueba parametrizada de la matriz | 3 h | S1-08 | `agent-skills:security-and-hardening`, `agent-skills:test-driven-development` |
| **S1-10** | ✅ API de cargos y usuarios (CRUD; contraseña temporal por correo y restablecimiento; **crear/promover/degradar SUPERADMIN** con `@trulab.co`, protección del último SUPERADMIN; auditoría de rol y `SUPERADMIN_ASIGNADO`) | 5 h | S1-09 | `agent-skills:api-and-interface-design`, `agent-skills:test-driven-development` |
| **S1-11** | ✅ UI: **login dual** (usuario/contraseña + botón Google), olvidé/restablecer/cambiar contraseña (incluido el cambio obligatorio), AuthProvider, guardas de ruta, AppShell responsivo (BottomBar / Sidebar plegable / Sidebar fija) con menú por rol | 7 h | S1-05, S1-08 | `agent-skills:frontend-ui-engineering` |
| S1-12 | → **semana 5.** UI: Cargos y Usuarios (tabla en escritorio, tarjetas en móvil, formularios, confirmaciones, alta de operativos y gestión de SUPERADMIN) | 4 h | S1-10, S1-11 | `agent-skills:frontend-ui-engineering` |
| **S1-13** | ✅ Cierre: actualizar `HANDOFF.md` y `CLAUDE.md` (estado) | 0,5 h | — | `claude-mem:handoff` |
| | **Total** | **≈ 46,5 h** (S1-01 a S1-07 ya hechas: 19 h) | | ⚠️ Supera la capacidad en unas 16 h; ver riesgos |

**Riesgos:**
- **R1.1** El OAuth Client ID (P-3) depende de un admin de Workspace, pero **ahora solo bloquea el login de SUPERADMIN**: el resto de roles entra con usuario y contraseña. *Mitigación:* login de desarrollo de SUPERADMIN habilitado **solo** con `ENV=local` y desactivado por prueba en CI.
- **R1.4** El correo de restablecimiento depende de SES (P-6: identidad verificada y salida del *sandbox*). *Mitigación:* interfaz `Mailer` con `MAIL_BACKEND=log` en local y pruebas con un doble; SES real solo se verifica en staging.
- **R1.5** Argon2id añade latencia al login (RNF-01) y es un blanco de fuerza bruta. *Mitigación:* parámetros calibrados, bloqueo por usuario e IP, pruebas de tiempo homogéneo.
- **R1.2** La semana está sobrecargada. *Mitigación:* **S1-12 (UI de Cargos y Usuarios) pasa a la semana 5** (el ADMIN puede operar por la API y Swagger mientras tanto); la API, las pruebas y la UI de login (S1-11) no se mueven.
- **R1.3** La configuración de Docker en Windows (WSL2) consume tiempo. *Mitigación:* hacer P-5 antes del día 1.

**Entregables:** repositorio con CI en verde; `docker compose up` levanta todo; login de operativos (usuario/contraseña, recuperación) y de SUPERADMIN (Google); CRUD de cargos y usuarios por API (UI en semana 5).

**Criterios de aceptación:**
- [x] Un VIAJERO/ADMIN/FINANCIERO activo entra con usuario y contraseña; credenciales erróneas, usuario inactivo o inexistente reciben el **mismo** 401 genérico.
- [x] La contraseña temporal obliga al cambio: el resto de la API responde 403 `CAMBIO_PASSWORD_REQUERIDO` hasta cambiarla.
- [x] `forgot` responde siempre 202; el token es de un solo uso, vence a los 15–30 min, se guarda solo como hash y restablecer revoca las sesiones.
- [x] Un SUPERADMIN `@trulab.co` entra con Google; no puede usar `/auth/login`; un operativo no puede usar `/auth/google`; otro dominio o no registrado recibe 403 claro. *(Probado con un verificador de Google falso; el login real espera el OAuth Client ID, P-3.)*
- [x] 5 fallos de login bloquean temporalmente; todo queda en `auditoria`; nunca se registran contraseñas, hashes ni tokens.
- [x] El access token no está en `localStorage`; el refresh renueva la sesión; el logout la revoca.
- [x] La prueba parametrizada de la matriz RBAC cubre cargos y usuarios para los 4 roles.
- [x] ADMIN no puede crear, promover ni modificar SUPERADMIN; un SUPERADMIN sí (con `@trulab.co` y `SUPERADMIN_ASIGNADO`); nadie puede desactivar ni degradar al último SUPERADMIN activo.
- [x] El layout funciona en 360, 768 y 1280 px.

**Gate de salida de la semana 1:** auth híbrida y RBAC en el backend terminados y probados (S1-07b, S1-08, S1-09 y S1-10), y UI de login (S1-11). Sin esto no se empieza la semana 2.

> ✅ **Gate cumplido el 2026-11-13** (S1-13). Pendientes que no bloquean: login real con Google (P-3), primera ejecución de la CI en GitHub (requiere push) y S1-12 (UI de cargos y usuarios, movida a la semana 5).

---

## Semana 2 · Fases F4 y F5: viáticos (solicitud + legalización directa), tarifas y gastos

**Objetivo:** el viajero completa desde su celular **ambos caminos**: pedir viáticos y tiquetes con presupuesto calculado (`CON_SOLICITUD`) y cargar gastos con foto (`LEGALIZACION_DIRECTA`); ADMIN puede aprobar o devolver. La habilitación de la legalización sobre la solicitud aprobada queda en el backend; su UI de gastos reutiliza la de la legalización directa.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| **S2-01** | ✅ **Catálogos y tarifas:** migración `proyectos` (con `codigo` y `exige_formato_prestador`) y `rubros` (la estructura `ConCatalogo` ya existe), `tarifas_viaticos` y **seed** desde el CSV validado (decisión 2026-11-13: lo hace la migración leyendo el CSV) (P-7: 22 destinos × empleado/prestador); API CRUD de `/catalogos` y `/catalogos/tarifas-viaticos` (solo SUPERADMIN, auditoría `TARIFA_*`) | 4 h | S1-10, P-7 | `agent-skills:test-driven-development`, `agent-skills:api-and-interface-design` |
| **S2-02** | ✅ **Migración `viaticos`** (modalidad, etapa, solicitud, `valor_transferido` generado, `CHECK`s de coherencia), `viatico_trayectos`, `viatico_eventos`, `archivos` (con `proposito`) + FK `usuarios.firma_archivo_id`, `gastos`; secuencia `seq_folio_viaticos`; vista `v_viatico_saldos` | 4 h | S2-01 | `engineering:system-design` |
| **S2-03** | ✅ **RLS** sobre `viaticos`, `viatico_trayectos`, `viatico_eventos`, `gastos` y `archivos` (ampliado de la estimación original: también eventos y archivos) + `SET LOCAL` por transacción (ya en S1-09) + pruebas de aislamiento con `trulab_app` (SQL directo y HTTP) | 3 h | S2-02 | `agent-skills:security-and-hardening`, `agent-skills:test-driven-development` |
| **S2-04a** | ✅ **Cálculo tarifario y creación/consulta base de viáticos** (adelanta parte de S2-05, decisión del dueño del producto): `calcular_presupuesto` (función pura, RN-29 y RN-30; TDD con tablas de casos: empleado/prestador, 1 día / varios días, "Otro", origen = destino, prestador con formato) y `POST /viaticos/calcular-presupuesto`; `POST /viaticos` en ambas modalidades (instantáneas del colaborador y de tarifas, evento `CREAR`) y `GET /viaticos/{id}` (alcance por dueño vía RLS) | 5 h | S2-01, S2-03 | `agent-skills:test-driven-development` |
| **S2-04b/S2-05** | ✅ **Listado y máquina de estados con etapa:** `GET /viaticos` (paginado, filtros, resumen financiero, `acciones_permitidas`); `PATCH`/`DELETE` en `PENDIENTE`/`PENDIENTE` (RN-09/S-05); `transicionar()` (bloqueo `FOR UPDATE`, evento en la misma transacción): `aprobar` (RN-06/RN-21 en `LEGALIZACION`), `rechazar`, `devolver` (RN-20), `habilitar-legalizacion` (RN-28); RN-27 en ambas etapas con auditoría para SUPERADMIN. **Pendiente** (depende de archivos/gastos, fuera de este alcance): `gestionar-tiquetes`, `valor-asignado`, `estado-financiero`, firma/formato adjunto, PDF | 6 h | S2-04a | `agent-skills:test-driven-development`, `engineering:system-design` |
| **S2-06/S2-07** | ✅ **Archivos, gastos y dinero** (alcance redefinido por el dueño del producto el 2026-11-13; agrupa las antiguas S2-06, S2-07 y S2-08 del backend): `app/modules/archivos` (detección por *magic bytes* por propósito, `LocalStorage` + **S3 con boto3**, URL prefirmada/firmada de 5 min, `POST /archivos`, `GET /archivos/{id}/url`, `/me/firma`); `app/modules/gastos` (CRUD JSON bajo `/viaticos/{id}/gastos`, solo etapa `LEGALIZACION` pendiente, adjuntos propios 1:1, eventos de gasto); `gestionar-tiquetes`, `valor-asignado` y `estado-financiero` con `LIQUIDAR` (antes en S3-01) y `acciones_permitidas` ampliadas. **Pendiente:** firma/formato adjunto del viático (`PUT /viaticos/{id}/firma`), conversión HEIC (se acepta HEIC tal cual), `/pagos` | 11 h | S2-05 | `agent-skills:test-driven-development`, `agent-skills:security-and-hardening` |
| S2-09 | Generar tipos TS desde OpenAPI e integrarlos en `apiClient` | 1 h | S2-06, S2-08 | `agent-skills:api-and-interface-design` |
| S2-10 | UI de lista de viáticos (tarjetas / tabla, filtros de etapa y estado, "Míos/Todos"), selector de modalidad y formulario de **legalización directa** | 3 h | S2-09 | `agent-skills:frontend-ui-engineering` |
| S2-11 | UI del detalle de viático: resumen, checklist, trayectos, gastos, historial; acciones Aprobar / Devolver / Rechazar y **Iniciar legalización** | 4 h | S2-10 | `agent-skills:frontend-ui-engineering` |
| S2-12 | UI de gasto: Sheet con cámara, compresión, progreso, editar, eliminar y reemplazar soporte, visor | 4 h | S2-11 | `agent-skills:frontend-ui-engineering`, `design:accessibility-review` |
| S2-13 | Prueba manual en un celular real (Android e iOS si es posible) de los flujos F-04b, F-05 y F-06 | 1 h | S2-12 | `agent-skills:browser-testing-with-devtools` |
| S2-14 | Cierre: `HANDOFF.md`, `CLAUDE.md` | 0,5 h | — | `claude-mem:handoff` |
| | **Total** | **≈ 44,5 h** | | ⚠️ Supera la capacidad en ~14 h; ver riesgos |

> La **UI del formulario de solicitud** (trayectos, presupuesto, firma, formato adjunto, PDF de solicitud) pasa a la semana 3 como **S3-11**, para que el gate de la semana 2 se alcance con el backend completo y un camino de UI (legalización directa).

**Riesgos:**
- **R2.1** Los valores de tarifas no están extraídos todavía de `calcularGastos.html` (P-7). *Mitigación:* S2-01 no empieza sin el CSV validado; mientras tanto se prueba con tarifas de prueba en los tests (nunca en las migraciones).
- **R2.2** La cámara y HEIC en iOS Safari se comportan distinto. *Mitigación:* dispositivo real temprano (S2-13) y conversión en el servidor.
- **R2.3** La complejidad de RLS con SQLAlchemy (`SET LOCAL` en cada transacción) y de la máquina con etapa. *Mitigación:* centralizar `SET LOCAL` en `get_db`; si se atasca más de 3 h, contingencia 5 del roadmap.
- **R2.4** Semana sobrecargada. *Mitigación:* la UI de solicitud ya salió (S3-11); si aún no alcanza, S2-12 se simplifica (sin reemplazo de soporte) y se completa en la semana 5.
- **R2.5** Los supuestos S-01 a S-14 (`SPEC.md` §17.3) se validan en la demo de la semana 2, en especial S-09 (solicitud sin gastos de viaje), S-10 (tiquetes) y S-11.

**Entregables:** módulo de viáticos y tarifas operativo en backend; flujo de legalización directa completo desde el móvil; ADMIN aprueba/devuelve.

**Criterios de aceptación:**
- [ ] Un VIAJERO no ve ni modifica viáticos ajenos, ni por API ni por consulta directa con `trulab_app` (prueba RLS).
- [ ] El cálculo tarifario devuelve el mismo resultado en `calcular-presupuesto` y en `POST /viaticos`, rechaza importes del cliente, y usa la tabla de empleado o la de prestador según el usuario.
- [ ] No se puede aprobar una solicitud incompleta ni una legalización sin gastos o con gastos sin comprobante (409 con detalle).
- [ ] *Habilitar legalización* solo con solicitud `APROBADO` (y `TRANSFERIDO` si pidió gastos de viaje); conserva el folio `VT-` y devuelve `estado` a `PENDIENTE`.
- [ ] Nadie aprueba su propio viático en ninguna etapa (RN-27), salvo SUPERADMIN con auditoría.
- [ ] Un archivo de más de 10 MB o con extensión falsa se rechaza. Los archivos se guardan en S3 (staging) o en el sistema local.
- [ ] El saldo del detalle coincide con la vista SQL (prueba). Probado en un celular real.

**Gate de salida de la semana 2:** máquina de estados con etapas (salvo pagar), tarifas, gastos con soportes y aislamiento por dueño probados. **DP-05 ya está resuelta (AWS)**; DP-21 (ECS Fargate o App Runner) se decide antes de S3-07.

---

## Semana 3 · Fases F6, F7 y F8, más la preparación de F10: pagos, PDF, dashboard y ETL

**Objetivo:** sistema funcionalmente completo y migración de datos ensayada con datos reales en staging.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S3-01 | Service y API: ~~`estado-financiero` y `valor-asignado`~~ (✅ adelantados en S2-06/S2-07); `/pagos` y `/pagos/resumen` con filtros | 2 h | S2-05 | `agent-skills:test-driven-development`, `agent-skills:api-and-interface-design` |
| S3-02 | UI de Pagos: tabla densa, filtros, totales, saldo coloreado, registrar valor asignado (con el presupuesto sugerido), confirmar estado financiero; tarjetas en móvil | 5 h | S3-01 | `agent-skills:frontend-ui-engineering` |
| S3-03 | **PDF de solicitud (con firma incrustada) y PDF de legalización:** plantillas Jinja2 + WeasyPrint (Docker), endpoints `pdf-solicitud` y `pdf-legalizacion`, prueba de humo (contienen folio, saldo / presupuesto y firma) | 8 h | S2-08 | `agent-skills:build`, `anthropic-skills:pdf` (para validar la salida) |
| S3-04 | Indicadores: endpoints de consumo por proyecto y por estado (KPIs opcional) | 2 h | S3-01 | `agent-skills:api-and-interface-design` |
| S3-05 | → **semana 5.** UI del dashboard: barras y dona en Recharts, filtros de fecha, "ver como tabla", navegación a la lista filtrada | 4 h | S3-04 | `dataviz`, `agent-skills:frontend-ui-engineering` |
| S3-06 | Script ETL (`scripts/etl_appsheet/`): leer los CSV, mapear a `viaticos` (`LEGALIZACION_DIRECTA`, etapa `LEGALIZACION`), crear usuarios operativos con `username` y contraseña temporal (P-8), subir soportes a S3, ajustar secuencias, informe de conciliación (conteos y sumas por tabla) | 6 h | S2-08, P-2, P-8 | `agent-skills:deprecation-and-migration`, `agent-skills:test-driven-development` |
| S3-07 | **Infra de staging en AWS** (ADR-028): RDS PostgreSQL 16, bucket S3 privado, SES (remitente verificado), ECS Fargate o App Runner (DP-21), IAM por rol de tarea, secretos, variables `AWS_*` y `FRONTEND_URL` | 5 h | P-6, DP-21 | `agent-skills:ci-cd-and-automation`, `agent-skills:shipping-and-launch` |
| S3-08 | Ensayo del ETL en staging y revisión de la conciliación con el dueño del producto | 1 h | S3-06, S3-07 | `agent-skills:deprecation-and-migration` |
| S3-09 | (Opcional, DP-06) Correos de notificación al aprobar, devolver, rechazar y pagar (reutiliza `Mailer`/SES de S1-08) | 3 h | S3-01 |
| **S3-11** | **UI de Solicitud de viáticos:** formulario con proyecto, líder, tiquetes, hasta 5 trayectos, días de estadía sugeridos, **presupuesto calculado en vivo** (`calcular-presupuesto`), firma (dibujada, subida o del perfil), formato de prestador y botón Descargar PDF de solicitud; pantalla de **Tarifas de viáticos** (SUPERADMIN) | 6 h | S2-09, S3-03 | `agent-skills:incremental-implementation` |
| S3-10 | Cierre: `HANDOFF.md`, `CLAUDE.md` | 0,5 h | — | `claude-mem:handoff` |
| | **Total** | **≈ 35,5 h** (+3 h opcional; S3-05 ya movida a la semana 5) | | ⚠️ ≈ 5,5 h sobre la capacidad |

**Riesgos:**
- **R3.1** Los soportes de AppSheet viven en Google Drive con rutas relativas; la descarga masiva es lenta o requiere permisos. *Mitigación:* resolver P-2 en la semana 0; el ETL es reanudable (idempotente por `migrado_de`).
- **R3.2** Los datos históricos están sucios (estados con otros nombres, gastos sin legalización). *Mitigación:* tabla de mapeo de estados y un informe de filas rechazadas; decidir con el negocio qué hacer con ellas.
- **R3.3** Las dependencias nativas de WeasyPrint en la imagen. *Mitigación:* imagen base `python:3.12-slim` con los paquetes `libpango` documentados en el Dockerfile.
- **R3.4** Hosting: **resuelto (AWS)**. Riesgo residual: DP-21 (ECS Fargate vs App Runner) y la salida del *sandbox* de SES (P-6). *Mitigación:* decidir DP-21 al inicio de la semana; por defecto App Runner.
- **R3.5** El PDF de solicitud con firma incrustada y los dos documentos aumentan el trabajo de S3-03. *Mitigación:* reusar la base de `solicitud.html` del Apps Script; las miniaturas siguen siendo lo primero que se recorta.

**Entregables:** módulos M6, M7 y M8 operativos; staging desplegado; ETL ensayado con su informe de conciliación.

**Criterios de aceptación:**
- [ ] No se puede liquidar sin cumplir RN-03 (etapa `LEGALIZACION`, `APROBADO`, comprobantes); la doble liquidación concurrente queda bloqueada (prueba).
- [ ] El viajero crea una solicitud completa desde el móvil, ve el presupuesto calculado igual al guardado y descarga el PDF con su firma.
- [ ] El saldo de Pagos, del detalle, del PDF y del dashboard coincide para la misma legalización.
- [ ] Los PDF se abren en el móvil y en el escritorio: el de solicitud contiene folio, trayectos, presupuesto y firma; el de legalización, folio, gastos, totales, saldo e historial.
- [ ] FINANCIERO ve el dashboard y VIAJERO recibe 403 en `/indicadores`.
- [ ] La conciliación del ETL muestra 100 % de filas migradas o explicadas, y las sumas de valores coinciden con AppSheet.

**Gate de salida de la semana 3:** todas las funcionalidades del MVP terminadas salvo las que el plan mueve explícitamente a la semana 5 (S1-12 y S3-05, UIs de administración y dashboard). Desde aquí solo se corrigen errores, se prueba y se despliega (*feature freeze*).

---

## Semana 4 · Fases F9 y F10: pruebas, endurecimiento y producción

**Objetivo:** MVP en producción, usado por personas reales, con los datos históricos y AppSheet retirado a solo lectura.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S4-01 | Completar la matriz RBAC automatizada (todos los endpoints × 4 roles × propio/ajeno) y las pruebas de RLS | 3 h | Gate S3 | `agent-skills:test-driven-development` |
| S4-02 | E2E con Playwright en 3 flujos: viajero legaliza, financiero devuelve, financiero paga | 4 h | Gate S3 | `agent-skills:browser-testing-with-devtools` |
| S4-03 | Revisión de seguridad: OWASP Top 10, dependencias (`pip-audit`, `npm audit`), encabezados, CORS, subida de archivos, logs sin secretos | 3 h | Gate S3 | `security-review`, `agent-skills:security-and-hardening` |
| S4-04 | Revisión responsiva y de accesibilidad (360, 768 y 1280 px; teclado; axe) y Lighthouse (RNF-01) | 3 h | Gate S3 | `design:accessibility-review`, `agent-skills:webperf` |
| S4-05 | → **semana 5.** UAT con 2 o 3 usuarios reales (uno por rol, **incluido un prestador de servicios**) en staging; registro de hallazgos | 3 h | S4-02 | `design:user-research` (guion de prueba) |
| S4-06 | → **semana 5.** Corrección de hallazgos y pulido visual | 6 h | S4-05 | `agent-skills:debugging-and-error-recovery`, `agent-skills:review` |
| S4-07 | **Producción en AWS:** RDS con respaldos diarios y restauración probada, S3, SES en producción, ECS/App Runner, monitoreo de errores (CloudWatch), dominio y TLS, IAM, secretos | 5 h | S3-07 | `agent-skills:shipping-and-launch` |
| S4-08 | → **semana 5.** Checklist de lanzamiento (go/no-go) | 1 h | S4-01..07 | `agent-skills:ship` |
| S4-09 | → **semana 5.** **Corte:** congelar AppSheet y la app de Apps Script (solo lectura), ETL definitivo, verificar la conciliación, enviar las contraseñas temporales y comunicar | 2 h | S4-08 | `agent-skills:deprecation-and-migration` |
| S4-10 | → **semana 5.** Soporte de los primeros días, guía rápida de uso (1 página por rol) y actualización final de la documentación | 2 h | S4-09 | `agent-skills:documentation-and-adrs`, `claude-mem:handoff` |
| | **Total** | **≈ 32 h**; en la semana 4 quedan S4-01 a S4-04 y S4-07 (**18 h**) y el resto pasa a la semana 5 | | |

**Riesgos:**
- **R4.1** UAT revela cambios de alcance. *Mitigación:* solo entran errores y bloqueantes; lo demás va al backlog post-MVP.
- **R4.2** El corte se hace con datos nuevos ingresados en AppSheet tras el ensayo. *Mitigación:* el ETL es idempotente y se congela AppSheet justo antes de la ejecución definitiva.
- **R4.3** Los usuarios no pueden entrar: no están dados de alta, no reciben el correo con la contraseña temporal (SES, correo mal escrito) o aún no cambiaron la contraseña. *Mitigación:* el ETL crea los usuarios desde `Usuarios` con revisión previa de roles y correos (P-8); ADMIN dispone de "restablecer contraseña"; se prueba el envío real en staging.

**Entregables:** MVP en producción; informe final de conciliación; guía de uso; documentación actualizada; backlog post-MVP priorizado.

**Criterios de aceptación (definición de MVP terminado):**
- [ ] Todos los criterios generales de `SPEC.md` §13 cumplidos en M1–M8 (con M3c, M4b y el correo de restablecimiento).
- [ ] CI en verde, sin vulnerabilidades altas o críticas abiertas.
- [ ] Lighthouse móvil: rendimiento ≥ 85 y accesibilidad ≥ 90 en Legalizaciones.
- [ ] Respaldos de BD configurados y una restauración probada una vez.
- [ ] Usuarios reales de los 4 roles operando en producción, incluidos prestadores de servicios.
- [ ] AppSheet y la app de Apps Script en solo lectura.

**Gate de salida de la semana 4:** seguridad, RBAC, E2E y producción AWS listos para UAT. El **GO** de `agent-skills:ship` y la firma de la UAT ocurren al cierre de la semana 5.

---

## Semana 5 · Holgura activada: UAT, corte y tareas desplazadas

> **Activada formalmente el 2026-11-12.** El plan de 4 semanas ya preveía una semana 5 como plan B; el nuevo alcance (acceso híbrido, solicitud con tarifas, PDF de solicitud, AWS) la vuelve necesaria. **El MVP se entrega al cierre de la semana 5.**

| ID | Tarea | Est. | Origen |
| :- | :--- | :-: | :--- |
| S1-12 | UI de Cargos y Usuarios (alta de operativos, restablecer contraseña, crear/promover SUPERADMIN, tipo de vinculación) | 4 h | Semana 1 |
| S3-05 | UI del dashboard (barras y dona, filtros de fecha) | 4 h | Semana 3 |
| S4-05 | UAT con usuarios reales de los 4 roles, con un prestador | 3 h | Semana 4 |
| S4-06 | Corrección de hallazgos y pulido visual | 6 h | Semana 4 |
| S4-08 | Checklist de lanzamiento (go/no-go) | 1 h | Semana 4 |
| S4-09 | Corte (AppSheet y Apps Script a solo lectura, ETL definitivo, contraseñas temporales) | 2 h | Semana 4 |
| S4-10 | Soporte inicial, guías por rol y documentación final | 2 h | Semana 4 |
| S5-01 | Colchón para desbordes de las semanas 1 a 3 | ≈ 8 h | — |
| | **Total** | **≈ 30 h** | |

**Gate de salida de la semana 5:** `agent-skills:ship` devuelve **GO**, el dueño del producto firma la UAT y los datos históricos están migrados.

---

## Resumen de capacidad

| Semana | Estimado | Capacidad | Holgura |
| :-: | :-: | :-: | :-: |
| 1 | 42,5 h (S1-12 pasa a la semana 5) | 30 h | **−12,5 h** → generación asistida y login de desarrollo de SUPERADMIN |
| 2 | 44,5 h | 30 h | **−14,5 h** → la semana más crítica |
| 3 | 35,5 h (+3 opcional; S3-05 pasa a la semana 5) | 30 h | −5,5 h |
| 4 | 18 h | 30 h | +12 h → absorbe desbordes de las semanas 2 y 3 |
| 5 | 30 h | 30 h | ≈ 0 (incluye ≈ 8 h de colchón) |
| **Total** | **≈ 162,5 h** | **150 h** | **≈ −12,5 h** |

**Lectura honesta:** el alcance nuevo (acceso híbrido con recuperación de contraseña, solicitud con tarifas y PDF firmado, entidad unificada y AWS) añade unas **35 h** al plan original de 4 semanas. Con la semana 5 activada la capacidad sube a 150 h. El déficit global restante (~12,5 h) está concentrado en las semanas 1 y 2 y se cubre con:
1. La contingencia del roadmap (recortar KPIs y miniaturas del PDF).
2. Generación de código asistida (Claude) en CRUD, UI repetitiva y pruebas parametrizadas.
3. Usar el colchón de la semana 4 (+12 h) para tareas sin dependencia de la semana 2 (por ejemplo, parte de S2-12 o de S3-11).

Si al cierre de la semana 2 el déficit real supera 10 h, se recorta el dashboard (contingencia 4) antes que cualquier prueba de RBAC, validación de archivos o migración.
