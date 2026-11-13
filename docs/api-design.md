# Diseño de API — Trulab Viajes

> Diseño del contrato. Implementado: `GET /api/v1/health` y la **autenticación de §3** (S1-08). La especificación OpenAPI que genere FastAPI será la referencia viva; este documento define las reglas que debe cumplir.
> Alineado con `SPEC.md` v0.4: DP-01 actualizada (acceso híbrido, ADR-027), DP-19 (entidad `viaticos`, ADR-029) y DP-20 (tarifas, ADR-030).

---

## 1. Principios

1. **REST orientado a recursos**, sustantivos en plural y en español, iguales a las tablas (`/viaticos`, `/gastos`).
2. **Las transiciones son acciones explícitas** (`POST /viaticos/{id}/aprobar`), nunca `PATCH estado=...`. La máquina de estados (ADR-015, ADR-021) es el único camino y cada acción tiene su permiso.
3. **El backend decide** lo que el usuario ve y hace; el detalle incluye `acciones_permitidas`.
4. **JSON en `snake_case`.** Tipos del frontend generados desde OpenAPI.
5. **Contrato tipado:** cada request y response es un esquema Pydantic con `extra="forbid"` en las entradas.
6. **Los importes tarifarios los calcula el servidor.** El cliente nunca envía tarifas, subtotales ni `presupuesto_solicitado` (RN-29).

## 2. Base y versionamiento

- URL base: `/api/v1`. Solo cambia la versión mayor ante cambios incompatibles.
- Al deprecar: encabezados `Deprecation: true` y `Sunset: <fecha>`.
- `GET /api/v1/health` devuelve `{status, version, db}` sin autenticación (implementado).

## 3. Autenticación (ADR-027)

Acceso **híbrido**: usuario y contraseña para `VIAJERO`, `ADMIN` y `FINANCIERO`; Google OAuth `@trulab.co` **exclusivamente** para `SUPERADMIN`.

| Método | Ruta | Descripción | Auth |
| :--- | :--- | :--- | :--- |
| POST | `/auth/login` | `{username, password}` → `{access_token, expires_in, usuario, debe_cambiar_password}` + cookie de refresh. **Solo operativos**: un `SUPERADMIN` no puede usar este endpoint | Pública, con límite de intentos |
| POST | `/auth/google` | `{id_token}` de Google Workspace → igual respuesta. **Restringido a `SUPERADMIN`** (RN-12) | Pública, con límite de intentos |
| POST | `/auth/password/forgot` | `{identificador}` (username o correo). **Siempre** `202` con el mismo mensaje, exista o no el usuario. Si existe, es operativo y está activo, envía el correo con el enlace de un solo uso | Pública, con límite estricto |
| POST | `/auth/password/reset` | `{token, nueva_password}`. Valida el token (existe, no usado, no vencido), fija la contraseña, marca `used_at`, quita `debe_cambiar_password`, revoca **todas** las sesiones | Pública, con límite |
| POST | `/auth/password/change` | `{password_actual, nueva_password}`. Cambio voluntario o **obligatorio** del primer acceso; revoca las demás sesiones y emite nueva | Bearer (operativos) |
| POST | `/auth/refresh` | Cookie de refresh → nuevo access; rota la cookie | Cookie |
| POST | `/auth/logout` | Revoca la sesión actual y borra la cookie | Bearer |
| GET | `/me` | Usuario actual: rol, cargo, célula, `es_prestador_servicios`, `debe_cambiar_password` y `permisos` (lista ordenada de la matriz RBAC del rol; **vacía** mientras haya un cambio de contraseña pendiente). La UI solo la usa para mostrar u ocultar | Bearer |
| POST | `/auth/dev/login` | `{correo}` → sesión de un **SUPERADMIN** sin pasar por Google. **Solo existe con `ENV=local`** (en otro entorno la ruta no se registra: 404); mientras no haya OAuth Client ID (R1.1) | Pública, solo local |

- Encabezado: `Authorization: Bearer <access_token>`. `/auth/refresh` y `/auth/logout` exigen `X-Requested-With: trulab-spa` (junto con `SameSite=Strict`).
- **Cambio obligatorio de contraseña:** si `debe_cambiar_password = true`, el access token lleva el claim `pwd_change` y **todos** los endpoints, salvo `/auth/password/change`, `/auth/logout` y `/me`, responden `403 CAMBIO_PASSWORD_REQUERIDO`.
- **Política de contraseña:** mínimo 12 caracteres, no igual al username ni al correo, no estar en una lista de contraseñas comunes; máximo 128. Error `422 PASSWORD_DEBIL` con los motivos.
- **Sin filtrar existencia:** `login` responde `401 CREDENCIALES_INVALIDAS` tanto si el usuario no existe, como si la contraseña es incorrecta, está inactivo o es SUPERADMIN, con tiempo de respuesta homogéneo (verificación Argon2id ficticia). El motivo real solo queda en `auditoria` (`LOGIN_FALLIDO`).
- **Bloqueo:** tras 5 fallos consecutivos de un usuario (`LOGIN_MAX_FAILED_ATTEMPTS`) se bloquea 15 minutos (`LOGIN_LOCKOUT_MINUTES`, S-14); mientras dure, el login responde `429 CUENTA_BLOQUEADA_TEMPORALMENTE` aun con la contraseña correcta.
- **Límite por IP** (en memoria del proceso; con varias instancias se pasa a WAF o a un contador compartido): `login` y `google` 10/min, `password/forgot` 5 cada 15 min, `password/reset` 10 cada 15 min → `429 DEMASIADAS_SOLICITUDES`.
- **Refresh rotativo con detección de reuso:** cada `/auth/refresh` revoca la sesión usada y emite otra (el access token de la anterior deja de valer). Presentar un refresh **ya rotado** revoca **todas** las sesiones del usuario y audita `ACCESO_DENEGADO` (`REFRESH_REUTILIZADO`).
- **Cambio de contraseña** (`change`) y **restablecimiento** (`reset`) revocan todas las sesiones; `change` emite una sesión nueva en la misma respuesta. El correo de `forgot` se envía en segundo plano para que el tiempo de respuesta no revele si la cuenta existe.
- **`/auth/google`:** valida firma, `aud`, `exp`, `email_verified`, `hd` = `GOOGLE_WORKSPACE_DOMAIN`, correo registrado, activo y **rol `SUPERADMIN`**. Si el correo existe pero el rol es operativo → `403 METODO_ACCESO_NO_PERMITIDO` ("Use su usuario y contraseña") y `ACCESO_DENEGADO`.
- Errores: `401` token ausente/inválido/vencido o credenciales inválidas; `403` dominio no permitido, usuario no registrado/inactivo/sin rol, método no permitido para el rol (RN-12).
- Auditoría: `LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `PASSWORD_CAMBIADA`, `PASSWORD_RECUPERACION_SOLICITADA`, `ACCESO_DENEGADO`. Nunca se registran contraseñas, hashes ni tokens.
- **Login de desarrollo:** solo con `ENV=local`, mientras llega el OAuth Client ID (R1.1); una prueba en CI verifica que está desactivado fuera de local. Para operativos no hace falta: el login normal funciona en local con el correo escrito en el log.

## 4. Autorización

- Cada endpoint declara un permiso (`require_permission(Permiso.X)`, S1-09). Matriz en `SPEC.md` §6 y `backend/app/core/permissions.py` (enum `Permiso`, `MATRIZ` inmutable); la prueba `tests/test_permisos.py` recorre todas las celdas rol × permiso, también por HTTP.
- `require_permission` incluye `UsuarioActual` (sesión vigente, sin cambio de contraseña pendiente) y lee el rol **de la BD**: sin token → `401`, sin permiso → `403 SIN_PERMISO` sin revelar cuál faltó (el detalle va al log `permiso_denegado`).
- El permiso solo dice qué acción puede intentar el rol; el alcance por dueño (`404`), el estado (`409`) y RN-27 los aplica el service.
- **Recurso ajeno o inexistente → `404`.** Visible pero sin permiso → `403`. Estado/etapa incorrectos → `409`.

| Permiso | Roles |
| :--- | :--- |
| `viaticos:leer_propios`, `viaticos:crear`, `viaticos:calcular_presupuesto`, `gastos:gestionar_propios`, `viaticos:habilitar_legalizacion` (propios) | V F A S |
| `viaticos:leer_todos`, `comprobantes:leer_todos` | F A S |
| `viaticos:aprobar`, `viaticos:rechazar`, `viaticos:devolver`, `viaticos:gestionar_tiquetes` | **A S** |
| `viaticos:registrar_valor_asignado`, `viaticos:cambiar_estado_financiero` | **F S** |
| `pagos:leer` | F A S (A solo lectura) |
| `cargos:leer` | F A S |
| `cargos:gestionar`, `usuarios:gestionar_operativos` | A S |
| `usuarios:gestionar_superadmin`, `catalogos:gestionar`, `tarifas:gestionar`, `auditoria:leer` | S |
| `catalogos:leer` | V F A S |
| `tarifas:leer` | F A S (los demás, solo vía preview) |
| `indicadores:leer` | F A S |

- **Sin autoaprobación** (RN-27): `aprobar`, `rechazar`, `devolver`, `gestionar-tiquetes`, `estado-financiero` y `valor-asignado` sobre un viático **creado por el propio usuario**, en **cualquier etapa**, responden `403 AUTOAPROBACION_NO_PERMITIDA` para ADMIN y FINANCIERO (S2-05 y S2-07), con un `detail` específico por acción. Solo SUPERADMIN puede, y cada uso se audita (`AUTOAPROBACION_SUPERADMIN`, con `datos.accion` desde S2-07).

## 5. Recursos y endpoints previstos

Leyenda: V=VIAJERO, F=FINANCIERO, A=ADMIN, S=SUPERADMIN.

### 5.1 Usuarios

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/usuarios` | A S | Filtros: `q`, `rol`, `cargo_id`, `celula_id`, `es_prestador_servicios`, `activo`; paginado. La cédula y la fecha de nacimiento no salen en el listado |
| POST | `/usuarios` | A S | Operativos: `{nombre_completo, correo, username, rol, cargo_id?, celula_id?, cedula?, es_prestador_servicios, fecha_nacimiento?}`. El servidor genera una **contraseña temporal** (`debe_cambiar_password = true`) y la envía **por correo**; ADMIN no la ve (S-13). **`rol = SUPERADMIN`** solo por S: exige correo del dominio `@trulab.co`, no lleva username ni contraseña, audita `SUPERADMIN_ASIGNADO`. ADMIN que intenta `SUPERADMIN` → `403 SIN_PERMISO` |
| GET | `/usuarios/{id}` | A S | |
| PATCH | `/usuarios/{id}` | A S | Cambiar el rol revoca sesiones y se audita. **Promover a `SUPERADMIN`** (solo S): valida correo `@trulab.co`, borra username/contraseña, audita `SUPERADMIN_ASIGNADO`. **Degradar un SUPERADMIN** (solo S): exige `username` y genera contraseña temporal; `409 ULTIMO_SUPERADMIN` si es el último activo. ADMIN no puede modificar a un SUPERADMIN (`403`) |
| POST | `/usuarios/{id}/desactivar` | A S | No a uno mismo (`409 ACCION_SOBRE_SI_MISMO`); idempotente; `409 ULTIMO_SUPERADMIN` si es el último SUPERADMIN activo; desactivar un SUPERADMIN solo S. Revoca sesiones |
| POST | `/usuarios/{id}/activar` | A S | |
| POST | `/usuarios/{id}/restablecer-password` | A S | Solo operativos: genera una contraseña temporal nueva, la envía por correo, `debe_cambiar_password = true`, revoca sesiones, audita `PASSWORD_CAMBIADA`. Sobre un SUPERADMIN → `409 SUPERADMIN_SIN_PASSWORD` |
| GET/PUT/DELETE | `/me/firma` | V F A S | **Implementado en S2-06.** `PUT {archivo_id}`: guarda como firma del perfil un archivo **propio** subido antes con `POST /archivos` y `proposito = FIRMA` (otro propósito → `415`; ajeno o inexistente → `422`). `GET` → `{archivo_id, url, expires_at, mime_type, nombre}` (URL temporal) o `404` si no tiene. `DELETE` → `204` (el archivo no se borra: es inmutable) (RN-32) |
| PATCH | `/me` | V F A S | Solo `fecha_nacimiento` (RN-31) |

**Implementado en S1-10.** Detalles del contrato:

- Listado paginado (`page`, `size`, `sort` ∈ `nombre_completo`, `-nombre_completo`, `created_at`, `-created_at`); `q` busca en nombre, correo y usuario. Cada fila trae `cargo`/`celula` como `{id, nombre}`, `activo`, `bloqueado` y `debe_cambiar_password`; nunca `password_hash` ni `google_sub`. El detalle agrega `cedula`, `fecha_nacimiento` y `updated_at`.
- `correo` y `username` se normalizan a minúsculas; únicos sin distinguir mayúsculas, igual que `cedula` → `409 DUPLICADO` con `errors[].field`. `cargo_id` eliminado o `celula_id` inactiva → `422 VALOR_NO_PERMITIDO`. Enviar `password`, `debe_cambiar_password`, `google_sub` o `activo` → `422 VALIDACION`.
- SUPERADMIN con correo de otro dominio o con `username` → `422 VALOR_NO_PERMITIDO` (`field`: `correo` / `username`). Cambiar el correo de un SUPERADMIN borra `google_sub` (se vuelve a fijar en su siguiente login con Google).
- La contraseña temporal solo viaja en el correo (en segundo plano, después del commit); la respuesta nunca la incluye. `restablecer-password` responde `{detail}`.
- Auditoría: `USUARIO_CREAR`, `USUARIO_EDITAR` (antes/después solo de lo que cambió; cédula enmascarada, fecha de nacimiento solo como "[dato personal]"), `ROL_CAMBIAR`, `SUPERADMIN_ASIGNADO` (`via`: `alta`/`promocion`), `USUARIO_ACTIVAR`/`USUARIO_DESACTIVAR` y `PASSWORD_CAMBIADA` (`motivo: RESTABLECIDA_POR_ADMIN`), siempre con el actor, la IP y el user agent.

### 5.2 Cargos

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/cargos` | F A S | |
| POST | `/cargos` | A S | Folio `CA-` generado |
| GET | `/cargos/{id}` | F A S | |
| PATCH | `/cargos/{id}` | A S | |
| DELETE | `/cargos/{id}` | A S | Lógico (`204`); `409 EN_USO` si algún usuario, activo o no, lo tiene |

**Implementado en S1-10:** listado paginado con `q` (nombre o folio) y `sort` ∈ `nombre`, `folio`, `created_at` (con `-` para descendente); nombre único sin distinguir mayúsculas entre los no eliminados (`409 DUPLICADO`), y se puede reutilizar tras eliminar. Auditoría `CARGO_CREAR`, `CARGO_EDITAR` (antes/después) y `CARGO_ELIMINAR`.

### 5.3 Catálogos (DP-14 ✅, ADR-022) y tarifas (DP-20 ✅, ADR-030)

`{tipo}` ∈ `proyectos`, `rubros`, `celulas`.

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/catalogos` | V F A S | `{proyectos: [{id, nombre, codigo, exige_formato_prestador}], rubros: [...], celulas: [...], ciudades: [...]}` solo **activos**, para los selectores. La opción **"Otro"** de proyecto **no** viene en la lista: la UI la agrega siempre al final (ADR-031). `ciudades` = destinos con tarifa activa para el tipo de vinculación del usuario |
| GET | `/catalogos/{tipo}` | S | Todos, con `uso` |
| POST | `/catalogos/{tipo}` | S | `{nombre, orden?}`; para `proyectos` también `{codigo?, exige_formato_prestador?}`. `409 DUPLICADO` |
| PATCH | `/catalogos/{tipo}/{id}` | S | Renombrar, ordenar; auditado |
| POST | `/catalogos/{tipo}/{id}/desactivar` · `/activar` | S | RN-24 |
| GET | `/catalogos/tarifas-viaticos` | F A S | Filtros: `ciudad`, `es_prestador_servicios`, `activo`; paginado |
| POST | `/catalogos/tarifas-viaticos` | S | `{ciudad, es_prestador_servicios, vr_alimentacion, otros_gastos, transporte_aeropuerto, transporte_intermunicipal, trans_interno_dia_1, trans_interno_varios_dias, orden?}` (dinero como string). `409 DUPLICADO` por (ciudad, tipo). Audita `TARIFA_CREAR` |
| GET | `/catalogos/tarifas-viaticos/{id}` | F A S | |
| PATCH | `/catalogos/tarifas-viaticos/{id}` | S | Valores y orden. **No** afecta solicitudes existentes (instantánea). Audita `TARIFA_EDITAR` |
| POST | `/catalogos/tarifas-viaticos/{id}/desactivar` · `/activar` | S | Sin `DELETE` |

> `tarifas-viaticos` es un literal fijo y se registra antes que la ruta `/{tipo}` para evitar ambigüedad.

**Implementado en S2-01.** Detalles del contrato:

- `GET /catalogos` (`catalogos:leer`, V F A S): combina los tres catálogos (solo filas activas,
  ordenadas por `orden` y luego por nombre) y `ciudades` (tarifas activas del tipo de vinculación
  —`es_prestador_servicios`— del usuario autenticado). `rubros`/`celulas` siempre traen `codigo` y
  `exige_formato_prestador` en `null`.
- `GET /catalogos/{tipo}` (`catalogos:gestionar`, solo S): todas las filas (activas e inactivas),
  con `uso` (entero, informativo). El `uso` de `proyectos` suma `viaticos.proyecto_id` +
  `gastos.proyecto_id` (sin los eliminados lógicamente); el de `rubros`, `gastos.rubro_id`; el de
  `celulas`, **todos** los usuarios con esa célula, activos o no (igual que `cargos`). `{tipo}`
  fuera de `proyectos`/`rubros`/`celulas` → `422 VALIDACION` (FastAPI valida el `Literal`).
- `POST`/`PATCH /catalogos/{tipo}`: `codigo` y `exige_formato_prestador` solo se aceptan para
  `proyectos`; enviarlos para `rubros`/`celulas` → `422 VALOR_NO_PERMITIDO` con el campo. `nombre`
  único sin distinguir mayúsculas entre **todas** las filas (no hay borrado lógico que libere el
  nombre); `codigo` único entre los no nulos. `PATCH` no permite dejar `nombre` en `null`.
- **Sin `DELETE`** en ningún catálogo ni en tarifas (RN-24): `desactivar`/`activar` son
  **idempotentes** (sin cambios ni auditoría si ya estaban en ese estado) y **no** verifican el
  `uso`: desactivar algo en uso es válido (solo deja de verse en los selectores); por eso no hay
  `409 EN_USO` aquí, a diferencia de `/cargos`.
- `POST`/`PATCH /catalogos/tarifas-viaticos`: los 6 montos aceptan número o string en la entrada
  (`Dinero`, ADR-012) y **siempre** salen como string (`"150000.00"`, con la precisión de
  `NUMERIC(14,2)`); `< 0` → `422 VALIDACION`. `PATCH` **no** acepta `ciudad` ni
  `es_prestador_servicios` (identifican la fila); enviarlos → `422 VALIDACION` (`extra="forbid"`).
  `409 DUPLICADO` por `(lower(ciudad), es_prestador_servicios)`.
- Auditoría: `CATALOGO_CREAR`, `CATALOGO_EDITAR` (antes/después), `CATALOGO_DESACTIVAR`,
  `CATALOGO_ACTIVAR` (entidad `catalogos`, con `tipo` en `datos`); `TARIFA_CREAR`, `TARIFA_EDITAR`
  (antes/después), `TARIFA_DESACTIVAR`, `TARIFA_ACTIVAR` (entidad `tarifas_viaticos`), siempre con
  el actor, la IP y el user agent.

### 5.4 Viáticos (entidad unificada, ADR-029)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/viaticos` | V (propios) F A S (todos) | Filtros: `modalidad`, `etapa`, `estado`, `estado_financiero`, `usuario_id` (F A S), `proyecto_id`, `desde`, `hasta` (sobre `fecha_legalizacion`), `q` (folio/motivo); orden fijo `-created_at` |
| POST | `/viaticos` | V F A S | `{modalidad, motivo_viaje, …}`. **`CON_SOLICITUD`:** `{proyecto_id | proyecto_otro, lider_proyecto, empresa?, requiere_tiquete, requiere_gastos_viaje, comentarios?, trayectos: [{orden, ciudad_origen, ciudad_destino, fecha_ida, fecha_regreso, requiere_hospedaje, dias_estadia}]}` (1–5). El servidor calcula las tarifas, el `presupuesto_solicitado` y las instantáneas; **rechaza** importes enviados por el cliente. Crea en etapa `SOLICITUD`, `estado = PENDIENTE`. **`LEGALIZACION_DIRECTA`:** `{motivo_viaje, recursos_propios}`; crea en etapa `LEGALIZACION`. Los `colaborador_*` se copian del usuario (RN-17). Folio `VT-` |
| POST | `/viaticos/calcular-presupuesto` | V F A S | **Vista previa sin guardar** (RN-29): `{proyecto_id | proyecto_otro, requiere_gastos_viaje, trayectos: […]}` → `{aplica, motivo_no_aplica?, trayectos: [{subtotal_estadia, transporte_aeropuerto, transporte_intermunicipal, …}], presupuesto_solicitado, exige_formato_prestador}`. Usa `es_prestador_servicios` del usuario autenticado. Es la misma función que usa `POST /viaticos`, por lo que la UI y el guardado coinciden |
| GET | `/viaticos/{id}` | dueño, F A S | Incluye modalidad, etapa, `estado`, `estado_financiero`, solicitud y `trayectos`, `valor_asignado`, `valor_transferido`, `presupuesto_solicitado`, totales, saldo, `acciones_permitidas` y `eventos` |
| PATCH | `/viaticos/{id}` | dueño, S (`estado = PENDIENTE` y `estado_financiero = PENDIENTE`) | En etapa `SOLICITUD`: campos de la solicitud y `trayectos` completos (se recalcula cuando cambia el proyecto, `requiere_gastos_viaje` o los trayectos). En etapa `LEGALIZACION`: `motivo_viaje`, `comentarios`; `recursos_propios` solo en `LEGALIZACION_DIRECTA` (S-05) |
| PUT/DELETE | `/viaticos/{id}/firma` · `/formato-adjunto` | dueño (`estado = PENDIENTE`, etapa `SOLICITUD`) | Multipart: firma (imagen) o formato de prestador (PDF/XLSX). La firma puede copiarse del perfil con `?desde_perfil=true` (RN-32, RN-33). Pendiente (llega con la subida de archivos) |
| DELETE | `/viaticos/{id}` | dueño, S | Solo `PENDIENTE` + financiero `PENDIENTE` (RN-09); lógico, con cascada a sus gastos |
| POST | `/viaticos/{id}/aprobar` | **A S** | Exige `estado = PENDIENTE`. Etapa `LEGALIZACION`: RN-06/RN-21 (≥1 gasto activo y todos con `soporte_id` o `archivo_id`, si no `409 COMPROBANTE_FALTANTE`). RN-27: sobre el propio viático, `403 AUTOAPROBACION_NO_PERMITIDA` (ADMIN) o permitido y auditado (`AUTOAPROBACION_SUPERADMIN`, solo SUPERADMIN) |
| POST | `/viaticos/{id}/rechazar` | **A S** | `PENDIENTE → RECHAZADO` (final). `{comentario}` obligatorio (`422 COMENTARIO_REQUERIDO`); RN-27 igual que aprobar |
| POST | `/viaticos/{id}/devolver` | **A S** | `PENDIENTE`/`APROBADO` → `PENDIENTE` si `estado_financiero` no es `PAGADO` ni `PROCESADO` (RN-20); `{comentario}` obligatorio; RN-27 igual que aprobar |
| POST | `/viaticos/{id}/gestionar-tiquetes` | **A S** | `{comentario?, referencia?}`; solo `CON_SOLICITUD` con `requiere_tiquete`, etapa `SOLICITUD` y `estado = APROBADO` (si no, `409 TRANSICION_INVALIDA`); RN-27; repetible; evento `GESTIONAR_TIQUETES` (S-10) |
| PATCH | `/viaticos/{id}/valor-asignado` | **F S** | `{valor_asignado (>= 0), comentario?}`. Exige `estado = APROBADO`, sin `recursos_propios` y sin liquidar (`409 TRANSICION_INVALIDA`); RN-27. La BD recalcula `valor_transferido` (RN-14); evento `EDITAR_VALOR_ASIGNADO` con antes/después y `presupuesto_solicitado` como referencia. ADMIN y VIAJERO → 403 |
| POST | `/viaticos/{id}/estado-financiero` | **F S** | `{estado_financiero, comentario?}`. Solo hacia adelante y con `estado = APROBADO`. `TRANSFERIDO` exige `valor_asignado > 0` y sin recursos propios; `PAGADO`/`PROCESADO` exigen RN-03 (etapa `LEGALIZACION`, gastos con comprobante). Registra `CAMBIAR_ESTADO_FINANCIERO` y, al liquidar, `LIQUIDAR` con el sentido (`REINTEGRO` / `REEMBOLSO` / `SIN_SALDO`) |
| POST | `/viaticos/{id}/habilitar-legalizacion` | dueño, S | Solo `CON_SOLICITUD`, etapa `SOLICITUD`, `estado = APROBADO` y, si `requiere_gastos_viaje`, `estado_financiero = TRANSFERIDO` (RN-28); si no, `409 LEGALIZACION_NO_HABILITABLE`. Pasa a etapa `LEGALIZACION`, `estado = PENDIENTE`, conserva `estado_financiero` y `valor_asignado` (S-12) |
| GET | `/viaticos/{id}/eventos` | dueño, F A S | Historial de las tres dimensiones. Por ahora va embebido en `GET /viaticos/{id}` (`eventos[]`); la ruta propia queda para cuando el historial crezca |
| GET | `/viaticos/{id}/pdf-solicitud` | dueño, F A S | `application/pdf` con la firma incrustada; solo `CON_SOLICITUD` y con firma (RN-32). `Content-Disposition: attachment; filename="VT-000123-solicitud.pdf"`. Pendiente |
| GET | `/viaticos/{id}/pdf-legalizacion` | dueño, F A S | PDF de la legalización con gastos, saldo e historial. Solo en etapa `LEGALIZACION`. `filename="VT-000123-legalizacion.pdf"`. Pendiente |

`estado-financiero` recibe el valor destino (S-03), pero sigue siendo una acción con permiso, validaciones e historial a través de `transicionar()`.

**Implementado en S2-04a** (cálculo tarifario, creación en ambas modalidades, `GET /viaticos/{id}`), **S2-04b/S2-05** (listado, edición/eliminación en `PENDIENTE` y la máquina de estados operativa) **y S2-06/S2-07** (`gestionar-tiquetes`, `valor-asignado`, `estado-financiero` con la liquidación). Quedan pendientes: `firma`/`formato-adjunto` del viático y los PDF. Detalles del contrato:

- `POST /viaticos/calcular-presupuesto` (`viaticos:calcular_presupuesto`, V F A S): cuerpo `{proyecto_id | proyecto_otro, requiere_gastos_viaje, trayectos: [{orden, ciudad_origen, ciudad_destino, fecha_ida, fecha_regreso, requiere_hospedaje, dias_estadia}]}` (1–5, `extra="forbid"`: el cliente no puede enviar tarifas ni totales). `aplica = false` con `motivo_no_aplica` en `SIN_GASTOS_VIAJE` (si `requiere_gastos_viaje = false`) o `FORMATO_PRESTADOR` (prestador + proyecto con `exige_formato_prestador = true`, RN-33); en ambos casos `trayectos[].*` tarifario sale en `null` y `presupuesto_solicitado = null`. Si aplica, cada trayecto trae su instantánea (`vr_alimentacion`, `otros_gastos`, `trans_interno` ya resuelto por `dias_estadia`, `transporte_aeropuerto`, `transporte_intermunicipal`, `subtotal_estadia`, todos `Dinero`) y `presupuesto_solicitado` es la suma (RN-29). Ningún proyecto, ningún proyecto_id+proyecto_otro juntos, 0 o más de 5 trayectos, destino = origen (salvo "Otro"), regreso < ida o días < 1 → `422 PROYECTO_REQUERIDO` / `PROYECTO_AMBIGUO` / `VALIDACION` / `TRAYECTOS_INVALIDOS`; una ciudad de destino sin tarifa activa para el tipo del usuario → `422 VALOR_NO_PERMITIDO`.
- `POST /viaticos` (`viaticos:crear`, V F A S) es una unión discriminada por `modalidad`: el cuerpo de `CON_SOLICITUD` (con `trayectos`, `proyecto_id | proyecto_otro`, `lider_proyecto`) y el de `LEGALIZACION_DIRECTA` (solo `motivo_viaje`, `recursos_propios?`) no comparten campos; enviar `proyecto_id`, `trayectos` o `recursos_propios` en la modalidad que no les corresponde → `422 VALIDACION` (`extra="forbid"`). `CON_SOLICITUD` usa la misma función que la vista previa para calcular y guardar la instantánea de cada `viatico_trayectos`; `requiere_tiquete = true` sin `fecha_nacimiento` en el perfil → `422 FECHA_NACIMIENTO_REQUERIDA` (RN-31). La instantánea del colaborador (RN-17: nombre, cargo, célula por nombre, tipo de vinculación, cédula, fecha de nacimiento) se copia del usuario autenticado. El evento inicial `CREAR` se inserta en `viatico_eventos` en la misma transacción.
- `GET /viaticos` (`viaticos:leer_propios`, V F A S): RLS ya limita lo que ve un VIAJERO (RN-01); los filtros son los mismos para todos los roles. Cada fila trae el resumen financiero de `v_viatico_saldos` (`valor_transferido`, `total_gastos`, `saldo`), el viajero (`{id, nombre}`) y `acciones_permitidas`. Orden fijo `-created_at` (sin `sort`).
- `GET /viaticos/{id}` (`viaticos:leer_propios`, dueño F A S): el alcance por dueño lo aplica RLS (S2-03, defensa en profundidad) — la consulta no filtra por `usuario_id` a propósito; sin fila visible, `404 NO_ENCONTRADO`, igual para un ajeno que para un id inexistente. `saldo`/`total_gastos` vienen de `v_viatico_saldos`.
- **`acciones_permitidas`** (`app/modules/viaticos/acciones.py`, función pura): `editar`/`eliminar` (dueño o SUPERADMIN, `PENDIENTE`/`PENDIENTE`); `aprobar`/`rechazar` (ADMIN/SUPERADMIN, `PENDIENTE`, RN-27); `devolver` (ADMIN/SUPERADMIN, `PENDIENTE`/`APROBADO` sin `PAGADO`/`PROCESADO`, RN-27); `habilitar_legalizacion` (dueño o SUPERADMIN, `CON_SOLICITUD`/`SOLICITUD`/`APROBADO`, RN-28); `gestionar_gastos` (dueño o SUPERADMIN, etapa `LEGALIZACION`, `PENDIENTE`). Así el frontend muestra u oculta botones sin repetir las reglas.
- **`PATCH /viaticos/{id}`** (dueño o SUPERADMIN; `409 NO_EDITABLE` fuera de `PENDIENTE`/`PENDIENTE`, RN-09/S-05): en etapa `SOLICITUD` acepta los campos de la cabecera y `trayectos` (reemplazo completo); enviar `recursos_propios` aquí → `422 VALOR_NO_PERMITIDO`. En etapa `LEGALIZACION` solo `motivo_viaje`/`comentarios` (y `recursos_propios` si es `LEGALIZACION_DIRECTA`); `trayectos`/`proyecto_*` → `422 VALOR_NO_PERMITIDO`. `proyecto_id`/`proyecto_otro`: enviar uno borra el otro si se envía sin el otro; enviar los dos en la misma petición valida la exclusividad tal cual (RN-16). El presupuesto se recalcula solo si cambian `proyecto_id`, `proyecto_otro`, `requiere_gastos_viaje` o `trayectos`.
- **`DELETE /viaticos/{id}`**: igual alcance que `PATCH`; marca `deleted_at`, pone en cascada `deleted_at` en sus `gastos`, registra `ELIMINAR` en `viatico_eventos` y `VIATICO_ELIMINAR` en `auditoria` (RF-014, a diferencia de la creación).
- **`transicionar()`** (`app/modules/viaticos/service.py`): núcleo común de todas las acciones (`aprobar`/`rechazar`/`devolver`/`habilitar-legalizacion` y, desde S2-07, `gestionar-tiquetes`/`valor-asignado`/`estado-financiero`): bloquea la fila (`SELECT … FOR UPDATE`), aplica la validación y el cambio de una función específica de cada acción, y registra el evento en `viatico_eventos`, todo en una sola transacción. El `estado_anterior`/`estado_nuevo` del evento es el de su dimensión (`estado_financiero` para `FINANCIERO`); las acciones que no cambian estado (tiquetes, valor asignado) los dejan en `null`. Admite eventos adicionales en la misma transacción (`LIQUIDAR`).
- **Estado financiero (S2-07):** orden `PENDIENTE → TRANSFERIDO → PAGADO → PROCESADO`, solo hacia adelante (repetir o retroceder → `409 TRANSICION_INVALIDA`); se pueden saltar pasos (S-03), p. ej. una legalización con recursos propios pasa de `PENDIENTE` a `PAGADO`. Siempre con `estado = APROBADO`. Marca `estado_financiero_at`. La primera llegada a `PAGADO` o `PROCESADO` registra además `LIQUIDAR` con `{valor_transferido, total_gastos, saldo, sentido}` (`v_viatico_saldos`; RN-02, RN-10).
- **`acciones_permitidas` (S2-07):** suma `gestionar_tiquetes` (ADMIN/SUPERADMIN, RN-27), `registrar_valor_asignado` y `cambiar_estado_financiero` (FINANCIERO/SUPERADMIN, RN-27; el segundo solo si hay algún destino válido, `acciones.destinos_financieros()`).
- **Dinero en `viatico_eventos.datos`:** siempre como string con 2 decimales (`"50000.00"`).
- Auditoría: la creación y la edición **no** pasan por `auditoria` (reservada para accesos, contraseñas, roles, catálogos, RF-014); su historial es `viatico_eventos`, que sí ve la UI y el PDF. Solo `VIATICO_ELIMINAR` y `AUTOAPROBACION_SUPERADMIN` (RN-27) llegan a `auditoria`.

### 5.5 Gastos (subrecurso)

**Implementado en S2-06.** Los adjuntos se suben antes con `POST /archivos` (§5.9) y el gasto los referencia por id; así las rutas de gastos son JSON y la validación de tipo vive en un solo lugar.

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/viaticos/{id}/gastos` | dueño, F A S | Gastos activos (sin los eliminados), por `fecha_factura`; cada uno con `rubro {id, nombre}`, `proyecto {id, nombre, en_catalogo}`, `soporte`/`archivo` (`{id, nombre, mime_type}` o `null`) y `tiene_comprobante` (RN-21). Sin paginar |
| GET | `/viaticos/{id}/gastos/{gasto_id}` | dueño, F A S | Detalle |
| POST | `/viaticos/{id}/gastos` | dueño, S | `{fecha_factura, rubro_id, proyecto_id \| proyecto_otro, concepto, cc_nit?, empresa?, valor, observaciones?, soporte_id?, archivo_id?}` → `201` con `Location`. Evento `REGISTRAR_GASTO` |
| PATCH | `/viaticos/{id}/gastos/{gasto_id}` | dueño, S | Solo lo enviado; `soporte_id`/`archivo_id` con otro id reemplazan el adjunto, en `null` lo quitan (el gasto puede quedar sin comprobante). `fecha_factura`, `rubro_id`, `concepto` y `valor` no admiten `null`. Evento `EDITAR_GASTO` con antes/después (si algo cambió) |
| DELETE | `/viaticos/{id}/gastos/{gasto_id}` | dueño, S | Lógico (`deleted_at`) → `204`; el saldo se recalcula solo (`v_viatico_saldos`). Evento `ELIMINAR_GASTO` |

- **Alcance:** viático invisible (ajeno para un VIAJERO, inexistente o eliminado) → `404`; visible pero no es el dueño ni SUPERADMIN (ADMIN, FINANCIERO) → `403`. Un gasto de otro viático → `404`.
- **Estado:** escribir exige etapa `LEGALIZACION` (si no, `409 ETAPA_INVALIDA`), `estado = PENDIENTE` y sin liquidar (`estado_financiero` ∉ {`PAGADO`, `PROCESADO`}); si no, `409 NO_EDITABLE`. **`TRANSFERIDO` se admite**: es el estado normal de una legalización `CON_SOLICITUD` con anticipo (S-12, docs/user-flows.md paso 5). Cada escritura bloquea el viático (`FOR UPDATE`): no compite con `aprobar`.
- `rubro_id`/`proyecto_id` inexistente o inactivo → `422 VALOR_NO_PERMITIDO` con el campo.
- **Proyecto híbrido (RN-16, ADR-031)**, en gastos y en la solicitud: se envía **exactamente uno** de `proyecto_id` (catálogo) o `proyecto_otro` (texto de 3 a 150 caracteres, se guarda recortado). Ninguno → `422 PROYECTO_REQUERIDO`; los dos → `422 PROYECTO_AMBIGUO`. Los `PATCH` siguen la misma regla: enviar uno borra el otro.
- `valor > 0` con máximo 2 decimales (RN-08) → si no, `422 VALIDACION`. `fecha_factura` futura (en hora de Colombia, UTC−5) → `422 VALOR_NO_PERMITIDO` con `errors[].code = FECHA_FUTURA` (RN-07). `cc_nit` es el NIT o la cédula del proveedor (hasta 30 caracteres).
- **Adjuntos:** el archivo debe existir y haberlo subido quien registra el gasto (si no, `422 VALOR_NO_PERMITIDO`, sin revelar si existe); `soporte_id` con `proposito = SOPORTE` (imagen) y `archivo_id` con `proposito = ARCHIVO` (PDF); cualquier otro → `415 TIPO_ARCHIVO_NO_PERMITIDO` (RN-13). Soporte y archivo distintos (`422`). Un archivo pertenece a **un solo gasto**, aunque ese gasto se haya eliminado (lo exige el `UNIQUE` de la BD y así el gasto eliminado conserva su comprobante) → `409 EN_USO`.
- El contenido de un adjunto se ve con `GET /archivos/{id}/url` (§5.9).

### 5.6 Pagos (modelo de lectura)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/pagos` | F A S (A solo lectura) | Filas de `v_viatico_saldos`. Filtros: `etapa` (por defecto incluye solicitudes `APROBADO` por desembolsar y legalizaciones `APROBADO`), `estado`, `estado_financiero` (por defecto `PENDIENTE,TRANSFERIDO`), `modalidad`, `saldo` (`negativo`/`positivo`/`cero`), `recursos_propios`, `usuario_id`, `proyecto_id`, `desde`, `hasta`; orden por `saldo`, `fecha_legalizacion` o `folio`. Cada fila trae `presupuesto_solicitado` como referencia |
| GET | `/pagos/resumen` | F A S | Totales del filtro: transferido, gastado, saldo a reembolsar y a reintegrar |

El cambio de estado financiero es `POST /viaticos/{id}/estado-financiero`.

### 5.7 Indicadores (DP-16 ✅: fecha de factura)

`desde`/`hasta` se aplican **siempre** como `gastos.fecha_factura BETWEEN desde AND hasta` (ADR-024).

| Método | Ruta | Roles | Respuesta |
| :--- | :--- | :--- | :--- |
| GET | `/indicadores/consumo-por-proyecto?desde&hasta` | F A S | `[{proyecto_id, proyecto, en_catalogo, total_gastos, cantidad_gastos}]`. Los gastos con "Otro" se agrupan por nombre normalizado, con `proyecto_id = null` y `en_catalogo = false` |
| GET | `/indicadores/estados?desde&hasta&proyecto_id` | F A S | `[{estado, cantidad}]` (estado operativo; S-07) |
| GET | `/indicadores/kpis?desde&hasta` | F A S | `{total_transferido, total_gastos, saldo_por_reembolsar, saldo_por_reintegrar, pendientes_aprobacion, pendientes_pago}` (opcional MVP) |

### 5.8 Auditoría (SUPERADMIN, post-MVP en la UI)

`GET /auditoria?entidad&entidad_id&usuario_id&accion&desde&hasta` (**implementado en S1-10**, permiso `auditoria:leer`): paginado, más reciente primero; `desde`/`hasta` son fechas UTC inclusivas.

### 5.9 Archivos (S2-06, ADR-028)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| POST | `/archivos` | V F A S | `multipart/form-data`: `archivo` + `proposito` ∈ `SOPORTE`, `ARCHIVO`, `FIRMA`, `FORMATO_PRESTADOR` → `201 {id, nombre_original, mime_type, tamano_bytes, sha256, proposito, created_at}` con `Location`. Nunca devuelve la clave de almacenamiento |
| GET | `/archivos/{id}` | quien lo subió, F A S | Metadatos |
| GET | `/archivos/{id}/url` | quien lo subió, F A S | `{url, expires_at, mime_type, nombre}`: URL temporal de **5 min** (`SIGNED_URL_TTL_SECONDS`) |
| GET | `/archivos/contenido?token=` | (token) | Solo `STORAGE_BACKEND=local`: sirve el contenido con un token firmado (con S3 → `404`) |

- **Tipo por contenido** (*magic bytes*, `app/modules/archivos/deteccion.py`), nunca por extensión ni `Content-Type`: `SOPORTE` = JPEG, PNG, WEBP, HEIC; `ARCHIVO` = PDF; `FIRMA` = JPEG, PNG, WEBP; `FORMATO_PRESTADOR` = PDF, XLSX, XLS (RN-13, RN-32, RN-33). Ejecutables, SVG, HTML, ZIP genéricos, DOCX/DOC o cualquier otro → `415 TIPO_ARCHIVO_NO_PERMITIDO`. Vacío → `422`.
- **Tamaño:** máximo `MAX_UPLOAD_MB` (10). Un `Content-Length` mayor que el límite + 1 MB se corta antes de leer el cuerpo (`LimiteCuerpoAdjuntosMiddleware`); el contenido se lee además con límite → `413 ARCHIVO_MUY_GRANDE`.
- Se calcula el **SHA-256**; la clave es `{proposito}/{AAAA}/{MM}/{uuid}{ext}` (sin el nombre del cliente). El contenido se guarda **antes** que la fila (si la BD falla, queda un objeto huérfano, nunca una fila sin contenido). Archivos **inmutables**: reemplazar = subir otro.
- **Alcance:** RLS de `archivos` (quien lo subió —`created_by`— o FINANCIERO/ADMIN/SUPERADMIN); lo ajeno → `404`.
- **URL de lectura:** con S3, URL **prefirmada** de `get_object` (bucket privado, `ResponseContentType` y `ResponseContentDisposition: inline` forzados, subida con `ServerSideEncryption=AES256`). En local, la API firma un token (JWT HS256 con una clave **derivada** de `JWT_SECRET` y audiencia propia: no sirve como access token) con la clave, el tipo, el nombre y la expiración; así un `<img src>` funciona sin `Authorization`, igual que con S3. La respuesta lleva `X-Content-Type-Options: nosniff` y `Content-Security-Policy: default-src 'none'; sandbox`.

## 6. Convenciones de respuesta

**Recurso individual:** el objeto, sin envoltorio.

```json
{
  "id": "6f1c…",
  "folio": "VT-000123",
  "modalidad": "CON_SOLICITUD",
  "etapa": "LEGALIZACION",
  "estado": "PENDIENTE",
  "estado_financiero": "TRANSFERIDO",
  "devuelta_at": null,
  "usuario": { "id": "…", "nombre_completo": "Ana Pérez" },
  "colaborador": { "nombre": "Ana Pérez", "cargo": "Profesional de campo", "celula": "Campo", "es_prestador_servicios": false },
  "motivo_viaje": "Taller de campo",
  "solicitud": {
    "proyecto": { "id": "…", "nombre": "Conexión Agro", "en_catalogo": true },
    "proyecto_otro": null,
    "lider_proyecto": "María Gómez",
    "requiere_tiquete": true,
    "requiere_gastos_viaje": true,
    "presupuesto_solicitado": "980000.00",
    "trayectos": [
      { "orden": 1, "ciudad_origen": "Cali", "ciudad_destino": "Bogotá",
        "fecha_ida": "2026-11-20T08:00:00Z", "fecha_regreso": "2026-11-22T18:00:00Z",
        "requiere_hospedaje": true, "dias_estadia": 3, "subtotal_estadia": "…" }
    ]
  },
  "fecha_legalizacion": "2026-11-06",
  "recursos_propios": false,
  "valor_asignado": "1000000.00",
  "valor_transferido": "1000000.00",
  "total_gastos": "1120000.00",
  "saldo": "-120000.00",
  "acciones_permitidas": ["cambiar_estado_financiero", "descargar_pdf_solicitud", "descargar_pdf_legalizacion"],
  "created_at": "2026-11-01T14:03:00Z",
  "updated_at": "2026-11-06T09:12:00Z"
}
```

(`solicitud` es `null` en `LEGALIZACION_DIRECTA`.)

**Colección paginada:** `{ "items": [ … ], "total": 134, "page": 1, "size": 20 }`. Parámetros: `page`, `size` (20, máx. 100), `sort`.

- **Dinero:** *string* decimal con 2 decimales (ADR-012). **Fechas:** `DATE` como `AAAA-MM-DD`; `TIMESTAMPTZ` en ISO 8601 UTC; la UI muestra America/Bogotá.
- **Estados, etapas y modalidades:** códigos en mayúsculas sin emojis.
- **Códigos:** `200`, `201` (con `Location`), `202` (`password/forgot`), `204`.
- Nulos como `null`.

## 7. Manejo de errores (RFC 9457, ADR-014)

`Content-Type: application/problem+json`

```json
{
  "type": "https://trulab.co/errores/regla-negocio",
  "title": "La solicitud no cumple los requisitos para aprobar",
  "status": 409,
  "code": "SOLICITUD_INCOMPLETA",
  "detail": "Falta la firma del solicitante.",
  "errors": [{ "field": "firma", "code": "FIRMA_REQUERIDA", "message": "La solicitud no tiene firma" }],
  "request_id": "01JC…"
}
```

| Estado | `code` típico | Cuándo |
| :--- | :--- | :--- |
| 400 | `SOLICITUD_INVALIDA` | JSON mal formado |
| 401 | `NO_AUTENTICADO`, `TOKEN_EXPIRADO`, `CREDENCIALES_INVALIDAS` | Sin token, token inválido, o credenciales incorrectas (mensaje genérico) |
| 403 | `SIN_PERMISO`, `USUARIO_INACTIVO`, `USUARIO_NO_REGISTRADO`, `DOMINIO_NO_PERMITIDO`, `METODO_ACCESO_NO_PERMITIDO`, `CAMBIO_PASSWORD_REQUERIDO`, `AUTOAPROBACION_NO_PERMITIDA` | RN-27 (`aprobar`/`rechazar`/`devolver`/`gestionar-tiquetes` sobre el propio viático, ADMIN; `valor-asignado`/`estado-financiero`, FINANCIERO) con un código específico desde S2-05 (antes se documentaba como `SIN_PERMISO`); incluye también la falta de `X-Requested-With` en `refresh`/`logout` |
| 404 | `NO_ENCONTRADO` | Recurso inexistente **o ajeno** |
| 409 | `TRANSICION_INVALIDA`, `SOLICITUD_INCOMPLETA`, `LEGALIZACION_INCOMPLETA`, `LEGALIZACION_NO_HABILITABLE`, `COMPROBANTE_FALTANTE`, `ETAPA_INVALIDA`, `REQUIERE_APROBACION`, `EN_USO`, `DUPLICADO`, `NO_EDITABLE`, `ULTIMO_SUPERADMIN`, `SUPERADMIN_SIN_PASSWORD`, `ACCION_SOBRE_SI_MISMO` | Reglas de negocio o de estado. `COMPROBANTE_FALTANTE` (S2-05, RN-06/RN-21): al aprobar una legalización sin gastos o con alguno sin `soporte`/`archivo` |
| 409 | `EN_USO` (adjuntos) | El archivo ya está adjunto a otro gasto (S2-06) |
| 413 | `ARCHIVO_MUY_GRANDE` | Más de 10 MB |
| 415 | `TIPO_ARCHIVO_NO_PERMITIDO` | Tipo real (por contenido) no admitido para el propósito, o un archivo de otro propósito en `soporte_id`/`archivo_id`/firma |
| 422 | `VALIDACION`, `VALOR_NO_PERMITIDO`, `PROYECTO_REQUERIDO`, `PROYECTO_AMBIGUO`, `COMENTARIO_REQUERIDO`, `PASSWORD_DEBIL`, `PASSWORD_ACTUAL_INCORRECTA`, `TOKEN_INVALIDO`, `TRAYECTOS_INVALIDOS`, `FECHA_NACIMIENTO_REQUERIDA`, `IMPORTE_NO_PERMITIDO` | Errores de campo; token de recuperación inexistente/usado/vencido (mensaje único); 0 ó más de 5 trayectos, origen = destino (salvo "Otro"), regreso anterior a la ida (RN-30); importes tarifarios enviados por el cliente (RN-29) |
| 429 | `DEMASIADAS_SOLICITUDES`, `CUENTA_BLOQUEADA_TEMPORALMENTE` | Límite en `/auth/*`; bloqueo por intentos |
| 500 | `ERROR_INTERNO` | Sin detalles internos |
| 503 | `LOGIN_GOOGLE_NO_DISPONIBLE` | `/auth/google` sin `GOOGLE_CLIENT_ID` configurado |

`code` es estable, en `MAYUSCULAS`; la UI traduce por `code`. Cada respuesta lleva `X-Request-ID`.

## 8. Seguridad transversal

- CORS limitado al origen de la SPA (`FRONTEND_URL`).
- Límite del cuerpo: 11 MB en rutas de adjuntos y 1 MB en el resto.
- **Límite de peticiones** en `/auth/*` (más estricto en `password/forgot` y `password/reset`).
- Encabezados: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` en el frontend.
- Nunca se aceptan en creación/edición: `usuario_id`, `estado`, `estado_financiero`, `etapa`, `folio`, `colaborador_*`, `valor_asignado`, `valor_transferido`, `presupuesto_solicitado` ni ningún importe tarifario; `valor_transferido` no se acepta en **ningún** endpoint (RN-14). La cédula, la fecha de nacimiento y la firma no aparecen en listados.
- **Contraseñas y tokens:** nunca en logs, auditoría ni respuestas (salvo el token por correo). `password_hash` jamás sale por la API.
- **Correo de recuperación:** el enlace usa `FRONTEND_URL`; en local el correo se escribe en el log del backend (sin SES).

## 9. Idempotencia y concurrencia

- Las acciones son idempotentes por estado: repetir `aprobar` sobre una `APROBADO` devuelve `409 TRANSICION_INVALIDA`; igual `habilitar-legalizacion` repetido (`409 ETAPA_INVALIDA`).
- La transición usa `SELECT … FOR UPDATE` sobre el viático, para evitar, por ejemplo, que ADMIN devuelva mientras FINANCIERO marca `PAGADO`, o que se habilite la legalización mientras se devuelve la solicitud.
- Un token de recuperación se consume con `UPDATE … WHERE used_at IS NULL` (un solo uso, sin carreras).
- **Futuro:** `ETag` / `If-Match` para ediciones concurrentes.
