# Diseño de API — Trulab Viajes

> Diseño del contrato. Implementado hasta ahora: solo `GET /api/v1/health`. La especificación OpenAPI que genere FastAPI será la referencia viva; este documento define las reglas que debe cumplir.
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
| GET | `/me` | Usuario actual: rol, cargo, célula, `es_prestador_servicios`, `debe_cambiar_password`, `permisos` | Bearer |

- Encabezado: `Authorization: Bearer <access_token>`. `/auth/refresh` y `/auth/logout` exigen `X-Requested-With: trulab-spa` (junto con `SameSite=Strict`).
- **Cambio obligatorio de contraseña:** si `debe_cambiar_password = true`, el access token lleva el claim `pwd_change` y **todos** los endpoints, salvo `/auth/password/change`, `/auth/logout` y `/me`, responden `403 CAMBIO_PASSWORD_REQUERIDO`.
- **Política de contraseña:** mínimo 12 caracteres, no igual al username ni al correo, no estar en una lista de contraseñas comunes; máximo 128. Error `422 PASSWORD_DEBIL` con los motivos.
- **Sin filtrar existencia:** `login` responde `401 CREDENCIALES_INVALIDAS` tanto si el usuario no existe, como si la contraseña es incorrecta, está inactivo o es SUPERADMIN, con tiempo de respuesta homogéneo (verificación Argon2id ficticia). El motivo real solo queda en `auditoria` (`LOGIN_FALLIDO`).
- **Bloqueo:** tras 5 fallos consecutivos de un usuario → `429 CUENTA_BLOQUEADA_TEMPORALMENTE` por 15 minutos (S-14); además, límite por IP.
- **`/auth/google`:** valida firma, `aud`, `exp`, `email_verified`, `hd` = `GOOGLE_WORKSPACE_DOMAIN`, correo registrado, activo y **rol `SUPERADMIN`**. Si el correo existe pero el rol es operativo → `403 METODO_ACCESO_NO_PERMITIDO` ("Use su usuario y contraseña") y `ACCESO_DENEGADO`.
- Errores: `401` token ausente/inválido/vencido o credenciales inválidas; `403` dominio no permitido, usuario no registrado/inactivo/sin rol, método no permitido para el rol (RN-12).
- Auditoría: `LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `PASSWORD_CAMBIADA`, `PASSWORD_RECUPERACION_SOLICITADA`, `ACCESO_DENEGADO`. Nunca se registran contraseñas, hashes ni tokens.
- **Login de desarrollo:** solo con `ENV=local`, mientras llega el OAuth Client ID (R1.1); una prueba en CI verifica que está desactivado fuera de local. Para operativos no hace falta: el login normal funciona en local con el correo escrito en el log.

## 4. Autorización

- Cada endpoint declara un permiso (`require_permission(...)`). Matriz en `SPEC.md` §6 y `backend/app/core/permissions.py`.
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

- **Sin autoaprobación** (RN-27): `aprobar`, `rechazar`, `devolver`, `gestionar-tiquetes`, `estado-financiero` y `valor-asignado` sobre un viático **creado por el propio usuario**, en **cualquier etapa**, responden `403 SIN_PERMISO` para ADMIN y FINANCIERO. Solo SUPERADMIN puede, y cada uso se audita.

## 5. Recursos y endpoints previstos

Leyenda: V=VIAJERO, F=FINANCIERO, A=ADMIN, S=SUPERADMIN.

### 5.1 Usuarios

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/usuarios` | A S | Filtros: `q`, `rol`, `cargo_id`, `celula_id`, `es_prestador_servicios`, `activo`; paginado. La cédula y la fecha de nacimiento no salen en el listado |
| POST | `/usuarios` | A S | Operativos: `{nombre_completo, correo, username, rol, cargo_id?, celula_id?, cedula?, es_prestador_servicios, fecha_nacimiento?}`. El servidor genera una **contraseña temporal** (`debe_cambiar_password = true`) y la envía **por correo**; ADMIN no la ve (S-13). **`rol = SUPERADMIN`** solo por S: exige correo del dominio `@trulab.co`, no lleva username ni contraseña, audita `SUPERADMIN_ASIGNADO`. ADMIN que intenta `SUPERADMIN` → `403 SIN_PERMISO` |
| GET | `/usuarios/{id}` | A S | |
| PATCH | `/usuarios/{id}` | A S | Cambiar el rol revoca sesiones y se audita. **Promover a `SUPERADMIN`** (solo S): valida correo `@trulab.co`, borra username/contraseña, audita `SUPERADMIN_ASIGNADO`. **Degradar un SUPERADMIN** (solo S): exige `username` y genera contraseña temporal; `409 ULTIMO_SUPERADMIN` si es el último activo. ADMIN no puede modificar a un SUPERADMIN (`403`) |
| POST | `/usuarios/{id}/desactivar` | A S | No a uno mismo; `409 ULTIMO_SUPERADMIN` si es el último SUPERADMIN activo; desactivar un SUPERADMIN solo S. Revoca sesiones |
| POST | `/usuarios/{id}/activar` | A S | |
| POST | `/usuarios/{id}/restablecer-password` | A S | Solo operativos: genera una contraseña temporal nueva, la envía por correo, `debe_cambiar_password = true`, revoca sesiones, audita `PASSWORD_CAMBIADA`. Sobre un SUPERADMIN → `409 SUPERADMIN_SIN_PASSWORD` |
| GET/PUT/DELETE | `/me/firma` | V F A S | Sube (multipart, imagen), consulta (URL firmada) o quita la firma del perfil (RN-32) |
| PATCH | `/me` | V F A S | Solo `fecha_nacimiento` (RN-31) |

### 5.2 Cargos

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/cargos` | F A S | |
| POST | `/cargos` | A S | Folio `CA-` generado |
| GET | `/cargos/{id}` | F A S | |
| PATCH | `/cargos/{id}` | A S | |
| DELETE | `/cargos/{id}` | A S | Lógico; `409` si está en uso |

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

### 5.4 Viáticos (entidad unificada, ADR-029)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/viaticos` | V (propios) F A S (todos) | Filtros: `modalidad`, `etapa`, `estado`, `estado_financiero`, `devuelta`, `usuario_id` (no V), `proyecto_id`, `proyecto_otro` (texto, no V), `desde`, `hasta` (sobre `fecha_legalizacion`), `q` (folio/motivo); orden `-fecha_legalizacion` |
| POST | `/viaticos` | V F A S | `{modalidad, motivo_viaje, …}`. **`CON_SOLICITUD`:** `{proyecto_id | proyecto_otro, lider_proyecto, empresa?, requiere_tiquete, requiere_gastos_viaje, comentarios?, trayectos: [{orden, ciudad_origen, ciudad_destino, fecha_ida, fecha_regreso, requiere_hospedaje, dias_estadia}]}` (1–5). El servidor calcula las tarifas, el `presupuesto_solicitado` y las instantáneas; **rechaza** importes enviados por el cliente. Crea en etapa `SOLICITUD`, `estado = PENDIENTE`. **`LEGALIZACION_DIRECTA`:** `{motivo_viaje, recursos_propios}`; crea en etapa `LEGALIZACION`. Los `colaborador_*` se copian del usuario (RN-17). Folio `VT-` |
| POST | `/viaticos/calcular-presupuesto` | V F A S | **Vista previa sin guardar** (RN-29): `{proyecto_id | proyecto_otro, requiere_gastos_viaje, trayectos: […]}` → `{aplica, motivo_no_aplica?, trayectos: [{subtotal_estadia, transporte_aeropuerto, transporte_intermunicipal, …}], presupuesto_solicitado, exige_formato_prestador}`. Usa `es_prestador_servicios` del usuario autenticado. Es la misma función que usa `POST /viaticos`, por lo que la UI y el guardado coinciden |
| GET | `/viaticos/{id}` | dueño, F A S | Incluye modalidad, etapa, `estado`, `estado_financiero`, solicitud y `trayectos`, `valor_asignado`, `valor_transferido`, `presupuesto_solicitado`, totales, saldo, `acciones_permitidas` y `eventos` |
| PATCH | `/viaticos/{id}` | dueño (`estado = PENDIENTE`) | En etapa `SOLICITUD`: campos de la solicitud y `trayectos` completos (se recalcula). En etapa `LEGALIZACION`: `motivo_viaje`; `recursos_propios` solo con `estado_financiero = PENDIENTE` (S-05) |
| PUT/DELETE | `/viaticos/{id}/firma` · `/formato-adjunto` | dueño (`estado = PENDIENTE`, etapa `SOLICITUD`) | Multipart: firma (imagen) o formato de prestador (PDF/XLSX). La firma puede copiarse del perfil con `?desde_perfil=true` (RN-32, RN-33) |
| DELETE | `/viaticos/{id}` | dueño, S | Solo `PENDIENTE` + financiero `PENDIENTE` (RN-09) |
| POST | `/viaticos/{id}/aprobar` | **A S** | Etapa `SOLICITUD`: exige RN-06 (trayectos, presupuesto o formato, firma, fecha de nacimiento si hay tiquete). Etapa `LEGALIZACION`: ≥1 gasto, todos con comprobante. `409 SOLICITUD_INCOMPLETA` / `409 LEGALIZACION_INCOMPLETA` con `errors[]` |
| POST | `/viaticos/{id}/rechazar` | **A S** | `PENDIENTE → RECHAZADO` (final). `{comentario}` obligatorio |
| POST | `/viaticos/{id}/devolver` | **A S** | `PENDIENTE`/`APROBADO` → `PENDIENTE`; `{comentario}` obligatorio; reglas de RN-20 |
| POST | `/viaticos/{id}/gestionar-tiquetes` | **A S** | `{comentario}`; solo si `requiere_tiquete`; evento `GESTIONAR_TIQUETES` (S-10) |
| PATCH | `/viaticos/{id}/valor-asignado` | **F S** | `{valor_asignado, comentario?}`. El servidor recalcula `valor_transferido` (RN-14) y registra `EDITAR_VALOR_ASIGNADO`. `presupuesto_solicitado` se muestra como referencia sugerida. ADMIN y VIAJERO → 403 |
| POST | `/viaticos/{id}/estado-financiero` | **F S** | `{estado_financiero, comentario?}`. `PAGADO`/`PROCESADO` exigen RN-03 (etapa `LEGALIZACION`, `APROBADO`, comprobantes). Registra `CAMBIAR_ESTADO_FINANCIERO` y, al liquidar, `LIQUIDAR` con el sentido (reintegro / reembolso) |
| POST | `/viaticos/{id}/habilitar-legalizacion` | dueño, S | Solo `CON_SOLICITUD`, etapa `SOLICITUD`, `estado = APROBADO` y, si `requiere_gastos_viaje`, `estado_financiero = TRANSFERIDO` (RN-28). Pasa a etapa `LEGALIZACION`, `estado = PENDIENTE`, conserva `estado_financiero` y `valor_asignado` (S-12). `409 LEGALIZACION_NO_HABILITABLE` con la causa |
| GET | `/viaticos/{id}/eventos` | dueño, F A S | Historial de las tres dimensiones |
| GET | `/viaticos/{id}/pdf-solicitud` | dueño, F A S | `application/pdf` con la firma incrustada; solo `CON_SOLICITUD` y con firma (RN-32). `Content-Disposition: attachment; filename="VT-000123-solicitud.pdf"` |
| GET | `/viaticos/{id}/pdf-legalizacion` | dueño, F A S | PDF de la legalización con gastos, saldo e historial. Solo en etapa `LEGALIZACION`. `filename="VT-000123-legalizacion.pdf"` |

`estado-financiero` recibe el valor destino (S-03), pero sigue siendo una acción con permiso, validaciones e historial a través de `transicionar()`.

### 5.5 Gastos (subrecurso)

| Método | Ruta | Roles | Notas |
| :--- | :--- | :--- | :--- |
| GET | `/viaticos/{id}/gastos` | dueño, F A S | `tiene_comprobante` por gasto (RN-21) |
| POST | `/viaticos/{id}/gastos` | dueño (`etapa = LEGALIZACION`, `estado = PENDIENTE`) | `multipart/form-data`: `fecha_factura`, `rubro_id`, `proyecto_id` **o** `proyecto_otro`, `concepto`, `cc_nit?`, `empresa?`, `valor`, `observaciones?`, `soporte?` (**imagen**), `archivo?` (**PDF**). En etapa `SOLICITUD` → `409 ETAPA_INVALIDA` |
| PATCH | `/gastos/{gasto_id}` | dueño (misma condición) | Sin archivos |
| DELETE | `/gastos/{gasto_id}` | dueño (misma condición) | Lógico |
| PUT | `/gastos/{gasto_id}/{tipo}` | dueño (misma condición) | `tipo` ∈ `soporte`, `archivo` |
| DELETE | `/gastos/{gasto_id}/{tipo}` | dueño (misma condición) | Puede dejar el gasto sin comprobante |
| GET | `/gastos/{gasto_id}/{tipo}` | dueño, F A S | `{url, expires_at, mime_type, nombre}`: URL **prefirmada de S3** de 5 min |

- `rubro_id`/`proyecto_id` inexistente o inactivo → `422 VALOR_NO_PERMITIDO`.
- **Proyecto híbrido (RN-16, ADR-031)**, en gastos y en la solicitud: se envía **exactamente uno** de `proyecto_id` (catálogo) o `proyecto_otro` (texto de 3 a 150 caracteres, se guarda recortado). Ninguno → `422 PROYECTO_REQUERIDO`; los dos → `422 PROYECTO_AMBIGUO`. Los `PATCH` siguen la misma regla: enviar uno borra el otro.
- PDF en `soporte` o imagen en `archivo` → `415 TIPO_ARCHIVO_NO_PERMITIDO` (RN-13).
- Las operaciones sobre un gasto usan `/gastos/{id}`; el acceso se valida a través de su viático.

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

`GET /auditoria?entidad&entidad_id&usuario_id&accion&desde&hasta`.

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
| 403 | `SIN_PERMISO`, `USUARIO_INACTIVO`, `USUARIO_NO_REGISTRADO`, `DOMINIO_NO_PERMITIDO`, `METODO_ACCESO_NO_PERMITIDO`, `CAMBIO_PASSWORD_REQUERIDO` | Incluye la autoaprobación (RN-27) |
| 404 | `NO_ENCONTRADO` | Recurso inexistente **o ajeno** |
| 409 | `TRANSICION_INVALIDA`, `SOLICITUD_INCOMPLETA`, `LEGALIZACION_INCOMPLETA`, `LEGALIZACION_NO_HABILITABLE`, `ETAPA_INVALIDA`, `REQUIERE_APROBACION`, `EN_USO`, `DUPLICADO`, `NO_EDITABLE`, `ULTIMO_SUPERADMIN`, `SUPERADMIN_SIN_PASSWORD` | Reglas de negocio o de estado |
| 413 | `ARCHIVO_MUY_GRANDE` | Más de 10 MB |
| 415 | `TIPO_ARCHIVO_NO_PERMITIDO` | Tipo no admitido o en el campo equivocado |
| 422 | `VALIDACION`, `VALOR_NO_PERMITIDO`, `PROYECTO_REQUERIDO`, `PROYECTO_AMBIGUO`, `COMENTARIO_REQUERIDO`, `PASSWORD_DEBIL`, `TOKEN_INVALIDO`, `TRAYECTOS_INVALIDOS`, `FECHA_NACIMIENTO_REQUERIDA`, `IMPORTE_NO_PERMITIDO` | Errores de campo; token de recuperación inexistente/usado/vencido (mensaje único); 0 ó más de 5 trayectos, origen = destino (salvo "Otro"), regreso anterior a la ida (RN-30); importes tarifarios enviados por el cliente (RN-29) |
| 429 | `DEMASIADAS_SOLICITUDES`, `CUENTA_BLOQUEADA_TEMPORALMENTE` | Límite en `/auth/*`; bloqueo por intentos |
| 500 | `ERROR_INTERNO` | Sin detalles internos |

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
