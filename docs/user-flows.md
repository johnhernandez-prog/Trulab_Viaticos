# Flujos de usuario — Trulab Viajes

> Cada flujo indica el actor, la precondición, los pasos, las reglas aplicadas y los caminos alternos.
> Referencias: reglas RN-xx y supuestos S-xx en `SPEC.md` §8 y §17.3; endpoints en `docs/api-design.md`.

## Máquina de estados de la legalización (definitiva, DP-13 ✅)

La legalización tiene **dos dimensiones independientes**, más un espejo:

| Dimensión | Columna | AppSheet | Quién la cambia |
| :--- | :--- | :--- | :--- |
| Operativa | `estado` | `Estado` | Sistema (inicial) · **ADMIN** / SUPERADMIN |
| Financiera | `estado_financiero` | `Estado_P` | Sistema (inicial) · **FINANCIERO** / SUPERADMIN |
| Espejo | — (no se almacena) | `Estado legalizacion` = `[Estado]` | — |

### Estado operativo (ADMIN)

```
                 crear (dueño; el sistema asigna PENDIENTE)
  (inicio) ─────────────────────────────────▶ PENDIENTE ⛔ ──── aprobar (A/S) ────▶ APROBADO
                                                │  ▲  ▲                               │
                          eliminar (dueño, si   │  │  └── devolver (A/S, comentario) ──┘
                          estado_financiero =   │  │      solo si estado_financiero ∉ {PAGADO, PROCESADO}
                          PENDIENTE)            │  │
                                ▼               │  └──── devolver (A/S, comentario): queda PENDIENTE y "Devuelta"
                          [eliminada]           │
                                                └──── rechazar (A/S, comentario) ────▶ RECHAZADO (final)
```

### Estado financiero (FINANCIERO)

```
  PENDIENTE ⌛ ──▶ TRANSFERIDO ──▶ PAGADO ──▶ PROCESADO
       (FINANCIERO elige el valor; el orden mostrado es el recorrido habitual, supuesto S-03)
  Regla dura (RN-03): PAGADO y PROCESADO solo si estado = APROBADO y todos los gastos tienen comprobante.
```

- **Editable por el dueño:** solo con `estado = PENDIENTE` (incluida una legalización devuelta). AppSheet no tiene un paso "enviar" (supuesto S-02).
- **Recursos propios:** lo marca el viajero al crear (DP-17 ✅). Si es verdadero, el valor transferido es 0 y la empresa reembolsa (RN-14, RN-25).
- **Valor transferido:** lo registra y modifica **solo FINANCIERO** (y SUPERADMIN) (DP-04 ✅).
- **Separación de funciones** (DP-18 ✅): ADMIN no toca la dimensión financiera; FINANCIERO no toca la operativa. Nadie aprueba, valida financieramente ni paga su propia legalización; la única excepción es SUPERADMIN, con auditoría (RN-27, regla definitiva).
- Cada flecha genera un registro en `legalizacion_eventos` (RN-10). Devolver y Rechazar exigen comentario.

---

## F-01 · Inicio de sesión

**Actor:** cualquier usuario. **Precondición:** el usuario existe en Usuarios, está activo y tiene rol (lo creó ADMIN o SUPERADMIN). **Método único:** Google Workspace de Trulab (DP-01 ✅).

1. El usuario abre la app y ve la pantalla de login con el logo y el botón **"Ingresar con Google"**. No hay campos de usuario ni contraseña.
2. Pulsa el botón; Google muestra el selector de cuenta.
3. Elige su cuenta corporativa de Google Workspace de Trulab. **Google verifica la identidad** y la SPA recibe el ID token.
4. La SPA envía el token a `POST /auth/google`.
5. La API valida, en orden: el token, el correo verificado, el dominio de Trulab, que el correo exista en Usuarios, que el usuario esté activo y que tenga rol asignado. Si todo se cumple, emite la sesión.
6. La SPA carga `/me` y redirige a la **vista inicial del rol**: VIAJERO → Legalizaciones; ADMIN → Revisión (pendientes); FINANCIERO → Pagos; SUPERADMIN → Legalizaciones.
7. La sesión se renueva sola (refresh) mientras el usuario usa la app; vence a los 7 días sin uso.

**Alternos:**
- Cuenta de otro dominio: "Use su cuenta corporativa @trulab.co".
- Correo no registrado, inactivo o sin rol: **acceso denegado**, con el mensaje "Su cuenta no tiene acceso. Contacte al administrador." Queda registrado en la auditoría.
- **Problemas con la contraseña de la cuenta corporativa:** la app no los gestiona. El colaborador contacta a los administradores de Google Workspace de Trulab. No existen opciones de registro, creación de cuenta, "olvidé mi contraseña" ni cambio de contraseña.
- **Cerrar sesión:** menú de perfil → "Cerrar sesión" → vuelve al login.

---

## F-02 · Gestión de usuarios

**Actor:** ADMIN o SUPERADMIN.

1. Menú → **Usuarios**. Se ve la tabla (escritorio) o las tarjetas (móvil) con nombre, rol, cargo, célula, correo y estado.
2. Puede buscar por nombre o correo y filtrar por rol, cargo, célula o activo.
3. **Crear:** botón "+ Nuevo usuario" → formulario con nombre completo, correo corporativo de Google Workspace, cédula, célula (catálogo), rol y cargo → Guardar. Desde ese momento el colaborador puede entrar con Google; no se envían contraseñas.
   - Validación: correo único y del dominio (RN-12). Un ADMIN no ve la opción `SUPERADMIN`.
4. **Editar:** clic en la fila → detalle → "Editar" → cambiar los campos → Guardar.
   - Si cambia el **rol**, aparece la confirmación "El usuario deberá volver a iniciar sesión". Se audita.
5. **Desactivar:** menú `⋯` → "Desactivar" → confirmación. El usuario ya no puede ingresar y su historial se conserva (RN-11).
6. **Reactivar:** filtro "Inactivos" → `⋯` → "Activar".

**Alternos:** no puede desactivarse a sí mismo; no puede desactivar ni degradar al último SUPERADMIN.

---

## F-03 · Gestión de cargos y catálogos

**F-03a · Cargos.** **Actor:** ADMIN o SUPERADMIN (FINANCIERO solo consulta).

1. Menú → **Cargos**. Se ve la lista con folio (`CA-000001`), nombre y cantidad de usuarios.
2. **Crear:** "+ Añadir" → nombre (y descripción opcional) → Guardar. El sistema asigna el folio (RN-04).
3. **Editar:** clic → editar el nombre o la descripción → Guardar.
4. **Eliminar:** `⋯` → "Eliminar" → confirmación.
   - Si tiene usuarios asignados, aparece "No se puede eliminar: 4 usuarios tienen este cargo" (409).

**F-03b · Catálogos (proyectos, rubros, células).** **Actor:** solo SUPERADMIN (DP-14 ✅).

1. Menú → **Catálogos** → pestañas Proyectos · Rubros · Células. Cada fila muestra nombre, estado (activo/inactivo) y cuántos registros lo usan.
2. **Crear:** "+ Añadir" → nombre → Guardar. Un nombre repetido (sin distinguir mayúsculas) muestra "Ya existe".
3. **Renombrar:** clic → editar → Guardar. El cambio se refleja en todos los registros que lo usan y se audita.
4. **Desactivar / Activar:** `⋯` → "Desactivar". El valor deja de aparecer en los selectores, pero los gastos y usuarios que ya lo tienen lo conservan (RN-24). No hay opción de eliminar.

> Para el viajero y el ADMIN la experiencia es la misma que en AppSheet: eligen proyecto, rubro y célula de una lista desplegable. Que la lista venga de una tabla maestra es un detalle interno.

---

## F-04 · Crear una legalización

**Actor:** cualquier rol (normalmente VIAJERO), siempre sobre una legalización propia.

1. **Legalizaciones** → FAB **"+"** (móvil) o "+ Nueva legalización" (escritorio).
2. Se muestran, **solo lectura**, los datos del colaborador tomados de su usuario: nombre, cargo, cédula y célula (RN-17; equivale a `LOOKUP(USEREMAIL())`).
3. Formulario (una columna en móvil):
   - Motivo del viaje (obligatorio)
   - ¿Viajó con **recursos propios**? (Sí/No). Lo decide el viajero en este momento (DP-17 ✅). Texto de ayuda: "Si pagó el viaje con su dinero, la empresa le reembolsará el total de los gastos".
   - La fecha de legalización se asigna automáticamente. No hay fechas de viaje (DP-16 ✅).
   - El **proyecto no se elige aquí**: se asigna en cada gasto (DP-02 ✅).
4. Guardar. El sistema crea la legalización con estado **PENDIENTE** y estado financiero **PENDIENTE** (DP-13 ✅) y le asigna el folio `LG-xxxxxx`.
5. La app abre el **detalle** de la legalización con la sección "Gastos" vacía y un CTA para agregar el primer gasto.
6. El valor transferido se muestra así: con recursos propios, "Recursos propios: $0 (a reembolsar)"; si no, "Pendiente de registrar por Financiero" mientras FINANCIERO no lo registre (DP-04 ✅).

**Alternos:** si cierra antes de guardar, el formulario pregunta "¿Descartar cambios?". Puede editar el motivo mientras esté PENDIENTE, y corregir "recursos propios" mientras además el estado financiero siga PENDIENTE (supuesto S-05).

---

## F-05 · Registrar un gasto

**Actor:** dueño de la legalización, con estado PENDIENTE.

1. En el detalle de la legalización → **"+ Agregar gasto"**. En móvil se abre un Sheet inferior.
2. **Comprobante primero** (el orden favorece la captura en campo). Debe haber **al menos uno** de los dos (DP-15 ✅):
   - **Soporte (imagen):** "Tomar foto" abre la cámara trasera, o "Elegir imagen". Se muestra la miniatura; la imagen se comprime en el cliente.
   - **Archivo (PDF):** "Adjuntar PDF" para facturas electrónicas o documentos digitales.
3. Datos (equivalen a `Registro_Gastos`):
   - Fecha de factura (por defecto hoy; no puede ser futura)
   - **Rubro** (catálogo; por ejemplo Hospedaje, Alimentación, Transporte, Combustible, Peajes)
   - **Proyecto** (catálogo; por ejemplo "Rutas PDET 3", "Conexión Agro", "Taller Multipropósito")
   - Concepto (por ejemplo "Taxi aeropuerto")
   - CC/NIT y empresa del proveedor
   - Valor ($)
   - Observaciones (opcional)
4. Guardar. Se ve una barra de progreso de subida y luego un toast "Gasto guardado".
5. El detalle se actualiza: el gasto aparece en la lista y el **total gastado** y el **saldo** se recalculan.
6. Para agregar otro, se repite el flujo (el Sheet ofrece "Guardar y agregar otro").

**Alternos:**
- Sin soporte ni archivo: se permite guardar, pero el gasto queda marcado "Falta comprobante" (en `warning`) y **la legalización no puede continuar**: ADMIN no podrá aprobarla (RN-21, supuesto S-04).
- PDF elegido como soporte, o imagen como archivo: error en línea "El soporte debe ser una imagen" / "El archivo debe ser un PDF" (RN-13).
- Archivo de más de 10 MB o de tipo no permitido: error en línea (RN-13).
- Fecha de factura futura: error en línea (RN-07).
- Sin conexión o subida fallida: "No se pudo subir. Reintentar". Los datos del formulario se conservan.
- **Editar o eliminar** un gasto: en la tarjeta, `⋯` → Editar / Reemplazar soporte / Reemplazar archivo / Eliminar (con confirmación).

---

## F-06 · Revisión operativa: aprobar, devolver o rechazar

**Actor:** ADMIN (o SUPERADMIN) (DP-13 ✅, DP-18 ✅). **Precondición:** legalización ajena con estado PENDIENTE (o APROBADO para devolver).

1. Menú → **Revisión**. Por defecto aparecen las legalizaciones **PENDIENTES** con al menos un gasto, ordenadas por fecha; un indicador muestra cuántos gastos tienen comprobante.
2. Clic en una fila abre el **detalle**:
   - Datos del colaborador y motivo
   - Lista de gastos; cada soporte o archivo se abre en un visor (imagen ampliable o PDF) con URL temporal
   - Checklist: ✅ al menos un gasto · ✅ todos los gastos con soporte o archivo
   - Resumen de saldo (solo lectura) e historial
3. ADMIN **revisa los comprobantes** y el **cumplimiento de políticas**, y decide:
   - **Aprobar** → confirmación "¿Aprobar LG-000123?" → el estado pasa a **APROBADO**; el dueño ya no puede editar (RN-06). El botón queda deshabilitado, con el motivo visible, si el checklist no está completo.
   - **Devolver** → comentario obligatorio ("El soporte del hotel es ilegible") → la legalización sigue **PENDIENTE**, marcada **"Devuelta"**; el viajero ve el comentario en una alerta en su detalle y corrige (vuelve a F-05). ADMIN también puede devolver una legalización **APROBADA** mientras no esté pagada ni procesada.
   - **Rechazar** → comentario obligatorio → el estado pasa a **RECHAZADO** (final).
4. (Si DP-06 aplica) El viajero recibe un correo.

**Reglas:** ADMIN no ve los botones de valor transferido ni de estado financiero (RN-26). Nadie modifica los gastos del viajero (DP-12). ADMIN no revisa sus propias legalizaciones (RN-27).

**Alternos:** si el servidor detecta al aprobar que falta un comprobante (por concurrencia), responde 409 y la UI muestra qué gastos fallan.

---

## F-07 · Gestión financiera: valor transferido

**Actor:** FINANCIERO (o SUPERADMIN) (DP-04 ✅). **Precondición:** legalización ajena no rechazada.

1. Menú → **Pagos**. Por defecto aparecen las legalizaciones **APROBADAS** con estado financiero PENDIENTE o TRANSFERIDO, ordenadas por fecha.
2. Filtra por viajero, proyecto, fechas, estado financiero o signo del saldo. El resumen superior muestra los totales a reembolsar y a reintegrar.
3. En el detalle → **"Registrar valor transferido"** → ingresa el monto asignado (`Valor_T`) → Guardar. El sistema recalcula el valor transferido (0 si hay recursos propios, RN-14) y el saldo, y registra un evento con el valor anterior y el nuevo. Puede hacerlo también como anticipo, mientras la legalización esté PENDIENTE.
4. Si hizo el desembolso, cambia el estado financiero a **TRANSFERIDO** (F-08).

**Reglas:** FINANCIERO no aprueba, devuelve ni rechaza (RN-26); si encuentra un problema en los comprobantes, se lo indica a ADMIN. No edita los gastos del viajero (DP-12).

---

## F-08 · Estado financiero y liquidación

**Actor:** FINANCIERO (o SUPERADMIN) (DP-13 ✅, DP-18 ✅).

1. Hace la transferencia, el reembolso o recibe el reintegro fuera del sistema (banca).
2. En el detalle → **"Cambiar estado financiero"** → elige `Transferido`, `Pagado` o `Procesado` y agrega una observación opcional (por ejemplo, la referencia de la transferencia).
3. Para **Pagado** o **Procesado** la confirmación muestra el resumen: "LG-000123 · Ana Pérez · Saldo −$120.000 (a reembolsar). ¿Confirmar?". Solo está disponible si la legalización está **APROBADA** y todos sus gastos tienen comprobante (RN-03).
4. Confirmar. Se actualiza el estado financiero, se registran `estado_financiero_at` y el evento, y, si es Pagado o Procesado, la fila sale del filtro por defecto de Pagos.
5. Toast "Estado financiero actualizado".

**Alternos:** si ADMIN la devolvió al mismo tiempo, el servidor responde 409 "La legalización ya cambió de estado" y la vista se recarga. Con recursos propios, el saldo es −total gastado: la empresa reembolsa todo (RN-25).

---

## F-09 · Generar el PDF

**Actor:** el dueño (las suyas), o FINANCIERO, ADMIN y SUPERADMIN (todas).

1. En el detalle de cualquier legalización → **"Descargar PDF"** (botón secundario, o `⋯` en móvil).
2. El botón muestra "Generando…".
3. Se descarga `LG-000123.pdf` con el encabezado corporativo, los datos del colaborador, el motivo, la tabla de gastos (con rubro y proyecto), los totales, el saldo, los dos estados, el historial y las miniaturas de los soportes de imagen.
4. En móvil se abre con el visor del sistema y se puede compartir.

**Alternos:** si falla la generación, aparece "No se pudo generar el PDF. Reintentar" (con `request_id` en el log).

---

## F-10 · Consultar indicadores

**Actor:** FINANCIERO, ADMIN o SUPERADMIN.

1. Menú → **Indicadores**.
2. Filtros:
   - **Fecha inicio y fecha fin**, que equivalen al `Segmentador` de AppSheet (DP-02 ✅) y se aplican sobre la **fecha de factura** de los gastos (DP-16 ✅). Por defecto el mes actual, con atajos "Este mes", "Trimestre" y "Año".
   - Proyecto (opcional).
3. Se ven:
   - (Opcional MVP) KPIs: total transferido, total gastado, por reembolsar, por reintegrar, pendientes de aprobación y pendientes de pago.
   - **Barras:** consumo por proyecto (suma de los gastos de cada proyecto con fecha de factura en el rango), de mayor a menor.
   - **Dona:** cantidad de legalizaciones por estado operativo (supuesto S-07).
4. Clic en una barra o segmento abre la lista de legalizaciones filtrada (Pagos o Legalizaciones con ese proyecto o estado).
5. "Ver como tabla" ofrece la versión accesible de cada gráfico.

**Alternos:** si no hay datos en el rango, aparece "No hay gastos en este período" con un botón para ampliar el rango.

---

## F-11 · Navegación general por rol

| Rol | Menú visible | Vista inicial |
| :--- | :--- | :--- |
| VIAJERO | Legalizaciones · Perfil | Legalizaciones (propias) |
| ADMIN | Legalizaciones · Revisión · Pagos (lectura) · Indicadores · Cargos · Usuarios | Revisión (pendientes) |
| FINANCIERO | Legalizaciones · Pagos · Indicadores · Cargos (lectura) | Pagos |
| SUPERADMIN | Todo lo anterior + Catálogos (+ Auditoría, post-MVP) | Legalizaciones (todas) |

Para roles con acceso global, **Legalizaciones** tiene un selector "Mías / Todas". "Revisión" es la lista de legalizaciones con el filtro `estado = PENDIENTE` preaplicado, no un módulo aparte.
