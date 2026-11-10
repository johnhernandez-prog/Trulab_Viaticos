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
│   ├── pagos/          # tabla densa de saldos, acción pagar
│   ├── cargos/
│   ├── usuarios/
│   └── indicadores/    # dashboard
├── lib/                # apiClient (fetch + refresh), formatos (COP, fechas), errores
└── types/              # tipos generados desde OpenAPI
```

**Decisiones:**
- **Estado del servidor en TanStack Query; nada de Redux.** Casi todo el estado es remoto. Query resuelve caché, reintentos e invalidación tras las mutaciones (por ejemplo, invalidar `legalizaciones` y `pagos` después de "Pagar").
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
│   ├── security.py         # JWT, hashing, verificación de token de Google
│   ├── permissions.py      # Rol, Permiso, matriz RBAC, require_permission()
│   ├── errors.py           # excepciones de dominio → problem+json
│   ├── storage.py          # interfaz Storage (S3/GCS/local) + URLs firmadas
│   └── audit.py            # registro de auditoría
├── modules/
│   ├── auth/               # router, schemas, service
│   ├── usuarios/           # router, schemas, service, models
│   ├── cargos/
│   ├── proyectos/          # (DP-02)
│   ├── legalizaciones/     # incluye la máquina de estados
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
- **Máquina de estados explícita** en `legalizaciones/service.py`: una tabla `TRANSICIONES = {(estado_origen, accion): (estado_destino, roles_permitidos, validaciones)}`. Cualquier cambio de estado pasa por una sola función, `transicionar()`, que valida, persiste e inserta el evento de historial en la misma transacción.
- **Una única fuente del saldo** (RN-02): la vista SQL `v_legalizacion_saldos` la consumen pagos, el detalle, el PDF y los indicadores.
- **Configuración por variables de entorno** (12-factor) con `.env.example` versionado. Los secretos nunca se versionan.

## 4. Arquitectura de base de datos

PostgreSQL 16. El detalle completo está en `docs/database-design.md`. En resumen:
- **Claves primarias UUID** (`gen_random_uuid()`) más **folio legible** (`LG-000001`) generado desde una secuencia. Los UUID evitan la enumeración de IDs; el folio responde a RN-04.
- **Dinero en `NUMERIC(14,2)`.**
- **Enums como `TEXT` + `CHECK`** (en lugar de `CREATE TYPE`), porque son más fáciles de migrar.
- **Eliminación lógica** con `deleted_at`; **auditoría** con `created_at/updated_at/created_by/updated_by`, más las tablas `legalizacion_eventos` y `auditoria`.
- **RLS como defensa en profundidad** sobre `legalizaciones` y `gastos` (§6).
- **Migraciones solo con Alembic.** Nunca se cambia el esquema a mano.

## 5. Flujo de autenticación

Corresponde a DP-01. Este diseño asume Google como método principal y deja la contraseña como opcional.

```
Usuario        SPA                         API                              Google
  │  clic "Ingresar con Google"            │                                   │
  │──────────▶│  Google Identity Services ─┼──────────────────────────────────▶│
  │           │◀──────── ID token (JWT de Google) ────────────────────────────│
  │           │  POST /api/v1/auth/google {id_token}                           │
  │           │───────────────────────────▶│ verifica firma, aud, exp          │
  │           │                            │ exige email_verified y hd=trulab.co
  │           │                            │ busca usuario por correo (activo) │
  │           │                            │ emite access JWT (15 min)         │
  │           │                            │ + refresh token (cookie httpOnly) │
  │           │◀── {access_token, usuario} │                                   │
  │           │  peticiones: Authorization: Bearer <access>                    │
  │           │  si 401 → POST /auth/refresh (cookie) → nuevo access           │
```

- **No hay autorregistro:** si el correo no existe en `usuarios` o está inactivo, la respuesta es 403 con el mensaje "Solicite acceso al administrador". Los usuarios los crea ADMIN (equivale al control de dominio de AppSheet).
- **Access token:** JWT HS256 con `sub` (id de usuario), `rol` y `exp` de 15 min. Se guarda en memoria en la SPA.
- **Refresh token:** valor aleatorio opaco que se guarda **hasheado** en la tabla `sesiones` (rotación en cada uso, revocable). Va en una cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`. Vence a los 7 días.
- **Cierre de sesión:** revoca la sesión y borra la cookie.
- **Cambio de rol o desactivación:** se revocan las sesiones del usuario. El rol se vuelve a leer de BD en cada petición (no se confía solo en el claim) para que el cambio sea efectivo al instante.
- **Contraseña** (si DP-01 la aprueba): `POST /auth/login` con bcrypt (coste 12), con límite de intentos (5 por minuto por IP y por correo).

## 6. Flujo de autorización (RBAC)

La autorización tiene tres capas; las dos primeras son obligatorias:

1. **Permiso por endpoint:** la dependencia `require_permission(Permiso.PAGOS_LEER)` en el router. La matriz `ROL → {permisos}` vive en `core/permissions.py` y se deriva de `SPEC.md` §6.
2. **Alcance por recurso** (en el service): para un VIAJERO, toda consulta de legalizaciones o gastos se filtra por `usuario_id = actual`. Un recurso ajeno responde **404, no 403**, para no revelar que existe. Además se valida el **estado** (por ejemplo, editar solo en `BORRADOR` o `DEVUELTA`).
3. **RLS en PostgreSQL** (defensa en profundidad): en cada transacción, `SET LOCAL app.usuario_id = …` y `SET LOCAL app.rol = …`. Las políticas replican RN-01. Así, un bug en un service no puede filtrar datos ajenos. La aplicación se conecta con un rol **sin** `BYPASSRLS` y que no es dueño de las tablas.

**Por qué no solo RLS:** las reglas de estado, las transiciones y los mensajes de error claros pertenecen a la aplicación. RLS solo garantiza el aislamiento de filas.

**Por qué no solo la aplicación:** el informe exige RLS (RNF-02), y es una red de seguridad barata para la regla más sensible del sistema.

**Prueba obligatoria:** una prueba parametrizada recorre `(rol × endpoint × propio/ajeno)` y compara contra la matriz de `SPEC.md` §6.

## 7. Gestión de archivos (soportes)

- **Subida a través de la API** (multipart), no directa al bucket. A este volumen simplifica la validación; si el volumen crece, se pasa a URLs firmadas de subida (ADR futuro).
- **Validación:** tamaño ≤ 10 MB; tipo real por *magic bytes* (JPG, PNG, WEBP, HEIC, PDF); rechazo de SVG y HTML. HEIC se convierte a JPEG en el servidor (pillow-heif) para que se vea en cualquier navegador y en el PDF.
- **Clave del objeto:** `soportes/{legalizacion_id}/{gasto_id}/{uuid}.{ext}`. El nombre original solo se guarda como metadato.
- **Bucket privado.** Para ver un soporte, la API verifica el permiso y responde con una **URL firmada de 5 minutos** (o hace streaming en local).
- **Interfaz `Storage`** con implementaciones `LocalStorage` (desarrollo) y `S3Storage`/`GCSStorage` (producción), elegida por configuración (DP-05).
- Eliminar un gasto **no** borra el objeto en el MVP (soft delete). Una limpieza programada queda para el futuro.

## 8. Generación de PDFs

- **WeasyPrint + plantilla HTML/Jinja2** (`templates/pdf/legalizacion.html`) con CSS de impresión. El contenido incluye encabezado corporativo, folio, viajero, cargo, proyecto, fechas, motivo, tabla de gastos, totales y saldo, historial de estados y miniaturas de los soportes de imagen.
- **Por qué WeasyPrint y no ReportLab:** la plantilla es HTML y CSS, la misma habilidad que el resto del proyecto, y el diseño se ajusta sin reescribir código de dibujo.
- **Riesgo:** WeasyPrint necesita Pango/GTK, que es incómodo en Windows. **Mitigación:** el backend siempre corre en Docker (Linux), también en desarrollo.
- **Generación bajo demanda** (`GET /legalizaciones/{id}/pdf`) y síncrona. Con menos de 50 gastos por legalización el tiempo esperado es inferior a 3 s.
- **Futuro:** guardar una copia inmutable del PDF al pasar a `PAGADA`, como evidencia contable.

## 9. Dashboard

- Endpoints de agregación dedicados (`/indicadores/...`) con `GROUP BY` sobre `v_legalizacion_saldos`. El frontend nunca descarga datos crudos para agregarlos.
- Filtros por rango de fechas (de `fecha_inicio`) y por proyecto.
- **MVP:** (a) total gastado por proyecto, en barras; (b) número de legalizaciones por estado, en dona. Las tarjetas KPI (total transferido, total gastado, saldo pendiente por pagar) son opcionales si hay tiempo.
- No se necesita caché a este volumen; si llega a necesitarse, se usa una vista materializada.

## 10. OCR (futuro)

- **Flujo propuesto:** al subir un soporte, se crea una tarea asíncrona que llama a un proveedor de visión, guarda sugerencias de `valor`, `fecha` y `NIT` en el gasto, y el usuario las **confirma o corrige** (nunca se aplican sin confirmación).
- **Proveedores candidatos:** Google Document AI (factura), Google Cloud Vision, o un modelo multimodal como Claude con visión. Se decide con un piloto sobre 50 soportes reales.
- **Preparación en el MVP:** la interfaz `Storage` y el modelo de gasto ya admiten campos opcionales; no se construye nada más.

## 11. Integraciones futuras

| Integración | Diseño previsto |
| :--- | :--- |
| Correo (DP-06) | Módulo `notificaciones` con una interfaz `Notifier` (SMTP o Gmail API) llamada desde `transicionar()`. En el MVP el envío es síncrono, tolerante a fallos y registrado en el log; luego se pasa a una cola. |
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
| ADR-006 | Google Identity como login principal; sin autorregistro | Propuesta (DP-01) | Continuidad con AppSheet; sin contraseñas que gestionar |
| ADR-007 | Autorización en el service + RLS en PostgreSQL como defensa en profundidad | Aceptada | RNF-02, aislamiento de la regla RN-01 |
| ADR-008 | Saldo calculado en la vista `v_legalizacion_saldos`, nunca almacenado | Aceptada | Una sola fuente de verdad, sin inconsistencias |
| ADR-009 | Archivos en bucket privado, servidos con URLs firmadas de corta duración | Aceptada | Los soportes contienen datos personales y financieros |
| ADR-010 | PDF con WeasyPrint + Jinja2, ejecutado en Docker | Propuesta | Diseño en HTML y CSS; Docker evita problemas de GTK en Windows |
| ADR-011 | PK UUID + folio legible con secuencia | Aceptada | Seguridad (no enumerable) más RN-04 |
| ADR-012 | Dinero en `NUMERIC(14,2)` / `Decimal`; en JSON se envía como string | Aceptada | Exactitud; evita errores de flotante en JS |
| ADR-013 | Eliminación lógica (`deleted_at`) en entidades operativas | Aceptada | Trazabilidad contable (RN-09) |
| ADR-014 | Errores en formato RFC 9457 (`application/problem+json`) | Aceptada | Estándar, fácil de mapear a mensajes de UI |
| ADR-015 | Máquina de estados centralizada con historial en la misma transacción | Aceptada | RN-05 y RN-10 garantizadas en un solo lugar |
| ADR-016 | Backend siempre en Docker, incluso en desarrollo | Propuesta | Paridad con producción y dependencias nativas de WeasyPrint |
