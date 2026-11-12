# Diseño de base de datos — Trulab Viajes

> Motor: PostgreSQL 16 (Amazon RDS en staging y producción). Esquema: `public`. Migraciones solo con Alembic.
> Modelo ajustado a la estructura real de AppSheet (DP-07 ✅, DP-13 a DP-18) y a la **fusión con la Solicitud de viáticos de Apps Script** (DP-19 ✅, DP-20 ✅, ADR-029, ADR-030) y al **acceso híbrido** (DP-01 actualizada, ADR-027). `SPEC.md` v0.4.
> **Estado de implementación:** existen en migración `usuarios`, `cargos`, `celulas`, `sesiones` y `auditoria` (S1-07). La migración correctiva `S1-07b` añade a `usuarios` los campos de este documento y crea `tokens_recuperacion_password`. Todo lo demás (`proyectos`, `rubros`, `tarifas_viaticos`, `viaticos`, …) llega en la semana 2.

---

## 1. Correspondencia con AppSheet y Apps Script

### 1.1 Tablas

| Origen | Nuevo modelo | Comentario |
| :--- | :--- | :--- |
| AppSheet `Cargos` | `cargos` | Igual, con folio `CA-` |
| AppSheet `Usuarios` | `usuarios` | Más `activo`, `ultimo_acceso`, `google_sub`, **`username`, `password_hash`, `debe_cambiar_password`, `es_prestador_servicios`, `fecha_nacimiento`, `firma_archivo_id`** (ADR-027) |
| AppSheet `Crear_legalizacion` | **`viaticos`** (`etapa = LEGALIZACION`, `modalidad = LEGALIZACION_DIRECTA`) | Se unifica con la solicitud. `Total Gastos` y `Saldo` salen de la vista. `Estado legalizacion` no se almacena |
| Apps Script (formulario de solicitud) | **`viaticos`** (`etapa = SOLICITUD`) + **`viatico_trayectos`** | Misma entidad (ADR-029) |
| AppSheet `Registro_Gastos` | `gastos` + `archivos` | Los adjuntos pasan a archivos gestionados |
| AppSheet `Segmentador` | **No se migra** | Parámetros `desde`/`hasta` sobre `gastos.fecha_factura` |
| Enums `Proyecto`, `Rubro`, `Celula` | `proyectos`, `rubros`, `celulas` (§2.3) | Administrables por SUPERADMIN |
| Sheet `PROYECTOS` (Apps Script) | `proyectos` | Reemplaza la hoja de cálculo |
| Sheet `CorreosExternos` (Apps Script) | — (no se migra) | El correo y el tipo de vinculación viven en `usuarios` |
| `calcularGastos.html` (tablas `gastosViaje2025` y `prestadores`) | **`tarifas_viaticos`** (§2.5) | Seed inicial de los 22 destinos |
| Enum `Rol` | `usuarios.rol` (`TEXT` + `CHECK`) | 4 roles fijos |
| — | `viatico_eventos` | Historial (RN-10) |
| — | `auditoria` | Acciones sensibles (RF-014) |
| — | `sesiones` | Refresh tokens |
| — | `tokens_recuperacion_password` | Restablecimiento de contraseña (RN-15) |

### 1.2 Campos (mapa para el ETL)

| AppSheet | Nuevo | Nota |
| :--- | :--- | :--- |
| `Cargos.ID Cargo` | `cargos.folio` (+ `migrado_de`) | DP-09 |
| `Cargos.Cargo` | `cargos.nombre` | |
| `Usuarios.ID usuario` | `usuarios.migrado_de` | PK nueva UUID |
| `Usuarios.Correo` | `usuarios.correo` | Contacto y recuperación; clave de login solo para SUPERADMIN |
| `Usuarios.Usuario` | `usuarios.nombre_completo` | |
| `Usuarios.Cargo` / `Cedula` / `Celula` / `Rol` | `cargo_id` / `cedula` / `celula_id` / `rol` | Igual que antes |
| — | `usuarios.username`, `password_hash` | El ETL no migra contraseñas: crea `username` y una contraseña temporal por usuario operativo, con `debe_cambiar_password = true` |
| `Crear_legalizacion.ID legalizacion` | `viaticos.migrado_de` | El folio nuevo es `VT-` (DP-09) |
| `Viajero` | `viaticos.usuario_id` | Por correo |
| `Nombre Colaborador`, `Cargo`, `Cedula`, `Celula` | `viaticos.colaborador_*` | Instantánea |
| `Motivo del viaje` | `viaticos.motivo_viaje` | |
| `Valor_T` | `viaticos.valor_asignado` | Lo registra FINANCIERO |
| `Valor transferido` | `viaticos.valor_transferido` | Columna generada; el ETL solo concilia |
| `Recursos propios` | `viaticos.recursos_propios` | |
| `Fecha legalizacion` | `viaticos.fecha_legalizacion` | |
| `Estado` / `Estado_P` | `viaticos.estado` / `estado_financiero` | Mapeo en §12 |
| `Estado legalizacion` | — | Espejo; el ETL verifica |
| (todo el registro migrado) | `viaticos.modalidad = 'LEGALIZACION_DIRECTA'`, `etapa = 'LEGALIZACION'` | Los datos históricos no tienen solicitud |
| `Registro_Gastos.*` | `gastos.*` | Igual que antes; `R_legalizacion` → `gastos.viatico_id` |

## 2. Entidades

Columnas comunes a **todas** las tablas operativas ("columnas base"):

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `UUID` PK | `DEFAULT gen_random_uuid()` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | `DEFAULT now()` |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | Lo actualiza el ORM |
| `created_by`, `updated_by` | `UUID NULL` FK → `usuarios.id` | `NULL` = sistema |
| `deleted_at` | `TIMESTAMPTZ NULL` | Eliminación lógica (§8) |
| `migrado_de` | `TEXT NULL` | ID original de AppSheet; solo en tablas migradas |

### 2.1 `cargos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `folio` | `TEXT` | `UNIQUE NOT NULL` (`CA-000001`) |
| `nombre` | `TEXT` | `NOT NULL`; único entre los no eliminados |
| `descripcion` | `TEXT NULL` | |

### 2.2 `usuarios`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `nombre_completo` | `TEXT` | `NOT NULL` |
| `correo` | `CITEXT` | `UNIQUE NOT NULL`. Es el **contacto y destino de la recuperación** de contraseña. Para `SUPERADMIN` debe ser del dominio `GOOGLE_WORKSPACE_DOMAIN` (`@trulab.co`); lo valida el service, porque el dominio es configuración. Operativos: correo personal o corporativo |
| **`username`** | `CITEXT NULL` | **Único.** Obligatorio para `VIAJERO`/`ADMIN`/`FINANCIERO` (`ck_usuarios__username_operativo`: `rol = 'SUPERADMIN' OR username IS NOT NULL`). Formato `^[a-z0-9._-]{3,40}$`. `NULL` para SUPERADMIN |
| **`password_hash`** | `VARCHAR(255) NULL` | Hash **Argon2id** (formato PHC, `$argon2id$…`). `CHECK ck_usuarios__password_segun_rol`: `(rol <> 'SUPERADMIN' AND password_hash IS NOT NULL) OR (rol = 'SUPERADMIN' AND password_hash IS NULL)`. Nunca se registra en logs ni auditoría |
| **`debe_cambiar_password`** | `BOOLEAN` | `NOT NULL DEFAULT false`. `true` mientras la contraseña sea temporal (alta o restablecimiento por ADMIN). Siempre `false` para SUPERADMIN |
| **`password_cambiada_at`** | `TIMESTAMPTZ NULL` | Último cambio de contraseña |
| **`intentos_fallidos`** | `SMALLINT` | `NOT NULL DEFAULT 0`. Se reinicia al ingresar bien (S-14, *Propuesta*) |
| **`bloqueado_hasta`** | `TIMESTAMPTZ NULL` | Bloqueo temporal por intentos fallidos (S-14, *Propuesta*) |
| `cedula` | `TEXT NULL` | Única entre los no eliminados; dato personal |
| `celula_id` | `UUID NULL` FK → `celulas.id` | `RESTRICT` |
| `rol` | `TEXT` | `NOT NULL CHECK (rol IN ('VIAJERO','FINANCIERO','ADMIN','SUPERADMIN'))` |
| `cargo_id` | `UUID NULL` FK → `cargos.id` | `RESTRICT` |
| **`es_prestador_servicios`** | `BOOLEAN` | `NOT NULL DEFAULT false`. `true` = prestador de servicios externo; define la tabla tarifaria y la regla de formato adjunto (RN-29, RN-33) |
| **`fecha_nacimiento`** | `DATE NULL` | Para la emisión de tiquetes (RN-31). Dato personal (RNF-09) |
| **`firma_archivo_id`** | `UUID NULL` FK → `archivos.id` | Firma guardada en el perfil, reutilizable en las solicitudes (RN-32). `RESTRICT`. La FK se agrega cuando existe `archivos` (semana 2) |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true` (RN-11) |
| `google_sub` | `TEXT NULL` | `UNIQUE`; se fija en el primer login con Google. `CHECK ck_usuarios__google_solo_superadmin`: `rol = 'SUPERADMIN' OR google_sub IS NULL` |
| `ultimo_acceso` | `TIMESTAMPTZ NULL` | |

> **Ya no es cierto que "no exista contraseña"** (RN-15 reemplazada): existe `password_hash`, pero solo para operativos, y la BD lo garantiza con el `CHECK` por rol. **Cambio de rol:** promover a `SUPERADMIN` exige poner `password_hash = NULL` y `debe_cambiar_password = false` en la misma operación (el `CHECK` lo obliga); degradar a operativo exige `username` y una contraseña temporal. **No se desactiva ni se degrada al último SUPERADMIN activo** (lo valida el service con bloqueo de fila; ver §8). En usuarios se usa `activo` y no `deleted_at`.
>
> Los usuarios ya creados por `S1-07` (solo el SUPERADMIN inicial) cumplen los `CHECK` nuevos sin transformar datos.

### 2.3 Catálogos: `proyectos`, `rubros`, `celulas` (DP-14 ✅, ADR-022)

Tres tablas con la **misma estructura**, administradas solo por SUPERADMIN (RN-24). Sin valores en el código.

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `UUID` PK | |
| `nombre` | `TEXT` | `NOT NULL`; `UNIQUE (lower(nombre))` |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true` |
| `orden` | `SMALLINT NULL` | |
| `created_at`, `updated_at`, `created_by`, `updated_by`, `migrado_de` | | Auditoría estándar |

**Solo `proyectos`** agrega:

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `codigo` | `TEXT NULL` | Código corto del proyecto (p. ej. `P-CONEXI-002`, de la hoja `PROYECTOS`). Único si no es nulo. Lo usa el formulario de solicitud |
| **`exige_formato_prestador`** | `BOOLEAN` | `NOT NULL DEFAULT false`. Si es `true` y el viajero es prestador, la solicitud no calcula por tabla y exige formato adjunto (RN-33). Sustituye la lista fija del código de `javaScript.html` |

- Sin `deleted_at`: se desactivan.
- Valores iniciales: de la exportación de AppSheet (P-2) y de la hoja `PROYECTOS` del Apps Script.
- Renombrar se audita (`CATALOGO_EDITAR`). El rol no es un catálogo.

### 2.4 `archivos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id`, `created_at`, `created_by` | | |
| `storage_key` | `TEXT` | `UNIQUE NOT NULL` (clave en el bucket S3) |
| `nombre_original` | `TEXT` | `NOT NULL` |
| `mime_type` | `TEXT` | `NOT NULL` (por contenido) |
| `tamano_bytes` | `INTEGER` | `NOT NULL CHECK (tamano_bytes <= 10485760)` |
| `sha256` | `TEXT` | `NOT NULL` |
| `proposito` | `TEXT` | `NOT NULL CHECK (proposito IN ('SOPORTE','ARCHIVO','FIRMA','FORMATO_PRESTADOR'))`. El service valida que el tipo MIME corresponda al propósito (RN-13) |

### 2.5 `tarifas_viaticos` (DP-20 ✅, ADR-030)

Tarifas por **ciudad de destino** y **tipo de vinculación**. Reemplaza las tablas `gastosViaje2025` (empleados) y `prestadores` de `calcularGastos.html`. Administrada solo por SUPERADMIN (RN-24, RF-018).

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `UUID` PK | |
| `ciudad` | `TEXT` | `NOT NULL`. Nombre del destino tal como aparece en el formulario (22 en el seed: Cali, Bogotá, Medellín, Barranquilla, Buenaventura, Palmira, Tuluá, Florida, Pichindé Valle, Dagua, Pradera, Sevilla, Ginebra, Versalles, Candelaria, Yumbo, Roldanillo, Cartago, Buga, Cumbre, Putumayo, Otro) |
| `es_prestador_servicios` | `BOOLEAN` | `NOT NULL`. `false` = tarifa de empleado interno; `true` = tarifa de prestador |
| `vr_alimentacion` | `NUMERIC(14,2)` | `NOT NULL CHECK (>= 0)`. Por día |
| `otros_gastos` | `NUMERIC(14,2)` | `NOT NULL CHECK (>= 0)`. Por día |
| `transporte_aeropuerto` | `NUMERIC(14,2)` | `NOT NULL CHECK (>= 0)`. Por trayecto/destino |
| `transporte_intermunicipal` | `NUMERIC(14,2)` | `NOT NULL CHECK (>= 0)`. Por trayecto/destino |
| `trans_interno_dia_1` | `NUMERIC(14,2)` | `NOT NULL CHECK (>= 0)`. Transporte interno si `dias_estadia = 1` |
| `trans_interno_varios_dias` | `NUMERIC(14,2)` | `NOT NULL CHECK (>= 0)`. Transporte interno si `dias_estadia > 1` |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true` |
| `orden` | `SMALLINT NULL` | Orden en el selector (por defecto, el del formulario original) |
| `created_at`, `updated_at`, `created_by`, `updated_by`, `migrado_de` | | |

- `UNIQUE (lower(ciudad), es_prestador_servicios)`: una fila por ciudad y tipo (hasta **44** filas en el seed: 22 × 2).
- **No se borra:** se desactiva. Cambiar una tarifa **no** altera solicitudes ya creadas: `viatico_trayectos` guarda una instantánea (§2.7).
- **Seed:** los valores oficiales (entregados por el dueño del producto el 2026-11-12, extraídos de `calcularGastos.html`) están en **`backend/app/modules/catalogos/datos/tarifas_viaticos.csv`** (44 filas; ver el `README.md` de esa carpeta). La ciudad visible usa la grafía en español (`Bogotá`, `Pichindé Valle`) y el identificador del código legado (`Bogota`, `PichindeValle`) va a `migrado_de`. El comando de carga (S2-01) es idempotente (clave: ciudad + tipo). **Los valores no se escriben en el código ni en las migraciones** (DP-14).
- **Ciudad = destino de lista cerrada:** la lista de ciudades del selector sale de aquí (filas activas del tipo del viajero). `"Otro"` es una fila más, con su propia tarifa.
- Cambios auditados: `TARIFA_CREAR`, `TARIFA_EDITAR`, `TARIFA_DESACTIVAR`.

### 2.6 `viaticos` (entidad unificada, DP-19 ✅, ADR-029)

Reemplaza a `legalizaciones`. Un registro recorre la etapa `SOLICITUD` y la `LEGALIZACION` con el **mismo id y folio**.

**Identidad y modalidad**

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `folio` | `TEXT` | `UNIQUE NOT NULL`, `DEFAULT 'VT-' \|\| lpad(nextval('seq_folio_viaticos')::text, 6, '0')` |
| `modalidad` | `TEXT` | `NOT NULL CHECK (modalidad IN ('CON_SOLICITUD','LEGALIZACION_DIRECTA'))`. Inmutable |
| `etapa` | `TEXT` | `NOT NULL CHECK (etapa IN ('SOLICITUD','LEGALIZACION'))`. `CON_SOLICITUD` inicia en `SOLICITUD`; `LEGALIZACION_DIRECTA` en `LEGALIZACION`. `CHECK`: `modalidad = 'CON_SOLICITUD' OR etapa = 'LEGALIZACION'` |
| `usuario_id` | `UUID` FK → `usuarios.id` | `NOT NULL`: el viajero dueño |
| `motivo_viaje` | `TEXT` | `NOT NULL`, 3 a 500 caracteres |
| `fecha_legalizacion` | `DATE` | `NOT NULL DEFAULT current_date`. Fecha de creación del registro (AppSheet) |

**Instantánea del colaborador (RN-17, ADR-020)**

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `colaborador_nombre` | `TEXT NOT NULL` | |
| `colaborador_cargo`, `colaborador_cedula`, `colaborador_celula` | `TEXT NULL` | Cédula = dato personal; célula por nombre (histórico) |
| `colaborador_es_prestador` | `BOOLEAN NOT NULL` | Tipo de vinculación al crear; define las tarifas aplicadas |
| `colaborador_fecha_nacimiento` | `DATE NULL` | Obligatoria si `requiere_tiquete` (RN-31) |

**Datos de la solicitud** (solo con `modalidad = 'CON_SOLICITUD'`; nulos en `LEGALIZACION_DIRECTA`)

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `proyecto_id` | `UUID NULL` FK → `proyectos.id` | `RESTRICT`. Obligatorio en `CON_SOLICITUD` |
| `lider_proyecto` | `TEXT NULL` | Gerente/líder del proyecto. Obligatorio en `CON_SOLICITUD` |
| `empresa` | `TEXT NULL` | Opcional |
| `requiere_tiquete` | `BOOLEAN NOT NULL DEFAULT false` | Si `true`, exige `colaborador_fecha_nacimiento` (RN-31) |
| `requiere_gastos_viaje` | `BOOLEAN NOT NULL DEFAULT false` | Si `false`, no hay cálculo presupuestal (RN-29) |
| `presupuesto_solicitado` | `NUMERIC(14,2) NULL` | `CHECK (>= 0)`. Calculado por el servidor (RN-29); `NULL` si no aplica (S-11). **Referencia sugerida para `valor_asignado`** (RN-19) |
| `comentarios` | `TEXT NULL` | Justificación si pide más (RN-29) |
| `firma_archivo_id` | `UUID NULL` FK → `archivos.id` | Firma del solicitante incrustada en el PDF (RN-32) |
| `formato_adjunto_id` | `UUID NULL` FK → `archivos.id` | Formato PDF/XLSX del prestador (RN-33) |
| `solicitud_aprobada_at` | `TIMESTAMPTZ NULL` | Marca de la aprobación de la solicitud (la fuente es `viatico_eventos`) |
| `legalizacion_habilitada_at` | `TIMESTAMPTZ NULL` | Cuándo pasó a la etapa `LEGALIZACION` |

**Estados y dinero**

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `recursos_propios` | `BOOLEAN` | `NOT NULL DEFAULT false`. Lo marca el viajero al crear (DP-17). `CHECK ck_viaticos__recursos_propios_directa`: `NOT recursos_propios OR modalidad = 'LEGALIZACION_DIRECTA'` |
| `valor_asignado` | `NUMERIC(14,2)` | `NOT NULL DEFAULT 0 CHECK (>= 0)`. El `Valor_T`; solo FINANCIERO/SUPERADMIN (RN-19) |
| `valor_transferido` | `NUMERIC(14,2)` | **`GENERATED ALWAYS AS (CASE WHEN recursos_propios THEN 0 ELSE valor_asignado END) STORED`** (RN-14) |
| `estado` | `TEXT` | Operativo. `NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO'))`. Aplica a **ambas** etapas (RN-20) |
| `estado_financiero` | `TEXT` | `NOT NULL DEFAULT 'PENDIENTE' CHECK (estado_financiero IN ('PENDIENTE','TRANSFERIDO','PAGADO','PROCESADO'))` (RN-22) |
| `aprobada_at` | `TIMESTAMPTZ NULL` | Última aprobación (de la etapa vigente) |
| `devuelta_at` | `TIMESTAMPTZ NULL` | Última devolución (S-01) |
| `estado_financiero_at` | `TIMESTAMPTZ NULL` | |
| `observaciones` | `TEXT NULL` | Último comentario de revisión |

**Restricciones de coherencia**

- `ck_viaticos__liquidacion_requiere_aprobado`: `estado_financiero NOT IN ('PAGADO','PROCESADO') OR (estado = 'APROBADO' AND etapa = 'LEGALIZACION')` (RN-03).
- `ck_viaticos__solicitud_solo_con_solicitud`: si `modalidad = 'LEGALIZACION_DIRECTA'`, entonces `proyecto_id`, `lider_proyecto`, `presupuesto_solicitado`, `firma_archivo_id`, `formato_adjunto_id`, `solicitud_aprobada_at` y `legalizacion_habilitada_at` son `NULL` y `requiere_tiquete = requiere_gastos_viaje = false`.
- `ck_viaticos__legalizacion_habilitada`: `etapa = 'LEGALIZACION' AND modalidad = 'CON_SOLICITUD'` implica `legalizacion_habilitada_at IS NOT NULL`.
- La obligatoriedad completa de la solicitud (trayectos, firma, formato, fecha de nacimiento) es **de servicio** (RN-06), porque la solicitud se guarda como borrador `PENDIENTE` antes de estar completa.

> Reglas de transición (aprobar, habilitar legalización, RN-27) no son `CHECK`: las aplica `transicionar()` (`docs/architecture.md` §3).
> `Estado legalizacion` no se almacena (RN-23). `DEVUELTO`/`CANCELADO` se añadirían ampliando el `CHECK`.

### 2.7 `viatico_trayectos`

De **1 a 5** tramos por solicitud (RN-30). Solo existen en viáticos `CON_SOLICITUD`.

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* (sin `deleted_at`) | | Los trayectos se reemplazan en bloque mientras la solicitud es editable |
| `viatico_id` | `UUID` FK → `viaticos.id` | `NOT NULL ON DELETE CASCADE` |
| `orden` | `SMALLINT` | `NOT NULL CHECK (orden BETWEEN 1 AND 5)`; `UNIQUE (viatico_id, orden)` |
| `ciudad_origen` | `TEXT` | `NOT NULL` |
| `ciudad_destino` | `TEXT` | `NOT NULL`. `CHECK (ciudad_destino <> ciudad_origen OR ciudad_destino = 'Otro')` (RN-30) |
| `fecha_ida` | `TIMESTAMPTZ` | `NOT NULL` |
| `fecha_regreso` | `TIMESTAMPTZ` | `NOT NULL CHECK (fecha_regreso >= fecha_ida)` |
| `requiere_hospedaje` | `BOOLEAN` | `NOT NULL DEFAULT false` |
| `dias_estadia` | `SMALLINT` | `NOT NULL CHECK (dias_estadia >= 1)`. Sugerido `ceil(fecha_regreso − fecha_ida) + 1`; editable |
| `tarifa_id` | `UUID NULL` FK → `tarifas_viaticos.id` | Fila de tarifa aplicada (destino + tipo). `RESTRICT`. `NULL` si no se calculó (RN-33 o `requiere_gastos_viaje = false`) |
| `vr_alimentacion`, `otros_gastos`, `trans_interno`, `transporte_aeropuerto`, `transporte_intermunicipal` | `NUMERIC(14,2) NULL` | **Instantánea** de las tarifas usadas (`trans_interno` ya resuelto según `dias_estadia`). Congela el cálculo aunque la tarifa cambie |
| `subtotal_estadia` | `NUMERIC(14,2) NULL` | `(vr_alimentacion + trans_interno + otros_gastos) × dias_estadia` |

`viaticos.presupuesto_solicitado = Σ(subtotal_estadia + transporte_aeropuerto + transporte_intermunicipal)` de sus trayectos (RN-29). Lo calcula un servicio puro; el cliente no envía importes.

### 2.8 `gastos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | `created_by` = `Creador` |
| **`viatico_id`** | `UUID` FK → `viaticos.id` | `NOT NULL ON DELETE RESTRICT`. Reemplaza `legalizacion_id`. Solo se crean gastos con `etapa = 'LEGALIZACION'` (lo valida el service) |
| `fecha_factura` | `DATE` | `NOT NULL`; no futura (RN-07). Fecha de análisis de los indicadores |
| `rubro_id` | `UUID` FK → `rubros.id` | `NOT NULL RESTRICT` |
| `proyecto_id` | `UUID` FK → `proyectos.id` | `NOT NULL RESTRICT` |
| `concepto` | `TEXT` | `NOT NULL` |
| `cc_nit`, `empresa` | `TEXT NULL` | Proveedor |
| `valor` | `NUMERIC(14,2)` | `NOT NULL CHECK (valor > 0)` |
| `soporte_id` | `UUID NULL` FK → `archivos.id` | Imagen (RN-13) |
| `archivo_id` | `UUID NULL` FK → `archivos.id` | PDF (RN-13) |
| `observaciones` | `TEXT NULL` | |

> **Adjunto mínimo (RN-21):** `soporte_id IS NOT NULL OR archivo_id IS NOT NULL` es obligatorio para Aprobar y liquidar, no para guardar. Lo valida `transicionar()`; la vista expone `gastos_sin_comprobante`.

### 2.9 `viatico_eventos` (historial, solo inserción)

Reemplaza a `legalizacion_eventos`.

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `UUID` PK | |
| `viatico_id` | `UUID` FK | `NOT NULL` |
| `etapa` | `TEXT` | `NOT NULL CHECK (etapa IN ('SOLICITUD','LEGALIZACION'))`. Etapa en la que ocurrió el evento |
| `accion` | `TEXT` | `CHECK (accion IN ('CREAR','EDITAR_SOLICITUD','APROBAR','RECHAZAR','DEVOLVER','GESTIONAR_TIQUETES','HABILITAR_LEGALIZACION','CAMBIAR_ESTADO_FINANCIERO','EDITAR_VALOR_ASIGNADO','CAMBIAR_RECURSOS_PROPIOS','LIQUIDAR','ELIMINAR'))`. `LIQUIDAR` registra reintegro o reembolso (datos: `{saldo, sentido}`) |
| `dimension` | `TEXT NULL` | `CHECK (dimension IN ('OPERATIVO','FINANCIERO','ETAPA'))` |
| `estado_anterior`, `estado_nuevo` | `TEXT NULL` | |
| `comentario` | `TEXT NULL` | Obligatorio en `DEVOLVER` y `RECHAZAR` (service, RN-10) |
| `datos` | `JSONB NULL` | P. ej. `{valor_asignado: {antes, despues}}`, `{presupuesto_solicitado}` |
| `usuario_id` | `UUID` FK | `NOT NULL` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |

### 2.10 `auditoria` (solo inserción)

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `BIGINT IDENTITY` | |
| `usuario_id` | `UUID NULL` | Actor (FK `SET NULL`) |
| `accion` | `TEXT` | Seguridad y administración: **`LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `PASSWORD_CAMBIADA`, `PASSWORD_RECUPERACION_SOLICITADA`, `ACCESO_DENEGADO`, `SUPERADMIN_ASIGNADO`**, `USUARIO_CREAR`, `ROL_CAMBIAR`, `USUARIO_DESACTIVAR`, `CATALOGO_*`, `TARIFA_*`, … |
| `entidad`, `entidad_id` | `TEXT`, `UUID NULL` | |
| `datos` | `JSONB` | Diferencias sin secretos (se rechazan `password`, `password_hash`, `token`, …) ni cédula completa |
| `ip`, `user_agent` | `INET`, `TEXT` | |
| `created_at` | `TIMESTAMPTZ` | |

> `LOGIN_FALLIDO` guarda el `username` o correo intentado (no la contraseña) y el motivo genérico; `usuario_id` solo si el usuario existe.

### 2.11 `sesiones`

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `UUID` PK | |
| `usuario_id` | `UUID` FK | `NOT NULL CASCADE` |
| `token_hash` | `TEXT` | `UNIQUE`, `CHECK` de 64 hex (SHA-256 del refresh) |
| `expires_at`, `revoked_at` | `TIMESTAMPTZ` | |
| `created_at`, `user_agent`, `ip` | | |

### 2.12 `tokens_recuperacion_password` (nueva; RN-15, ADR-027)

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `UUID` PK | `DEFAULT gen_random_uuid()` |
| `usuario_id` | `UUID` FK → `usuarios.id` | `NOT NULL ON DELETE CASCADE` |
| `token_hash` | `TEXT` | `NOT NULL UNIQUE`; **`CHECK (token_hash ~ '^[0-9a-f]{64}$')`** (SHA-256 en hexadecimal): un token en claro no puede guardarse |
| `expires_at` | `TIMESTAMPTZ` | `NOT NULL`, `CHECK (expires_at > created_at)`. TTL de 15–30 min (variable `PASSWORD_RESET_TTL_MINUTES`) |
| `used_at` | `TIMESTAMPTZ NULL` | Marca el uso (un solo uso) |
| `ip` | `INET NULL` | IP de quien lo pidió |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |

- Índices: `UNIQUE (token_hash)`, `(usuario_id)`, `(expires_at)`.
- El token en claro (aleatorio de 32 bytes, URL-safe) solo viaja por correo; en la BD está su SHA-256.
- Al pedir uno nuevo se invalidan los anteriores del usuario (`used_at = now()`); al restablecer se revocan todas las `sesiones`.
- Privilegios de `trulab_app`: `SELECT, INSERT, UPDATE` (marcar uso); sin `DELETE`. Limpieza de vencidos: tarea futura.

### 2.13 Enums del sistema (no administrables)

| Enum | Usado en | Valores |
| :--- | :--- | :--- |
| `ROLES` | `usuarios.rol` | `VIAJERO`, `FINANCIERO`, `ADMIN`, `SUPERADMIN` |
| `MODALIDADES` | `viaticos.modalidad` | `CON_SOLICITUD`, `LEGALIZACION_DIRECTA` |
| `ETAPAS` | `viaticos.etapa`, `viatico_eventos.etapa` | `SOLICITUD`, `LEGALIZACION` |
| `ESTADOS` | `viaticos.estado` | `PENDIENTE`, `APROBADO`, `RECHAZADO` |
| `ESTADOS_FINANCIEROS` | `viaticos.estado_financiero` | `PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO` |

`TEXT` + `CHECK`, expuestos en `app/core/enums.py`. Las listas de negocio (proyectos, rubros, células, tarifas) son tablas.

### 2.14 Vista `v_viatico_saldos` (fuente única del saldo, ADR-008)

```
v_viatico_saldos(
  viatico_id, folio, usuario_id, modalidad, etapa, estado, estado_financiero, fecha_legalizacion,
  recursos_propios, valor_asignado,
  valor_transferido,                       -- columna generada (RN-14)
  presupuesto_solicitado,                  -- referencia, no entra al saldo
  total_gastos     = COALESCE(SUM(g.valor) FILTER (WHERE g.deleted_at IS NULL), 0),
  cantidad_gastos  = COUNT(g.id) FILTER (WHERE g.deleted_at IS NULL),
  gastos_sin_comprobante = COUNT(g.id) FILTER (
      WHERE g.deleted_at IS NULL AND g.soporte_id IS NULL AND g.archivo_id IS NULL),  -- RN-21
  saldo            = valor_transferido − total_gastos
)
-- viaticos v LEFT JOIN gastos g … WHERE v.deleted_at IS NULL GROUP BY v.id
-- security_invoker = true para respetar el RLS de las tablas base.
```

`saldo > 0` ⇒ reintegro a la empresa; `saldo < 0` ⇒ reembolso al viajero (RN-02). En `etapa = 'SOLICITUD'` el saldo no es significativo (sin gastos) y la UI no lo muestra.

Los **indicadores** no usan esta vista como base temporal: agrupan `gastos` por `proyecto_id` filtrando `fecha_factura BETWEEN desde AND hasta`.

## 3. Relaciones y cardinalidades

| Relación | Cardinalidad | Regla de borrado |
| :--- | :--- | :--- |
| `cargos` → `usuarios` | 1 : N | `RESTRICT` |
| `celulas` → `usuarios` | 1 : N | `RESTRICT` |
| `archivos` → `usuarios` (firma) | 1 : 0..1 | `RESTRICT` |
| `usuarios` → `viaticos` | 1 : N | `RESTRICT` |
| `proyectos` → `viaticos` (cabecera de solicitud) | 1 : N | `RESTRICT` |
| `viaticos` → `viatico_trayectos` | 1 : 1..5 (solo `CON_SOLICITUD`) | `CASCADE` |
| `tarifas_viaticos` → `viatico_trayectos` | 1 : N | `RESTRICT` |
| `archivos` → `viaticos` (firma, formato) | 1 : 0..1 cada uno | `RESTRICT` |
| `viaticos` → `gastos` | 1 : 0..N (solo en etapa `LEGALIZACION`) | `RESTRICT`; borrado lógico en cascada desde el service |
| `proyectos` / `rubros` → `gastos` | 1 : N | `RESTRICT` |
| `archivos` → `gastos` (soporte, archivo) | 1 : 0..1 | `RESTRICT` |
| `viaticos` → `viatico_eventos` | 1 : N (≥1) | Nunca se borran |
| `usuarios` → `sesiones` | 1 : N | `CASCADE` |
| `usuarios` → `tokens_recuperacion_password` | 1 : N | `CASCADE` |
| `usuarios` → `auditoria` | 1 : N | `SET NULL` |

## 4. Diagrama de relaciones (texto)

```
 ┌────────┐  ┌────────┐                       ┌──────────────────────────┐
 │ cargos │  │celulas │                       │  tarifas_viaticos        │ (catálogo, SUPERADMIN)
 └───┬────┘  └───┬────┘                       │ ciudad + es_prestador    │
     │ 1         │ 1                          │ 6 conceptos tarifarios   │
     │ 0..N      │ 0..N                       └────────────┬─────────────┘
┌─────────┐ N 1 ┌┴───────────────────────────────┐        │ 1
│sesiones │─────│           usuarios             │ 1  N   │ 0..N
└─────────┘     │ rol, username, password_hash*  │──── auditoria
┌──────────────┐│ es_prestador_servicios         │
│tokens_recup. ││ fecha_nacimiento, firma        │   *solo operativos; SUPERADMIN = Google
│  _password   │└───────────────┬────────────────┘
└──────┬───────┘                │ 1 (dueño / viajero)
       └─ N:1 usuarios          │ 0..N
                     ┌──────────┴─────────────────────┐ 1       1..N ┌────────────────┐
 ┌───────────┐ 1  N  │            viaticos            │──────────────│ viatico_eventos│
 │ proyectos │───────│ folio VT-, modalidad, etapa    │              └────────────────┘
 └───────────┘       │ estado (operativo)             │ 1   1..5  ┌──────────────────┐
                     │ estado_financiero              │───────────│ viatico_trayectos│─ tarifa_id → tarifas
                     │ solicitud: proyecto, líder,    │           │ origen, destino  │
                     │  tiquete, presupuesto, firma   │           │ fechas, días,    │
                     │ recursos_propios, valor_asig.  │           │ instantánea tarif│
                     │ valor_transferido (gen)        │           └──────────────────┘
                     └──────────┬─────────────────────┘
                                │ 1   0..N (etapa LEGALIZACION)
 ┌──────────────┐ 1  N  ┌───────┴────────────┐ 0..1   1 ┌──────────────┐
 │ proyectos/   │───────│       gastos       │──────────│   archivos   │ (S3)
 │ rubros       │       │ fecha_factura,valor│ soporte  │ proposito    │
 └──────────────┘       └────────────────────┘ archivo  └──────────────┘

   v_viatico_saldos = viaticos ⟕ Σ gastos   (saldo calculado)
```

## 5. Índices recomendados

| Tabla | Índice | Motivo |
| :--- | :--- | :--- |
| `usuarios` | `UNIQUE (correo)`, **`UNIQUE (username)`** | Login y recuperación |
| `usuarios` | `UNIQUE (cedula) WHERE deleted_at IS NULL AND cedula IS NOT NULL` | Duplicados |
| `usuarios` | `(rol) WHERE activo` | Listados; contar SUPERADMIN activos (`WHERE rol = 'SUPERADMIN' AND activo`) |
| `usuarios` | `(celula_id)`, `(cargo_id)` | FK |
| `cargos` | `UNIQUE (lower(nombre)) WHERE deleted_at IS NULL` | |
| `proyectos`, `rubros`, `celulas` | `UNIQUE (lower(nombre))`; `proyectos`: `UNIQUE (codigo) WHERE codigo IS NOT NULL` | RN-24 |
| `tarifas_viaticos` | `UNIQUE (lower(ciudad), es_prestador_servicios)` | Una fila por ciudad y tipo |
| `viaticos` | `(usuario_id, etapa, estado) WHERE deleted_at IS NULL` | "Mis viáticos" |
| `viaticos` | `(estado, estado_financiero, etapa, fecha_legalizacion DESC) WHERE deleted_at IS NULL` | Bandeja de ADMIN y vista de pagos |
| `viaticos` | `UNIQUE (folio)`; `UNIQUE (migrado_de) WHERE migrado_de IS NOT NULL` | Búsqueda; ETL idempotente |
| `viaticos` | `(proyecto_id)` | FK |
| `viatico_trayectos` | `UNIQUE (viatico_id, orden)`, `(tarifa_id)` | |
| `gastos` | `(viatico_id) WHERE deleted_at IS NULL` | Suma del saldo |
| `gastos` | `(fecha_factura, proyecto_id) WHERE deleted_at IS NULL` | Indicadores |
| `gastos` | `(rubro_id)`, `(proyecto_id)` | FK |
| `archivos` | `(sha256)` | Duplicados |
| `viatico_eventos` | `(viatico_id, created_at)` | Historial |
| `sesiones` | `UNIQUE (token_hash)`, `(usuario_id)` | |
| `tokens_recuperacion_password` | `UNIQUE (token_hash)`, `(usuario_id)`, `(expires_at)` | |
| `auditoria` | `(entidad, entidad_id)`, `(created_at)`, `(accion, created_at)` | Consultas y alertas de `LOGIN_FALLIDO` |

Todas las FK llevan índice.

## 6. Estrategia RLS

**Objetivo:** que RN-01 se cumpla aunque falle el código de la aplicación (ADR-007).

1. Roles de BD: `trulab_owner` (migraciones) y `trulab_app` (la API, sin `BYPASSRLS` ni propiedad). En RDS, `rds_superuser` solo se usa para el arranque.
2. En cada transacción: `SET LOCAL app.usuario_id = '<uuid>'; SET LOCAL app.rol = '<ROL>';`.
3. RLS en `viaticos`, `viatico_trayectos` y `gastos` (`ENABLE` + `FORCE`).
4. Políticas:

```
-- viaticos
POLICY ver_propios_o_privilegiado FOR ALL TO trulab_app
  USING ( current_setting('app.rol', true) IN ('FINANCIERO','ADMIN','SUPERADMIN')
          OR usuario_id = current_setting('app.usuario_id', true)::uuid )
  WITH CHECK (misma condición);

-- viatico_trayectos y gastos: se apoyan en la visibilidad del viático
POLICY ... USING (EXISTS (SELECT 1 FROM viaticos v WHERE v.id = <tabla>.viatico_id))
```

5. Sin variables definidas, `current_setting(..., true)` es `NULL` y la política deniega.
6. **Login:** la autenticación consulta `usuarios` **antes** de existir un contexto de usuario. `usuarios`, `sesiones` y `tokens_recuperacion_password` **no llevan RLS** (el acceso se controla en el service y por privilegios). Si más adelante se quiere RLS en `usuarios`, el login deberá usar una función `SECURITY DEFINER` acotada (ADR futuro).
7. Catálogos y `tarifas_viaticos` sin RLS: todos los roles leen; la escritura (solo SUPERADMIN) se controla en el service.
8. **Pruebas:** con `trulab_app` y `app.rol='VIAJERO'`, un `SELECT` sin `WHERE` devuelve solo filas propias.

> RLS no reemplaza las reglas de estado, etapa ni de rol (RN-19, RN-20, RN-22, RN-27), que viven en el service y en su prueba RBAC.

## 7. Estrategia de auditoría

1. **Columnas base** en todas las tablas.
2. **`viatico_eventos`:** historial funcional (etapa, estado operativo y financiero, tiquetes, valor asignado, recursos propios, liquidación). Se muestra en la UI y en los PDF; se escribe en la misma transacción que el cambio.
3. **`auditoria`:** seguridad y administración (**accesos, contraseñas, SUPERADMIN**, usuarios, roles, catálogos, tarifas, eliminaciones). Solo la consulta SUPERADMIN.

Las tablas de eventos y auditoría son de solo inserción (`REVOKE` + trigger en `auditoria`). **Nunca** se guardan contraseñas, hashes de contraseña, tokens ni contenido de archivos (`app/core/audit.py` rechaza esas claves).

## 8. Estrategia de eliminación lógica

- `cargos`, `viaticos` y `gastos` usan `deleted_at`; las consultas del ORM lo filtran por defecto.
- Los `UNIQUE` de negocio son parciales (`WHERE deleted_at IS NULL`).
- Un viático solo se elimina con `estado = 'PENDIENTE'` y `estado_financiero = 'PENDIENTE'` (RN-09). Sus gastos se marcan eliminados en la misma transacción y se registra el evento `ELIMINAR`. Un viático `CON_SOLICITUD` ya `TRANSFERIDO` no se elimina.
- Un cargo con usuarios asociados no se elimina (409).
- Usuarios, catálogos y tarifas se **desactivan**. **Último SUPERADMIN activo:** antes de desactivar o degradar a un SUPERADMIN, el service toma `SELECT … FOR UPDATE` sobre los SUPERADMIN activos y verifica que quede al menos uno distinto; si no, `409 ULTIMO_SUPERADMIN`.
- Purga física: fuera del MVP.

## 9. Convenciones de nomenclatura

| Elemento | Convención | Ejemplo |
| :--- | :--- | :--- |
| Tablas | `snake_case`, plural, español | `viaticos`, `gastos`, `tarifas_viaticos` |
| Columnas | `snake_case`, singular | `fecha_factura`, `valor_asignado` |
| PK / FK | `id` / `<entidad_singular>_id` | `usuario_id`, `viatico_id` |
| Fechas sin hora | `fecha_*` (`DATE`) | `fecha_legalizacion`, `fecha_nacimiento` |
| Marcas de tiempo | `*_at` (`TIMESTAMPTZ`, UTC) | `aprobada_at`; en trayectos `fecha_ida`/`fecha_regreso` son `TIMESTAMPTZ` por el formulario original |
| Booleanos | adjetivo/participio claro | `activo`, `recursos_propios`, `es_prestador_servicios` |
| Dinero | `NUMERIC(14,2)` | `valor_transferido`, `vr_alimentacion` |
| Instantáneas | `<entidad>_<campo>` | `colaborador_cargo` |
| Enums de sistema | `TEXT` + `CHECK`, `MAYUSCULAS` | `'PENDIENTE'` |
| Índices | `ix_<tabla>__<columnas>` | |
| Únicos | `uq_<tabla>__<columnas>` | `uq_usuarios__username` |
| FK (constraint) | `fk_<tabla>__<columna>__<tabla_ref>` | |
| Checks | `ck_<tabla>__<regla>` | `ck_usuarios__password_segun_rol` |
| Vistas | `v_<nombre>` | `v_viatico_saldos` |
| Migraciones Alembic | `AAAAMMDD_HHMM_<descripcion>` | `20261113_0900_usuarios_acceso_hibrido` |

## 10. Extensiones requeridas

`pgcrypto` y `citext` (ya instaladas por la migración base).

## 11. Folios (RN-04)

- Una secuencia por entidad: `seq_folio_cargos` (existe) y **`seq_folio_viaticos`** (nueva; reemplaza a `seq_folio_legalizaciones`, que nunca se creó).
- `DEFAULT 'VT-' || lpad(nextval('seq_folio_viaticos')::text, 6, '0')`. Pueden quedar huecos.
- El folio `VT-` se asigna **al crear** el registro y **no cambia** al pasar de `SOLICITUD` a `LEGALIZACION` (ADR-029).
- ETL: los viáticos históricos reciben un `VT-` nuevo; el `ID legalizacion` de AppSheet queda en `migrado_de` (DP-09, recomendación). Si DP-09 resolviera conservar los IDs, se ajusta con `setval`.

## 12. Notas para el ETL (fase F10)

- **Orden:** catálogos → `tarifas_viaticos` (seed, no del ETL de AppSheet) → cargos → usuarios → viáticos → archivos → gastos. Idempotente por `migrado_de`.
- **Usuarios:** el ETL crea un `username` por usuario operativo y una contraseña temporal (con `debe_cambiar_password = true`) enviada por correo; los `SUPERADMIN` migrados quedan sin contraseña y con correo `@trulab.co` (si algún SUPERADMIN histórico no tiene correo `@trulab.co`, se reporta y se decide con el negocio).
- **Viáticos históricos:** `modalidad = 'LEGALIZACION_DIRECTA'`, `etapa = 'LEGALIZACION'`; los campos de solicitud quedan nulos. `es_prestador_servicios` se completa con el dueño del producto (no existe en AppSheet).
- **Catálogos:** de los valores distintos de `Proyecto`, `Rubro` y `Celula`, conservando la grafía; informe de duplicados.
- **Datos del colaborador:** de las columnas propias de `Crear_legalizacion` (instantánea histórica).
- **Valor transferido:** se migran `Valor_T` y `Recursos propios`; el `Valor transferido` de AppSheet concilia contra la columna generada.
- **Total Gastos / Saldo:** se concilian con `v_viatico_saldos`.
- **Estados:**

  | AppSheet `Estado` | → `estado` | AppSheet `Estado_P` | → `estado_financiero` |
  | :--- | :--- | :--- | :--- |
  | `Pendiente ⛔` | `PENDIENTE` | `Pendiente⌛` | `PENDIENTE` |
  | `Aprobado` | `APROBADO` | `Transferido` | `TRANSFERIDO` |
  | `Rechazado` | `RECHAZADO` | `Pagado` | `PAGADO` |
  | | | `Procesado` | `PROCESADO` |

  Un valor fuera de la tabla detiene el ETL. Filas con `Estado_P` en `PAGADO`/`PROCESADO` y `Estado` distinto de `Aprobado` violan `ck_viaticos__liquidacion_requiere_aprobado`: se reportan y se decide antes del corte.
- **Adjuntos:** `Soporte` → `soporte_id`, `Archivo` → `archivo_id` (por tipo real). Destino: bucket S3.
- **Segmentador:** no se migra. **`CorreosExternos` y `PROYECTOS` (Sheets):** `PROYECTOS` alimenta `proyectos`; `CorreosExternos` se revisa como fuente de `es_prestador_servicios` y correos de contacto.
