# Arquitectura — Trulab Viajes

> Versión alineada con `SPEC.md` v0.4 (ADR-027 a ADR-030, 2026-11-12). Relacionados: `SPEC.md` (qué), `docs/database-design.md`, `docs/api-design.md`, `docs/design-system.md`.
> Toda decisión estructural nueva se agrega como ADR en §13.

---

## 1. Arquitectura general

**Estilo:** monolito modular con dos aplicaciones desplegables (SPA y API) y una base de datos.

```
┌──────────────────────────┐        HTTPS / JSON         ┌───────────────────────────────┐
│  SPA React (Vite, TS)    │ ──────────────────────────▶ │  API FastAPI (Python 3.12)    │
│  Móvil · Tablet · PC     │ ◀────────────────────────── │  /api/v1                      │
└────────────┬─────────────┘                             │  routers → services → models  │
             │ usuario/contraseña (operativos)           └──┬───────────┬─────────────┬──┘
             │ Google Identity Services (solo SUPERADMIN)   │           │             │
             ▼ (ID token)                            SQL (SQLAlchemy)  S3 (boto3)   SES (boto3)
      ┌──────────────┐                                      │           │             │ correos:
      │ Google OAuth │◀── verificación de token ─┐          ▼           ▼             │ restablecimiento
      └──────────────┘    (solo SUPERADMIN)      │  ┌────────────┐ ┌──────────────┐  │ y notificaciones
                                                 └──│ Amazon RDS │ │ Amazon S3    │  ▼
                                                    │ PostgreSQL │ │ bucket       │ Amazon SES
                                                    │ 16 (+RLS)  │ │ privado      │
                                                    └────────────┘ └──────────────┘
   Producción y staging: AWS (ADR-028). Local: PostgreSQL en Docker, STORAGE_BACKEND=local, correo en el log.
```

**Por qué:**
- Un solo desarrollador y 4 semanas: un monolito minimiza la operación, el despliegue y la depuración.
- El dominio es pequeño (unas 15 tablas), así que la separación por módulos dentro del código da la mantenibilidad necesaria sin el costo de los servicios distribuidos.
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
│   ├── auth/           # login dual (usuario/contraseña · Google), recuperar/cambiar contraseña, AuthProvider, guardas, usePermissions
│   ├── viaticos/       # lista (cards/tabla), detalle, solicitud (trayectos, presupuesto, firma), legalización directa, acciones, habilitar legalización
│   ├── gastos/         # formulario con cámara, lista, visor de soporte
│   ├── pagos/          # tabla densa de saldos, valor asignado, estado financiero
│   ├── cargos/
│   ├── catalogos/      # administración de proyectos, rubros, células y tarifas de viáticos (SUPERADMIN)
│   ├── usuarios/
│   └── indicadores/    # dashboard
├── lib/                # apiClient (fetch + refresh), formatos (COP, fechas), errores
└── types/              # tipos generados desde OpenAPI
```

**Decisiones:**
- **Estado del servidor en TanStack Query; nada de Redux.** Casi todo el estado es remoto. Query resuelve caché, reintentos e invalidación tras las mutaciones (por ejemplo, invalidar `viaticos` y `pagos` después de cambiar el estado financiero).
- **Tipos generados desde OpenAPI** (`openapi-typescript`). Así hay un contrato único entre frontend y backend y el frontend no se desincroniza.
- **Token de acceso en memoria** (nunca en `localStorage`). El refresh token vive en una cookie httpOnly (§5). `apiClient` reintenta una vez tras un 401 llamando a `/auth/refresh`.
- **Permisos en el frontend solo para la experiencia** (ocultar botones y rutas). `usePermissions()` lee el rol de `/me`. La autoridad es el backend.
- **Cálculo tarifario sin lógica en el cliente:** el formulario de solicitud llama a `POST /viaticos/calcular-presupuesto` para la vista previa; la SPA nunca calcula ni envía importes (RN-29).
- **Mobile-first:** en el teléfono la lista de viáticos se muestra como tarjetas, y desde `lg` como tabla. El layout cambia de *BottomBar* a *Sidebar* (`docs/design-system.md` §12).
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
│   ├── security.py         # JWT, hash de refresh tokens, Argon2id (hash/verify de contraseñas), tokens de recuperación, verificación de token de Google
│   ├── permissions.py      # Rol, Permiso, matriz RBAC, require_permission()
│   ├── errors.py           # excepciones de dominio → problem+json
│   ├── storage.py          # interfaz Storage (S3 con boto3 / local) + URLs prefirmadas
│   ├── mail.py             # interfaz Mailer (Amazon SES con boto3 / log local)
│   └── audit.py            # registro de auditoría
├── modules/
│   ├── auth/               # router, schemas, service (login, google, forgot/reset/change, refresh)
│   ├── usuarios/           # router, schemas, service, models (incluye gestión de SUPERADMIN)
│   ├── cargos/
│   ├── catalogos/          # tablas maestras: proyectos, rubros, células (ADR-022) y tarifas_viaticos (ADR-030)
│   ├── viaticos/           # entidad unificada (ADR-029): solicitud, trayectos, cálculo tarifario (función pura) y máquina de estados (etapa, operativa y financiera)
│   ├── gastos/
│   ├── pagos/              # modelo de lectura sobre viaticos
│   ├── reportes/           # PDF de solicitud y de legalización (plantillas Jinja2)
│   └── indicadores/
└── templates/pdf/
backend/alembic/            # migraciones
backend/tests/              # pruebas por módulo + matriz RBAC
```

**Decisiones:**
- **Sesiones síncronas.** FastAPI ejecuta los endpoints `def` en un pool de hilos. A la carga esperada (decenas de usuarios) async no aporta nada y sí complejidad (lazy loading, drivers, pruebas).
- **Reglas de negocio solo en `services`.** Los routers no contienen lógica, así que las reglas se prueban sin HTTP.
- **Máquina de estados explícita** en `viaticos/service.py` con **tres dimensiones** (ADR-021, ADR-029): `etapa` (`SOLICITUD` → `LEGALIZACION`, solo por *habilitar legalización*), `estado` operativo (aprobar, rechazar, devolver; ADMIN y SUPERADMIN, en ambas etapas) y `estado_financiero` (FINANCIERO y SUPERADMIN; ADR-025). Una tabla `TRANSICIONES = {(dimension, etapa, estado_origen, accion): (destino, roles, validaciones)}`. Cualquier cambio pasa por una sola función, `transicionar()`, que valida (permisos, autoaprobación RN-27 en toda etapa, completitud de la solicitud o comprobantes de la legalización, coherencia entre dimensiones y etapa), persiste e inserta el evento en `viatico_eventos` en la misma transacción. *Habilitar legalización* cambia la etapa, devuelve `estado` a `PENDIENTE` y conserva `estado_financiero` y `valor_asignado` (S-12). `Estado legalizacion` de AppSheet no se modela.
- **Una única fuente del saldo** (RN-02): la vista SQL `v_viatico_saldos` la consumen pagos, el detalle, el PDF y los indicadores.
- **Una única función de cálculo tarifario** (RN-29), pura y sin acceso a la BD (recibe trayectos y tarifas): la usan `calcular-presupuesto` y `POST /viaticos`, así la vista previa y lo guardado coinciden. Se prueba con tablas de casos (empleado/prestador, 1 día / varios días, "Otro").
- **Configuración por variables de entorno** (12-factor) con `.env.example` versionado. Los secretos nunca se versionan.

## 4. Arquitectura de base de datos

PostgreSQL 16 (Amazon RDS en staging y producción). El detalle completo está en `docs/database-design.md`. En resumen:
- **Claves primarias UUID** (`gen_random_uuid()`) más **folio legible** (`CA-000001`, `VT-000001`) generado desde una secuencia. El folio `VT-` se conserva de la solicitud a la legalización. Los UUID evitan la enumeración de IDs; el folio responde a RN-04.
- **Dinero en `NUMERIC(14,2)`.**
- **Enums del sistema** (rol, modalidad, etapa, estado, estado financiero) como `TEXT` + `CHECK` (en lugar de `CREATE TYPE`), porque son más fáciles de migrar. **Listas de negocio** (proyectos, rubros, células y **tarifas de viáticos**) como tablas maestras administrables (ADR-022, ADR-030).
- **Eliminación lógica** con `deleted_at`; **auditoría** con `created_at/updated_at/created_by/updated_by`, más las tablas `viatico_eventos` y `auditoria`.
- **Contraseñas** solo para operativos: `usuarios.password_hash` (Argon2id) con `CHECK` por rol; tokens de recuperación solo como hash SHA-256.
- **RLS como defensa en profundidad** sobre `viaticos`, `viatico_trayectos` y `gastos` (§6).
- **Migraciones solo con Alembic.** Nunca se cambia el esquema a mano.

## 5. Flujo de autenticación

**DP-01 actualizada (ADR-027, reemplaza a ADR-006):** acceso **híbrido**. Dominio corporativo `@trulab.co`.

| Rol | Método | Credencial |
| :--- | :--- | :--- |
| `VIAJERO`, `ADMIN`, `FINANCIERO` | **Usuario y contraseña** (`POST /auth/login`) | `username` + contraseña (Argon2id). Pueden ser prestadores de servicios sin correo corporativo |
| `SUPERADMIN` | **Google OAuth exclusivo** (`POST /auth/google`) | Cuenta de Google Workspace `@trulab.co`. Sin contraseña; no puede usar el formulario de usuario/contraseña |

**Superadministrador principal:** `john.hernandez@trulab.co` (`SUPERADMIN_EMAIL`), creado por el seed. Cualquier SUPERADMIN activo puede crear o promover a otros (solo con correo `@trulab.co`); nunca se desactiva ni degrada al último.

### 5.1 Login de operativos (usuario y contraseña)

```
Usuario        SPA                         API
  │ usuario + contraseña                    │
  │──────────▶│ POST /api/v1/auth/login     │
  │           │────────────────────────────▶│ ¿límite de intentos / bloqueo?
  │           │                             │ busca por username (CITEXT); rol operativo, activo
  │           │                             │ verifica Argon2id (también con usuario inexistente: tiempo homogéneo)
  │           │                             │ emite access JWT (15 min) + refresh (cookie httpOnly)
  │           │◀── {access_token, usuario, debe_cambiar_password}
  │           │ si debe_cambiar_password → pantalla "Cambiar contraseña" (el resto de la API devuelve 403)
```

- **Respuesta genérica** `401 CREDENCIALES_INVALIDAS` ante cualquier fallo; el motivo real solo va a `auditoria` (`LOGIN_FALLIDO`).
- **Argon2id** con `argon2-cffi` (parámetros OWASP: mínimo m=19 MiB, t=2, p=1; se ajustan para ~100–300 ms en producción). `password_hash` en formato PHC; si los parámetros cambian, se rehace el hash en el siguiente login correcto.
- **Política:** 12–128 caracteres, distinta del username y del correo, fuera de una lista de contraseñas comunes.
- **Bloqueo:** 5 fallos consecutivos → 15 min (S-14) y límite por IP.
- **Contraseña temporal:** la genera el servidor en el alta o el restablecimiento por ADMIN/SUPERADMIN, se envía por correo y fija `debe_cambiar_password = true`. ADMIN nunca la ve (S-13).

### 5.2 Recuperación y cambio de contraseña (RF-002)

```
POST /auth/password/forgot {identificador}  → 202 siempre (mismo mensaje)
   si el usuario existe, es operativo y está activo:
     genera token aleatorio de 32 bytes, guarda SHA-256 en tokens_recuperacion_password (TTL 15–30 min),
     invalida los anteriores, envía el correo con FRONTEND_URL/restablecer?token=… (Amazon SES; en local, al log)
POST /auth/password/reset {token, nueva_password}
   UPDATE … SET used_at = now() WHERE token_hash = sha256(token) AND used_at IS NULL AND expires_at > now()
   → cambia el hash, debe_cambiar_password = false, revoca todas las sesiones, audita PASSWORD_CAMBIADA
POST /auth/password/change {password_actual, nueva_password}   (con sesión)
```

- Token de **un solo uso**, solo como hash; el enlace nunca se registra en logs (en local, el log de correo muestra el enlace únicamente con `ENV=local`).
- El correo sale de `AWS_SES_SENDER` (identidad verificada en SES).

### 5.3 Login de SUPERADMIN (Google OAuth)

```
Usuario        SPA                         API                              Google
  │  "Ingresar con Google"                 │                                   │
  │──────────▶│  Google Identity Services ─┼──────────────────────────────────▶│
  │           │◀──────── ID token ────────────────────────────────────────────│
  │           │  POST /api/v1/auth/google {id_token}                           │
  │           │───────────────────────────▶│ verifica firma, aud, exp          │
  │           │                            │ exige email_verified y hd=trulab.co
  │           │                            │ ¿existe en usuarios? ¿activo?     │
  │           │                            │ ¿rol = SUPERADMIN? (si no → 403)  │
  │           │◀── {access_token, usuario} │ access JWT + refresh (cookie)     │
```

Validaciones en orden (RN-12): firma/`aud`/`exp`; `email_verified`; `hd` del dominio de Trulab; correo en `usuarios`; activo; **rol `SUPERADMIN`**. Primer login: fija `google_sub`; en los siguientes debe coincidir. Fallo → 403 y `ACCESO_DENEGADO`. Un operativo que intenta Google recibe `METODO_ACCESO_NO_PERMITIDO`.

### 5.4 Sesión (igual para ambos métodos, ADR-005)

- **Access token:** JWT HS256 con `sub`, `rol`, `exp` de 15 min y, si corresponde, `pwd_change`. En memoria en la SPA.
- **Refresh token:** valor opaco guardado **hasheado** en `sesiones` (rotación en cada uso, revocable). Cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`. Vence a los 7 días.
- **Cierre de sesión:** revoca la sesión y borra la cookie.
- **Cambio de rol, desactivación, cambio o restablecimiento de contraseña:** revocan las sesiones. El rol se lee de BD en cada petición, no solo del claim.
- **No hay autorregistro:** los operativos los crean ADMIN o SUPERADMIN; los SUPERADMIN, solo otro SUPERADMIN.
- **Límite de peticiones:** `/auth/login` y `/auth/google` (10/min por IP), `password/forgot` y `reset` más estricto.
- **Login de desarrollo (Google):** solo con `ENV=local` mientras llega el OAuth Client ID (R1.1); una prueba en CI verifica que está desactivado fuera de local.
- **Auditoría:** `LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `PASSWORD_CAMBIADA`, `PASSWORD_RECUPERACION_SOLICITADA`, `ACCESO_DENEGADO`, `SUPERADMIN_ASIGNADO`.

## 6. Flujo de autorización (RBAC)

La autorización tiene tres capas; las dos primeras son obligatorias:

1. **Permiso por endpoint:** la dependencia `require_permission(Permiso.PAGOS_LEER)` en el router. La matriz `ROL → {permisos}` vive en `core/permissions.py` y se deriva de `SPEC.md` §6.
2. **Alcance por recurso** (en el service): para un VIAJERO, toda consulta de viáticos o gastos se filtra por `usuario_id = actual`. Un recurso ajeno responde **404, no 403**, para no revelar que existe. Además se valida la **etapa y el estado** (el dueño edita solo la etapa vigente con `estado = PENDIENTE`), la **separación de funciones** (ADMIN no toca la dimensión financiera, FINANCIERO no toca la operativa y nadie cambia el estado de lo propio, en ninguna etapa, salvo SUPERADMIN) y la **gestión de SUPERADMIN** (solo otro SUPERADMIN crea, promueve, desactiva o degrada; nunca el último).
3. **RLS en PostgreSQL** (defensa en profundidad): en cada transacción, `SET LOCAL app.usuario_id = …` y `SET LOCAL app.rol = …`. Las políticas replican RN-01 sobre `viaticos`, `viatico_trayectos` y `gastos`. `usuarios`, `sesiones` y `tokens_recuperacion_password` no llevan RLS porque el login consulta antes de tener contexto de usuario (`docs/database-design.md` §6). Así, un bug en un service no puede filtrar datos ajenos. La aplicación se conecta con un rol **sin** `BYPASSRLS` y que no es dueño de las tablas.

**Por qué no solo RLS:** las reglas de estado, las transiciones y los mensajes de error claros pertenecen a la aplicación. RLS solo garantiza el aislamiento de filas.

**Por qué no solo la aplicación:** el informe exige RLS (RNF-02), y es una red de seguridad barata para la regla más sensible del sistema.

**Prueba obligatoria:** una prueba parametrizada recorre `(rol × endpoint × propio/ajeno)` y compara contra la matriz de `SPEC.md` §6.

## 7. Gestión de archivos (soportes)

- **Subida a través de la API** (multipart), no directa al bucket. A este volumen simplifica la validación; si el volumen crece, se pasa a URLs firmadas de subida (ADR futuro).
- **Dos adjuntos tipados por gasto** (ADR-023): `soporte` = imagen (JPG, PNG, WEBP, HEIC) y `archivo` = PDF. Al menos uno es necesario para aprobar y liquidar (RN-21), no para guardar el gasto. La **solicitud** suma dos archivos: `firma` (imagen) y `formato adjunto` de prestador (PDF/XLSX), además de la firma reutilizable del perfil (`archivos.proposito`).
- **Validación:** tamaño ≤ 10 MB; tipo real por *magic bytes*, comprobando que coincida con el propósito; rechazo de SVG y HTML. HEIC se convierte a JPEG en el servidor (pillow-heif).
- **Clave del objeto:** `viaticos/{viatico_id}/gastos/{gasto_id}/{soporte|archivo}/{uuid}.{ext}`; `viaticos/{viatico_id}/solicitud/{firma|formato}/{uuid}.{ext}`; `usuarios/{usuario_id}/firma/{uuid}.{ext}`. El nombre original solo se guarda como metadato.
- **Bucket S3 privado** (ADR-028), sin acceso público, cifrado en reposo. Para ver un archivo, la API verifica el permiso y responde con una **URL prefirmada de 5 minutos** (`boto3`; en local, streaming desde el sistema de archivos).
- **Interfaz `Storage`** con `LocalStorage` (desarrollo) y `S3Storage` (staging y producción), elegida por `STORAGE_BACKEND`. GCS queda descartado (DP-05).
- Eliminar un gasto **no** borra el objeto en el MVP (soft delete). Una limpieza programada queda para el futuro.

## 8. Generación de PDFs

- **WeasyPrint + plantillas HTML/Jinja2** con CSS de impresión. Hay **dos documentos**:
  - `templates/pdf/solicitud.html` (basado en `solicitud.html` de Apps Script): encabezado corporativo, folio `VT-`, colaborador, proyecto, líder, trayectos, desglose del presupuesto (o referencia al formato de prestador), tiquetes, comentarios, estado y **firma del solicitante incrustada** (RN-32).
  - `templates/pdf/legalizacion.html`: encabezado, folio, colaborador, motivo, fecha, tabla de gastos (fecha de factura, rubro, proyecto, concepto, valor), totales y saldo, estados operativo y financiero, historial y miniaturas de los soportes de imagen.
- **Por qué WeasyPrint y no ReportLab:** la plantilla es HTML y CSS, la misma habilidad que el resto del proyecto, y el diseño se ajusta sin reescribir código de dibujo.
- **Riesgo:** WeasyPrint necesita Pango/GTK, que es incómodo en Windows. **Mitigación:** el backend siempre corre en Docker (Linux), también en desarrollo.
- **Generación bajo demanda** (`GET /viaticos/{id}/pdf-solicitud` y `/pdf-legalizacion`) y síncrona. Con menos de 50 gastos el tiempo esperado es inferior a 3 s.
- **Futuro:** guardar una copia inmutable del PDF cuando el estado financiero pasa a `PROCESADO`, como evidencia contable.

## 9. Dashboard

- Endpoints de agregación dedicados (`/indicadores/...`). El frontend nunca descarga datos crudos para agregarlos.
  - El **consumo por proyecto** agrupa `gastos` por `gastos.proyecto` (DP-02 ✅: el proyecto vive en el gasto, así que una legalización puede aportar a varios proyectos).
  - La **distribución por estado** agrupa `viaticos` por estado operativo (`estado`, que es también el `Estado legalizacion` de AppSheet; DP-13 ✅).
- **Filtro temporal = Segmentador** (DP-02 ✅, ADR-018): el usuario elige inicio y fin, y se envían como parámetros `desde`/`hasta`. No hay tabla. El último rango usado se recuerda en el navegador por comodidad.
- **Fecha de análisis = `gastos.fecha_factura`** (DP-16 ✅, ADR-024): todo indicador aplica `fecha_factura BETWEEN desde AND hasta`. `fecha_legalizacion` no se usa como fecha principal de análisis.
- Filtro opcional adicional por proyecto.
- **MVP:** (a) total gastado por proyecto, en barras; (b) número de viáticos por estado, en dona. Las tarjetas KPI (total transferido, total gastado, saldo pendiente por pagar) son opcionales si hay tiempo.
- No se necesita caché a este volumen; si llega a necesitarse, se usa una vista materializada.

## 10. OCR (futuro)

- **Flujo propuesto:** al subir un soporte, se crea una tarea asíncrona que llama a un proveedor de visión, guarda sugerencias de `valor`, `fecha` y `NIT` en el gasto, y el usuario las **confirma o corrige** (nunca se aplican sin confirmación).
- **Proveedores candidatos:** Google Document AI (factura), Google Cloud Vision, o un modelo multimodal como Claude con visión. Se decide con un piloto sobre 50 soportes reales.
- **Preparación en el MVP:** la interfaz `Storage` y el modelo de gasto ya admiten campos opcionales; no se construye nada más.

## 11. Integraciones futuras

| Integración | Diseño previsto |
| :--- | :--- |
| Correo transaccional | **Amazon SES** (`boto3`) tras la interfaz `Mailer` de `core/mail.py`. En el MVP se usa **sí o sí** para el restablecimiento de contraseña y el alta de usuarios (contraseña temporal). Las **notificaciones de estado** (DP-06: aprobar, devolver, rechazar, pagado, solicitudes) usan la misma interfaz desde `transicionar()`; son opcionales. Envío síncrono, tolerante a fallos y registrado; luego, una cola. En local, `MAIL_BACKEND=log` escribe el correo en el log. |
| Google Chat | Webhooks entrantes por espacio para avisos; una Chat App con comandos `/` (consultar estado por folio) sobre los mismos endpoints. |
| Asana (heredada de `consumoApi.html`) | Post-MVP: crear tareas al solicitar hospedaje o tiquetes y una vista de seguimiento. Hoy inactiva en Apps Script; no entra al MVP. |
| Excel/CSV | Endpoint `GET /pagos/export?formato=xlsx` con openpyxl. |
| ERP/contabilidad | Fuera de alcance; el folio y las tablas de eventos facilitan una futura exportación. |

## 12. Entornos y despliegue

- **Local:** `docker compose up` levanta postgres, la API (con recarga) y el frontend (Vite dev server), con `STORAGE_BACKEND=local` y `MAIL_BACKEND=log`.
- **CI** (GitHub Actions): lint, verificación de tipos, pruebas de backend con Postgres real, build del frontend.
- **Staging y producción: AWS** (DP-05 ✅, ADR-028):
  - Base de datos: **Amazon RDS for PostgreSQL 16** con respaldo automático diario (retención ≥ 7 días), cifrado en reposo y acceso solo desde la red privada de la API.
  - Archivos: **Amazon S3**, bucket privado con bloqueo de acceso público, cifrado, URLs prefirmadas de 5 min.
  - Correo: **Amazon SES** con identidad de remitente verificada (`AWS_SES_SENDER`).
  - Cómputo: **AWS ECS Fargate** o **AWS App Runner** para la API (DP-21 elige uno); el frontend, como estático (S3 + CloudFront) o servido junto a la API. Credenciales mediante **rol de IAM de la tarea** (sin claves de acceso en variables en producción), secretos en Secrets Manager o Parameter Store.
  - Las migraciones se aplican como paso previo al arranque (tarea `migrate`). TLS en el balanceador/dominio.

## 13. Registro de decisiones (ADR)

Formato: **ID · Decisión · Estado · Motivo**. Estados posibles: *Aceptada*, *Propuesta* (se aplica salvo objeción) o *Reemplazada por ADR-x*.

| ID | Decisión | Estado | Motivo |
| :--- | :--- | :--- | :--- |
| ADR-001 | Monolito modular en monorepo (`backend/`, `frontend/`) | Aceptada | Un desarrollador, dominio pequeño, despliegue simple |
| ADR-002 | React + Vite + **TypeScript** + Tailwind + shadcn/ui | Propuesta | El informe fija React y Tailwind; TS reduce errores al refactorizar y permite generar tipos desde OpenAPI |
| ADR-003 | FastAPI + SQLAlchemy 2 síncrono + Alembic | Aceptada | Exigido por el informe; la versión síncrona es más simple al volumen esperado |
| ADR-004 | PostgreSQL 16 | Aceptada | El informe pide 15+; la 16 es estable y está soportada por los proveedores gestionados |
| ADR-005 | Sesión propia: access JWT de 15 min en memoria + refresh opaco rotativo en cookie httpOnly | Aceptada | Evita tokens en `localStorage` (XSS) y permite revocar |
| ADR-006 | ~~Google Workspace de Trulab como único método de acceso; sin autorregistro ni gestión de contraseñas~~ | **Reemplazada por ADR-027** (2026-11-12) | Los prestadores de servicios externos no tienen correo corporativo. Se conserva como historial: la parte "sin autorregistro, solo usuarios registrados, activos y con rol" sigue vigente |
| ADR-007 | Autorización en el service + RLS en PostgreSQL como defensa en profundidad | Aceptada | RNF-02, aislamiento de la regla RN-01 |
| ADR-008 | Saldo calculado en la vista `v_viatico_saldos` (antes `v_legalizacion_saldos`; ADR-029), nunca almacenado | Aceptada | Una sola fuente de verdad, sin inconsistencias |
| ADR-009 | Archivos en bucket privado (Amazon S3, ADR-028), servidos con URLs prefirmadas de corta duración | Aceptada | Los soportes contienen datos personales y financieros |
| ADR-010 | PDF con WeasyPrint + Jinja2, ejecutado en Docker | Propuesta | Diseño en HTML y CSS; Docker evita problemas de GTK en Windows |
| ADR-011 | PK UUID + folio legible con secuencia (`CA-`, `VT-`) | Aceptada | Seguridad (no enumerable) más RN-04 |
| ADR-012 | Dinero en `NUMERIC(14,2)` / `Decimal`; en JSON se envía como string | Aceptada | Exactitud; evita errores de flotante en JS |
| ADR-013 | Eliminación lógica (`deleted_at`) en entidades operativas | Aceptada | Trazabilidad contable (RN-09) |
| ADR-014 | Errores en formato RFC 9457 (`application/problem+json`) | Aceptada | Estándar, fácil de mapear a mensajes de UI |
| ADR-015 | Máquina de estados centralizada con historial en la misma transacción | Aceptada | RN-05 y RN-10 garantizadas en un solo lugar. El contenido de la máquina lo define ADR-021 |
| ADR-016 | Backend siempre en Docker, incluso en desarrollo | Propuesta | Paridad con producción y dependencias nativas de WeasyPrint |
| ADR-017 | **El proyecto es una lista cerrada en cada gasto** (no en la legalización); no se acepta texto libre (*para el proyecto, ajustado por ADR-031: catálogo u opción "Otro" con nombre escrito*). Lo mismo para `rubro` y `celula` | **Aceptada (DP-02 ✅, definitiva).** El *mecanismo* original (listas en `core/catalogos.py` + `CHECK`, sin tabla) queda **reemplazado por ADR-022** (DP-14 ✅) | Replica fielmente AppSheet (`Registro_Gastos.Proyecto` es un enum) |
| ADR-018 | **Segmentador no se migra**: el filtro temporal del dashboard se implementa como parámetros `desde`/`hasta` | **Aceptada (DP-02 ✅, definitiva)** | En AppSheet era una tabla auxiliar solo para filtrar por fechas; en una SPA eso es estado de la vista, no una entidad |
| ADR-019 | **`valor_transferido` es una columna generada**: `CASE WHEN recursos_propios THEN 0 ELSE valor_asignado END`. Solo FINANCIERO (y SUPERADMIN) escribe `valor_asignado`; `recursos_propios` lo marca el viajero al crear | **Aceptada (DP-04 ✅, DP-17 ✅, definitiva)** | Regla real de AppSheet `IF([Recursos propios]=TRUE,0,[Valor_T])`. Calcularla en la BD impide valores inconsistentes |
| ADR-020 | **Modelo de datos alineado con la estructura real de AppSheet**, con instantánea de los datos del colaborador (`colaborador_nombre/cargo/cedula/celula`) en la legalización al crearla | **Aceptada (DP-07 ✅)**; la instantánea es *Propuesta* | AppSheet copia esos datos con `LOOKUP(USEREMAIL())`. La instantánea conserva el cargo y la célula históricos aunque el usuario cambie |
| ADR-021 | **Dos dimensiones de estado**: `estado` (operativo: `PENDIENTE`, `APROBADO`, `RECHAZADO`) y `estado_financiero` (`PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO`), ambas `TEXT` + `CHECK` e iniciadas en `PENDIENTE` por el sistema. `Estado legalizacion` no se almacena (espejo de `estado`). *Devolver* regresa a `PENDIENTE` con comentario y `devuelta_at`; `DEVUELTO` y `CANCELADO` quedan como extensión futura. `PAGADO`/`PROCESADO` exigen `APROBADO` (`CHECK` de coherencia) | **Aceptada (DP-13 ✅, definitiva)**; los detalles S-01, S-03 y S-08 son *Propuesta* | Replica los enums reales de AppSheet sin inventar valores; dos columnas evitan estados combinados ambiguos. Desde ADR-029 rigen sobre el viático en **ambas etapas**, con `etapa` como tercera dimensión |
| ADR-022 | **Catálogos como tablas maestras** `proyectos`, `rubros` y `celulas` (`nombre`, `activo`, `orden`), referenciadas por FK desde `gastos` y `usuarios`, administradas solo por SUPERADMIN. Se desactivan, no se eliminan. Valores iniciales desde la exportación de AppSheet | **Aceptada (DP-14 ✅, confirmada definitivamente por el negocio el 2026-11-11)**; reemplaza el mecanismo de ADR-017 | Evita valores escritos en el código; permite agregar proyectos, rubros y células sin desplegar; consistencia de datos y mejores reportes. **Sin cambio funcional para el usuario** (sigue eligiendo de una lista desplegable); el cambio es interno: texto/enum → referencia a tabla maestra |
| ADR-023 | **Dos adjuntos tipados por gasto**: `soporte_id` (imagen) y `archivo_id` (PDF); se exige al menos uno para aprobar y liquidar, no para guardar | **Aceptada (DP-15 ✅, definitiva)**; guardar sin comprobante es *Propuesta* (S-04) | Replica `Soporte`/`Archivo` de AppSheet y permite capturar en campo con conexión inestable |
| ADR-024 | **Indicadores sobre `gastos.fecha_factura`** con `BETWEEN desde AND hasta`; `fecha_legalizacion` solo para listas operativas | **Aceptada (DP-16 ✅, definitiva)** | Es la fecha real del consumo y la correcta para el análisis fiscal |
| ADR-025 | **Separación de funciones ADMIN / FINANCIERO**: ADMIN = operación interna (estado operativo, revisión de comprobantes); FINANCIERO = tesorería (valor transferido, estado financiero, pagos, liquidación). Sin autoaprobación salvo SUPERADMIN (RN-27): nadie aprueba, valida financieramente ni paga lo propio | **Aceptada (DP-18 ✅ y RN-27 ✅, definitivas)** | Control interno: quien aprueba no paga y quien paga no aprueba |
| ADR-026 | **Node 24 LTS como runtime estándar del frontend** (imagen `node:24.22.1-bookworm-slim`, CI y equipos de desarrollo; versión fijada en `frontend/.nvmrc`) en lugar de Node 20 | **Aceptada (aprobada por el dueño del producto el 2026-11-12)** | Node 20 llegó a fin de soporte en abril de 2026 y las herramientas actuales (ESLint 10, entre otras) exigen Node ≥ 20.19. Node 24 tiene soporte LTS hasta 2028 |
| ADR-027 | **Autenticación híbrida.** `VIAJERO`, `ADMIN` y `FINANCIERO`: **usuario y contraseña** (Argon2id con `argon2-cffi`), recuperación por correo con token de un solo uso de 15–30 min guardado como SHA-256 en `tokens_recuperacion_password`, contraseña temporal con cambio obligatorio en el primer acceso, límite de intentos y auditoría (`LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `PASSWORD_CAMBIADA`, `PASSWORD_RECUPERACION_SOLICITADA`, `ACCESO_DENEGADO`, `SUPERADMIN_ASIGNADO`). `SUPERADMIN`: **exclusivamente Google OAuth** con cuenta `@trulab.co`, sin contraseña (`CHECK` por rol en la BD). SUPERADMIN inicial `john.hernandez@trulab.co`; cualquier SUPERADMIN activo crea o promueve a otros; nunca se desactiva ni degrada al último. Reemplaza ADR-006, RN-12 y RN-15; reactiva RF-002 | **Aceptada (DP-01 actualizada, 2026-11-12, definitiva)** | La empresa trabaja con prestadores de servicios externos sin correo `@trulab.co` por la regulación colombiana sobre no subordinación. Se mantiene Google para el rol de mayor privilegio, donde el control de Workspace (MFA, bajas) aporta más. Alternativas descartadas: Google para todos (excluye a los prestadores); cuentas Workspace para prestadores (contradice la no subordinación) |
| ADR-028 | **Infraestructura en AWS** para staging y producción: Amazon RDS for PostgreSQL 16, Amazon S3 (bucket privado, URLs prefirmadas de 5 min con `boto3`), Amazon SES (correos transaccionales) y AWS ECS Fargate o App Runner (cómputo; DP-21). En desarrollo se mantiene `STORAGE_BACKEND=local` y `MAIL_BACKEND=log`. Se descarta GCP (Cloud Run, Cloud SQL, GCS) | **Aceptada (resuelve DP-05, 2026-11-12, definitiva)** | Decisión del dueño del producto. Con SES, S3 y RDS bajo un mismo proveedor, el correo de recuperación y los archivos no requieren servicios adicionales |
| ADR-029 | **Entidad unificada `viaticos`** (folio `VT-000001`) que fusiona la Solicitud de viáticos (Apps Script) y la Legalización (AppSheet) y reemplaza a `legalizaciones` (`LG-`). Modalidades `CON_SOLICITUD` y `LEGALIZACION_DIRECTA`; **etapas** `SOLICITUD` y `LEGALIZACION` sobre el mismo registro; `estado` operativo y `estado_financiero` rigen en ambas etapas; tablas `viatico_trayectos` (1–5) y `viatico_eventos`; vista `v_viatico_saldos`; RN-27 en todas las etapas. Se eliminan la dependencia de Google Sheets (`PROYECTOS`, `CorreosExternos`) y la integración Asana (post-MVP) | **Aceptada (DP-19, 2026-11-12, definitiva)** | Trazabilidad completa solicitud → desembolso → facturas → liquidación en un solo folio, sin reconciliar dos sistemas. Alternativa descartada: dos entidades enlazadas (duplica estados, permisos y PDFs) |
| ADR-030 | **Tabla maestra `tarifas_viaticos`** por ciudad y tipo de vinculación (`es_prestador_servicios`), con los 6 conceptos del código legado (`vr_alimentacion`, `otros_gastos`, `transporte_aeropuerto`, `transporte_intermunicipal`, `trans_interno_dia_1`, `trans_interno_varios_dias`), administrada solo por SUPERADMIN, con seed de los 22 destinos de `calcularGastos.html`. El cálculo (RN-29) es una función pura del servidor y se guarda una instantánea de las tarifas en cada trayecto. La regla "prestador + proyecto exige formato" pasa a la columna `proyectos.exige_formato_prestador` | **Aceptada (DP-20, 2026-11-12, definitiva)** | Extiende DP-14: sin valores quemados en el código; cambiar una tarifa no exige despliegue ni altera solicitudes ya hechas |
| ADR-031 | **Proyecto con esquema híbrido:** se mantiene la tabla maestra `proyectos` (SUPERADMIN) y los formularios de solicitud y de gasto ofrecen siempre la opción "Otro", que exige escribir el nombre (`proyecto_otro`, `VARCHAR(150)`). En `gastos` y `viaticos` (`CON_SOLICITUD`), `proyecto_id` pasa a ser nullable y un `CHECK` exige **exactamente uno** de `proyecto_id` / `proyecto_otro`. Rubros y células siguen cerrados. Ajusta RN-16 y DP-14 (y la regla "no se acepta texto libre" de ADR-017 para el proyecto) | **Aceptada (decisión del dueño del producto, 2026-11-12)** | Los viajeros cargan gastos de proyectos nuevos antes de que SUPERADMIN los cree; bloquearlos frenaría la operación. Costo aceptado: los indicadores agrupan esos nombres por texto normalizado y pueden aparecer grafías distintas, que SUPERADMIN revisa y regulariza |
