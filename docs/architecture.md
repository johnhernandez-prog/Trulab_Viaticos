# Arquitectura — Trulab Viajes

> Relacionados: `SPEC.md` (qué), `docs/database-design.md`, `docs/api-design.md`, `docs/design-system.md`.
> Toda decisión estructural nueva se agrega como ADR en §13.

---

## 1. Arquitectura general

**Estilo:** monolito modular con dos aplicaciones desplegables (SPA y API) y una base de datos.

```
┌──────────────────────────┐        HTTPS / JSON         ┌───────────────────────────────┐
│  SPA React (Vite, TS)    │ ──────────────────────────▶ │  API FastAPI (Python 3.12)    │
│  Móvil · Tablet · PC     │ ◀────────────────────────── │  /api/v1                      │
└────────────┬─────────────┘                             │  routers → services → models  │
             │ Google Identity Services                  └──┬───────────┬─────────────┬──┘
             ▼ (ID token)                                   │           │             │
      ┌──────────────┐                            SQL (SQLAlchemy)  objetos (S3/GCS)  correo (futuro)
      │ Google OAuth │◀── verificación de token ─┐  │           │
      └──────────────┘                           │  ▼           ▼
                                                 │ ┌────────────┐ ┌──────────────────┐
                                                 └─│ PostgreSQL │ │ Bucket privado   │
                                                   │ 16 (+RLS)  │ │ soportes / PDFs  │
                                                   └────────────┘ └──────────────────┘
```

**Por qué:**
- Un solo desarrollador y 4 semanas: un monolito minimiza la operación, el despliegue y la depuración.
- El dominio es pequeño (5–8 tablas), así que la separación por módulos dentro del código da la mantenibilidad necesaria sin el costo de los servicios distribuidos.
- Separar SPA y API permite alojar el frontend como estático (CDN) y mantener el contrato REST documentado automáticamente por FastAPI (OpenAPI).

**Estructura del repositorio (monorepo):**

```
Trulab-viaticos/
├── backend/            # API FastAPI
├── frontend/           # SPA React
├── docs/               # Documentación de arquitectura, diseño y flujos
├── infra/              # docker-compose, Dockerfiles, configuración de despliegue
├── scripts/            # ETL de migración AppSheet (fase 9) y utilidades
├── SPEC.md  CLAUDE.md  ROADMAP.md  SPRINTS.md  HANDOFF.md
└── .github/workflows/  # CI
```

## 2. Arquitectura frontend

**Stack:** React 18, Vite y TypeScript; Tailwind CSS con shadcn/ui (componentes Radix accesibles, copiados al repo); TanStack Query para el estado del servidor; React Router; React Hook Form + Zod para formularios; Recharts para los gráficos; Lucide para los iconos.

**Organización por funcionalidad** (no por tipo de archivo):

```
frontend/src/
├── app/                # router, providers (QueryClient, Auth), layout raíz
├── components/
│   ├── ui/             # primitivas shadcn (Button, Input, Dialog, Table…)
│   └── layout/         # AppShell, Sidebar, BottomBar, PageHeader
├── features/
│   ├── auth/           # login, AuthProvider, guardas de ruta, usePermissions
│   ├── legalizaciones/ # lista (cards/tabla), detalle, formulario, acciones
│   ├── gastos/         # formulario con cámara, lista, visor de soporte
│   ├── pagos/          # tabla densa de saldos, valor transferido, estado financiero
│   ├── cargos/
│   ├── catalogos/      # administración de proyectos, rubros y células (SUPERADMIN)
│   ├── usuarios/
│   └── indicadores/    # dashboard
├── lib/                # apiClient (fetch + refresh), formatos (COP, fechas), errores
└── types/              # tipos generados desde OpenAPI
```

**Decisiones:**
- **Estado del servidor en TanStack Query; nada de Redux.** Casi todo el estado es remoto. Query resuelve caché, reintentos e invalidación tras las mutaciones (por ejemplo, invalidar `legalizaciones` y `pagos` después de cambiar el estado financiero).
- **Tipos generados desde OpenAPI** (`openapi-typescript`). Así hay un contrato único entre frontend y backend y el frontend no se desincroniza.
- **Token de acceso en memoria** (nunca en `localStorage`). El refresh token vive en una cookie httpOnly (§5). `apiClient` reintenta una vez tras un 401 llamando a `/auth/refresh`.
- **Permisos en el frontend solo para la experiencia** (ocultar botones y rutas). `usePermissions()` lee el rol de `/me`. La autoridad es el backend.
- **Mobile-first:** en el teléfono la lista de legalizaciones se muestra como tarjetas, y desde `lg` como tabla. El layout cambia de *BottomBar* a *Sidebar* (`docs/design-system.md` §12).
- **Captura de cámara:** `<input type="file" accept="image/*,application/pdf" capture="environment">`. Las imágenes se comprimen en el cliente (máximo ~1600 px, JPEG al 80 %) antes de subir, para redes móviles lentas.

## 3. Arquitectura backend

**Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 (estilo 2.0, sesiones **síncronas**), Alembic, psycopg 3.

**Capas** (dependencias de arriba hacia abajo, nunca al revés):

```
routers (HTTP: validación de entrada, códigos de estado, dependencias de auth)
   ↓
services (reglas de negocio, máquina de estados, autorización por recurso)
   ↓
models (SQLAlchemy) + core/storage + core/pdf
```

```
backend/app/
├── main.py                 # creación de la app, middlewares, routers
├── core/
│   ├── config.py           # Settings (pydantic-settings, variables de entorno)
│   ├── db.py               # engine, SessionLocal, dependencia get_db, SET LOCAL para RLS
│   ├── security.py         # JWT, hash de refresh tokens, verificación de token de Google
│   ├── permissions.py      # Rol, Permiso, matriz RBAC, require_permission()
│   ├── errors.py           # excepciones de dominio → problem+json
│   ├── storage.py          # interfaz Storage (S3/GCS/local) + URLs firmadas
│   └── audit.py            # registro de auditoría
├── modules/
│   ├── auth/               # router, schemas, service
│   ├── usuarios/           # router, schemas, service, models
│   ├── cargos/
│   ├── catalogos/          # tablas maestras: proyectos, rubros, células (ADR-022)
│   ├── legalizaciones/     # incluye la máquina de estados (operativa y financiera)
│   ├── gastos/
│   ├── pagos/              # modelo de lectura sobre legalizaciones
│   ├── reportes/           # PDF (plantillas Jinja2)
│   └── indicadores/
└── templates/pdf/
backend/alembic/            # migraciones
backend/tests/              # pruebas por módulo + matriz RBAC
```

**Decisiones:**
- **Sesiones síncronas.** FastAPI ejecuta los endpoints `def` en un pool de hilos. A la carga esperada (decenas de usuarios) async no aporta nada y sí complejidad (lazy loading, drivers, pruebas).
- **Reglas de negocio solo en `services`.** Los routers no contienen lógica, así que las reglas se prueban sin HTTP.
- **Máquina de estados explícita** en `legalizaciones/service.py` con **dos dimensiones** (ADR-021): una tabla `TRANSICIONES = {(dimension, estado_origen, accion): (estado_destino, roles_permitidos, validaciones)}`. La dimensión `OPERATIVO` (`estado`: aprobar, rechazar, devolver) solo admite ADMIN y SUPERADMIN; la `FINANCIERO` (`estado_financiero`) solo FINANCIERO y SUPERADMIN (ADR-025). Cualquier cambio de estado pasa por una sola función, `transicionar()`, que valida (permisos, autoaprobación, comprobantes, coherencia entre dimensiones), persiste e inserta el evento de historial en la misma transacción. `Estado legalizacion` de AppSheet no se modela: es `estado`.
- **Una única fuente del saldo** (RN-02): la vista SQL `v_legalizacion_saldos` la consumen pagos, el detalle, el PDF y los indicadores.
- **Configuración por variables de entorno** (12-factor) con `.env.example` versionado. Los secretos nunca se versionan.

## 4. Arquitectura de base de datos

PostgreSQL 16. El detalle completo está en `docs/database-design.md`. En resumen:
- **Claves primarias UUID** (`gen_random_uuid()`) más **folio legible** (`LG-000001`) generado desde una secuencia. Los UUID evitan la enumeración de IDs; el folio responde a RN-04.
- **Dinero en `NUMERIC(14,2)`.**
- **Enums del sistema** (rol, estado, estado financiero) como `TEXT` + `CHECK` (en lugar de `CREATE TYPE`), porque son más fáciles de migrar. **Listas de negocio** (proyectos, rubros, células) como tablas maestras administrables (ADR-022).
- **Eliminación lógica** con `deleted_at`; **auditoría** con `created_at/updated_at/created_by/updated_by`, más las tablas `legalizacion_eventos` y `auditoria`.
- **RLS como defensa en profundidad** sobre `legalizaciones` y `gastos` (§6).
- **Migraciones solo con Alembic.** Nunca se cambia el esquema a mano.

## 5. Flujo de autenticación

**DP-01 ✅ resuelta y definitiva:** Google OAuth es el **único** método de acceso, solo con cuentas de Google Workspace de Trulab. Replica la configuración real de AppSheet: *Require user sign-in* = sí, *Identity Provider* = Google, *Allow all signed-in users* = no.

```
Usuario        SPA                         API                              Google
  │  clic "Ingresar con Google"            │                                   │
  │──────────▶│  Google Identity Services ─┼──────────────────────────────────▶│
  │           │◀──────── ID token (JWT de Google) ────────────────────────────│
  │           │  POST /api/v1/auth/google {id_token}                           │
  │           │───────────────────────────▶│ verifica firma, aud, exp          │
  │           │                            │ exige email_verified y hd=trulab.co
  │           │                            │ ¿existe en usuarios? ¿activo?     │
  │           │                            │ ¿tiene rol? (si no → 403)         │
  │           │                            │ emite access JWT (15 min)         │
  │           │                            │ + refresh token (cookie httpOnly) │
  │           │◀── {access_token, usuario} │                                   │
  │           │  peticiones: Authorization: Bearer <access>                    │
  │           │  si 401 → POST /auth/refresh (cookie) → nuevo access           │
```

- **Validaciones en orden** (RN-12). Todas deben cumplirse:
  1. Firma, `aud` y `exp` del ID token.
  2. `email_verified`.
  3. Dominio de Google Workspace de Trulab (claim `hd`).
  4. El correo existe en `usuarios`.
  5. El usuario está `activo`.
  6. Tiene un rol válido.

  Si falla cualquiera, la respuesta es 403 con el mensaje "Su cuenta no tiene acceso. Contacte al administrador", y se registra `ACCESO_DENEGADO` en `auditoria`.
- **No hay autorregistro:** los usuarios los crean ADMIN o SUPERADMIN. Equivale a *Allow all signed-in users = no* y a la tabla Usuarios de AppSheet, que ya resolvía los datos con `LOOKUP(USEREMAIL())`.
- **Sin contraseñas** (RN-15): la app no almacena, crea, recupera, restablece ni cambia credenciales. No existen endpoints ni pantallas para eso. Los problemas de cuenta los atienden los administradores de Google Workspace de Trulab.
- **Access token:** JWT HS256 con `sub` (id de usuario), `rol` y `exp` de 15 min. Se guarda en memoria en la SPA.
- **Refresh token:** valor aleatorio opaco que se guarda **hasheado** en la tabla `sesiones` (rotación en cada uso, revocable). Va en una cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`. Vence a los 7 días.
- **Cierre de sesión:** revoca la sesión y borra la cookie.
- **Cambio de rol o desactivación:** se revocan las sesiones del usuario. El rol se vuelve a leer de BD en cada petición (no se confía solo en el claim) para que el cambio sea efectivo al instante.
- **Límite de peticiones** en `/auth/google` (10 por minuto por IP) contra el abuso del endpoint.
- **Login de desarrollo:** solo con `ENV=local`, para trabajar mientras llega el OAuth Client ID (riesgo R1.1 de `SPRINTS.md`). Una prueba en CI verifica que está desactivado fuera de local.

## 6. Flujo de autorización (RBAC)

La autorización tiene tres capas; las dos primeras son obligatorias:

1. **Permiso por endpoint:** la dependencia `require_permission(Permiso.PAGOS_LEER)` en el router. La matriz `ROL → {permisos}` vive en `core/permissions.py` y se deriva de `SPEC.md` §6.
2. **Alcance por recurso** (en el service): para un VIAJERO, toda consulta de legalizaciones o gastos se filtra por `usuario_id = actual`. Un recurso ajeno responde **404, no 403**, para no revelar que existe. Además se valida el **estado** (por ejemplo, el dueño edita solo con `estado = PENDIENTE`) y la **separación de funciones** (ADMIN no toca la dimensión financiera, FINANCIERO no toca la operativa y nadie cambia el estado de lo propio salvo SUPERADMIN).
3. **RLS en PostgreSQL** (defensa en profundidad): en cada transacción, `SET LOCAL app.usuario_id = …` y `SET LOCAL app.rol = …`. Las políticas replican RN-01. Así, un bug en un service no puede filtrar datos ajenos. La aplicación se conecta con un rol **sin** `BYPASSRLS` y que no es dueño de las tablas.

**Por qué no solo RLS:** las reglas de estado, las transiciones y los mensajes de error claros pertenecen a la aplicación. RLS solo garantiza el aislamiento de filas.

**Por qué no solo la aplicación:** el informe exige RLS (RNF-02), y es una red de seguridad barata para la regla más sensible del sistema.

**Prueba obligatoria:** una prueba parametrizada recorre `(rol × endpoint × propio/ajeno)` y compara contra la matriz de `SPEC.md` §6.

## 7. Gestión de archivos (soportes)

- **Subida a través de la API** (multipart), no directa al bucket. A este volumen simplifica la validación; si el volumen crece, se pasa a URLs firmadas de subida (ADR futuro).
- **Dos adjuntos tipados por gasto** (ADR-023): `soporte` = imagen (JPG, PNG, WEBP, HEIC) y `archivo` = PDF. Al menos uno es necesario para aprobar y liquidar (RN-21), no para guardar el gasto.
- **Validación:** tamaño ≤ 10 MB; tipo real por *magic bytes*, comprobando que coincida con el campo (imagen en `soporte`, PDF en `archivo`); rechazo de SVG y HTML. HEIC se convierte a JPEG en el servidor (pillow-heif) para que se vea en cualquier navegador y en el PDF.
- **Clave del objeto:** `gastos/{legalizacion_id}/{gasto_id}/{soporte|archivo}/{uuid}.{ext}`. El nombre original solo se guarda como metadato.
- **Bucket privado.** Para ver un soporte, la API verifica el permiso y responde con una **URL firmada de 5 minutos** (o hace streaming en local).
- **Interfaz `Storage`** con implementaciones `LocalStorage` (desarrollo) y `S3Storage`/`GCSStorage` (producción), elegida por configuración (DP-05).
- Eliminar un gasto **no** borra el objeto en el MVP (soft delete). Una limpieza programada queda para el futuro.

## 8. Generación de PDFs

- **WeasyPrint + plantilla HTML/Jinja2** (`templates/pdf/legalizacion.html`) con CSS de impresión. El contenido incluye encabezado corporativo, folio, colaborador (nombre, cargo, célula), motivo, fecha de legalización, tabla de gastos (fecha de factura, rubro, proyecto, concepto, valor), totales y saldo, estado operativo y financiero, historial y miniaturas de los soportes de imagen.
- **Por qué WeasyPrint y no ReportLab:** la plantilla es HTML y CSS, la misma habilidad que el resto del proyecto, y el diseño se ajusta sin reescribir código de dibujo.
- **Riesgo:** WeasyPrint necesita Pango/GTK, que es incómodo en Windows. **Mitigación:** el backend siempre corre en Docker (Linux), también en desarrollo.
- **Generación bajo demanda** (`GET /legalizaciones/{id}/pdf`) y síncrona. Con menos de 50 gastos por legalización el tiempo esperado es inferior a 3 s.
- **Futuro:** guardar una copia inmutable del PDF cuando el estado financiero pasa a `PROCESADO`, como evidencia contable.

## 9. Dashboard

- Endpoints de agregación dedicados (`/indicadores/...`). El frontend nunca descarga datos crudos para agregarlos.
  - El **consumo por proyecto** agrupa `gastos` por `gastos.proyecto` (DP-02 ✅: el proyecto vive en el gasto, así que una legalización puede aportar a varios proyectos).
  - La **distribución por estado** agrupa `legalizaciones` por estado operativo (`estado`, que es también el `Estado legalizacion` de AppSheet; DP-13 ✅).
- **Filtro temporal = Segmentador** (DP-02 ✅, ADR-018): el usuario elige inicio y fin, y se envían como parámetros `desde`/`hasta`. No hay tabla. El último rango usado se recuerda en el navegador por comodidad.
- **Fecha de análisis = `gastos.fecha_factura`** (DP-16 ✅, ADR-024): todo indicador aplica `fecha_factura BETWEEN desde AND hasta`. `fecha_legalizacion` no se usa como fecha principal de análisis.
- Filtro opcional adicional por proyecto.
- **MVP:** (a) total gastado por proyecto, en barras; (b) número de legalizaciones por estado, en dona. Las tarjetas KPI (total transferido, total gastado, saldo pendiente por pagar) son opcionales si hay tiempo.
- No se necesita caché a este volumen; si llega a necesitarse, se usa una vista materializada.

## 10. OCR (futuro)

- **Flujo propuesto:** al subir un soporte, se crea una tarea asíncrona que llama a un proveedor de visión, guarda sugerencias de `valor`, `fecha` y `NIT` en el gasto, y el usuario las **confirma o corrige** (nunca se aplican sin confirmación).
- **Proveedores candidatos:** Google Document AI (factura), Google Cloud Vision, o un modelo multimodal como Claude con visión. Se decide con un piloto sobre 50 soportes reales.
- **Preparación en el MVP:** la interfaz `Storage` y el modelo de gasto ya admiten campos opcionales; no se construye nada más.

## 11. Integraciones futuras

| Integración | Diseño previsto |
| :--- | :--- |
| Correo (DP-06) | Módulo `notificaciones` con una interfaz `Notifier` (SMTP o Gmail API) llamada desde `transicionar()` (aprobar, devolver, rechazar, pagado). En el MVP el envío es síncrono, tolerante a fallos y registrado en el log; luego se pasa a una cola. |
| Google Chat | Webhooks entrantes por espacio para avisos; una Chat App con comandos `/` (consultar estado por folio) sobre los mismos endpoints. |
| Excel/CSV | Endpoint `GET /pagos/export?formato=xlsx` con openpyxl. |
| ERP/contabilidad | Fuera de alcance; el folio y las tablas de eventos facilitan una futura exportación. |

## 12. Entornos y despliegue

- **Local:** `docker compose up` levanta postgres, minio (opcional), la API (con recarga) y el frontend (Vite dev server).
- **CI** (GitHub Actions): lint, verificación de tipos, pruebas de backend con Postgres de servicio, build del frontend.
- **Producción** (DP-05): API en contenedor, frontend estático en CDN, Postgres gestionado con respaldo diario y bucket privado. Las migraciones se aplican como paso previo al arranque del contenedor.

## 13. Registro de decisiones (ADR)

Formato: **ID · Decisión · Estado · Motivo**. Estados posibles: *Aceptada*, *Propuesta* (se aplica salvo objeción) o *Reemplazada por ADR-x*.

| ID | Decisión | Estado | Motivo |
| :--- | :--- | :--- | :--- |
| ADR-001 | Monolito modular en monorepo (`backend/`, `frontend/`) | Aceptada | Un desarrollador, dominio pequeño, despliegue simple |
| ADR-002 | React + Vite + **TypeScript** + Tailwind + shadcn/ui | Propuesta | El informe fija React y Tailwind; TS reduce errores al refactorizar y permite generar tipos desde OpenAPI |
| ADR-003 | FastAPI + SQLAlchemy 2 síncrono + Alembic | Aceptada | Exigido por el informe; la versión síncrona es más simple al volumen esperado |
| ADR-004 | PostgreSQL 16 | Aceptada | El informe pide 15+; la 16 es estable y está soportada por los proveedores gestionados |
| ADR-005 | Sesión propia: access JWT de 15 min en memoria + refresh opaco rotativo en cookie httpOnly | Aceptada | Evita tokens en `localStorage` (XSS) y permite revocar |
| ADR-006 | **Google Workspace de Trulab como único método de acceso**; acceso solo para usuarios registrados, activos y con rol; sin autorregistro ni gestión de contraseñas | **Aceptada (DP-01 ✅, definitiva)** | Replica la seguridad real de AppSheet (*Require sign-in*, proveedor Google, *Allow all signed-in users* = no). Las credenciales quedan en Google Workspace |
| ADR-007 | Autorización en el service + RLS en PostgreSQL como defensa en profundidad | Aceptada | RNF-02, aislamiento de la regla RN-01 |
| ADR-008 | Saldo calculado en la vista `v_legalizacion_saldos`, nunca almacenado | Aceptada | Una sola fuente de verdad, sin inconsistencias |
| ADR-009 | Archivos en bucket privado, servidos con URLs firmadas de corta duración | Aceptada | Los soportes contienen datos personales y financieros |
| ADR-010 | PDF con WeasyPrint + Jinja2, ejecutado en Docker | Propuesta | Diseño en HTML y CSS; Docker evita problemas de GTK en Windows |
| ADR-011 | PK UUID + folio legible con secuencia | Aceptada | Seguridad (no enumerable) más RN-04 |
| ADR-012 | Dinero en `NUMERIC(14,2)` / `Decimal`; en JSON se envía como string | Aceptada | Exactitud; evita errores de flotante en JS |
| ADR-013 | Eliminación lógica (`deleted_at`) en entidades operativas | Aceptada | Trazabilidad contable (RN-09) |
| ADR-014 | Errores en formato RFC 9457 (`application/problem+json`) | Aceptada | Estándar, fácil de mapear a mensajes de UI |
| ADR-015 | Máquina de estados centralizada con historial en la misma transacción | Aceptada | RN-05 y RN-10 garantizadas en un solo lugar. El contenido de la máquina lo define ADR-021 |
| ADR-016 | Backend siempre en Docker, incluso en desarrollo | Propuesta | Paridad con producción y dependencias nativas de WeasyPrint |
| ADR-017 | **El proyecto es una lista cerrada en cada gasto** (no en la legalización); no se acepta texto libre. Lo mismo para `rubro` y `celula` | **Aceptada (DP-02 ✅, definitiva).** El *mecanismo* original (listas en `core/catalogos.py` + `CHECK`, sin tabla) queda **reemplazado por ADR-022** (DP-14 ✅) | Replica fielmente AppSheet (`Registro_Gastos.Proyecto` es un enum) |
| ADR-018 | **Segmentador no se migra**: el filtro temporal del dashboard se implementa como parámetros `desde`/`hasta` | **Aceptada (DP-02 ✅, definitiva)** | En AppSheet era una tabla auxiliar solo para filtrar por fechas; en una SPA eso es estado de la vista, no una entidad |
| ADR-019 | **`valor_transferido` es una columna generada**: `CASE WHEN recursos_propios THEN 0 ELSE valor_asignado END`. Solo FINANCIERO (y SUPERADMIN) escribe `valor_asignado`; `recursos_propios` lo marca el viajero al crear | **Aceptada (DP-04 ✅, DP-17 ✅, definitiva)** | Regla real de AppSheet `IF([Recursos propios]=TRUE,0,[Valor_T])`. Calcularla en la BD impide valores inconsistentes |
| ADR-020 | **Modelo de datos alineado con la estructura real de AppSheet**, con instantánea de los datos del colaborador (`colaborador_nombre/cargo/cedula/celula`) en la legalización al crearla | **Aceptada (DP-07 ✅)**; la instantánea es *Propuesta* | AppSheet copia esos datos con `LOOKUP(USEREMAIL())`. La instantánea conserva el cargo y la célula históricos aunque el usuario cambie |
| ADR-021 | **Dos dimensiones de estado**: `estado` (operativo: `PENDIENTE`, `APROBADO`, `RECHAZADO`) y `estado_financiero` (`PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO`), ambas `TEXT` + `CHECK` e iniciadas en `PENDIENTE` por el sistema. `Estado legalizacion` no se almacena (espejo de `estado`). *Devolver* regresa a `PENDIENTE` con comentario y `devuelta_at`; `DEVUELTO` y `CANCELADO` quedan como extensión futura. `PAGADO`/`PROCESADO` exigen `APROBADO` (`CHECK` de coherencia) | **Aceptada (DP-13 ✅, definitiva)**; los detalles S-01, S-03 y S-08 son *Propuesta* | Replica los enums reales de AppSheet sin inventar valores; dos columnas evitan estados combinados ambiguos |
| ADR-022 | **Catálogos como tablas maestras** `proyectos`, `rubros` y `celulas` (`nombre`, `activo`, `orden`), referenciadas por FK desde `gastos` y `usuarios`, administradas solo por SUPERADMIN. Se desactivan, no se eliminan. Valores iniciales desde la exportación de AppSheet | **Aceptada (DP-14 ✅, confirmada definitivamente por el negocio el 2026-11-11)**; reemplaza el mecanismo de ADR-017 | Evita valores escritos en el código; permite agregar proyectos, rubros y células sin desplegar; consistencia de datos y mejores reportes. **Sin cambio funcional para el usuario** (sigue eligiendo de una lista desplegable); el cambio es interno: texto/enum → referencia a tabla maestra |
| ADR-023 | **Dos adjuntos tipados por gasto**: `soporte_id` (imagen) y `archivo_id` (PDF); se exige al menos uno para aprobar y liquidar, no para guardar | **Aceptada (DP-15 ✅, definitiva)**; guardar sin comprobante es *Propuesta* (S-04) | Replica `Soporte`/`Archivo` de AppSheet y permite capturar en campo con conexión inestable |
| ADR-024 | **Indicadores sobre `gastos.fecha_factura`** con `BETWEEN desde AND hasta`; `fecha_legalizacion` solo para listas operativas | **Aceptada (DP-16 ✅, definitiva)** | Es la fecha real del consumo y la correcta para el análisis fiscal |
| ADR-025 | **Separación de funciones ADMIN / FINANCIERO**: ADMIN = operación interna (estado operativo, revisión de comprobantes); FINANCIERO = tesorería (valor transferido, estado financiero, pagos, liquidación). Sin autoaprobación salvo SUPERADMIN (RN-27): nadie aprueba, valida financieramente ni paga lo propio | **Aceptada (DP-18 ✅ y RN-27 ✅, definitivas)** | Control interno: quien aprueba no paga y quien paga no aprueba |
