# Diseño de API — Trulab Viajes

> Diseño del contrato; **no hay endpoints implementados todavía**. La especificación OpenAPI que genere FastAPI será la referencia viva una vez implementado; este documento define las reglas que esa especificación debe cumplir.

---

## 1. Principios

1. **REST orientado a recursos**, con sustantivos en plural y en español, iguales a las tablas (`/legalizaciones`, `/gastos`).
2. **Las transiciones de estado son acciones explícitas** (`POST /legalizaciones/{id}/legalizar`), nunca `PATCH estado=...`. Así la máquina de estados (ADR-015) es el único camino y cada acción tiene su propio permiso.
3. **El backend decide** lo que el usuario puede ver y hacer. Las respuestas de detalle incluyen `acciones_permitidas` para que la UI no replique la lógica.
4. **JSON en `snake_case`** igual que Python y la BD. El frontend usa tipos generados, así que no se convierte a camelCase.
5. **Contrato tipado:** cada request y response es un esquema Pydantic. Los tipos del frontend se generan desde `/api/v1/openapi.json`.

## 2. Base y versionamiento

- URL base: `/api/v1`.
- Una versión **mayor** solo cambia (`/api/v2`) ante cambios incompatibles: eliminar o renombrar campos, o cambiar su semántica. Agregar campos opcionales o endpoints nuevos no cambia la versión.
- Al deprecar algo se agrega el encabezado `Deprecation: true` y `Sunset: <fecha>` en la versión vieja, durante al menos un ciclo.
- `GET /api/v1/health` devuelve `{status, version, db}` sin autenticación.

## 3. Autenticación

| Método | Ruta | Descripción | Auth |
| :--- | :--- | :--- | :--- |
| POST | `/auth/google` | Recibe `{id_token}` de Google y devuelve `{access_token, expires_in, usuario}` más la cookie de refresh | Pública |
| POST | `/auth/login` | `{correo, password}` (solo si DP-01 lo aprueba) | Pública, con límite de intentos |
| POST | `/auth/refresh` | Usa la cookie de refresh y devuelve un nuevo access; rota la cookie | Cookie |
| POST | `/auth/logout` | Revoca la sesión actual y borra la cookie | Bearer |
| GET | `/me` | Usuario actual, con rol, cargo y lista de `permisos` | Bearer |

- Encabezado: `Authorization: Bearer <access_token>`.
- `/auth/refresh` y `/auth/logout` exigen además el encabezado `X-Requested-With: trulab-spa` (mitigación CSRF junto con `SameSite=Strict`).
- Errores: `401` cuando el token falta, es inválido o venció; `403` cuando el usuario está inactivo, el dominio no está permitido o no está registrado.

## 4. Autorización

- Cada endpoint declara un permiso (`require_permission(...)`). La matriz completa está en `SPEC.md` §6 y en `backend/app/core/permissions.py`.
- **Recurso ajeno o inexistente → `404`.** Recurso propio pero sin permiso para la acción → `403`. Acción válida pero en un estado incorrecto → `409`.
- Permisos previstos: `legalizaciones:leer_propias`, `legalizaciones:leer_todas`, `legalizaciones:crear`, `legalizaciones:editar_transferido`, `legalizaciones:legalizar`, `legalizaciones:devolver`, `legalizaciones:pagar`, `gastos:gestionar_propios`, `pagos:leer`, `cargos:leer`, `cargos:gestionar`, `usuarios:gestionar`, `usuarios:asignar_superadmin`, `indicadores:leer`, `proyectos:leer`, `proyectos:gestionar`, `auditoria:leer`.

## 5. Recursos y endpoints previstos

Leyenda de roles: V=VIAJERO, F=FINANCIERO, A=ADMIN, S=SUPERADMIN.

### 5.1 Usuarios

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/usuarios` | A S | Filtros: `q`, `rol`, `cargo_id`, `activo`; paginado |
| POST | `/usuarios` | A S | A no puede crear `SUPERADMIN` |
| GET | `/usuarios/{id}` | A S | |
| PATCH | `/usuarios/{id}` | A S | Cambiar el rol revoca las sesiones y se audita |
| POST | `/usuarios/{id}/desactivar` | A S | No se puede desactivar a uno mismo ni al último SUPERADMIN |
| POST | `/usuarios/{id}/activar` | A S | |

### 5.2 Cargos

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/cargos` | F A S | |
| POST | `/cargos` | A S | El folio lo genera el servidor |
| GET | `/cargos/{id}` | F A S | |
| PATCH | `/cargos/{id}` | A S | |
| DELETE | `/cargos/{id}` | A S | Eliminación lógica; `409` si está en uso |

### 5.3 Proyectos (DP-02)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/proyectos` | V F A S | Solo activos, para el selector del formulario |
| POST / PATCH | `/proyectos`, `/proyectos/{id}` | A S | |

### 5.4 Legalizaciones

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/legalizaciones` | V (propias) F A S (todas) | Filtros: `estado`, `usuario_id` (no V), `proyecto_id`, `desde`, `hasta`, `q` (folio/motivo); orden `-fecha_inicio` |
| POST | `/legalizaciones` | V F A S | Siempre se crea en `BORRADOR` con dueño = usuario actual (S puede indicar `usuario_id`) |
| GET | `/legalizaciones/{id}` | dueño, F A S | Incluye totales, saldo, `acciones_permitidas` y `eventos` |
| PATCH | `/legalizaciones/{id}` | dueño (en BORRADOR o DEVUELTA) | Motivo, fechas, proyecto |
| PATCH | `/legalizaciones/{id}/valor-transferido` | F A S | `{valor_transferido}`; registra el evento `EDITAR_TRANSFERIDO` (DP-04) |
| DELETE | `/legalizaciones/{id}` | dueño (en BORRADOR), S | Eliminación lógica |
| POST | `/legalizaciones/{id}/legalizar` | dueño | Exige RN-06; `409` con la lista de errores si no cumple |
| POST | `/legalizaciones/{id}/devolver` | F A S | `{comentario}` obligatorio |
| POST | `/legalizaciones/{id}/pagar` | F A S | Exige RN-03; `{comentario?}` |
| GET | `/legalizaciones/{id}/eventos` | dueño, F A S | Historial |
| GET | `/legalizaciones/{id}/pdf` | dueño, F A S | `application/pdf`, con `Content-Disposition: attachment; filename="LG-000123.pdf"` |

### 5.5 Gastos (subrecurso)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/legalizaciones/{id}/gastos` | dueño, F A S | |
| POST | `/legalizaciones/{id}/gastos` | dueño (en BORRADOR o DEVUELTA) | `multipart/form-data`: campos más `soporte` opcional |
| PATCH | `/gastos/{gasto_id}` | dueño (en BORRADOR o DEVUELTA) | |
| DELETE | `/gastos/{gasto_id}` | dueño (en BORRADOR o DEVUELTA) | Eliminación lógica |
| PUT | `/gastos/{gasto_id}/soporte` | dueño (en BORRADOR o DEVUELTA) | Reemplaza el soporte (multipart) |
| GET | `/gastos/{gasto_id}/soporte` | dueño, F A S | `{url, expires_at, mime_type, nombre}`: URL firmada de 5 min |

> Las operaciones sobre un gasto concreto usan `/gastos/{id}` (sin anidar) para tener rutas cortas. El servidor valida el acceso a través de su legalización.

### 5.6 Pagos (modelo de lectura)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/pagos` | F A S | Filas de `v_legalizacion_saldos`. Filtros: `estado` (por defecto `LEGALIZADA`), `saldo` (`negativo`/`positivo`/`cero`), `usuario_id`, `proyecto_id`, `desde`, `hasta`; orden por `saldo`, `fecha_inicio` o `folio` |
| GET | `/pagos/resumen` | F A S | Totales del filtro: transferido, gastado, saldo a reembolsar y a reintegrar |

La acción de pagar es `POST /legalizaciones/{id}/pagar`. No se duplica en `/pagos`.

### 5.7 Indicadores

| Método | Ruta | Roles | Respuesta |
| :--- | :--- | :--- | :--- |
| GET | `/indicadores/consumo-por-proyecto?desde&hasta` | F A S | `[{proyecto_id, proyecto, total_gastos, cantidad}]` |
| GET | `/indicadores/estados?desde&hasta&proyecto_id` | F A S | `[{estado, cantidad}]` |
| GET | `/indicadores/kpis?desde&hasta` | F A S | `{total_transferido, total_gastos, saldo_por_reembolsar, saldo_por_reintegrar, pendientes_revision}` (opcional MVP) |

### 5.8 Auditoría (SUPERADMIN, post-MVP en la UI)

`GET /auditoria?entidad&entidad_id&usuario_id&desde&hasta`.

## 6. Convenciones de respuesta

**Recurso individual:** el objeto directamente, sin envoltorio.

```json
{
  "id": "6f1c…",
  "folio": "LG-000123",
  "estado": "LEGALIZADA",
  "usuario": { "id": "…", "nombre_completo": "Ana Pérez" },
  "proyecto": { "id": "…", "codigo": "PRJ-01", "nombre": "Proyecto Norte" },
  "motivo_viaje": "Taller de campo",
  "fecha_inicio": "2026-11-02",
  "fecha_fin": "2026-11-05",
  "valor_transferido": "1500000.00",
  "total_gastos": "1620000.00",
  "saldo": "-120000.00",
  "acciones_permitidas": ["pagar", "devolver", "descargar_pdf"],
  "created_at": "2026-11-01T14:03:00Z",
  "updated_at": "2026-11-06T09:12:00Z"
}
```

**Colección paginada:**

```json
{ "items": [ … ], "total": 134, "page": 1, "size": 20 }
```

- Parámetros: `page` (desde 1) y `size` (por defecto 20, máximo 100), `sort` (`campo` o `-campo`).
- **Dinero:** siempre como *string* decimal con 2 decimales (ADR-012). La UI formatea a `$ 1.500.000`.
- **Fechas:** `DATE` como `AAAA-MM-DD`; marcas de tiempo en ISO 8601 UTC (`Z`). La UI muestra la hora de America/Bogotá.
- **Códigos:** `200` lectura o actualización, `201` creación (con encabezado `Location`), `204` eliminación o logout sin cuerpo.
- Los campos nulos se envían como `null`; no se omiten.

## 7. Manejo de errores (RFC 9457, ADR-014)

`Content-Type: application/problem+json`

```json
{
  "type": "https://trulab.co/errores/regla-negocio",
  "title": "La legalización no cumple los requisitos para legalizar",
  "status": 409,
  "code": "LEGALIZACION_INCOMPLETA",
  "detail": "Hay 2 gastos sin soporte.",
  "errors": [
    { "field": "gastos[3].soporte", "code": "SOPORTE_REQUERIDO", "message": "El gasto 'Taxi' no tiene soporte" }
  ],
  "request_id": "01JC…"
}
```

| Estado | `code` típico | Cuándo |
| :--- | :--- | :--- |
| 400 | `SOLICITUD_INVALIDA` | JSON mal formado |
| 401 | `NO_AUTENTICADO`, `TOKEN_EXPIRADO` | Sin token o con token inválido |
| 403 | `SIN_PERMISO`, `USUARIO_INACTIVO`, `DOMINIO_NO_PERMITIDO` | |
| 404 | `NO_ENCONTRADO` | Recurso inexistente **o ajeno** |
| 409 | `TRANSICION_INVALIDA`, `LEGALIZACION_INCOMPLETA`, `EN_USO`, `DUPLICADO`, `NO_EDITABLE` | Reglas de negocio o de estado |
| 413 | `ARCHIVO_MUY_GRANDE` | Más de 10 MB |
| 415 | `TIPO_ARCHIVO_NO_PERMITIDO` | |
| 422 | `VALIDACION` | Errores de campo de Pydantic, normalizados a `errors[]` |
| 429 | `DEMASIADAS_SOLICITUDES` | Límite de intentos en el login |
| 500 | `ERROR_INTERNO` | Sin detalles internos; solo `request_id` |

- `code` es estable y en `MAYUSCULAS`. La UI traduce por `code`, no por `title`.
- Cada respuesta lleva el encabezado `X-Request-ID`, que también aparece en los logs.

## 8. Seguridad transversal

- CORS limitado al origen de la SPA.
- Límite del cuerpo: 11 MB en las rutas de soporte y 1 MB en el resto.
- Límite de peticiones en `/auth/*`.
- Encabezados de seguridad: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` en el frontend.
- Nunca se aceptan `usuario_id`, `estado` ni `folio` en el cuerpo de creación o edición del VIAJERO; el servidor los fija. Esquemas Pydantic distintos para crear y editar, con `extra="forbid"`.
- Los logs nunca registran tokens, cookies ni contenido de archivos.

## 9. Idempotencia y concurrencia

- Las acciones (`legalizar`, `pagar`, `devolver`) son idempotentes por estado: repetir `pagar` sobre una `PAGADA` devuelve `409 TRANSICION_INVALIDA`, sin efecto doble.
- La transición usa `SELECT … FOR UPDATE` sobre la legalización para evitar dobles pagos concurrentes.
- **Futuro:** `ETag` / `If-Match` para ediciones concurrentes de formularios.
