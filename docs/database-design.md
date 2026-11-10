# Diseño de base de datos — Trulab Viajes

> Motor: PostgreSQL 16. Esquema: `public` (MVP). Migraciones solo con Alembic.
> El modelo de AppSheet (`DB_Legalizaciones`) se dedujo por ingeniería inversa. **Validar contra la exportación real (DP-07) antes de la primera migración de la fase 4.**

---

## 1. Correspondencia con AppSheet

| AppSheet | Nuevo modelo | Comentario |
| :--- | :--- | :--- |
| `Cargos` | `cargos` | Igual, con folio `CA-000001` |
| `Usuarios` | `usuarios` | Más `activo`, `ultimo_acceso`; el rol pasa a ser `CHECK` |
| `Crear_legalizacion` | `legalizaciones` | Nombre en sustantivo; más `folio`, `proyecto_id`, `observaciones` |
| `Registro_Gastos` | `gastos` + `archivos` | El soporte pasa a ser un archivo gestionado (clave de objeto, no URL pública) |
| `Segmentador` | `proyectos` (propuesta) | DP-02: confirmar qué contiene realmente |
| `SlicefiltrarporViajero`, `SliceUsuarios` | Autorización en el service + RLS | Ver §6 |
| — | `legalizacion_eventos` | Nuevo: historial de estados (RN-10) |
| — | `auditoria` | Nuevo: acciones sensibles (RF-014) |
| — | `sesiones` | Nuevo: refresh tokens |

## 2. Entidades

Columnas comunes a **todas** las tablas operativas (en adelante, "columnas base"):

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `UUID` PK | `DEFAULT gen_random_uuid()` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | `DEFAULT now()` |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | Lo actualiza el ORM o un trigger |
| `created_by` | `UUID NULL` FK → `usuarios.id` | `NULL` para registros migrados o del sistema |
| `updated_by` | `UUID NULL` FK → `usuarios.id` | |
| `deleted_at` | `TIMESTAMPTZ NULL` | Eliminación lógica (§8) |

### 2.1 `cargos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `folio` | `TEXT` | `UNIQUE NOT NULL`, `CA-000001` |
| `nombre` | `TEXT` | `NOT NULL`; único entre los no eliminados |
| `descripcion` | `TEXT NULL` | |

### 2.2 `usuarios`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `nombre_completo` | `TEXT` | `NOT NULL` |
| `correo` | `CITEXT` | `UNIQUE NOT NULL`; dominio corporativo validado en la app (RN-12) |
| `rol` | `TEXT` | `NOT NULL CHECK (rol IN ('VIAJERO','FINANCIERO','ADMIN','SUPERADMIN'))` |
| `cargo_id` | `UUID NULL` FK → `cargos.id` | `ON DELETE RESTRICT` |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true` (RN-11) |
| `password_hash` | `TEXT NULL` | Solo si DP-01 aprueba contraseña |
| `google_sub` | `TEXT NULL` | `UNIQUE`; se fija en el primer login con Google |
| `ultimo_acceso` | `TIMESTAMPTZ NULL` | |

> En usuarios se usa `activo` y no `deleted_at` para el ciclo normal, porque un usuario inactivo sigue apareciendo en el historial. `deleted_at` queda reservado para errores de alta.

### 2.3 `proyectos` (DP-02)

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `codigo` | `TEXT` | `UNIQUE NOT NULL` (código de centro de costo) |
| `nombre` | `TEXT` | `NOT NULL` |
| `activo` | `BOOLEAN` | `NOT NULL DEFAULT true` |

### 2.4 `legalizaciones`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `folio` | `TEXT` | `UNIQUE NOT NULL`, `LG-000001` |
| `usuario_id` | `UUID` FK → `usuarios.id` | `NOT NULL`: el dueño o viajero |
| `proyecto_id` | `UUID NULL` FK → `proyectos.id` | `NOT NULL` tras resolver DP-02 (los migrados pueden ser `NULL`) |
| `motivo_viaje` | `TEXT` | `NOT NULL`, de 3 a 500 caracteres |
| `destino` | `TEXT NULL` | Opcional, útil en reportes |
| `fecha_inicio` | `DATE` | `NOT NULL` |
| `fecha_fin` | `DATE` | `NOT NULL CHECK (fecha_fin >= fecha_inicio)` |
| `valor_transferido` | `NUMERIC(14,2)` | `NOT NULL DEFAULT 0 CHECK (valor_transferido >= 0)` |
| `estado` | `TEXT` | `NOT NULL DEFAULT 'BORRADOR' CHECK (estado IN ('BORRADOR','LEGALIZADA','DEVUELTA','PAGADA'))` |
| `legalizada_at` | `TIMESTAMPTZ NULL` | Desnormalizado para filtros; la fuente es `legalizacion_eventos` |
| `pagada_at` | `TIMESTAMPTZ NULL` | Ídem |
| `observaciones` | `TEXT NULL` | Última observación de financiero |
| `migrado_de` | `TEXT NULL` | ID original de AppSheet (trazabilidad del ETL) |

### 2.5 `gastos`

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| *columnas base* | | |
| `legalizacion_id` | `UUID` FK → `legalizaciones.id` | `NOT NULL ON DELETE RESTRICT` |
| `descripcion` | `TEXT` | `NOT NULL` |
| `valor` | `NUMERIC(14,2)` | `NOT NULL CHECK (valor > 0)` |
| `fecha_gasto` | `DATE` | `NOT NULL` |
| `soporte_archivo_id` | `UUID NULL` FK → `archivos.id` | Obligatorio para legalizar y pagar (RN-03, RN-06) |
| `proveedor_nit` | `TEXT NULL` | Preparado para OCR (futuro) |
| `migrado_de` | `TEXT NULL` | |

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
| `accion` | `TEXT` | `CHECK (accion IN ('CREAR','LEGALIZAR','DEVOLVER','PAGAR','EDITAR_TRANSFERIDO','ELIMINAR'))` |
| `estado_anterior` | `TEXT NULL` | |
| `estado_nuevo` | `TEXT NULL` | |
| `comentario` | `TEXT NULL` | Obligatorio en `DEVOLVER` (lo valida el service) |
| `datos` | `JSONB NULL` | Por ejemplo `{valor_transferido: {antes, despues}}` |
| `usuario_id` | `UUID` FK | `NOT NULL` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |

### 2.8 `auditoria` (solo inserción)

| Columna | Tipo | Nota |
| :--- | :--- | :--- |
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | Orden natural |
| `usuario_id` | `UUID NULL` | Actor |
| `accion` | `TEXT` | `USUARIO_CREAR`, `ROL_CAMBIAR`, `USUARIO_DESACTIVAR`, `LOGIN_FALLIDO`… |
| `entidad`, `entidad_id` | `TEXT`, `UUID NULL` | |
| `datos` | `JSONB` | Diferencias (antes/después) sin secretos |
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

### 2.10 Vista `v_legalizacion_saldos` (fuente única del saldo, ADR-008)

```
v_legalizacion_saldos(
  legalizacion_id, folio, usuario_id, proyecto_id, estado, fecha_inicio, fecha_fin,
  valor_transferido,
  total_gastos     = COALESCE(SUM(g.valor) FILTER (WHERE g.deleted_at IS NULL), 0),
  cantidad_gastos  = COUNT(g.id) FILTER (WHERE g.deleted_at IS NULL),
  gastos_sin_soporte = COUNT(g.id) FILTER (WHERE g.deleted_at IS NULL AND g.soporte_archivo_id IS NULL),
  saldo            = valor_transferido − total_gastos
)
-- legalizaciones l LEFT JOIN gastos g … WHERE l.deleted_at IS NULL GROUP BY l.id
-- Definida con security_invoker = true para que respete el RLS de las tablas base.
```

## 3. Relaciones y cardinalidades

| Relación | Cardinalidad | Regla de borrado |
| :--- | :--- | :--- |
| `cargos` → `usuarios` | 1 : N (un usuario tiene 0..1 cargo) | `RESTRICT` (no se borra un cargo en uso) |
| `usuarios` → `legalizaciones` | 1 : N | `RESTRICT` |
| `proyectos` → `legalizaciones` | 1 : N | `RESTRICT` |
| `legalizaciones` → `gastos` | 1 : N (0..N) | `RESTRICT`; borrado lógico en cascada desde el service |
| `archivos` → `gastos` | 1 : 0..1 (un soporte por gasto en el MVP) | `RESTRICT` |
| `legalizaciones` → `legalizacion_eventos` | 1 : N (≥1) | Nunca se borran |
| `usuarios` → `sesiones` | 1 : N | `CASCADE` |
| `usuarios` → `auditoria` | 1 : N | `SET NULL` |

## 4. Diagrama de relaciones (texto)

```
                 ┌──────────────┐
                 │   cargos     │
                 │ id, folio    │
                 │ nombre       │
                 └──────┬───────┘
                        │ 1
                        │
                        │ 0..N
┌───────────┐ N   1 ┌───┴──────────┐ 1      N ┌──────────────┐
│ sesiones  │───────│   usuarios   │──────────│  auditoria   │
└───────────┘       │ correo, rol  │          └──────────────┘
                    │ activo       │
                    └───┬──────────┘
                        │ 1 (dueño)
                        │
                        │ 0..N
┌────────────┐ 1   0..N ┌──┴────────────────┐ 1        1..N ┌──────────────────────┐
│ proyectos  │──────────│  legalizaciones   │───────────────│ legalizacion_eventos │
│ codigo     │          │ folio, estado     │               │ accion, comentario   │
└────────────┘          │ valor_transferido │               └──────────────────────┘
                        └──┬────────────────┘
                           │ 1
                           │
                           │ 0..N
                        ┌──┴───────────┐ 0..1     1 ┌──────────────┐
                        │   gastos     │────────────│   archivos   │
                        │ valor, fecha │  soporte   │ storage_key  │
                        └──────────────┘            └──────────────┘

   v_legalizacion_saldos = legalizaciones ⟕ Σ gastos   (saldo calculado)
```

## 5. Índices recomendados

| Tabla | Índice | Motivo |
| :--- | :--- | :--- |
| `usuarios` | `UNIQUE (correo)` | Login |
| `usuarios` | `(rol) WHERE activo` | Listados por rol |
| `cargos` | `UNIQUE (lower(nombre)) WHERE deleted_at IS NULL` | Evitar duplicados |
| `legalizaciones` | `(usuario_id, estado) WHERE deleted_at IS NULL` | Lista "mis legalizaciones" (consulta más frecuente) |
| `legalizaciones` | `(estado, fecha_inicio DESC) WHERE deleted_at IS NULL` | Vista de pagos y filtros financieros |
| `legalizaciones` | `(proyecto_id, fecha_inicio)` | Dashboard |
| `legalizaciones` | `UNIQUE (folio)` | Búsqueda por folio |
| `gastos` | `(legalizacion_id) WHERE deleted_at IS NULL` | Suma del saldo y detalle |
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
7. **Pruebas:** con la conexión `trulab_app` y `app.rol='VIAJERO'`, un `SELECT` sin `WHERE` debe devolver solo filas propias.

> RLS **no** reemplaza las reglas de estado ni de edición. Esas viven en el service.

## 7. Estrategia de auditoría

Hay tres niveles, de menor a mayor detalle:

1. **Columnas base** (`created_*`, `updated_*`) en todas las tablas: quién creó o tocó cada registro por última vez.
2. **`legalizacion_eventos`:** historial funcional del flujo. Se muestra en la UI y en el PDF. Se escribe en la **misma transacción** que el cambio de estado.
3. **`auditoria`:** eventos de seguridad y administración (gestión de usuarios, cambios de rol, accesos fallidos, eliminaciones, descargas masivas). Solo la consulta SUPERADMIN.

Las tablas de eventos y auditoría son de **solo inserción**: `trulab_app` recibe `INSERT, SELECT` pero no `UPDATE, DELETE`. Nunca se guardan contraseñas, tokens ni contenido de archivos.

## 8. Estrategia de eliminación lógica

- Las entidades operativas (`cargos`, `proyectos`, `legalizaciones`, `gastos`) usan `deleted_at`.
- **Todas** las consultas del ORM filtran `deleted_at IS NULL` por defecto mediante un filtro global (`with_loader_criteria`) o una función base del repositorio. Incluir eliminados requiere un parámetro explícito.
- Los índices `UNIQUE` de negocio son **parciales** (`WHERE deleted_at IS NULL`) para permitir recrear un nombre eliminado.
- Una legalización solo se elimina en `BORRADOR` (RN-09). Al eliminarla, sus gastos se marcan como eliminados en la misma transacción y se registra el evento `ELIMINAR`.
- Un cargo o proyecto con registros activos asociados no se puede eliminar; se responde 409 con el mensaje "en uso".
- Los usuarios se **desactivan** (`activo=false`); no se eliminan.
- Purga física: fuera del MVP. Si se hace, será un proceso manual auditado.

## 9. Convenciones de nomenclatura

| Elemento | Convención | Ejemplo |
| :--- | :--- | :--- |
| Tablas | `snake_case`, plural, en español | `legalizaciones`, `gastos` |
| Columnas | `snake_case`, singular | `fecha_inicio`, `valor_transferido` |
| PK | `id` | |
| FK | `<entidad_singular>_id` | `usuario_id`, `legalizacion_id` |
| Fechas sin hora | `fecha_*` (`DATE`) | `fecha_gasto` |
| Marcas de tiempo | `*_at` (`TIMESTAMPTZ`, UTC) | `pagada_at` |
| Booleanos | adjetivo o participio | `activo` |
| Dinero | `valor_*`, `NUMERIC(14,2)` | `valor_transferido` |
| Enums | `TEXT` + `CHECK`, valores en `MAYUSCULAS` | `'BORRADOR'` |
| Índices | `ix_<tabla>__<columnas>` | `ix_legalizaciones__usuario_id_estado` |
| Únicos | `uq_<tabla>__<columnas>` | `uq_usuarios__correo` |
| FK (constraint) | `fk_<tabla>__<columna>__<tabla_ref>` | |
| Checks | `ck_<tabla>__<regla>` | `ck_legalizaciones__fechas` |
| Vistas | `v_<nombre>` | `v_legalizacion_saldos` |
| Migraciones Alembic | `AAAAMMDD_HHMM_<descripcion>` | `20261116_0900_crear_cargos_usuarios` |

Las convenciones de constraints se configuran en el `MetaData(naming_convention=...)` de SQLAlchemy para que Alembic genere nombres estables.

## 10. Extensiones requeridas

`pgcrypto` (o PG ≥ 13 nativo para `gen_random_uuid`) y `citext`.

## 11. Folios (RN-04)

- Una secuencia por entidad: `seq_folio_cargos` y `seq_folio_legalizaciones`.
- El folio se calcula en el `INSERT` con `DEFAULT 'LG-' || lpad(nextval('seq_folio_legalizaciones')::text, 6, '0')`.
- Las secuencias pueden dejar huecos (rollback); se acepta, porque el folio identifica y no numera contablemente. Si contabilidad exige numeración sin huecos, se necesita otro ADR.
- En el ETL, los folios históricos se conservan si existen en AppSheet, y la secuencia se ajusta después con `setval` al máximo + 1.
