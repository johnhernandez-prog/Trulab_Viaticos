# Diseño de API — Trulab Viajes

> Diseño del contrato; **no hay endpoints implementados todavía**. La especificación OpenAPI que genere FastAPI será la referencia viva una vez implementado; este documento define las reglas que esa especificación debe cumplir.
> Alineado con las decisiones definitivas DP-01, DP-02, DP-04, DP-07 y DP-13 a DP-18 (`SPEC.md` §17.1).

---

## 1. Principios

1. **REST orientado a recursos**, con sustantivos en plural y en español, iguales a las tablas (`/legalizaciones`, `/gastos`).
2. **Las transiciones de estado son acciones explícitas** (`POST /legalizaciones/{id}/aprobar`), nunca `PATCH estado=...`. Así la máquina de estados (ADR-015, ADR-021) es el único camino y cada acción tiene su propio permiso.
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
| POST | `/auth/google` | Recibe `{id_token}` de Google Workspace y devuelve `{access_token, expires_in, usuario}` más la cookie de refresh. **Único método de acceso** (DP-01 ✅) | Pública, con límite de intentos |
| POST | `/auth/refresh` | Usa la cookie de refresh y devuelve un nuevo access; rota la cookie | Cookie |
| POST | `/auth/logout` | Revoca la sesión actual y borra la cookie | Bearer |
| GET | `/me` | Usuario actual, con rol, cargo, célula y lista de `permisos` | Bearer |

- Encabezado: `Authorization: Bearer <access_token>`.
- `/auth/refresh` y `/auth/logout` exigen además el encabezado `X-Requested-With: trulab-spa` (mitigación CSRF junto con `SameSite=Strict`).
- Errores: `401` cuando el token falta, es inválido o venció; `403` cuando el dominio no es de Trulab, el correo no está en Usuarios, el usuario está inactivo o no tiene rol (RN-12).
- **No existen** endpoints de registro, creación de cuentas, contraseña, recuperación, restablecimiento ni cambio de contraseña (DP-01 ✅, RN-15).

## 4. Autorización

- Cada endpoint declara un permiso (`require_permission(...)`). La matriz completa está en `SPEC.md` §6 y en `backend/app/core/permissions.py`.
- **Recurso ajeno o inexistente → `404`.** Recurso visible pero sin permiso para la acción → `403`. Acción válida pero en un estado incorrecto → `409`.
- Permisos previstos:

| Permiso | Roles |
| :--- | :--- |
| `legalizaciones:leer_propias`, `legalizaciones:crear`, `gastos:gestionar_propios` | V F A S |
| `legalizaciones:leer_todas`, `comprobantes:leer_todos` | F A S |
| `legalizaciones:aprobar`, `legalizaciones:rechazar`, `legalizaciones:devolver` (estado operativo, DP-13 ✅, DP-18 ✅) | **A S** |
| `legalizaciones:registrar_valor_transferido` (DP-04 ✅), `legalizaciones:cambiar_estado_financiero` (DP-13 ✅) | **F S** |
| `pagos:leer` | F A S (A solo lectura) |
| `cargos:leer` | F A S |
| `cargos:gestionar`, `usuarios:gestionar` | A S |
| `usuarios:asignar_superadmin`, `catalogos:gestionar` (DP-14 ✅), `auditoria:leer` | S |
| `catalogos:leer` | V F A S |
| `indicadores:leer` | F A S |

- **Sin autoaprobación** (RN-27, regla definitiva): las acciones `aprobar`, `rechazar`, `devolver`, `estado-financiero` y `valor-transferido` sobre una legalización **creada por el propio usuario** responden `403 SIN_PERMISO` para ADMIN y FINANCIERO. Solo SUPERADMIN puede ejecutarlas (soporte, contingencia, administración o pruebas controladas) y cada uso se registra en `auditoria`.

## 5. Recursos y endpoints previstos

Leyenda de roles: V=VIAJERO, F=FINANCIERO, A=ADMIN, S=SUPERADMIN.

### 5.1 Usuarios

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/usuarios` | A S | Filtros: `q`, `rol`, `cargo_id`, `celula_id`, `activo`; paginado |
| POST | `/usuarios` | A S | `celula_id` debe ser un valor activo del catálogo. A no puede crear `SUPERADMIN` |
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

### 5.3 Catálogos (tablas maestras, DP-14 ✅, ADR-022)

`{tipo}` ∈ `proyectos`, `rubros`, `celulas`.

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/catalogos` | V F A S | `{proyectos: [{id, nombre}], rubros: [...], celulas: [...]}` con los valores **activos**, para los selectores |
| GET | `/catalogos/{tipo}` | S | Todos los valores (activos e inactivos) con `uso` (cantidad de registros que los referencian) |
| POST | `/catalogos/{tipo}` | S | `{nombre, orden?}`. `409 DUPLICADO` si el nombre ya existe (sin distinguir mayúsculas) |
| PATCH | `/catalogos/{tipo}/{id}` | S | Renombrar u ordenar. Se audita |
| POST | `/catalogos/{tipo}/{id}/desactivar` | S | El valor deja de ofrecerse; los registros existentes lo conservan (RN-24) |
| POST | `/catalogos/{tipo}/{id}/activar` | S | |

No hay `DELETE`: los valores en uso no se eliminan.

### 5.4 Legalizaciones

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/legalizaciones` | V (propias) F A S (todas) | Filtros: `estado`, `estado_financiero`, `devuelta` (bool), `usuario_id` (no V), `proyecto_id` (con algún gasto de ese proyecto), `desde`, `hasta` (sobre `fecha_legalizacion`; es una lista operativa, no un indicador), `q` (folio/motivo); orden `-fecha_legalizacion` |
| POST | `/legalizaciones` | V F A S | `{motivo_viaje, recursos_propios}` (DP-17 ✅: lo indica el viajero al crear). Se crea con `estado = PENDIENTE` y `estado_financiero = PENDIENTE`, dueño = usuario actual (S puede indicar `usuario_id`). Los `colaborador_*` se copian del usuario (RN-17) |
| GET | `/legalizaciones/{id}` | dueño, F A S | Incluye `estado`, `estado_financiero`, `devuelta_at`, `valor_asignado`, `recursos_propios`, `valor_transferido`, totales, saldo, `acciones_permitidas` y `eventos` |
| PATCH | `/legalizaciones/{id}` | dueño (con `estado = PENDIENTE`) | `motivo_viaje`; `recursos_propios` solo si además `estado_financiero = PENDIENTE` (supuesto S-05) |
| PATCH | `/legalizaciones/{id}/valor-transferido` | **F S** (DP-04 ✅) | `{valor_asignado, comentario?}`. El servidor recalcula `valor_transferido` (RN-14) y registra `EDITAR_VALOR_ASIGNADO`. Con `recursos_propios = true` el valor se guarda pero el transferido sigue en 0. ADMIN y VIAJERO → 403 |
| DELETE | `/legalizaciones/{id}` | dueño, S | Solo con `estado = PENDIENTE` y `estado_financiero = PENDIENTE` (RN-09); eliminación lógica |
| POST | `/legalizaciones/{id}/aprobar` | **A S** | `PENDIENTE → APROBADO`. Exige RN-06 (≥1 gasto, todos con soporte o archivo); `409 LEGALIZACION_INCOMPLETA` con la lista de errores si no cumple. `{comentario?}` |
| POST | `/legalizaciones/{id}/rechazar` | **A S** | `PENDIENTE → RECHAZADO` (final). `{comentario}` obligatorio |
| POST | `/legalizaciones/{id}/devolver` | **A S** | `PENDIENTE` o `APROBADO` → `PENDIENTE`, fija `devuelta_at`. `{comentario}` obligatorio. Desde `APROBADO` solo si `estado_financiero` ∉ {`PAGADO`, `PROCESADO`} (RN-20) |
| POST | `/legalizaciones/{id}/estado-financiero` | **F S** | `{estado_financiero, comentario?}` con un valor de `ESTADOS_FINANCIEROS`. `PAGADO` y `PROCESADO` exigen RN-03 (`APROBADO` + comprobantes). Registra `CAMBIAR_ESTADO_FINANCIERO`. ADMIN → 403 (DP-18 ✅) |
| GET | `/legalizaciones/{id}/eventos` | dueño, F A S | Historial de ambas dimensiones |
| GET | `/legalizaciones/{id}/pdf` | dueño, F A S | `application/pdf`, con `Content-Disposition: attachment; filename="LG-000123.pdf"` |

`estado-financiero` recibe el valor destino porque `Estado_P` es un enum que FINANCIERO elige (supuesto S-03), pero sigue siendo una **acción** que pasa por `transicionar()`, con permiso, validaciones e historial; no es un `PATCH` genérico.

### 5.5 Gastos (subrecurso)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/legalizaciones/{id}/gastos` | dueño, F A S | Cada gasto incluye `tiene_comprobante` (RN-21) |
| POST | `/legalizaciones/{id}/gastos` | dueño (con `estado = PENDIENTE`) | `multipart/form-data`: `fecha_factura`, `rubro_id`, `proyecto_id` (valores activos de `/catalogos`), `concepto`, `cc_nit?`, `empresa?`, `valor`, `observaciones?`, más `soporte?` (**imagen**) y `archivo?` (**PDF**) (DP-15 ✅) |
| PATCH | `/gastos/{gasto_id}` | dueño (con `estado = PENDIENTE`) | Mismos campos (sin archivos) |
| DELETE | `/gastos/{gasto_id}` | dueño (con `estado = PENDIENTE`) | Eliminación lógica |
| PUT | `/gastos/{gasto_id}/{tipo}` | dueño (con `estado = PENDIENTE`) | `tipo` ∈ `soporte` (solo imagen), `archivo` (solo PDF). Reemplaza el archivo (multipart) |
| DELETE | `/gastos/{gasto_id}/{tipo}` | dueño (con `estado = PENDIENTE`) | Quita el adjunto; el gasto puede quedar sin comprobante (bloquea Aprobar) |
| GET | `/gastos/{gasto_id}/{tipo}` | dueño, F A S | `{url, expires_at, mime_type, nombre}`: URL firmada de 5 min |

- `rubro_id` o `proyecto_id` inexistente o inactivo → `422` con `code: VALOR_NO_PERMITIDO`.
- Un PDF en `soporte` o una imagen en `archivo` → `415 TIPO_ARCHIVO_NO_PERMITIDO` (RN-13).

> Las operaciones sobre un gasto concreto usan `/gastos/{id}` (sin anidar) para tener rutas cortas. El servidor valida el acceso a través de su legalización.

### 5.6 Pagos (modelo de lectura)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/pagos` | F A S (A solo lectura) | Filas de `v_legalizacion_saldos`. Filtros: `estado` (por defecto `APROBADO`), `estado_financiero` (por defecto `PENDIENTE,TRANSFERIDO`), `saldo` (`negativo`/`positivo`/`cero`), `recursos_propios`, `usuario_id`, `proyecto_id`, `desde`, `hasta` (sobre `fecha_legalizacion`); orden por `saldo`, `fecha_legalizacion` o `folio` |
| GET | `/pagos/resumen` | F A S | Totales del filtro: transferido, gastado, saldo a reembolsar y a reintegrar |

El cambio de estado financiero es `POST /legalizaciones/{id}/estado-financiero`. No se duplica en `/pagos`.

### 5.7 Indicadores (DP-16 ✅: fecha de factura)

`desde`/`hasta` reemplazan la tabla `Segmentador` de AppSheet (ADR-018) y se aplican **siempre** como `gastos.fecha_factura BETWEEN desde AND hasta` (ADR-024).

| Método | Ruta | Roles | Respuesta |
| :--- | :--- | :--- | :--- |
| GET | `/indicadores/consumo-por-proyecto?desde&hasta` | F A S | `[{proyecto_id, proyecto, total_gastos, cantidad_gastos}]`, agrupado por proyecto del gasto (DP-02 ✅) |
| GET | `/indicadores/estados?desde&hasta&proyecto_id` | F A S | `[{estado, cantidad}]` sobre el estado operativo (= `Estado legalizacion`), contando legalizaciones con algún gasto en el rango (supuesto S-07) |
| GET | `/indicadores/kpis?desde&hasta` | F A S | `{total_transferido, total_gastos, saldo_por_reembolsar, saldo_por_reintegrar, pendientes_aprobacion, pendientes_pago}` (opcional MVP) |

### 5.8 Auditoría (SUPERADMIN, post-MVP en la UI)

`GET /auditoria?entidad&entidad_id&usuario_id&desde&hasta`.

## 6. Convenciones de respuesta

**Recurso individual:** el objeto directamente, sin envoltorio.

```json
{
  "id": "6f1c…",
  "folio": "LG-000123",
  "estado": "APROBADO",
  "estado_financiero": "TRANSFERIDO",
  "devuelta_at": null,
  "usuario": { "id": "…", "nombre_completo": "Ana Pérez" },
  "colaborador": { "nombre": "Ana Pérez", "cargo": "Profesional de campo", "celula": "Campo" },
  "motivo_viaje": "Taller de campo",
  "fecha_legalizacion": "2026-11-06",
  "recursos_propios": false,
  "valor_asignado": "1500000.00",
  "valor_transferido": "1500000.00",
  "proyectos": ["Conexión Agro", "Rutas PDET 3"],
  "total_gastos": "1620000.00",
  "saldo": "-120000.00",
  "acciones_permitidas": ["cambiar_estado_financiero", "descargar_pdf"],
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
- **Estados:** códigos en mayúsculas sin emojis (`PENDIENTE`); la UI los traduce a etiquetas.
- **Códigos:** `200` lectura o actualización, `201` creación (con encabezado `Location`), `204` eliminación o logout sin cuerpo.
- Los campos nulos se envían como `null`; no se omiten.

## 7. Manejo de errores (RFC 9457, ADR-014)

`Content-Type: application/problem+json`

```json
{
  "type": "https://trulab.co/errores/regla-negocio",
  "title": "La legalización no cumple los requisitos para aprobar",
  "status": 409,
  "code": "LEGALIZACION_INCOMPLETA",
  "detail": "Hay 2 gastos sin soporte ni archivo.",
  "errors": [
    { "field": "gastos[3]", "code": "COMPROBANTE_REQUERIDO", "message": "El gasto 'Taxi' no tiene soporte ni archivo" }
  ],
  "request_id": "01JC…"
}
```

| Estado | `code` típico | Cuándo |
| :--- | :--- | :--- |
| 400 | `SOLICITUD_INVALIDA` | JSON mal formado |
| 401 | `NO_AUTENTICADO`, `TOKEN_EXPIRADO` | Sin token o con token inválido |
| 403 | `SIN_PERMISO`, `USUARIO_INACTIVO`, `USUARIO_NO_REGISTRADO`, `DOMINIO_NO_PERMITIDO` | Incluye la autoaprobación (RN-27) |
| 404 | `NO_ENCONTRADO` | Recurso inexistente **o ajeno** |
| 409 | `TRANSICION_INVALIDA`, `LEGALIZACION_INCOMPLETA`, `REQUIERE_APROBACION`, `EN_USO`, `DUPLICADO`, `NO_EDITABLE` | Reglas de negocio o de estado (`REQUIERE_APROBACION`: `PAGADO`/`PROCESADO` sin `APROBADO`) |
| 413 | `ARCHIVO_MUY_GRANDE` | Más de 10 MB |
| 415 | `TIPO_ARCHIVO_NO_PERMITIDO` | Tipo no admitido, o imagen/PDF en el campo equivocado |
| 422 | `VALIDACION`, `VALOR_NO_PERMITIDO`, `COMENTARIO_REQUERIDO` | Errores de campo de Pydantic, normalizados a `errors[]`; valor de catálogo inexistente o inactivo; devolver o rechazar sin comentario |
| 429 | `DEMASIADAS_SOLICITUDES` | Límite de peticiones en `/auth/google` |
| 500 | `ERROR_INTERNO` | Sin detalles internos; solo `request_id` |

- `code` es estable y en `MAYUSCULAS`. La UI traduce por `code`, no por `title`.
- Cada respuesta lleva el encabezado `X-Request-ID`, que también aparece en los logs.

## 8. Seguridad transversal

- CORS limitado al origen de la SPA.
- Límite del cuerpo: 11 MB en las rutas de adjuntos y 1 MB en el resto.
- Límite de peticiones en `/auth/*`.
- Encabezados de seguridad: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` en el frontend.
- Nunca se aceptan `usuario_id`, `estado`, `estado_financiero`, `folio`, `colaborador_*`, `valor_asignado` ni `valor_transferido` en el cuerpo de creación o edición de la legalización; el servidor los fija o los cambia solo por sus acciones. `valor_transferido` no se acepta en **ningún** endpoint, porque siempre se calcula (RN-14). La cédula no aparece en los listados; solo en el detalle, para los roles autorizados (RNF-09). Esquemas Pydantic distintos para crear y editar, con `extra="forbid"`.
- Los logs nunca registran tokens, cookies ni contenido de archivos.

## 9. Idempotencia y concurrencia

- Las acciones (`aprobar`, `rechazar`, `devolver`, `estado-financiero`) son idempotentes por estado: repetir `aprobar` sobre una `APROBADO` devuelve `409 TRANSICION_INVALIDA`, sin efecto doble; fijar el mismo `estado_financiero` que ya tiene también responde 409.
- La transición usa `SELECT … FOR UPDATE` sobre la legalización para evitar, por ejemplo, que ADMIN devuelva mientras FINANCIERO marca `PAGADO`.
- **Futuro:** `ETag` / `If-Match` para ediciones concurrentes de formularios.
