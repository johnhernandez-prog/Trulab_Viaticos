# SPRINTS — Plan detallado de 4 semanas

> Fuente: `ROADMAP.md`. Supuestos: 1 desarrollador full-stack, 5 días por semana, unas 6 h productivas al día (alrededor de 30 h por semana).
> Las estimaciones van en horas (h). Si una semana supera su capacidad, se aplica el recorte de `ROADMAP.md` (contingencia).
> Las skills se nombran como se invocan en Claude Code (detalle en `docs/skills-strategy.md`).
> **Regla de puerta:** no se empieza la semana siguiente sin cumplir su *Gate de salida*. Si falta algo, se termina primero o se recorta de forma explícita (registrándolo en `HANDOFF.md`).
> **Terminología (DP-13 ✅, 2026-11-11).** Las tareas y estimaciones de este plan **no cambiaron**; sus nombres de acciones vienen de la máquina provisional y se leen así: *legalizar* → **aprobar** (ADMIN); *devolver* → **devolver** (ADMIN, regresa a `PENDIENTE`) y además **rechazar** (ADMIN); *pagar* → **cambiar estado financiero** a `TRANSFERIDO`/`PAGADO`/`PROCESADO` (FINANCIERO); `BORRADOR`/`DEVUELTA` (editable) → `PENDIENTE`; `LEGALIZADA` → `APROBADO`; `PAGADA` → `estado_financiero` `PAGADO`/`PROCESADO`; "listas cerradas" → **tablas de catálogo** (DP-14 ✅); "soporte obligatorio" → **soporte o archivo** (DP-15 ✅). Detalle en `SPEC.md` §17.1 y `docs/user-flows.md`.

---

## Semana 0 · Preparación (antes de empezar; no consume capacidad de desarrollo)

| # | Tarea | Responsable |
| :- | :--- | :--- |
| P-1 | ✅ DP-01, DP-02, DP-04 y DP-07 resueltas (2026-11-10); ✅ DP-13 a DP-18 resueltas (2026-11-11). **No quedan decisiones bloqueantes** (`SPEC.md` §17.1) | Dueño del producto |
| P-2 | Exportar desde AppSheet los **datos** de las 5 tablas en CSV y los soportes (imágenes y PDF), y confirmar dónde se guardan. La estructura ya está validada (DP-07 ✅) | Dueño del producto / admin AppSheet |
| P-3 | Crear el proyecto en Google Cloud Console y el **OAuth Client ID** (web) con los orígenes local y de producción | Admin de Google Workspace |
| P-4 | Entregar el logo y la paleta corporativa (DP-08) | Comunicaciones |
| P-5 | Instalar Docker Desktop, Node 20 LTS, Python 3.12 y el CLI `gh` en el equipo de desarrollo | Desarrollador |

---

## Semana 1 · Fases F1, F2 y F3: base técnica, seguridad, usuarios y cargos

**Objetivo:** un esqueleto desplegable localmente donde un usuario real entra con Google y un ADMIN gestiona usuarios y cargos, con permisos probados.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S1-01 | Estructura del monorepo (`backend/`, `frontend/`, `infra/`, `scripts/`), `.gitignore`, `.editorconfig`, `.env.example`, pre-commit | 2 h | — | `agent-skills:incremental-implementation`, `agent-skills:git-workflow-and-versioning` |
| S1-02 | `docker-compose.yml`: postgres 16, api (con recarga), frontend y minio opcional | 3 h | S1-01 | `agent-skills:ci-cd-and-automation` |
| S1-03 | Backend esqueleto: FastAPI, `core/config`, `core/db`, `/health`, manejo de errores problem+json, `X-Request-ID`, logs estructurados | 4 h | S1-02 | `agent-skills:api-and-interface-design`, `agent-skills:build` |
| S1-04 | Alembic con `naming_convention`, roles de BD `trulab_owner`/`trulab_app`, extensiones `citext` y `pgcrypto` | 2 h | S1-03 | `engineering:architecture` |
| S1-05 | Frontend esqueleto: Vite, React, TS, Tailwind, shadcn/ui, tokens del design-system, React Router, TanStack Query, `apiClient` | 4 h | S1-01 | `agent-skills:frontend-ui-engineering`, `design:design-system` |
| S1-06 | CI en GitHub Actions: ruff, mypy, pytest (con Postgres de servicio), eslint, tsc y build | 2 h | S1-03, S1-05 | `agent-skills:ci-cd-and-automation` |
| S1-07 | Migración `cargos` y `usuarios` + `sesiones` + `auditoria`; seed del primer SUPERADMIN por variable de entorno | 2 h | S1-04 | `agent-skills:test-driven-development` |
| S1-08 | Auth: `/auth/google` (verificación del ID token, `hd`), JWT de acceso, refresh rotativo en cookie, `/auth/refresh`, `/auth/logout`, `/me` | 5 h | S1-07, P-3 | `agent-skills:security-and-hardening`, `agent-skills:test-driven-development` |
| S1-09 | `core/permissions.py`: matriz RBAC, `require_permission`, prueba parametrizada de la matriz | 3 h | S1-08 | `agent-skills:security-and-hardening`, `agent-skills:test-driven-development` |
| S1-10 | API de cargos y usuarios (CRUD, desactivar, reglas de SUPERADMIN, auditoría de cambio de rol) | 4 h | S1-09 | `agent-skills:api-and-interface-design`, `agent-skills:test-driven-development` |
| S1-11 | UI: login, AuthProvider, guardas de ruta, AppShell responsivo (BottomBar / Sidebar plegable / Sidebar fija) con menú por rol | 5 h | S1-05, S1-08 | `agent-skills:frontend-ui-engineering` |
| S1-12 | UI: Cargos y Usuarios (tabla en escritorio, tarjetas en móvil, formularios, confirmaciones) | 4 h | S1-10, S1-11 | `agent-skills:frontend-ui-engineering` |
| S1-13 | Cierre: actualizar `HANDOFF.md` y `CLAUDE.md` (estado) | 0,5 h | — | `claude-mem:handoff` |
| | **Total** | **≈ 40 h** | | ⚠️ Supera la capacidad en unas 10 h; ver riesgos |

**Riesgos:**
- **R1.1** La configuración del OAuth Client ID depende de un admin de Workspace (P-3). *Mitigación:* mientras tanto, desarrollar con un "login de desarrollo" habilitado **solo** con `ENV=local` y desactivado por prueba en CI.
- **R1.2** La semana está sobrecargada. *Mitigación:* S1-12 (UI de usuarios) puede pasar a la mañana del día 1 de la semana 2; la API y las pruebas no se mueven.
- **R1.3** La configuración de Docker en Windows (WSL2) consume tiempo. *Mitigación:* hacer P-5 antes del día 1.

**Entregables:** repositorio con CI en verde; `docker compose up` levanta todo; login con Google; CRUD de cargos y usuarios desde la UI.

**Criterios de aceptación:**
- [ ] Un usuario `@trulab.co` registrado y activo entra; un usuario de otro dominio o no registrado recibe 403 con un mensaje claro.
- [ ] El access token no está en `localStorage`; el refresh renueva la sesión; el logout la revoca.
- [ ] La prueba parametrizada de la matriz RBAC cubre cargos y usuarios para los 4 roles.
- [ ] ADMIN no puede crear SUPERADMIN; nadie puede desactivar al último SUPERADMIN.
- [ ] El layout funciona en 360, 768 y 1280 px.

**Gate de salida de la semana 1:** auth y RBAC en el backend terminados y probados (S1-08, S1-09 y S1-10). Sin esto no se empieza la semana 2.

---

## Semana 2 · Fases F4 y F5: legalizaciones y registro de gastos

**Objetivo:** el viajero completa desde su celular el ciclo crear → agregar gastos con foto → legalizar, y financiero puede devolver.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S2-01 | Incorporar las respuestas de DP-13 a DP-17 al modelo (estructura base ya validada, DP-07 ✅) y ajustar `docs/database-design.md` | 2 h | P-2 | `agent-skills:spec-driven-development`, `agent-skills:documentation-and-adrs` |
| S2-02 | Migración `legalizaciones` (con `valor_transferido` generado), `legalizacion_eventos`, `archivos`, `gastos` (con `rubro` y `proyecto` como listas cerradas); secuencias de folio; vista `v_legalizacion_saldos` | 3 h | S2-01 | `engineering:system-design` |
| S2-03 | RLS sobre `legalizaciones` y `gastos` + `SET LOCAL` por transacción + prueba de aislamiento con `trulab_app` | 3 h | S2-02 | `agent-skills:security-and-hardening`, `agent-skills:test-driven-development` |
| S2-04 | Service de legalizaciones: CRUD, alcance por dueño (404 si es ajena), máquina de estados `transicionar()` (legalizar y devolver), historial; pruebas de RN-05, RN-06, RN-07, RN-09 y RN-10 | 5 h | S2-03 | `agent-skills:test-driven-development`, `engineering:system-design` |
| S2-05 | API de legalizaciones y catálogos (lista con filtros y paginación, detalle con `acciones_permitidas` y saldo, `GET /catalogos`) | 3 h | S2-04 | `agent-skills:api-and-interface-design` |
| S2-06 | `core/storage.py` (Local + S3/GCS), validación por magic bytes, conversión HEIC, URL firmada | 3 h | S1-03 | `agent-skills:security-and-hardening` |
| S2-07 | Service y API de gastos (multipart, reemplazar y ver soporte, eliminación lógica); pruebas de RN-08 y RN-13 | 4 h | S2-04, S2-06 | `agent-skills:test-driven-development` |
| S2-08 | Generar tipos TS desde OpenAPI e integrarlos en `apiClient` | 1 h | S2-05, S2-07 | `agent-skills:api-and-interface-design` |
| S2-09 | UI de lista de legalizaciones (tarjetas en móvil, tabla en escritorio, filtro de estado, "Mías/Todas") y formulario de creación y edición | 4 h | S2-08 | `agent-skills:frontend-ui-engineering` |
| S2-10 | UI del detalle: resumen del saldo, checklist, gastos, historial, acciones Legalizar y Devolver | 4 h | S2-09 | `agent-skills:frontend-ui-engineering` |
| S2-11 | UI de gasto: Sheet con cámara, compresión, progreso, editar, eliminar y reemplazar soporte, visor de soporte | 4 h | S2-10 | `agent-skills:frontend-ui-engineering`, `design:accessibility-review` |
| S2-12 | Prueba manual en un celular real (Android e iOS si es posible) del flujo F-04 a F-06 | 1 h | S2-11 | `agent-skills:browser-testing-with-devtools` |
| S2-13 | Cierre: `HANDOFF.md`, `CLAUDE.md` | 0,5 h | — | `claude-mem:handoff` |
| | **Total** | **≈ 37 h** (+ arrastre de S1-12) | | ⚠️ Ajustada |

**Riesgos:**
- **R2.1** El esquema real de AppSheet difiere del informe. *Mitigación:* S2-01 va primero; los cambios se reflejan en la migración antes de construir encima.
- **R2.2** La cámara y HEIC en iOS Safari se comportan distinto. *Mitigación:* probar en un dispositivo real temprano (S2-12) y convertir en el servidor.
- **R2.3** La complejidad de RLS con SQLAlchemy (el `SET LOCAL` debe ir en cada transacción). *Mitigación:* centralizarlo en la dependencia `get_db`; si se atasca más de 3 h, aplicar la contingencia 5 del roadmap.
- **R2.4** ~~DP-13 a DP-17 sin respuesta al inicio de la semana 2~~ → **cerrado ✅**: todas resueltas el 2026-11-11. Riesgo residual: validar los supuestos S-01 a S-08 (`SPEC.md` §17.3) en la demo de la semana 2.

**Entregables:** módulo de legalizaciones y gastos operativo; flujo del viajero completo desde móvil.

**Criterios de aceptación:**
- [ ] Un VIAJERO no ve ni modifica legalizaciones ajenas, ni por API ni por consulta directa con `trulab_app` (prueba RLS).
- [ ] No se puede legalizar sin gastos o con gastos sin soporte (409 con el detalle).
- [ ] Una legalización LEGALIZADA no es editable por su dueño; DEVUELTA sí, y muestra el comentario.
- [ ] Un archivo de más de 10 MB o con extensión falsa se rechaza.
- [ ] El saldo del detalle coincide con la vista SQL (prueba).
- [ ] Probado en un celular real.

**Gate de salida de la semana 2:** máquina de estados (salvo pagar), gastos con soportes y aislamiento por dueño probados. Además, **DP-05 decidido** (para preparar la infraestructura en la semana 3).

---

## Semana 3 · Fases F6, F7 y F8, más la preparación de F10: pagos, PDF, dashboard y ETL

**Objetivo:** sistema funcionalmente completo y migración de datos ensayada con datos reales en staging.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S3-01 | Service y API: transición `pagar` (RN-03, `FOR UPDATE`), `valor-transferido` con evento, `/pagos` y `/pagos/resumen` con filtros | 4 h | S2-04 | `agent-skills:test-driven-development`, `agent-skills:api-and-interface-design` |
| S3-02 | UI de Pagos: tabla densa, filtros, totales, saldo coloreado, editar transferido, confirmar pago; tarjetas en móvil | 5 h | S3-01 | `agent-skills:frontend-ui-engineering` |
| S3-03 | PDF: plantilla Jinja2 + WeasyPrint (Docker), endpoint `/pdf`, prueba de humo (se genera y contiene el folio y el saldo) | 5 h | S2-07 | `agent-skills:build`, `anthropic-skills:pdf` (para validar la salida) |
| S3-04 | Indicadores: endpoints de consumo por proyecto y por estado (KPIs opcional) | 2 h | S3-01 | `agent-skills:api-and-interface-design` |
| S3-05 | UI del dashboard: barras y dona en Recharts, filtros de fecha, "ver como tabla", navegación a la lista filtrada | 4 h | S3-04 | `dataviz`, `agent-skills:frontend-ui-engineering` |
| S3-06 | Script ETL (`scripts/etl_appsheet/`): leer los CSV, mapear (`migrado_de`), subir soportes al bucket, ajustar secuencias, informe de conciliación (conteos y sumas por tabla) | 6 h | S2-07, P-2 | `agent-skills:deprecation-and-migration`, `agent-skills:test-driven-development` |
| S3-07 | Infra de staging según DP-05: BD gestionada, bucket, despliegue de la API y el frontend, secretos | 3 h | DP-05 | `agent-skills:ci-cd-and-automation`, `agent-skills:shipping-and-launch` |
| S3-08 | Ensayo del ETL en staging y revisión de la conciliación con el dueño del producto | 1 h | S3-06, S3-07 | `agent-skills:deprecation-and-migration` |
| S3-09 | (Opcional, DP-06) Correos al legalizar, devolver y pagar | 3 h | S3-01 | `agent-skills:incremental-implementation` |
| S3-10 | Cierre: `HANDOFF.md`, `CLAUDE.md` | 0,5 h | — | `claude-mem:handoff` |
| | **Total** | **≈ 30,5 h** (+3 h opcional) | | |

**Riesgos:**
- **R3.1** Los soportes de AppSheet viven en Google Drive con rutas relativas; la descarga masiva es lenta o requiere permisos. *Mitigación:* resolver P-2 en la semana 0; el ETL es reanudable (idempotente por `migrado_de`).
- **R3.2** Los datos históricos están sucios (estados con otros nombres, gastos sin legalización). *Mitigación:* tabla de mapeo de estados y un informe de filas rechazadas; decidir con el negocio qué hacer con ellas.
- **R3.3** Las dependencias nativas de WeasyPrint en la imagen. *Mitigación:* imagen base `python:3.12-slim` con los paquetes `libpango` documentados en el Dockerfile.
- **R3.4** El proveedor de hosting no está decidido. *Mitigación:* el gate de la semana 2 lo exige; si no, se usa por defecto Render + Postgres gestionado + S3.

**Entregables:** módulos M6, M7 y M8 operativos; staging desplegado; ETL ensayado con su informe de conciliación.

**Criterios de aceptación:**
- [ ] No se puede pagar sin cumplir RN-03; el doble pago concurrente queda bloqueado (prueba).
- [ ] El saldo de Pagos, del detalle, del PDF y del dashboard coincide para la misma legalización.
- [ ] El PDF se abre en el móvil y en el escritorio y contiene folio, gastos, totales, saldo e historial.
- [ ] FINANCIERO ve el dashboard y VIAJERO recibe 403 en `/indicadores`.
- [ ] La conciliación del ETL muestra 100 % de filas migradas o explicadas, y las sumas de valores coinciden con AppSheet.

**Gate de salida de la semana 3:** todas las funcionalidades del MVP terminadas (*feature freeze*). Desde aquí solo se corrigen errores, se prueba y se despliega.

---

## Semana 4 · Fases F9 y F10: pruebas, endurecimiento y producción

**Objetivo:** MVP en producción, usado por personas reales, con los datos históricos y AppSheet retirado a solo lectura.

| ID | Tarea | Est. | Depende de | Skills recomendadas |
| :- | :--- | :-: | :- | :--- |
| S4-01 | Completar la matriz RBAC automatizada (todos los endpoints × 4 roles × propio/ajeno) y las pruebas de RLS | 3 h | Gate S3 | `agent-skills:test-driven-development` |
| S4-02 | E2E con Playwright en 3 flujos: viajero legaliza, financiero devuelve, financiero paga | 4 h | Gate S3 | `agent-skills:browser-testing-with-devtools` |
| S4-03 | Revisión de seguridad: OWASP Top 10, dependencias (`pip-audit`, `npm audit`), encabezados, CORS, subida de archivos, logs sin secretos | 3 h | Gate S3 | `security-review`, `agent-skills:security-and-hardening` |
| S4-04 | Revisión responsiva y de accesibilidad (360, 768 y 1280 px; teclado; axe) y Lighthouse (RNF-01) | 3 h | Gate S3 | `design:accessibility-review`, `agent-skills:webperf` |
| S4-05 | UAT con 2 o 3 usuarios reales (uno por rol) en staging; registro de hallazgos | 3 h | S4-02 | `design:user-research` (guion de prueba) |
| S4-06 | Corrección de hallazgos y pulido visual | 6 h | S4-05 | `agent-skills:debugging-and-error-recovery`, `agent-skills:review` |
| S4-07 | Producción: infraestructura, respaldos diarios, monitoreo de errores, dominio y TLS, variables y secretos | 3 h | S3-07 | `agent-skills:shipping-and-launch` |
| S4-08 | Checklist de lanzamiento (go/no-go) | 1 h | S4-01..07 | `agent-skills:ship` |
| S4-09 | **Corte:** congelar AppSheet (solo lectura), ETL definitivo, verificar la conciliación, habilitar usuarios y comunicar | 2 h | S4-08 | `agent-skills:deprecation-and-migration` |
| S4-10 | Soporte de los primeros días, guía rápida de uso (1 página por rol) y actualización final de la documentación | 2 h | S4-09 | `agent-skills:documentation-and-adrs`, `claude-mem:handoff` |
| | **Total** | **≈ 30 h** | | |

**Riesgos:**
- **R4.1** UAT revela cambios de alcance. *Mitigación:* solo entran errores y bloqueantes; lo demás va al backlog post-MVP.
- **R4.2** El corte se hace con datos nuevos ingresados en AppSheet tras el ensayo. *Mitigación:* el ETL es idempotente y se congela AppSheet justo antes de la ejecución definitiva.
- **R4.3** Los usuarios no tienen acceso porque no están dados de alta. *Mitigación:* el ETL crea los usuarios desde la tabla `Usuarios`, con revisión previa de roles por parte de ADMIN.

**Entregables:** MVP en producción; informe final de conciliación; guía de uso; documentación actualizada; backlog post-MVP priorizado.

**Criterios de aceptación (definición de MVP terminado):**
- [ ] Todos los criterios generales de `SPEC.md` §13 cumplidos en M1–M8.
- [ ] CI en verde, sin vulnerabilidades altas o críticas abiertas.
- [ ] Lighthouse móvil: rendimiento ≥ 85 y accesibilidad ≥ 90 en Legalizaciones.
- [ ] Respaldos de BD configurados y una restauración probada una vez.
- [ ] Usuarios reales de los 4 roles operando en producción.
- [ ] AppSheet en solo lectura.

**Gate de salida de la semana 4:** `agent-skills:ship` devuelve **GO** y el dueño del producto firma la UAT.

---

## Resumen de capacidad

| Semana | Estimado | Capacidad | Holgura |
| :-: | :-: | :-: | :-: |
| 1 | 40 h | 30 h | **−10 h** → mover S1-12 a la semana 2 y apoyarse en el login de desarrollo |
| 2 | 37 h (+4 h) | 30 h | **−11 h** → la semana más crítica |
| 3 | 30,5 h (+3) | 30 h | ≈ 0 |
| 4 | 30 h | 30 h | 0 |

**Lectura honesta:** el plan de 4 semanas del informe es **ajustado**, con un déficit de unas 20 h en las semanas 1 y 2. Opciones:
1. Aplicar la contingencia del roadmap (recortar KPIs y miniaturas del PDF; el login con contraseña ya quedó fuera por DP-01 ✅).
2. Usar intensamente la generación de código asistida (Claude) en CRUD y UI repetitiva.
3. Pactar desde ya una semana 5 de holgura para UAT y corte.

Se recomienda combinar 1 y 2 y **comunicar la opción 3 como plan B**.
