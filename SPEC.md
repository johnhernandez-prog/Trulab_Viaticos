# SPEC — Trulab Viajes (Sistema de Gestión de Viáticos)

> **Fuente principal de verdad del proyecto.** Consolida el informe de auditoría de la app AppSheet "Trulab viajes" (legalización de gastos), el análisis funcional de AppSheet (DP-01, DP-02, DP-04, DP-07, DP-13 a DP-18) y el análisis de los 10 archivos de la app Google Apps Script "Solicitud de tiquetes y gastos de viaje" (DP-19, DP-20), que se fusionan en una sola plataforma.
> Cuando un informe y la app real se contradicen, manda la app real. Si algo no está aquí, se decide y se agrega aquí antes de implementarlo.

| Campo | Valor |
| :--- | :--- |
| Versión | **0.4** |
| Fecha | 2026-11-12 |
| Estado | **Sin decisiones bloqueantes.** El 2026-11-12 el dueño del producto aprobó cambios estratégicos que **reemplazan** DP-01 (acceso híbrido, ADR-027), cierran DP-05 (AWS, ADR-028) y agregan DP-19 (entidad unificada `viaticos`, ADR-029) y DP-20 (tarifas por tipo de vinculación, ADR-030). El baseline `62b91cf` queda superado por esta versión; el resto de decisiones definitivas se mantiene. Cualquier cambio posterior requiere decisión explícita del dueño del producto y un ADR |

---

## 1. Resumen ejecutivo

Trulab Viajes es la reconstrucción, con código propio, de dos sistemas que hoy están separados y que se fusionan en uno:

1. **AppSheet "Trulab viajes":** el colaborador registra los gastos de su viaje con soporte digital (**legalización**); ADMIN aprueba; FINANCIERO registra lo transferido, paga y liquida.
2. **Google Apps Script "Solicitud de tiquetes y gastos de viaje":** el colaborador pide, **antes del viaje**, tiquetes y viáticos (trayectos, días de estadía y presupuesto calculado por tarifa), con PDF firmado.

La plataforma unifica ambos en una sola entidad trazable, el **viático** (`VT-000001`), que recorre dos etapas: **SOLICITUD** (antes del viaje) y **LEGALIZACIÓN** (después). También admite viajes sin solicitud previa o con recursos propios (`LEGALIZACION_DIRECTA`).

**Acceso híbrido** (DP-01 reemplazada, ADR-027). Trulab trabaja con **prestadores de servicios externos** que no tienen correo `@trulab.co` (por la no subordinación que exige la regulación laboral colombiana). Por eso:
- `VIAJERO`, `ADMIN` y `FINANCIERO` entran con **usuario y contraseña**, con recuperación por correo y cambio obligatorio de la contraseña temporal.
- `SUPERADMIN` entra **exclusivamente con Google OAuth** de una cuenta corporativa `@trulab.co`.

**Superadministrador principal:** `john.hernandez@trulab.co` (John Hernandez), creador del sistema. Cualquier `SUPERADMIN` activo puede crear o promover a otros `SUPERADMIN` (cuenta `@trulab.co`).

La migración tiene cuatro objetivos: quitar la dependencia y el costo por usuario de AppSheet y de Apps Script; mover la seguridad al backend; dar una experiencia responsiva en móvil, tablet y escritorio; y dejar la base lista para OCR e integraciones.

**Restricción de ejecución:** 1 desarrollador full-stack. El plan original de 4 semanas se amplía con una **semana 5 de holgura, activada formalmente** por el nuevo alcance (`SPRINTS.md`).

## 2. Objetivo del sistema

Garantizar trazabilidad entre **lo que el colaborador pide** (solicitud), **lo que la empresa transfiere** (o el hecho de que viajó con recursos propios) y **lo que el colaborador legaliza** con comprobantes, sobre un mismo folio `VT-xxxxxx`. El sistema calcula el presupuesto tarifario y el saldo, y registra la aprobación operativa y la liquidación financiera de cada etapa.

## 3. Alcance

**Dentro del alcance (sistema completo):**
- Cargos.
- Usuarios con roles, incluida la distinción empleado / prestador de servicios.
- Catálogos administrables: proyectos, rubros, células y **tarifas de viáticos** (DP-14 ✅, DP-20 ✅).
- **Viáticos** (entidad unificada): solicitud con trayectos, cálculo tarifario y PDF firmado; legalización con gastos.
- Registro de gastos clasificados por rubro y proyecto, con soporte (imagen) y/o archivo (PDF).
- Registro del valor transferido o de los recursos propios.
- Flujo de estados: etapa, estado operativo (ADMIN) y estado financiero (FINANCIERO).
- Módulo de pagos con saldos.
- Reportes PDF: **PDF de solicitud** (con firma) y **PDF de legalización**.
- Indicadores con filtro por rango de fechas sobre la fecha de factura.
- Autenticación híbrida y envío de correos transaccionales (restablecimiento de contraseña).
- Migración de datos históricos desde AppSheet.

**Fuera del alcance del MVP** (ver §16): OCR, Google Chat, integración con Asana, exportación a Excel, atributos extendidos de proyecto, estados `Devuelto` y `Cancelado` como valores propios, app nativa, multi-moneda.

**Fuera del alcance total:** contabilidad general, nómina y ERP.

## 4. Módulos del sistema

| # | Módulo | Propósito | Prioridad | En MVP |
| :- | :--- | :--- | :--- | :---: |
| M1 | Autenticación | Login híbrido (usuario/contraseña para operativos; Google `@trulab.co` para SUPERADMIN), recuperación y cambio de contraseña, sesión y perfil | Crítica | ✅ |
| M2 | Usuarios | Directorio: rol, cargo, cédula, célula, tipo de vinculación (prestador), activación; SUPERADMIN gestiona a otros SUPERADMIN | Crítica | ✅ |
| M3 | Cargos | Catálogo de puestos | Media | ✅ |
| M3b | Catálogos | Proyectos, rubros y células, administrados por SUPERADMIN (DP-14 ✅) | Alta | ✅ |
| M3c | **Tarifas de viáticos** | Tarifas por ciudad y tipo de vinculación (empleado / prestador), administradas por SUPERADMIN (DP-20 ✅) | Alta | ✅ |
| M4 | **Viáticos** | Entidad unificada `VT-`: modalidad, etapa, estado operativo, estado financiero, recursos propios, valor transferido | Crítica | ✅ |
| M4b | **Solicitud de viáticos** | Trayectos (1–5), tiquetes, cálculo tarifario, firma, formato de prestador | Crítica | ✅ |
| M5 | Registro de gastos | Ítems de la etapa de legalización con rubro, proyecto, concepto, NIT, empresa, valor, soporte y archivo | Crítica | ✅ |
| M6 | Pagos | Vista financiera de saldos, valor transferido, estado financiero y liquidación | Crítica | ✅ |
| M7 | Reportes PDF | **PDF de solicitud** (con firma) y **PDF de legalización** | Alta | ✅ |
| M8 | Indicadores | Dashboard: consumo por proyecto y distribución por estado, por rango de fecha de factura | Alta | ✅ |
| M9 | Notificaciones | Correo (Amazon SES) ante cambios de estado. El correo de **restablecimiento de contraseña** sí es MVP (parte de M1) | Media | ⚠️ Opcional (DP-06) |
| M10 | OCR de soportes | Extracción automática de datos de comprobantes | Baja | ❌ Futuro |
| M11 | Google Chat | Tarjetas y comandos `/` | Baja | ❌ Futuro |
| M12 | Integración Asana | Crear tareas al solicitar hospedaje o tiquetes | Baja | ❌ Futuro (§16) |

## 5. Actores del sistema

| Actor | Descripción |
| :--- | :--- |
| Viajero | Colaborador (empleado) o **prestador de servicios** que viaja: solicita viáticos y tiquetes, registra sus gastos con comprobantes y puede viajar con recursos propios |
| Administrador (ADMIN) | **Operación interna** (DP-18 ✅): revisa solicitudes y comprobantes, controla políticas, gestiona tiquetes y **aprueba, rechaza o devuelve** en ambas etapas. Gestiona usuarios operativos y cargos. **No** toca dinero: no registra valor transferido, no cambia el estado financiero, no paga ni liquida |
| Financiero | **Tesorería** (DP-04 ✅, DP-18 ✅): valor asignado/transferido, desembolsos, pagos y liquidaciones. Único que cambia el estado financiero |
| Superadministrador (SUPERADMIN) | Acceso completo; administra catálogos y tarifas; **crea o promueve a otros SUPERADMIN**. Sistema creado por `john.hernandez@trulab.co` |
| Dirección General | Consume indicadores (se le asigna FINANCIERO o ADMIN; no es un rol propio) |
| Administradores de Google Workspace (externo) | Gestionan las cuentas `@trulab.co` y el OAuth Client ID. Solo afectan a los SUPERADMIN |
| Sistema | Valida identidad, asigna estados iniciales, calcula presupuesto, valor transferido y saldo, genera folios, registra el historial y genera PDFs |

## 6. Roles y permisos (RBAC)

Hay cuatro roles, y cada usuario tiene **exactamente uno**: `VIAJERO`, `FINANCIERO`, `ADMIN` y `SUPERADMIN`. El rol es lo único que determina los permisos.

Leyenda: C=crear, R=leer, U=editar, D=eliminar (lógico), — = denegado. "Viático" incluye sus dos etapas.

| Recurso / acción | VIAJERO | FINANCIERO | ADMIN | SUPERADMIN |
| :--- | :---: | :---: | :---: | :---: |
| Viáticos propios (solicitud y legalización) | C R U D¹ | C R U D¹ | C R U D¹ | C R U D |
| Viáticos de otros | — | R | R | C R U D |
| Gastos de viáticos propios | C R U D¹ | C R U D¹ | C R U D¹ | C R U D |
| Gastos y comprobantes de viáticos de otros | — | R | R | C R U D |
| Previsualizar presupuesto tarifario | ✅ | ✅ | ✅ | ✅ |
| Marcar "Recursos propios" (al crear, `LEGALIZACION_DIRECTA`; DP-17 ✅) | ✅ propios | ✅ propios | ✅ propios | ✅ |
| **Registrar o modificar el valor asignado/transferido** (DP-04 ✅) | — | ✅² | **—** | ✅ |
| **Estado operativo:** Aprobar / Rechazar / Devolver (DP-13 ✅, DP-18 ✅) — solicitud y legalización | — | **—** | ✅² | ✅ |
| **Gestionar tiquetes** (registrar emisión) | — | — | ✅² | ✅ |
| **Habilitar legalización** de una solicitud aprobada (dueño) | ✅ propios | ✅ propios | ✅ propios | ✅ |
| **Estado financiero:** Transferido / Pagado / Procesado (DP-13 ✅) | — | ✅² | **—** | ✅ |
| Módulo Pagos | — | R U | R³ | C R U D |
| Cargos | — | R | C R U D | C R U D |
| Usuarios operativos (`VIAJERO`, `ADMIN`, `FINANCIERO`): crear, editar, desactivar, restablecer contraseña | — | — | C R U D⁴ | C R U D |
| **Usuarios `SUPERADMIN`: crear o promover, editar, desactivar** | — | — | **—** | ✅⁵ |
| Catálogos (proyectos, rubros, células) | R | R | R | C R U D⁶ |
| **Tarifas de viáticos** (DP-20 ✅) | R (vía preview) | R | R | C R U D⁶ |
| Indicadores | — | R | R | R |
| Descargar PDF de solicitud / legalización | propios | todos | todos | todos |
| Auditoría | — | — | — | R |

¹ El dueño edita **mientras el estado operativo es `PENDIENTE`** en la etapa actual (incluida una devolución). La solicitud queda congelada al habilitar la legalización. Eliminar: solo en `PENDIENTE` con estado financiero `PENDIENTE` (RN-09).
² Sobre viáticos **ajenos**: nadie salvo SUPERADMIN aprueba, valida financieramente ni paga el suyo (RN-27, definitiva). FINANCIERO y ADMIN nunca editan los gastos ni la solicitud del viajero (DP-12).
³ ADMIN consulta saldos en solo lectura (DP-18 ✅).
⁴ ADMIN no puede crear, promover ni modificar usuarios `SUPERADMIN`.
⁵ Con auditoría (`SUPERADMIN_ASIGNADO`). No se puede desactivar ni degradar al **último SUPERADMIN activo** (RN-12).
⁶ Los valores en uso no se eliminan: se desactivan (RN-24).

La autorización se aplica **en el backend**. El frontend solo oculta lo que no corresponde (`docs/architecture.md` §6).

## 7. Casos de uso principales

| ID | Caso de uso | Actor principal |
| :--- | :--- | :--- |
| CU-01 | Iniciar sesión: usuario y contraseña (operativos) o Google `@trulab.co` (SUPERADMIN) | Todos |
| CU-01b | Recuperar, restablecer y cambiar la contraseña; cambio obligatorio de la temporal | VIAJERO, ADMIN, FINANCIERO |
| CU-02 | Crear / editar / desactivar usuario operativo, asignar rol, cargo, cédula, célula y tipo de vinculación; restablecer su contraseña | ADMIN, SUPERADMIN |
| CU-02b | **Crear o promover a otro SUPERADMIN** (cuenta `@trulab.co`) | SUPERADMIN |
| CU-03 | Gestionar catálogo de cargos | ADMIN, SUPERADMIN |
| CU-04 | Crear un viático: **`CON_SOLICITUD`** (pedir viáticos y tiquetes antes del viaje) o **`LEGALIZACION_DIRECTA`** (cargar gastos ya realizados / recursos propios) | Todos |
| CU-04b | Diligenciar la solicitud: proyecto (catálogo u "Otro"), líder, trayectos (1–5), tiquetes, firma, comentarios; ver el presupuesto calculado | Dueño |
| CU-05 | Registrar gasto: rubro, proyecto, concepto, CC/NIT, empresa, valor, fecha de factura, soporte y/o archivo | Dueño |
| CU-06 | **Aprobar** la solicitud o la legalización | ADMIN, SUPERADMIN |
| CU-07 | Revisar comprobantes y cumplimiento de políticas | ADMIN (FINANCIERO en consulta) |
| CU-08 | **Devolver** (a `PENDIENTE`) o **rechazar** | ADMIN, SUPERADMIN |
| CU-08b | Gestionar tiquetes (registrar emisión) | ADMIN, SUPERADMIN |
| CU-09 | Gestionar el **estado financiero**: transferido, pagado, procesado | FINANCIERO, SUPERADMIN |
| CU-09b | **Habilitar la legalización** sobre la solicitud aprobada (y desembolsada, si pidió gastos de viaje) | Dueño |
| CU-10 | Generar / descargar PDF de solicitud o de legalización | Dueño, FINANCIERO, ADMIN |
| CU-11 | Consultar indicadores por rango de fecha de factura | FINANCIERO, ADMIN, SUPERADMIN |
| CU-12 | Migrar datos históricos de AppSheet (una sola vez) | SUPERADMIN / desarrollador |
| CU-13 | Registrar o modificar el valor asignado (desembolso) | **Solo FINANCIERO** (y SUPERADMIN) |
| CU-14 | Administrar catálogos de proyectos, rubros y células | **Solo SUPERADMIN** |
| CU-15 | **Administrar las tarifas de viáticos** por ciudad y tipo de vinculación | **Solo SUPERADMIN** |

## 8. Reglas de negocio

| ID | Regla |
| :--- | :--- |
| RN-01 | **Aislamiento por dueño:** un VIAJERO solo ve y opera sus propios viáticos y gastos. FINANCIERO, ADMIN y SUPERADMIN ven todos. Se aplica en el backend en **todas** las consultas. |
| RN-02 | **Saldo** = `valor_transferido − Σ(gastos.valor)` de gastos no eliminados, con el `valor_transferido` efectivo de RN-14. Se calcula (vista `v_viatico_saldos`); no se almacena. `saldo > 0`: el viajero **reintegra** a la empresa. `saldo < 0`: la empresa **reembolsa** al viajero (se muestra en rojo). El saldo solo es relevante en la etapa `LEGALIZACION`. |
| RN-03 | **Liquidación:** `estado_financiero` solo pasa a `PAGADO` o `PROCESADO` si la etapa es `LEGALIZACION`, el estado operativo es `APROBADO`, hay al menos un gasto y todos cumplen RN-21. |
| RN-04 | **Folios legibles** con prefijo y 6 dígitos secuenciales: `CA-000001` (cargos) y **`VT-000001` (viáticos; reemplaza a `LG-`)**. El folio `VT-` es el mismo en la solicitud y en la legalización. Son distintos de la PK interna. Ver DP-09. |
| RN-05 | **Tres dimensiones independientes** en `viaticos`: (a) **`etapa`**: `SOLICITUD` \| `LEGALIZACION` (lo cambia solo la acción *habilitar legalización*); (b) **`estado`** (operativo, AppSheet `Estado`): `PENDIENTE` → `APROBADO` / `RECHAZADO`, con *devolver* que regresa a `PENDIENTE`, vigente en **ambas** etapas; (c) **`estado_financiero`** (AppSheet `Estado_P`): `PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO`. `Estado legalizacion` = `[Estado]` no se almacena (RN-23). Inician en `PENDIENTE`. Transiciones en `docs/user-flows.md`. |
| RN-06 | **Aprobar** exige: en etapa `SOLICITUD`, trayectos válidos (RN-30), presupuesto calculado o formato adjunto de prestador (RN-33), firma (RN-32) y fecha de nacimiento si requiere tiquete (RN-31); en etapa `LEGALIZACION`, al menos un gasto y que todos cumplan RN-21. Al aprobar, el dueño ya no edita esa etapa. |
| RN-07 | **Fechas** (DP-16 actualizada): las **fechas de viaje** (`fecha_ida`, `fecha_regreso`) existen ahora en `viatico_trayectos` (RN-30). La **fecha de factura** de cada gasto sigue siendo obligatoria, no futura, y es la **base de los indicadores** (RN-18). `fecha_legalizacion` es solo la fecha de creación del registro. |
| RN-08 | Valores monetarios en **COP**, `> 0` en gastos y `>= 0` en valor asignado y tarifas. Decimal exacto; nunca flotante. |
| RN-09 | **Eliminación lógica:** nada operativo se borra físicamente. Un viático solo se elimina con `estado = PENDIENTE` y `estado_financiero = PENDIENTE`. |
| RN-10 | **Trazabilidad** (`viatico_eventos`): cada cambio de **etapa**, de estado operativo o financiero, la gestión de tiquetes, y cada cambio de valor asignado o recursos propios registra quién, cuándo, valor anterior, nuevo y comentario. **Devolver y Rechazar exigen comentario.** La liquidación registra reintegro (`saldo > 0`) o reembolso (`saldo < 0`). |
| RN-11 | Un usuario desactivado no puede iniciar sesión (por ningún método) y sus sesiones se revocan; su historial se conserva. |
| RN-12 | **Control de acceso híbrido** (reemplaza la versión de DP-01; ADR-027). Se exigen siempre: usuario **existente, activo y con rol**. Además: **(a) `VIAJERO`/`ADMIN`/`FINANCIERO`** entran **solo** con `username` + contraseña; no pueden usar Google OAuth. **(b) `SUPERADMIN`** entra **solo** con Google OAuth: cuenta de Google Workspace del dominio **`@trulab.co`** (claim `hd`), correo verificado y registrado; no tiene contraseña y no puede usar el formulario de usuario/contraseña. **No hay autorregistro.** Los operativos los crean ADMIN o SUPERADMIN. **Gestión de SUPERADMIN:** el creador del sistema y `SUPERADMIN` inicial es **John Hernandez (`john.hernandez@trulab.co`, `SUPERADMIN_EMAIL`)**; cualquier `SUPERADMIN` activo puede **crear o promover** a otros `SUPERADMIN` (solo con correo `@trulab.co`); ADMIN no. **Nunca** puede desactivarse ni degradarse al **último SUPERADMIN activo**. Cada alta o promoción se audita (`SUPERADMIN_ASIGNADO`). Fallo de cualquier condición → acceso denegado (`ACCESO_DENEGADO`). |
| RN-13 | **Tipos de adjunto** (DP-15 ✅). Gasto: `soporte` = imagen (JPG, PNG, WEBP, HEIC) y `archivo` = PDF. Solicitud: `firma` = imagen (PNG, JPG, WEBP) y `formato adjunto` = PDF o XLSX (RN-33). Máximo 10 MB por archivo. El tipo se valida por contenido (*magic bytes*), no por extensión; se rechazan SVG y HTML. |
| RN-14 | **Recursos propios** (regla real de AppSheet): `valor_transferido = 0` si `recursos_propios = true`; si no, `= valor_asignado`. Calculado, nunca escrito a mano. **Se mantiene igual en la migración.** `recursos_propios = true` solo es válido en `LEGALIZACION_DIRECTA` (RN-28). |
| RN-15 | **Contraseñas** (reemplaza "sin contraseñas"; ADR-027). Solo existen para `VIAJERO`, `ADMIN` y `FINANCIERO`. Se guardan con **Argon2id**; mínimo 12 caracteres; nunca en claro ni en logs. Toda contraseña asignada por el sistema es **temporal** y exige cambio en el primer acceso (`debe_cambiar_password`). **Recuperación:** el usuario pide el restablecimiento con su usuario o correo; el sistema responde siempre lo mismo (no revela si existe) y envía por correo un enlace con un token de **un solo uso**, de **15–30 min**, guardado solo como hash SHA-256. Restablecer o cambiar la contraseña revoca todas las sesiones. Intentos de login limitados (RNF-02). **SUPERADMIN no tiene contraseña.** Se audita `LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `PASSWORD_CAMBIADA`, `PASSWORD_RECUPERACION_SOLICITADA`, `ACCESO_DENEGADO`, `SUPERADMIN_ASIGNADO`. |
| RN-16 | **Proyecto y rubro** (DP-02, DP-14, **esquema híbrido de proyecto, ADR-031**). El **rubro** sale siempre de la lista cerrada (catálogo `rubros`). El **proyecto** se elige de la lista de proyectos **activos** del catálogo `proyectos` (administrado por SUPERADMIN) **o** de la opción fija **"Otro"**, que siempre está disponible: al elegirla, el formulario exige escribir el nombre del proyecto en `proyecto_otro` (texto obligatorio, 3–150 caracteres) para cuando aún no exista en el catálogo. Se guarda **exactamente uno** de los dos (`proyecto_id` o `proyecto_otro`; `CHECK` en la BD). Aplica al **gasto** y a la **cabecera de la solicitud** (`CON_SOLICITUD`); una legalización puede tener gastos de varios proyectos. "Otro" no es una fila del catálogo sino una opción de la interfaz. Los proyectos escritos a mano se pueden revisar después para crearlos en el catálogo; el sistema no los convierte solo. |
| RN-17 | **Datos del colaborador automáticos:** nombre, cargo, cédula, célula y tipo de vinculación del viático se toman del usuario autenticado y se guardan como instantánea. El viajero nunca los escribe. |
| RN-18 | **Filtro temporal de indicadores:** siempre sobre **`gastos.fecha_factura`** con `BETWEEN desde AND hasta`. No se usan fechas de viaje ni `fecha_legalizacion` para el análisis financiero. |
| RN-19 | Solo **FINANCIERO** (y SUPERADMIN) registra o modifica el `valor_asignado` (DP-04). El `presupuesto_solicitado` calculado en la solicitud es solo un **monto sugerido de referencia** para el desembolso; no es el valor transferido. |
| RN-20 | **Estado operativo:** solo **ADMIN** (y SUPERADMIN) aprueba, rechaza o devuelve, en la etapa `SOLICITUD` y en la `LEGALIZACION`. `RECHAZADO` es final. *Devolver* desde `APROBADO` solo si `estado_financiero` ∉ {`PAGADO`, `PROCESADO`}; en la etapa `SOLICITUD`, tampoco si ya se habilitó la legalización. |
| RN-21 | **Adjunto mínimo** (DP-15): cada gasto debe tener **al menos uno** de `soporte` o `archivo`. Sin ninguno se puede guardar, pero bloquea Aprobar (RN-06) y la liquidación (RN-03). |
| RN-22 | **Estado financiero:** solo **FINANCIERO** (y SUPERADMIN). `PAGADO` y `PROCESADO` exigen RN-03. |
| RN-23 | **Estado legalizacion es un espejo** de `estado`; no se almacena. |
| RN-24 | **Catálogos administrables** (DP-14): proyectos, rubros y células viven en tablas maestras administradas por SUPERADMIN; se desactivan, no se borran; nombres únicos. El mismo criterio rige para `tarifas_viaticos` (RN-29). |
| RN-25 | **Recursos propios lo marca el VIAJERO** al crear un viático `LEGALIZACION_DIRECTA` (DP-17): transferido = 0 y la empresa reembolsa. |
| RN-26 | **Separación de funciones** (DP-18): ADMIN = operación interna; FINANCIERO = tesorería. Ninguno ejecuta las acciones del otro. |
| RN-27 | **Sin autoaprobación, en todas las etapas** (definitiva; ADR-025): **nadie aprueba, rechaza, devuelve, valida financieramente ni liquida un viático creado por sí mismo**, ni en la etapa `SOLICITUD` ni en la `LEGALIZACION`; tampoco registra su propio valor asignado. **Única excepción: SUPERADMIN**, con auditoría. |
| RN-28 | **Modalidades** (DP-19). **`CON_SOLICITUD`:** nace en etapa `SOLICITUD`; con la solicitud `APROBADO` (y `TRANSFERIDO` si `requiere_gastos_viaje`), el dueño ejecuta *habilitar legalización*: **sobre el mismo `VT-xxxxxx`** pasa a etapa `LEGALIZACION` y el estado operativo vuelve a `PENDIENTE` para auditar las facturas. **`LEGALIZACION_DIRECTA`:** nace directamente en etapa `LEGALIZACION` (viaje ya hecho, con o sin recursos propios). La modalidad no cambia después de crear. |
| RN-29 | **Cálculo tarifario.** Por trayecto con `dias_estadia`: `trans_interno = dias_estadia > 1 ? trans_interno_varios_dias : trans_interno_dia_1`; `gasto_diario = vr_alimentacion + trans_interno + otros_gastos`; `subtotal_estadia = gasto_diario × dias_estadia`. `presupuesto_solicitado = Σ(subtotal_estadia + transporte_aeropuerto + transporte_intermunicipal)`. Las tarifas salen de `tarifas_viaticos` según la **ciudad de destino** y `es_prestador_servicios` del viajero (empleado y prestador tienen tablas distintas). El cálculo lo hace **solo el servidor**; el solicitante **no edita** los valores unitarios. Si necesita más dinero, lo justifica en `comentarios` con la autorización del líder de proyecto. Se guarda una instantánea de las tarifas aplicadas en cada trayecto. Si `requiere_gastos_viaje = false`, no hay cálculo. |
| RN-30 | **Trayectos:** de **1 a 5** por solicitud, con `orden`; `ciudad_destino` distinta de `ciudad_origen` salvo que sea `"Otro"`; `fecha_regreso >= fecha_ida`; `dias_estadia` entero `>= 1`, sugerido como `ceil(fecha_regreso − fecha_ida) + 1` y editable por el usuario; `requiere_hospedaje` booleano. Ciudades de la lista cerrada de `tarifas_viaticos`. |
| RN-31 | **Fecha de nacimiento:** si `requiere_tiquete = true`, el viajero debe tener `fecha_nacimiento` (para la emisión de tiquetes); se toma de su perfil o la completa al solicitar, y se guarda como instantánea. Dato personal (RNF-09). |
| RN-32 | **Firma:** la solicitud lleva la firma del solicitante (imagen) y se incrusta en el PDF oficial de solicitud. Se puede reutilizar la firma guardada en el perfil. Sin firma no se puede aprobar la solicitud ni generar su PDF. |
| RN-33 | **Formato adjunto de prestador:** si el viajero es **prestador de servicios** y el `proyecto_id` de la solicitud tiene `exige_formato_prestador = true` (p. ej. `P-CONEXI-002`; configurable en el catálogo, no en el código; un proyecto escrito en "Otro" no tiene esa marca, así que se calcula por tarifa), **no se calcula presupuesto por tabla**: debe adjuntar un formato diligenciado (PDF o XLSX, `formato_adjunto_id`) y FINANCIERO fija el valor asignado a partir de él. Sin formato no se puede aprobar. |

## 9. Requisitos funcionales

| ID | Requisito | Módulo | MVP |
| :--- | :--- | :--- | :---: |
| RF-001 | Autenticación con **Google OAuth exclusivamente para SUPERADMIN** (dominio `@trulab.co`), validación contra Usuarios y emisión de sesión propia (JWT + refresh) | M1 | ✅ |
| RF-002 | **Reactivado.** Login con **usuario y contraseña** para VIAJERO, ADMIN y FINANCIERO; recuperación y restablecimiento por correo (Amazon SES; log en local); cambio de contraseña y cambio obligatorio de la temporal; hashing Argon2id | M1 | ✅ |
| RF-003 | CRUD de usuarios con rol, cargo, cédula, célula, tipo de vinculación (prestador), fecha de nacimiento, firma y estado activo/inactivo; SUPERADMIN crea o promueve a otros SUPERADMIN | M2 | ✅ |
| RF-004 | CRUD de cargos con folio automático | M3 | ✅ |
| RF-005 | CRUD de viáticos (`VT-`) con filtros (etapa, modalidad, estado, estado financiero, fechas, viajero) y datos del colaborador autocompletados (RN-17) | M4 | ✅ |
| RF-006 | CRUD de gastos con rubro y proyecto (catálogo u "Otro" con nombre escrito), concepto, CC/NIT, empresa, fecha de factura, observaciones, soporte (con captura desde cámara) y archivo | M5 | ✅ |
| RF-007 | Acciones de estado con historial: operativas (aprobar, rechazar, devolver; ADMIN), financieras (FINANCIERO) y *habilitar legalización* (dueño) | M4/M6 | ✅ |
| RF-008 | Vista de pagos: valor transferido, total gastado y saldo, con resaltado de negativos, filtros y orden | M6 | ✅ |
| RF-009 | Generación y descarga del **PDF de legalización** con sus gastos | M7 | ✅ |
| RF-010 | Dashboard: consumo por proyecto del gasto (barras; los proyectos escritos en "Otro" se agrupan por su nombre normalizado y se marcan como fuera de catálogo) y conteo por estado (dona), con filtro por rango de fecha de factura | M8 | ✅ |
| RF-011 | Visualización segura de soportes, archivos, firmas y formatos (URL temporal) | M5 | ✅ |
| RF-012 | Migración de datos históricos desde AppSheet | — | ✅ |
| RF-013 | Notificación por correo (Amazon SES) al aprobar, devolver, rechazar y pagar | M9 | DP-06 |
| RF-014 | Registro de auditoría de acciones sensibles (accesos, contraseñas, roles, SUPERADMIN, estados, valor asignado, catálogos, tarifas, eliminaciones) | Transversal | ✅ |
| RF-015 | Registro y modificación del valor asignado, con historial (RN-14, RN-19) | M6 | ✅ |
| RF-016 | Administración de catálogos (proyectos, rubros, células): crear, renombrar, activar y desactivar, solo SUPERADMIN | M3b | ✅ |
| RF-017 | **Solicitud de viáticos y tiquetes:** hasta 5 trayectos, cálculo tarifario (empleado vs. prestador), previsualización del presupuesto, firma, formato adjunto de prestador, **PDF de solicitud con firma** y paso a legalización sobre el mismo folio | M4b/M7 | ✅ |
| RF-018 | **Administración de tarifas de viáticos** por ciudad y tipo de vinculación (6 conceptos), solo SUPERADMIN, con seed inicial de los 22 destinos | M3c | ✅ |

## 10. Requisitos no funcionales

| ID | Categoría | Requisito | Cómo se verifica |
| :--- | :--- | :--- | :--- |
| RNF-01 | Rendimiento | Carga inicial < 1,2 s (LCP en 4G), API p95 < 200 ms en operaciones CRUD (el login con Argon2id puede tardar más, < 1 s) | Lighthouse, logs |
| RNF-02 | Seguridad | TLS en tránsito, cifrado en reposo (AES-256), autorización en backend, RLS como defensa en profundidad. **Contraseñas con Argon2id** (parámetros OWASP), política de 12+ caracteres, **límite de intentos de login** por usuario e IP con bloqueo temporal, respuestas que no revelan si un usuario existe, tokens de recuperación de un solo uso y solo como hash | Pruebas de permisos y de auth, revisión de seguridad |
| RNF-03 | Compatibilidad | Últimas 2 versiones de Chrome, Safari (incluido iOS), Firefox y Edge | Prueba manual |
| RNF-04 | Responsivo | Usable desde 360 px; mobile-first | Revisión en 3 tamaños |
| RNF-05 | Accesibilidad | WCAG 2.1 AA en flujos críticos | axe y teclado |
| RNF-06 | Mantenibilidad | Tipado estático, lint en CI, migraciones versionadas | CI |
| RNF-07 | Pruebas | Las reglas de negocio y la matriz RBAC tienen pruebas automatizadas; cobertura ≥ 80 % en la capa de servicios | CI |
| RNF-08 | Disponibilidad | Horario laboral; respaldo diario de BD (RDS) con retención de 7 días como mínimo | Política de AWS |
| RNF-09 | Privacidad | Datos personales según la Ley 1581 de 2012. La **cédula**, la **fecha de nacimiento** y la **firma** solo las ven el titular, FINANCIERO, ADMIN y SUPERADMIN, y nunca aparecen en logs. Los archivos nunca son públicos | Revisión |
| RNF-10 | Observabilidad | Logs estructurados con id de petición; errores 5xx registrados | Revisión |

## 11. Flujos críticos

Detalle en `docs/user-flows.md`.

1. **Acceso dual:** operativos → usuario y contraseña (→ cambio obligatorio si es temporal) → sesión. SUPERADMIN → Google `@trulab.co` → validación contra Usuarios y rol → sesión. Cualquier fallo deniega.
2. **Ciclo `CON_SOLICITUD`:** el viajero crea la solicitud (trayectos, presupuesto calculado, firma) → ADMIN aprueba (y gestiona tiquetes) → FINANCIERO registra el valor asignado y marca `TRANSFERIDO` → el viajero **habilita la legalización** (mismo `VT-`, estado operativo vuelve a `PENDIENTE`) → carga gastos con soporte → ADMIN aprueba → FINANCIERO liquida (`PAGADO`/`PROCESADO`).
3. **Ciclo `LEGALIZACION_DIRECTA`:** el viajero crea el viático (con o sin recursos propios) → carga gastos → ADMIN aprueba → FINANCIERO registra el valor asignado (si no hay recursos propios) y liquida.
4. **Cálculo de saldo y de presupuesto:** una sola vista SQL para el saldo y una sola función de servidor para el presupuesto; idénticos en pantalla, pagos y PDF.
5. **Aislamiento de datos:** un VIAJERO nunca obtiene datos ajenos, ni adivinando IDs (404).

## 12. Restricciones técnicas

- Un solo desarrollador; se prefieren soluciones conocidas sobre las novedosas.
- Monolito modular. Sin microservicios ni colas en el MVP.
- Desarrollo local en Windows; ejecución en contenedores Linux (Docker).
- **Producción y staging en AWS** (DP-05 ✅, ADR-028): Amazon RDS for PostgreSQL 16, Amazon S3, Amazon SES, y cómputo en AWS ECS Fargate o AWS App Runner.
- La estructura de AppSheet está validada (§18); para el ETL falta la **exportación de datos** (P-2). Las **tarifas iniciales** se extraen de `calcularGastos.html` (Apps Script) y se validan con el dueño del producto antes de cargarse.
- Sin dependencia de AppSheet ni de Apps Script tras el corte. Sin dependencia de Google Sheets (`PROYECTOS`, `CorreosExternos`): los proyectos viven en la tabla maestra (DP-14).
- El OAuth Client ID de Google Workspace solo es necesario para el login de SUPERADMIN (tarea P-3).

## 13. Criterios de aceptación generales

Una funcionalidad está **terminada** cuando:
1. Cumple su RF y las RN asociadas, con pruebas automatizadas de backend para la lógica y los permisos.
2. Respeta la matriz RBAC (§6), con pruebas para el rol permitido y al menos un rol denegado.
3. Funciona en móvil (360 px), tablet (768 px) y escritorio (1280 px).
4. Muestra estados de carga, vacío y error.
5. No introduce errores de lint ni de tipos, y las migraciones aplican desde cero.
6. `HANDOFF.md` está actualizado (y `CLAUDE.md` si cambió una decisión).

## 14. Tecnologías aprobadas

| Capa | Tecnología |
| :--- | :--- |
| Frontend | React 18 + Vite + **TypeScript**, Tailwind CSS, shadcn/ui (Radix), Lucide, TanStack Query, React Router, React Hook Form + Zod, Recharts, Google Identity Services (solo para el login de SUPERADMIN) |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3 |
| Seguridad | google-auth (verificación de ID token, solo SUPERADMIN), PyJWT, **`argon2-cffi`** (Argon2id para contraseñas) |
| AWS | **`boto3`** (Amazon S3: archivos con URLs prefirmadas; Amazon SES: correos transaccionales) |
| PDF | WeasyPrint + plantillas Jinja2 (en Docker) |
| Base de datos | PostgreSQL 16 (**Amazon RDS for PostgreSQL 16** en staging y producción) |
| Archivos | **Amazon S3** (bucket privado) en staging y producción; `STORAGE_BACKEND=local` en desarrollo |
| Correo | **Amazon SES** en staging y producción; en local, el correo se escribe en el log |
| Pruebas | pytest + httpx, con Postgres real en Docker; Vitest + Testing Library; Playwright solo para flujos críticos |
| Calidad | ruff + mypy (backend), ESLint + Prettier + tsc (frontend), pre-commit |
| Infra | Docker Compose (local); **AWS ECS Fargate o AWS App Runner** (cómputo), RDS, S3, SES |

Cualquier tecnología nueva requiere un ADR en `docs/architecture.md` §13.

## 15. Alcance MVP

Incluye M1 a M8 (con M3b, M3c y M4b), el envío de correo de restablecimiento de contraseña, la migración de datos históricos, el despliegue en AWS y las pruebas de RBAC y de reglas de negocio. **Plazo: 5 semanas** (4 originales + la semana 5 de holgura, activada por el nuevo alcance; `SPRINTS.md`).

**Criterio de éxito del MVP:** el equipo de Trulab, incluidos los prestadores de servicios, puede dejar de usar AppSheet y la app de Apps Script. Todo viajero puede pedir viáticos y tiquetes antes de viajar o registrar sus gastos ya realizados desde el celular; ADMIN aprueba, devuelve o rechaza; financiero registra transferencias y liquida; los datos históricos están disponibles.

## 16. Funcionalidades futuras (post-MVP, sin compromiso de fecha)

1. Notificaciones por correo (si no entran al MVP, DP-06).
2. OCR de soportes: precarga de valor, fecha y NIT; el usuario confirma.
3. Integración con Google Chat.
4. Exportación a Excel/CSV.
5. Proyecto enriquecido: código, responsable, cliente o convenio, vigencia.
6. Topes por rubro o por cargo.
7. Estados operativos `DEVUELTO` y `CANCELADO` como valores propios.
8. Registro del pago o reintegro (referencia bancaria y comprobante).
9. PWA instalable y modo sin conexión.
10. Panel de auditoría para SUPERADMIN.
11. **Integración con Asana** (heredada de `consumoApi.html`, hoy inactiva): crear tareas al solicitar hospedaje o tiquetes y vista de seguimiento. No entra al MVP; los proyectos ya viven en la tabla `proyectos`.
12. Inicio de sesión con Google también para operativos que tengan cuenta corporativa (hoy descartado por ADR-027).

## 17. Decisiones

### 17.1 Resueltas: definitivas, no reabrir

Solo se cambian con una decisión explícita del dueño del producto, registrada como ADR nuevo.

| ID | Decisión | Resolución definitiva | ADR |
| :--- | :--- | :--- | :--- |
| **DP-01** ✅ *(actualizada 2026-11-12)* | Autenticación | **Híbrida.** Dominio corporativo `@trulab.co`. **VIAJERO, ADMIN y FINANCIERO:** usuario y contraseña (Argon2id), recuperación por correo y cambio obligatorio de la temporal; **no** usan Google OAuth. **SUPERADMIN:** exclusivamente Google OAuth `@trulab.co`; sin contraseña. SUPERADMIN inicial: `john.hernandez@trulab.co`; cualquier SUPERADMIN activo crea o promueve a otros; nunca se desactiva ni degrada al último. *Motivo:* los prestadores de servicios externos no tienen correo corporativo (no subordinación laboral). **Reemplaza** la versión del 2026-11-10 ("solo Google, sin contraseñas"). RN-12 y RN-15 reescritas; RF-002 reactivado | ADR-027 (reemplaza ADR-006) |
| **DP-02** ✅ | Proyectos y Segmentador | `Segmentador` es solo un filtro temporal (`desde`/`hasta`). Los proyectos se eligen en cada gasto (y en la cabecera de la solicitud) del catálogo **o** con la opción "Otro" y texto propio (RN-16, ADR-031) | ADR-017, ADR-018, ADR-031 |
| **DP-03** ✅ | Estado para devolver | Absorbida por DP-13: *devolver* regresa a `PENDIENTE` con comentario | ADR-021 |
| **DP-04** ✅ | Valor transferido | Solo FINANCIERO (y SUPERADMIN) registra el valor asignado. `valor_transferido = IF(recursos_propios, 0, valor_asignado)` | ADR-019 |
| **DP-05** ✅ *(resuelta 2026-11-12)* | Hosting y archivos | **AWS.** Staging y producción en Amazon Web Services: RDS for PostgreSQL 16, S3 (archivos, URLs prefirmadas de 5 min), SES (correos) y ECS Fargate o App Runner. **Se descarta GCP** (Cloud Run, Cloud SQL, GCS). Desarrollo local sin cambios (`STORAGE_BACKEND=local`) | ADR-028 |
| **DP-07** ✅ | Estructura real de AppSheet | Validadas las 5 tablas (§18) | ADR-020 |
| **DP-13** ✅ | Estados | `estado` (ADMIN) y `estado_financiero` (FINANCIERO), más el espejo. Ahora rigen sobre ambas etapas del viático | ADR-021 |
| **DP-14** ✅ *(ajustada 2026-11-12)* | Catálogos | Proyectos, rubros y células en tablas maestras de SUPERADMIN. Se extiende a `tarifas_viaticos` (DP-20). **Proyecto con esquema híbrido:** catálogo + opción "Otro" con nombre escrito (`proyecto_otro`), exactamente uno de los dos (RN-16). Rubros y células siguen siendo listas cerradas | ADR-022, ADR-031 |
| **DP-15** ✅ | Adjuntos | `soporte` (imagen) o `archivo` (PDF), al menos uno por gasto | ADR-023 |
| **DP-16** ✅ *(ajustada)* | Fecha de análisis | Indicadores sobre `gastos.fecha_factura`. Las fechas de viaje (`viatico_trayectos`) existen para la solicitud pero **no** son base de indicadores | ADR-024 |
| **DP-17** ✅ | Recursos propios | Lo marca el VIAJERO al crear un viático `LEGALIZACION_DIRECTA` | ADR-019 |
| **DP-18** ✅ | Permisos de ADMIN | Operación interna; no toca dinero | ADR-025 |
| **DP-19** ✅ *(nueva)* | Unificación Solicitud + Legalización | Una única entidad `viaticos` con folio `VT-000001`, que reemplaza a `legalizaciones` (`LG-`). Modalidades `CON_SOLICITUD` y `LEGALIZACION_DIRECTA`; etapas `SOLICITUD` y `LEGALIZACION` sobre el mismo registro. Se elimina la dependencia de Google Sheets (`PROYECTOS`, `CorreosExternos`) y de Asana (futuro) | ADR-029 |
| **DP-20** ✅ *(nueva)* | Tarifas de viáticos | Tabla maestra `tarifas_viaticos` por ciudad y tipo de vinculación (empleado / prestador), con 6 conceptos, administrada por SUPERADMIN. Seed inicial: 22 destinos tomados de `calcularGastos.html` | ADR-030 |

### 17.2 Abiertas (ninguna bloquea)

Cada una tiene una recomendación por defecto. Si no hay respuesta antes de la fase indicada, se aplica y se registra como ADR.

| ID | Pregunta | Recomendación por defecto | Bloquea |
| :--- | :--- | :--- | :--- |
| DP-06 | ¿Las notificaciones por correo de cambios de estado entran al MVP? (el correo de restablecimiento sí entra) | Solo si sobra tiempo; ya existe SES | Fase 6 |
| DP-08 | Paleta, logo y tipografía corporativos | Tokens provisionales de `docs/design-system.md` | Fase 4 (UI) |
| DP-09 | Formato de folios. Con la unificación: `CA-` y `VT-`. ¿Qué se hace con los IDs históricos `ID legalizacion` de AppSheet? | Los viáticos migrados reciben `VT-` nuevo (modalidad `LEGALIZACION_DIRECTA`, etapa `LEGALIZACION`) y el ID de AppSheet se conserva en `migrado_de` | Fase 3 |
| DP-10 | ¿Qué se registra al pagar un saldo? | Solo el cambio de estado financiero con comentario | Fase 6 |
| DP-11 | Moneda | Solo COP | — |
| DP-12 | ¿FINANCIERO puede corregir valores de gastos ajenos? | No; pide a ADMIN que devuelva el viático | Fase 5 |
| DP-21 | Servicio de ejecución en AWS: ECS Fargate o App Runner | App Runner si basta con un contenedor por servicio; ECS Fargate si se necesita red privada con RDS más fina | Fase 10 (semana 3, S3-07) |

### 17.3 Supuestos de implementación derivados (no bloqueantes)

Se aplican y se ajustan sin ADR nuevo mientras no contradigan §17.1. Se validan en la demo de la semana 2.

| ID | Supuesto | Origen |
| :--- | :--- | :--- |
| S-01 | **Devolver** regresa `estado` a `PENDIENTE`, exige comentario y marca `devuelta_at`; la UI muestra "Devuelta". Se puede devolver desde `PENDIENTE` o desde `APROBADO` (RN-20) | DP-13, DP-18 |
| S-02 | No hay paso "enviar": el viático está `PENDIENTE` desde que se crea y el viajero lo edita hasta que ADMIN lo aprueba o rechaza | DP-13 |
| S-03 | `TRANSFERIDO` = desembolso enviado al viajero; `PAGADO` = saldo liquidado; `PROCESADO` = cierre contable. FINANCIERO elige el valor; el sistema solo impone RN-03 | DP-13 |
| S-04 | Un gasto sin soporte ni archivo se puede guardar, pero bloquea Aprobar y la liquidación | DP-15 |
| S-05 | El dueño puede corregir `recursos_propios` mientras `estado` y `estado_financiero` estén `PENDIENTE` | DP-17 |
| ~~S-06~~ | Promovido a RN-27 | — |
| S-07 | El dashboard de estados cuenta los viáticos con al menos un gasto cuya `fecha_factura` cae en el rango | DP-16 |
| S-08 | `PAGADO`/`PROCESADO` exigen `APROBADO`. Un viático `RECHAZADO` con anticipo `TRANSFERIDO` se gestiona fuera del sistema | DP-13 |
| S-09 | Si `requiere_gastos_viaje = false` (solo tiquetes), no hay presupuesto ni desembolso: *habilitar legalización* exige solo la solicitud `APROBADO`, y el viajero puede igualmente legalizar gastos (saldo = −gastos, a reembolsar) | DP-19 |
| S-10 | La **gestión de tiquetes** la registra ADMIN (o SUPERADMIN) como un evento con comentario (`GESTIONAR_TIQUETES`), sin un estado propio. Si el negocio quiere un estado de tiquete, se amplía en un ADR | DP-19 |
| S-11 | Con formato de prestador (RN-33) o con `requiere_gastos_viaje = false`, `presupuesto_solicitado` queda en `NULL` | DP-20 |
| S-12 | Al habilitar la legalización, `estado_financiero` conserva su valor (`TRANSFERIDO`) y `valor_asignado` no cambia; la liquidación posterior compara el anticipo con los gastos | DP-19 |
| S-13 | Cada operativo (VIAJERO/ADMIN/FINANCIERO) recibe un `username` único (recomendado: parte local del correo corporativo o el definido por ADMIN); la contraseña temporal la genera el servidor y se envía solo por correo (ADMIN no la ve). Si no hay correo válido, ADMIN usa "restablecer contraseña" tras corregirlo | DP-01 |
| S-14 | Bloqueo de login: 5 fallos consecutivos por usuario → bloqueo de 15 min (además del límite por IP) | DP-01 |
| S-15 | `proyecto_otro` se guarda recortado (sin espacios al inicio ni al final); el filtro `proyecto_id` de listas y pagos no incluye los "Otro"; existe el filtro `proyecto_otro` (búsqueda por texto) para FINANCIERO, ADMIN y SUPERADMIN | ADR-031 |

## 18. Estructura real de AppSheet (validada, DP-07 ✅) y del proyecto Apps Script

### 18.1 AppSheet

Referencia para el modelo y el ETL. La correspondencia campo a campo está en `docs/database-design.md` §1.

| Tabla AppSheet | Propósito | Campos |
| :--- | :--- | :--- |
| `Cargos` | Catálogo de cargos | `ID Cargo` (Key), `Cargo` |
| `Usuarios` | Directorio y RBAC | `ID usuario` (Key), `Correo`, `Usuario`, `Cargo` (Ref), `Cedula`, `Celula` (Enum), `Rol` (Enum) |
| `Crear_legalizacion` | Cabecera del proceso | `ID legalizacion`, `Viajero`, `Nombre Colaborador`, `Cargo`, `Cedula`, `Celula` (vía `LOOKUP(USEREMAIL())`), `Motivo del viaje`, `Valor_T`, `Valor transferido` (fórmula RN-14), `Fecha legalizacion`, `Estado`, `Estado_P`, `Recursos propios`, `Total Gastos`, `Estado legalizacion`, `Saldo` |
| `Registro_Gastos` | Detalle de gastos | `ID Registro`, `R_legalizacion` (Ref), `Creador`, `Fecha fact`, `Rubro`, `Concepto`, `CC_Nit`, `Proyecto`, `Empresa`, `Valor`, `Soporte`, `Archivo`, `Observaciones` |
| `Segmentador` | Filtro temporal del dashboard | `Row ID`, `ID Fecha`, `Inicio`, `Fin`. **No** son proyectos |

| AppSheet | Valores reales | Nuevo modelo | Quién lo cambia |
| :--- | :--- | :--- | :--- |
| `Estado` | `Pendiente ⛔`, `Aprobado`, `Rechazado` | `estado`: `PENDIENTE`, `APROBADO`, `RECHAZADO` | Sistema; ADMIN y SUPERADMIN |
| `Estado_P` | `Pendiente⌛`, `Pagado`, `Transferido`, `Procesado` | `estado_financiero`: `PENDIENTE`, `PAGADO`, `TRANSFERIDO`, `PROCESADO` | Sistema; FINANCIERO y SUPERADMIN |
| `Estado legalizacion` | Fórmula `[Estado]` | No se almacena | — |

Los valores de AppSheet incluyen emojis; el ETL los normaliza (`docs/database-design.md` §12).

### 18.2 Google Apps Script "Solicitud de tiquetes y gastos de viaje" (10 archivos)

| Archivo | Qué aporta al nuevo sistema |
| :--- | :--- |
| `calcularGastos.html` | Las **dos tablas tarifarias** (`gastosViaje2025` para empleados y `prestadores`) con 22 destinos y los 6 conceptos de cada uno → `tarifas_viaticos` (RN-29, DP-20). Fuente del seed inicial |
| `javaScript.html` | Lógica del formulario: trayectos, días de estadía, `requiere_tiquete`, `requiere_gastos_viaje`, y la regla de prestadores con proyectos que exigen formato (p. ej. `P-CONEXI-002`) → RN-30 a RN-33 |
| `formulario.html`, `formulario_style.html`, `modal.html` | Campos y UX del formulario de solicitud → pantalla de Solicitud |
| `solicitud.html`, `plantilla_correo.html` | Plantillas del documento de solicitud y del correo → PDF de solicitud (WeasyPrint) y correos (SES) |
| `Codigo.gs`, `appsscript.json` | Backend de Apps Script (lectura de Sheets `PROYECTOS` y `CorreosExternos`, envío de correo) → **se elimina**; lo reemplazan la tabla `proyectos` y SES |
| `consumoApi.html` | Integración con Asana, inactiva → post-MVP (§16) |
