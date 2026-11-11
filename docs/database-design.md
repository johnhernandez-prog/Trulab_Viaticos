# Diseño de base de datos — Trulab Viajes

> Motor: PostgreSQL 16. Esquema: `public` (MVP). Migraciones solo con Alembic.
> **Modelo ajustado a la estructura y al comportamiento real de AppSheet** (DP-07 ✅, DP-13 a DP-17 ✅; `SPEC.md` §17.1 y §18). Ya no quedan decisiones pendientes que bloqueen la migración de la fase F4.

---

## 1. Correspondencia con AppSheet (validada)

### 1.1 Tablas

| AppSheet | Nuevo modelo | Comentario |
| :--- | :--- | :--- |
| `Cargos` | `cargos` | Igual, con folio (DP-09) |
| `Usuarios` | `usuarios` | Más `activo`, `ultimo_acceso`, `google_sub`. **Sin contraseña** (DP-01 ✅) |
| `Crear_legalizacion` | `legalizaciones` | Sustantivo plural. `Total Gastos` y `Saldo` no se almacenan: salen de la vista (ADR-008). `Estado legalizacion` no se almacena (espejo de `Estado`, RN-23) |
| `Registro_Gastos` | `gastos` + `archivos` | Los adjuntos pasan a ser archivos gestionados (clave de objeto, no URL pública) |
| `Segmentador` | **No se migra** | Es solo un filtro temporal: se reemplaza por los parámetros `desde`/`hasta` sobre `gastos.fecha_factura` (DP-02 ✅, DP-16 ✅, ADR-018, ADR-024) |
| Enum `Proyecto`, `Rubro`, `Celula` | Tablas maestras `proyectos`, `rubros`, `celulas` (§2.3) | Administrables por SUPERADMIN (DP-14 ✅, ADR-022) |
| Enum `Rol` | `usuarios.rol` (`TEXT` + `CHECK`) | Enum fijo del sistema: 4 roles |
| `SlicefiltrarporViajero`, `SliceUsuarios` | Autorización en el service + RLS | Ver §6 |
| — | `legalizacion_eventos` | Nuevo: historial (RN-10) |
| — | `auditoria` | Nuevo: acciones sensibles (RF-014) |
| — | `sesiones` | Nuevo: refresh tokens |

### 1.2 Campos (mapa para el ETL)

| AppSheet | Nuevo | Nota |
| :--- | :--- | :--- |
| **Cargos.**`ID Cargo` | `cargos.folio` (+ `migrado_de`) | DP-09: conservar como folio si es legible |
| Cargos.`Cargo` | `cargos.nombre` | |
| **Usuarios.**`ID usuario` | `usuarios.migrado_de` | La PK nueva es UUID |
| Usuarios.`Correo` | `usuarios.correo` | Clave de login (Google) |
| Usuarios.`Usuario` | `usuarios.nombre_completo` | |
| Usuarios.`Cargo` (Ref) | `usuarios.cargo_id` | Se resuelve por `ID Cargo` |
| Usuarios.`Cedula` | `usuarios.cedula` | Dato personal (RNF-09) |
| Usuarios.`Celula` (Enum) | `usuarios.celula_id` → `celulas` | Catálogo (DP-14 ✅) |
| Usuarios.`Rol` (Enum) | `usuarios.rol` | Mapeo directo a los 4 roles |
| **Crear_legalizacion.**`ID legalizacion` | `legalizaciones.folio` (+ `migrado_de`) | DP-09 |
| `Viajero` | `legalizaciones.usuario_id` | Se resuelve por correo |
| `Nombre Colaborador`, `Cargo`, `Cedula`, `Celula` | `legalizaciones.colaborador_*` | Instantánea al crear, en texto (ADR-020, RN-17) |
| `Motivo del viaje` | `legalizaciones.motivo_viaje` | |
| `Valor_T` | `legalizaciones.valor_asignado` | Lo registra FINANCIERO (DP-04 ✅) |
| `Valor transferido` | `legalizaciones.valor_transferido` | **Columna generada** (RN-14); en el ETL solo se usa para conciliar |
| `Recursos propios` (Yes/No) | `legalizaciones.recursos_propios` | Lo marca el viajero al crear (DP-17 ✅) |
| `Fecha legalizacion` | `legalizaciones.fecha_legalizacion` | |
| `Estado` (Enum) | `legalizaciones.estado` | `PENDIENTE` / `APROBADO` / `RECHAZADO` (DP-13 ✅) |
| `Estado_P` (Enum) | `legalizaciones.estado_financiero` | `PENDIENTE` / `TRANSFERIDO` / `PAGADO` / `PROCESADO` (DP-13 ✅) |
| `Estado legalizacion` | — (no se migra) | Fórmula `[Estado]`; el ETL verifica que coincida con `Estado` (RN-23) |
| `Total Gastos`, `Saldo` | `v_legalizacion_saldos` | Calculados; en el ETL solo se usan para conciliar |
| `Related Registro_Gastos` | Relación `gastos.legalizacion_id` | Virtual en AppSheet |
| **Registro_Gastos.**`ID Registro` | `gastos.migrado_de` | |
| `R_legalizacion` (Ref) | `gastos.legalizacion_id` | |
| `Creador` | `gastos.created_by` | Se resuelve por correo |
| `Fecha fact` | `gastos.fecha_factura` | **Fecha de análisis de los indicadores** (DP-16 ✅) |
| `Rubro` (Enum) | `gastos.rubro_id` → `rubros` | Catálogo (DP-14 ✅) |
| `Concepto` | `gastos.concepto` | Equivale a la "descripción" del informe |
| `CC_Nit` | `gastos.cc_nit` | Identificación del proveedor |
| `Proyecto` (Enum) | `gastos.proyecto_id` → `proyectos` | Catálogo (DP-02 ✅, DP-14 ✅) |
| `Empresa` | `gastos.empresa` | Razón social del proveedor |
| `Valor` | `gastos.valor` | |
| `Soporte` | `gastos.soporte_id` → `archivos` | **Imagen** (DP-15 ✅) |
| `Archivo` | `gastos.archivo_id` → `archivos` | **PDF** (DP-15 ✅) |
| `Observaciones` | `gastos.observaciones` | |

## 2. Entidades

Columnas comunes a **todas** las tablas operativas (en adelante, "columnas base"):

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `UUID` PK | `DEFAULT gen_random_uuid()` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | `DEFAULT now()` |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | Lo actualiza el ORM o un trigger |
| `created_by` | `UUID NULL` FK → `usuarios.id` | `NULL` para registros del sistema |
| `updated_by` | `UUID NULL` FK → `usuarios.id` | |
| `deleted_at` | `TIMESTAMPTZ NULL` | Eliminación lógica (§8) |
| `migrado_de` | `TEXT NULL` | ID original de AppSheet (trazabilidad e idempotencia del ETL); solo en las tablas migradas |

### 2.1 `cargos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `folio` | `TEXT` | `UNIQUE NOT NULL` (DP-09) |
| `nombre` | `TEXT` | `NOT NULL`; único entre los no eliminados |
| `descripcion` | `TEXT NULL` | No existe en AppSheet; opcional |

### 2.2 `usuarios`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `nombre_completo` | `TEXT` | `NOT NULL` (AppSheet: `Usuario`) |
| `correo` | `CITEXT` | `UNIQUE NOT NULL`; dominio de Google Workspace de Trulab (RN-12) |
| `cedula` | `TEXT NULL` | Única entre los no eliminados; dato personal (RNF-09) |
| `celula_id` | `UUID NULL` FK → `celulas.id` | `ON DELETE RESTRICT` (DP-14 ✅) |
| `rol` | `TEXT` | `NOT NULL CHECK (rol IN ('VIAJERO','FINANCIERO','ADMIN','SUPERADMIN'))` |
| `cargo_id` | `UUID NULL` FK → `cargos.id` | `ON DELETE RESTRICT` |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true` (RN-11) |
| `google_sub` | `TEXT NULL` | `UNIQUE`; se fija en el primer login con Google |
| `ultimo_acceso` | `TIMESTAMPTZ NULL` | |

> **No existe columna de contraseña** (DP-01 ✅, RN-15). En usuarios se usa `activo` y no `deleted_at` para el ciclo normal, porque un usuario inactivo sigue apareciendo en el historial.

### 2.3 Catálogos: `proyectos`, `rubros`, `celulas` (DP-14 ✅, ADR-022)

Tres tablas con la **misma estructura**, administradas solo por SUPERADMIN (RN-24). No se escriben valores en el código. **Decisión confirmada definitivamente por el negocio (2026-11-11).**

| | AppSheet (antes) | Nuevo sistema (ahora) |
| :--- | :--- | :--- |
| Lo que ve el usuario | Selecciona Proyecto de un Enum | Selecciona Proyecto de una **lista desplegable** (sin cambio funcional) |
| Lo que se guarda | `Proyecto` = texto del enum | `gastos.proyecto_id` = **referencia** (FK) a `proyectos.id` |
| Cómo se agrega un valor | Editar la columna en AppSheet | SUPERADMIN lo crea desde la app, sin tocar código ni desplegar |

El mismo criterio aplica a `rubros` (`gastos.rubro_id`) y `celulas` (`usuarios.celula_id`).

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `UUID` PK | `DEFAULT gen_random_uuid()` |
| `nombre` | `TEXT` | `NOT NULL`; valor **exacto** de AppSheet (por ejemplo `'Conexión Agro'`). `UNIQUE (lower(nombre))` |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true`. Inactivo = no se ofrece para registros nuevos, pero se conserva en los existentes |
| `orden` | `SMALLINT NULL` | Orden opcional en los selectores (por defecto, alfabético) |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | Auditoría estándar |
| `migrado_de` | `TEXT NULL` | Valor original de AppSheet (incluye la grafía exacta) |

- **Sin `deleted_at`:** los valores se desactivan, nunca se eliminan si están en uso (FK `RESTRICT`).
- **Valores iniciales:** se cargan desde la exportación de AppSheet (valores distintos encontrados en los CSV) más los ejemplos confirmados: rubros *Hospedaje, Alimentación, Transporte, Combustible, Peajes*; proyectos *Rutas PDET 3, Conexión Agro, Taller Multipropósito*; células *Laboratorio, Operaciones, Campo, Administración*.
- **Renombrar** un valor cambia cómo se muestra en todos los registros (la relación es por `id`). Se audita en `auditoria` (`CATALOGO_EDITAR`).
- El rol (`usuarios.rol`) **no** es un catálogo: es un enum fijo porque determina los permisos del sistema.

### 2.4 `legalizaciones`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `folio` | `TEXT` | `UNIQUE NOT NULL` (DP-09) |
| `usuario_id` | `UUID` FK → `usuarios.id` | `NOT NULL`: el dueño o viajero (AppSheet: `Viajero`) |
| `colaborador_nombre` | `TEXT` | `NOT NULL`: instantánea al crear (RN-17, ADR-020) |
| `colaborador_cargo` | `TEXT NULL` | Instantánea |
| `colaborador_cedula` | `TEXT NULL` | Instantánea; dato personal |
| `colaborador_celula` | `TEXT NULL` | Instantánea del **nombre** de la célula (no FK: conserva el valor histórico) |
| `motivo_viaje` | `TEXT` | `NOT NULL`, de 3 a 500 caracteres |
| `fecha_legalizacion` | `DATE` | `NOT NULL DEFAULT current_date` |
| `recursos_propios` | `BOOLEAN` | `NOT NULL DEFAULT false`. Lo marca el **viajero al crear** (DP-17 ✅, RN-25) |
| `valor_asignado` | `NUMERIC(14,2)` | `NOT NULL DEFAULT 0 CHECK (valor_asignado >= 0)`: el `Valor_T`, que solo registra FINANCIERO (DP-04 ✅) |
| `valor_transferido` | `NUMERIC(14,2)` | **`GENERATED ALWAYS AS (CASE WHEN recursos_propios THEN 0 ELSE valor_asignado END) STORED`** (RN-14). No se escribe nunca |
| `estado` | `TEXT` | Estado **operativo** (AppSheet `Estado`). `NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO'))`. Lo cambia solo ADMIN/SUPERADMIN (RN-20) |
| `estado_financiero` | `TEXT` | Estado **financiero** (AppSheet `Estado_P`). `NOT NULL DEFAULT 'PENDIENTE' CHECK (estado_financiero IN ('PENDIENTE','TRANSFERIDO','PAGADO','PROCESADO'))`. Lo cambia solo FINANCIERO/SUPERADMIN (RN-22) |
| `aprobada_at` | `TIMESTAMPTZ NULL` | Desnormalizado para filtros; la fuente es `legalizacion_eventos` |
| `devuelta_at` | `TIMESTAMPTZ NULL` | Última devolución. La UI muestra "Devuelta" si `estado = 'PENDIENTE'` y no es nulo (supuesto S-01) |
| `estado_financiero_at` | `TIMESTAMPTZ NULL` | Último cambio de estado financiero |
| `observaciones` | `TEXT NULL` | Último comentario de revisión (devolución o rechazo) |

**Restricción de coherencia entre dimensiones (RN-03):**
`CHECK (estado_financiero NOT IN ('PAGADO','PROCESADO') OR estado = 'APROBADO')` — `ck_legalizaciones__liquidacion_requiere_aprobado`.

> **Estado legalizacion** (AppSheet) es la fórmula `[Estado]`: no se crea columna (RN-23). **Fechas de viaje** (`fecha_inicio`, `fecha_fin`, `destino` del informe) no existen en AppSheet y no se agregan (DP-16 ✅).
> Los valores futuros `DEVUELTO` y `CANCELADO` (DP-13) se añadirían ampliando el `CHECK` en una migración, sin cambiar columnas.

### 2.5 `gastos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | `created_by` = `Creador` |
| `legalizacion_id` | `UUID` FK → `legalizaciones.id` | `NOT NULL ON DELETE RESTRICT` |
| `fecha_factura` | `DATE` | `NOT NULL` (AppSheet: `Fecha fact`); no futura (RN-07). Fecha de análisis de los indicadores (RN-18) |
| `rubro_id` | `UUID` FK → `rubros.id` | `NOT NULL ON DELETE RESTRICT` (DP-14 ✅) |
| `proyecto_id` | `UUID` FK → `proyectos.id` | `NOT NULL ON DELETE RESTRICT` (DP-02 ✅, DP-14 ✅) |
| `concepto` | `TEXT` | `NOT NULL` |
| `cc_nit` | `TEXT NULL` | Cédula o NIT del proveedor |
| `empresa` | `TEXT NULL` | Razón social del proveedor |
| `valor` | `NUMERIC(14,2)` | `NOT NULL CHECK (valor > 0)` |
| `soporte_id` | `UUID NULL` FK → `archivos.id` | **Imagen** (AppSheet `Soporte`). El service valida que el archivo sea imagen (RN-13) |
| `archivo_id` | `UUID NULL` FK → `archivos.id` | **PDF** (AppSheet `Archivo`). El service valida que el archivo sea PDF (RN-13) |
| `observaciones` | `TEXT NULL` | |

> **Adjunto mínimo (RN-21, DP-15 ✅):** `soporte_id IS NOT NULL OR archivo_id IS NOT NULL` es obligatorio para **Aprobar** y **liquidar**, no para guardar el gasto (supuesto S-04). Por eso no es un `CHECK` de tabla: lo valida `transicionar()` y lo expone la vista (`gastos_sin_comprobante`).

### 2.6 `archivos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id`, `created_at`, `created_by` | | |
| `storage_key` | `TEXT` | `UNIQUE NOT NULL` (ruta en el bucket) |
| `nombre_original` | `TEXT` | `NOT NULL` |
| `mime_type` | `TEXT` | `NOT NULL` (detectado por contenido) |
| `tamano_bytes` | `INTEGER` | `NOT NULL CHECK (tamano_bytes <= 10485760)` |
| `sha256` | `TEXT` | `NOT NULL` (integridad y detección de soportes duplicados) |

### 2.7 `legalizacion_eventos` (historial, solo inserción)

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `UUID` PK | |
| `legalizacion_id` | `UUID` FK | `NOT NULL` |
| `accion` | `TEXT` | `CHECK (accion IN ('CREAR','APROBAR','RECHAZAR','DEVOLVER','CAMBIAR_ESTADO_FINANCIERO','EDITAR_VALOR_ASIGNADO','CAMBIAR_RECURSOS_PROPIOS','ELIMINAR'))` |
| `dimension` | `TEXT NULL` | `CHECK (dimension IN ('OPERATIVO','FINANCIERO'))`; nulo en acciones que no cambian estado |
| `estado_anterior` | `TEXT NULL` | |
| `estado_nuevo` | `TEXT NULL` | |
| `comentario` | `TEXT NULL` | Obligatorio en `DEVOLVER` y `RECHAZAR` (lo valida el service, RN-10) |
| `datos` | `JSONB NULL` | Por ejemplo `{valor_asignado: {antes, despues}}` |
| `usuario_id` | `UUID` FK | `NOT NULL` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |

### 2.8 `auditoria` (solo inserción)

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | Orden natural |
| `usuario_id` | `UUID NULL` | Actor |
| `accion` | `TEXT` | `USUARIO_CREAR`, `ROL_CAMBIAR`, `USUARIO_DESACTIVAR`, `CATALOGO_CREAR`, `CATALOGO_EDITAR`, `CATALOGO_DESACTIVAR`, `ACCESO_DENEGADO` (dominio, no registrado o inactivo)… |
| `entidad`, `entidad_id` | `TEXT`, `UUID NULL` | |
| `datos` | `JSONB` | Diferencias (antes/después) sin secretos y sin la cédula completa |
| `ip`, `user_agent` | `INET`, `TEXT` | |
| `created_at` | `TIMESTAMPTZ` | |

### 2.9 `sesiones`

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `UUID` PK | |
| `usuario_id` | `UUID` FK | `NOT NULL` |
| `token_hash` | `TEXT` | `UNIQUE`, SHA-256 del refresh token |
| `expires_at`, `revoked_at` | `TIMESTAMPTZ` | |
| `created_at`, `user_agent`, `ip` | | |

### 2.10 Enums del sistema (no administrables)

| Enum | Usado en | Valores | Fuente |
| :--- | :--- | :--- | :--- |
| `ROLES` | `usuarios.rol` | `VIAJERO`, `FINANCIERO`, `ADMIN`, `SUPERADMIN` | Definitivo |
| `ESTADOS` | `legalizaciones.estado` | `PENDIENTE`, `APROBADO`, `RECHAZADO` | DP-13 ✅ |
| `ESTADOS_FINANCIEROS` | `legalizaciones.estado_financiero` | `PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO` | DP-13 ✅ |

Se implementan como `TEXT` + `CHECK` y se exponen en un único módulo del backend. Las listas de negocio (proyectos, rubros, células) **no** van aquí: son tablas (§2.3).

### 2.11 Vista `v_legalizacion_saldos` (fuente única del saldo, ADR-008)

```
v_legalizacion_saldos(
  legalizacion_id, folio, usuario_id, estado, estado_financiero, fecha_legalizacion,
  recursos_propios, valor_asignado,
  valor_transferido,                       -- columna generada (RN-14)
  total_gastos     = COALESCE(SUM(g.valor) FILTER (WHERE g.deleted_at IS NULL), 0),
  cantidad_gastos  = COUNT(g.id) FILTER (WHERE g.deleted_at IS NULL),
  gastos_sin_comprobante = COUNT(g.id) FILTER (
      WHERE g.deleted_at IS NULL AND g.soporte_id IS NULL AND g.archivo_id IS NULL),  -- RN-21
  saldo            = valor_transferido − total_gastos
)
-- legalizaciones l LEFT JOIN gastos g … WHERE l.deleted_at IS NULL GROUP BY l.id
-- Definida con security_invoker = true para que respete el RLS de las tablas base.
```

Los **indicadores** no usan esta vista como base temporal: agrupan `gastos` por `proyecto_id` (y opcionalmente `rubro_id`) filtrando `fecha_factura BETWEEN desde AND hasta` (DP-16 ✅).

## 3. Relaciones y cardinalidades

| Relación | Cardinalidad | Regla de borrado |
| :--- | :--- | :--- |
| `cargos` → `usuarios` | 1 : N (un usuario tiene 0..1 cargo) | `RESTRICT` (no se borra un cargo en uso) |
| `celulas` → `usuarios` | 1 : N (un usuario tiene 0..1 célula) | `RESTRICT` (se desactiva, no se borra) |
| `usuarios` → `legalizaciones` | 1 : N | `RESTRICT` |
| `legalizaciones` → `gastos` | 1 : N (0..N) | `RESTRICT`; borrado lógico en cascada desde el service |
| `proyectos` → `gastos` | 1 : N | `RESTRICT` |
| `rubros` → `gastos` | 1 : N | `RESTRICT` |
| `archivos` → `gastos` (soporte, imagen) | 1 : 0..1 | `RESTRICT` |
| `archivos` → `gastos` (archivo, PDF) | 1 : 0..1 | `RESTRICT` |
| `legalizaciones` → `legalizacion_eventos` | 1 : N (≥1) | Nunca se borran |
| `usuarios` → `sesiones` | 1 : N | `CASCADE` |
| `usuarios` → `auditoria` | 1 : N | `SET NULL` |

## 4. Diagrama de relaciones (texto)

```
   ┌──────────────┐                     ┌──────────────┐
   │   cargos     │                     │   celulas    │ (catálogo)
   │ id, folio    │                     │ nombre,activo│
   └──────┬───────┘                     └──────┬───────┘
          │ 1                                  │ 1
          │ 0..N                               │ 0..N
┌───────────┐ N   1 ┌───┴──────────────────────┴┐ 1      N ┌──────────────┐
│ sesiones  │───────│         usuarios          │──────────│  auditoria   │
└───────────┘       │ correo, rol, cedula       │          └──────────────┘
                    │ activo                    │
                    └───┬───────────────────────┘
                        │ 1 (dueño / viajero)
                        │ 0..N
                     ┌──┴─────────────────────────┐ 1        1..N ┌──────────────────────┐
                     │      legalizaciones        │───────────────│ legalizacion_eventos │
                     │ folio                      │               │ accion, dimension    │
                     │ estado (operativo)         │               │ comentario           │
                     │ estado_financiero          │               └──────────────────────┘
                     │ colaborador_* (snap)       │
                     │ recursos_propios           │
                     │ valor_asignado             │
                     │ valor_transferido (gen)    │
                     └──┬─────────────────────────┘
                        │ 1
                        │ 0..N
 ┌──────────────┐ 1  N ┌┴──────────────────────┐ 0..1     1 ┌──────────────┐
 │  proyectos   │──────│        gastos         │────────────│   archivos   │
 └──────────────┘      │ fecha_factura, valor  │  soporte   │ storage_key  │
 ┌──────────────┐ 1  N │ concepto, cc_nit      │  (imagen)  │ mime_type    │
 │   rubros     │──────│ empresa               │  archivo   └──────────────┘
 └──────────────┘      └───────────────────────┘  (PDF)

   v_legalizacion_saldos = legalizaciones ⟕ Σ gastos   (saldo calculado)
   Segmentador = parámetros desde/hasta sobre gastos.fecha_factura (sin tabla)
```

## 5. Índices recomendados

| Tabla | Índice | Motivo |
| :--- | :--- | :--- |
| `usuarios` | `UNIQUE (correo)` | Login |
| `usuarios` | `UNIQUE (cedula) WHERE deleted_at IS NULL AND cedula IS NOT NULL` | Evitar duplicados |
| `usuarios` | `(rol) WHERE activo` | Listados por rol |
| `usuarios` | `(celula_id)` | FK |
| `cargos` | `UNIQUE (lower(nombre)) WHERE deleted_at IS NULL` | Evitar duplicados |
| `proyectos`, `rubros`, `celulas` | `UNIQUE (lower(nombre))` | Nombres únicos por catálogo (RN-24) |
| `legalizaciones` | `(usuario_id, estado) WHERE deleted_at IS NULL` | Lista "mis legalizaciones" (consulta más frecuente) |
| `legalizaciones` | `(estado, estado_financiero, fecha_legalizacion DESC) WHERE deleted_at IS NULL` | Bandeja de revisión de ADMIN y vista de pagos |
| `legalizaciones` | `UNIQUE (folio)` | Búsqueda por folio |
| `legalizaciones` | `UNIQUE (migrado_de) WHERE migrado_de IS NOT NULL` | ETL idempotente (lo mismo en cargos, usuarios, gastos y catálogos) |
| `gastos` | `(legalizacion_id) WHERE deleted_at IS NULL` | Suma del saldo y detalle |
| `gastos` | `(fecha_factura, proyecto_id) WHERE deleted_at IS NULL` | Indicadores por rango de fecha de factura (DP-16 ✅) |
| `gastos` | `(rubro_id)`, `(proyecto_id)` | FK y agrupaciones |
| `archivos` | `(sha256)` | Detectar soportes repetidos (advertencia) |
| `legalizacion_eventos` | `(legalizacion_id, created_at)` | Historial |
| `sesiones` | `UNIQUE (token_hash)`, `(usuario_id)` | Refresh y revocación |
| `auditoria` | `(entidad, entidad_id)`, `(created_at)` | Consultas de auditoría |

Todas las FK llevan índice. PostgreSQL no lo crea solo; se agrega en cada migración.

## 6. Estrategia RLS

**Objetivo:** que la regla RN-01 se cumpla aunque falle el código de la aplicación (ADR-007).

1. Se crean dos roles de BD: `trulab_owner` (dueño del esquema, ejecuta migraciones) y `trulab_app` (con el que se conecta la API, **sin** `BYPASSRLS` y sin ser dueño).
2. En cada transacción, la API ejecuta:
   `SET LOCAL app.usuario_id = '<uuid>'; SET LOCAL app.rol = '<ROL>';`
3. Se habilita RLS en `legalizaciones` y `gastos` (`ENABLE` + `FORCE ROW LEVEL SECURITY`).
4. Políticas (pseudocódigo):

```
-- legalizaciones
POLICY ver_propias_o_privilegiado FOR ALL TO trulab_app
  USING (
    current_setting('app.rol', true) IN ('FINANCIERO','ADMIN','SUPERADMIN')
    OR usuario_id = current_setting('app.usuario_id', true)::uuid
  )
  WITH CHECK (misma condición);

-- gastos
POLICY ver_gastos_de_legalizaciones_visibles FOR ALL TO trulab_app
  USING (EXISTS (SELECT 1 FROM legalizaciones l WHERE l.id = gastos.legalizacion_id))
  -- se apoya en la política de legalizaciones
```

5. Si las variables no están definidas, `current_setting(..., true)` devuelve `NULL` y la política deniega. Ese es el comportamiento seguro por defecto.
6. Las tareas del sistema (ETL, reportes programados) usan `trulab_owner` o fijan `app.rol = 'SUPERADMIN'` de forma explícita y registrada.
7. Los catálogos (`proyectos`, `rubros`, `celulas`) no llevan RLS: todos los roles los leen; la escritura (solo SUPERADMIN) se controla en el service.
8. **Pruebas:** con la conexión `trulab_app` y `app.rol='VIAJERO'`, un `SELECT` sin `WHERE` debe devolver solo filas propias.

> RLS **no** reemplaza las reglas de estado ni de edición. Tampoco cubre las reglas "solo FINANCIERO edita `valor_asignado` y `estado_financiero`" (RN-19, RN-22) ni "solo ADMIN cambia `estado`" (RN-20), que viven en el service y en su prueba RBAC.

## 7. Estrategia de auditoría

Hay tres niveles, de menor a mayor detalle:

1. **Columnas base** (`created_*`, `updated_*`) en todas las tablas: quién creó o tocó cada registro por última vez.
2. **`legalizacion_eventos`:** historial funcional del flujo (estado operativo, estado financiero, `valor_asignado` y `recursos_propios`). Se muestra en la UI y en el PDF. Se escribe en la **misma transacción** que el cambio.
3. **`auditoria`:** eventos de seguridad y administración (gestión de usuarios, cambios de rol, cambios de catálogos, accesos denegados, eliminaciones). Solo la consulta SUPERADMIN.

Las tablas de eventos y auditoría son de **solo inserción**: `trulab_app` recibe `INSERT, SELECT` pero no `UPDATE, DELETE`. Nunca se guardan tokens ni contenido de archivos (no hay contraseñas en el sistema).

## 8. Estrategia de eliminación lógica

- Las entidades operativas (`cargos`, `legalizaciones`, `gastos`) usan `deleted_at`.
- **Todas** las consultas del ORM filtran `deleted_at IS NULL` por defecto mediante un filtro global (`with_loader_criteria`) o una función base del repositorio. Incluir eliminados requiere un parámetro explícito.
- Los índices `UNIQUE` de negocio son **parciales** (`WHERE deleted_at IS NULL`) para permitir recrear un nombre eliminado.
- Una legalización solo se elimina con `estado = 'PENDIENTE'` y `estado_financiero = 'PENDIENTE'` (RN-09). Al eliminarla, sus gastos se marcan como eliminados en la misma transacción y se registra el evento `ELIMINAR`.
- Un cargo con usuarios activos asociados no se puede eliminar; se responde 409 con el mensaje "en uso".
- Los usuarios y los valores de catálogo se **desactivan** (`activo=false`); no se eliminan.
- Purga física: fuera del MVP. Si se hace, será un proceso manual auditado.

## 9. Convenciones de nomenclatura

| Elemento | Convención | Ejemplo |
| :--- | :--- | :--- |
| Tablas | `snake_case`, plural, en español | `legalizaciones`, `gastos`, `rubros` |
| Columnas | `snake_case`, singular | `fecha_factura`, `valor_asignado` |
| PK | `id` | |
| FK | `<entidad_singular>_id` | `usuario_id`, `proyecto_id`, `soporte_id` |
| Fechas sin hora | `fecha_*` (`DATE`) | `fecha_legalizacion` |
| Marcas de tiempo | `*_at` (`TIMESTAMPTZ`, UTC) | `aprobada_at` |
| Booleanos | adjetivo, participio o sustantivo claro | `activo`, `recursos_propios` |
| Dinero | `valor_*`, `NUMERIC(14,2)` | `valor_transferido` |
| Instantáneas | `<entidad>_<campo>` | `colaborador_cargo` |
| Enums de sistema | `TEXT` + `CHECK`, valores en `MAYUSCULAS` sin emojis | `'PENDIENTE'` |
| Catálogos de negocio | Tabla con `nombre` = valor **exacto** de AppSheet | `'Conexión Agro'` |
| Índices | `ix_<tabla>__<columnas>` | `ix_gastos__fecha_factura_proyecto_id` |
| Únicos | `uq_<tabla>__<columnas>` | `uq_usuarios__correo` |
| FK (constraint) | `fk_<tabla>__<columna>__<tabla_ref>` | |
| Checks | `ck_<tabla>__<regla>` | `ck_legalizaciones__estado` |
| Vistas | `v_<nombre>` | `v_legalizacion_saldos` |
| Migraciones Alembic | `AAAAMMDD_HHMM_<descripcion>` | `20261116_0900_crear_cargos_usuarios` |

Las convenciones de constraints se configuran en el `MetaData(naming_convention=...)` de SQLAlchemy para que Alembic genere nombres estables.

## 10. Extensiones requeridas

`pgcrypto` (o PG ≥ 13 nativo para `gen_random_uuid`) y `citext`.

## 11. Folios (RN-04)

- Una secuencia por entidad: `seq_folio_cargos` y `seq_folio_legalizaciones`.
- El folio se calcula en el `INSERT` con `DEFAULT 'LG-' || lpad(nextval('seq_folio_legalizaciones')::text, 6, '0')`.
- Las secuencias pueden dejar huecos (rollback); se acepta, porque el folio identifica y no numera contablemente. Si contabilidad exige numeración sin huecos, se necesita otro ADR.
- En el ETL, los IDs históricos de AppSheet (`ID Cargo`, `ID legalizacion`) se conservan como folio si son legibles (DP-09), y la secuencia se ajusta después con `setval` al máximo + 1.

## 12. Notas para el ETL (fase F10)

- **Orden:** catálogos (proyectos, rubros, células) → cargos → usuarios → legalizaciones → archivos → gastos. Es idempotente por `migrado_de`.
- **Catálogos:** se crean a partir de los valores **distintos** de `Registro_Gastos.Proyecto`, `Registro_Gastos.Rubro` y `Usuarios.Celula`, conservando la grafía exacta. Se genera un informe con los valores encontrados y su frecuencia para que SUPERADMIN detecte duplicados por grafía (por ejemplo, con y sin tilde) y los unifique antes del corte.
- **Datos del colaborador:** se toman de las columnas propias de `Crear_legalizacion` (son la instantánea histórica), no del usuario actual.
- **Valor transferido:** se migran `Valor_T` y `Recursos propios`. El `Valor transferido` de AppSheet se compara con la columna generada; cualquier diferencia va al informe de conciliación (RN-14 se mantiene igual).
- **Total Gastos / Saldo:** no se migran; se comparan con `v_legalizacion_saldos`.
- **Estados** (DP-13 ✅), con normalización de emojis y espacios:

  | AppSheet `Estado` | → `estado` | AppSheet `Estado_P` | → `estado_financiero` |
  | :--- | :--- | :--- | :--- |
  | `Pendiente ⛔` | `PENDIENTE` | `Pendiente⌛` | `PENDIENTE` |
  | `Aprobado` | `APROBADO` | `Transferido` | `TRANSFERIDO` |
  | `Rechazado` | `RECHAZADO` | `Pagado` | `PAGADO` |
  | | | `Procesado` | `PROCESADO` |

  Un valor fuera de la tabla detiene el ETL con un informe. `Estado legalizacion` se compara con `Estado` y las diferencias se reportan. Las filas históricas con `Estado_P` en `PAGADO`/`PROCESADO` y `Estado` distinto de `Aprobado` violarían `ck_legalizaciones__liquidacion_requiere_aprobado`: se reportan y se decide con el negocio antes del corte.
- **Adjuntos:** `Soporte` → `soporte_id` (imagen) y `Archivo` → `archivo_id` (PDF). Si el tipo real no coincide con el campo (por ejemplo, un PDF en `Soporte`), se migra en el campo que corresponde a su tipo y se reporta.
- **Segmentador:** no se migra.
