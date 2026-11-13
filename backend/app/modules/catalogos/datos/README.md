# Datos iniciales de catálogos

Archivos de datos (no código). Los valores **no se escriben en el código ni en las migraciones** (DP-14, ADR-030): la migración de S2-02 (`20261113_1349_catalogos_viaticos_y_gastos`) los lee de aquí.

## `tarifas_viaticos.csv`

Tarifas oficiales de viáticos en COP, extraídas de `calcularGastos.html` (proyecto Google Apps Script "Solicitud de tiquetes y gastos de viaje") y entregadas por el dueño del producto el 2026-11-12. Son 22 destinos × 2 tipos de vinculación = 44 filas.

| Columna | Significado |
| :--- | :--- |
| `clave_legado` | Identificador de la ciudad en el código de Apps Script (`Bogota`, `PichindeValle`…). El seed lo guarda en `tarifas_viaticos.migrado_de` |
| `ciudad` | Nombre visible en el selector, con la grafía en español |
| `es_prestador_servicios` | `false` = tabla de empleados (`gastosViaje2025`); `true` = tabla de prestadores (`prestadores`) |
| `vr_alimentacion`, `otros_gastos` | Por día |
| `transporte_aeropuerto`, `transporte_intermunicipal` | Por trayecto/destino |
| `trans_interno_dia_1` | Transporte interno si `dias_estadia = 1` |
| `trans_interno_varios_dias` | Transporte interno si `dias_estadia > 1` |
| `orden` | Orden del selector (el del código original) |

**Regla del transporte interno para prestadores (código legado).** En `Cali`, `Bogota`, `Medellin`, `Barranquilla` y `Buenaventura` se aplica `trans_interno_dia_1` con 1 día y `trans_interno_varios_dias` con más de 1. En los demás municipios se aplica siempre `trans_interno_varios_dias`. En esas filas los dos valores son iguales (50000 o 70000), así que la fórmula general de RN-29 da el mismo resultado; `tests/test_datos_tarifas.py` lo verifica para que un cambio futuro no rompa la equivalencia sin aviso.

**Proyecto que exige formato de prestador** (`javaScript.html`): `P-CONEXI-002`. Se configura con `proyectos.exige_formato_prestador = true` cuando se cree el catálogo de proyectos (S2-01).

Lo carga la migración de S2-02 al crear la tabla (las 44 filas; `created_by = NULL`, `migrado_de` = `clave_legado`). Después de la carga inicial, las tarifas se administran desde la app (SUPERADMIN); este archivo no se vuelve a aplicar sobre valores editados. **No lo edite pensando que cambia las tarifas vigentes:** solo afectaría a una BD nueva.
