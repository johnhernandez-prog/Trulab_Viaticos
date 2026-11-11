# SPEC — Trulab Viajes (Sistema de Gestión de Viáticos)

> **Fuente principal de verdad del proyecto.** Consolida el documento *INFORME FINAL PARA PROYECTO TRULAB.md* (auditoría de la app AppSheet) y el **análisis funcional definitivo de la app AppSheet original** (DP-01, DP-02, DP-04, DP-07 y DP-13 a DP-18).
> Cuando el informe y la app real se contradicen, manda la app real. Si algo no está aquí, se decide y se agrega aquí antes de implementarlo.

| Campo | Valor |
| :--- | :--- |
| Versión | 0.3 |
| Fecha | 2026-11-11 |
| Estado | **Todas las decisiones bloqueantes están RESUELTAS** (DP-01, DP-02, DP-04, DP-07, DP-13 a DP-18; §17.1). Las preguntas que siguen abiertas no bloquean ninguna fase con fecha cercana (§17.2). RN-27 y DP-14 confirmadas definitivamente por el negocio. **El proyecto está listo para iniciar oficialmente el Sprint 1. Documentación congelada (baseline de requisitos) desde el 2026-11-11:** cualquier cambio posterior requiere decisión explícita del dueño del producto y un ADR |

---

## 1. Resumen ejecutivo

Trulab Viajes es la reconstrucción, con código propio, de la app AppSheet "Trulab viajes". La usan los colaboradores de Trulab para **registrar los gastos de sus comisiones de viaje con soporte digital**; el área operativa (ADMIN) para **revisar y aprobar** esas legalizaciones; y el área financiera para **registrar lo transferido, pagar y liquidar**.

El acceso es **solo con cuentas corporativas de Google Workspace de Trulab** y solo para usuarios dados de alta en el sistema.

La migración tiene cuatro objetivos:
- Quitar la dependencia y el costo por usuario de AppSheet.
- Mover la seguridad al backend.
- Dar una experiencia responsiva de verdad en móvil, tablet y escritorio.
- Dejar la base lista para OCR e integraciones.

**Restricción de ejecución:** 1 desarrollador full-stack, 4 semanas, entrega de un MVP operativo.

## 2. Objetivo del sistema

Garantizar trazabilidad entre **lo que la empresa transfiere** a un colaborador (o el hecho de que viajó con recursos propios) y **lo que ese colaborador legaliza** con comprobantes. El sistema también debe calcular automáticamente el saldo resultante y registrar su aprobación operativa y su liquidación financiera.

## 3. Alcance

**Dentro del alcance (sistema completo):**
- Cargos.
- Usuarios con roles.
- Catálogos administrables: proyectos, rubros y células (DP-14 ✅).
- Legalizaciones (cabecera).
- Registro de gastos clasificados por rubro y proyecto, con soporte (imagen) y/o archivo (PDF).
- Registro del valor transferido o de los recursos propios.
- Flujo de estados en dos dimensiones: operativo (ADMIN) y financiero (FINANCIERO).
- Módulo de pagos con saldos.
- Reporte PDF.
- Indicadores con filtro por rango de fechas sobre la fecha de factura.
- Migración de datos históricos desde AppSheet.

**Fuera del alcance del MVP** (ver §16): OCR, Google Chat, exportación a Excel, atributos extendidos de proyecto (código, responsable), estados `Devuelto` y `Cancelado` como valores propios, app nativa, multi-moneda.

**Fuera del alcance total:**
- Gestión de credenciales o contraseñas, que es responsabilidad de Google Workspace.
- Contabilidad general, nómina y ERP.

## 4. Módulos del sistema

| # | Módulo | Propósito | Prioridad | En MVP |
| :- | :--- | :--- | :--- | :---: |
| M1 | Autenticación | Inicio de sesión con Google Workspace, validación contra Usuarios, sesión y perfil | Crítica | ✅ |
| M2 | Usuarios | Directorio de personal: rol, cargo, cédula, célula, activación | Crítica | ✅ |
| M3 | Cargos | Catálogo de puestos | Media | ✅ |
| M3b | Catálogos | Tablas maestras de proyectos, rubros y células, administradas por SUPERADMIN (DP-14 ✅) | Alta | ✅ |
| M4 | Legalizaciones | Cabecera: motivo, fecha, recursos propios, valor transferido, estado operativo y estado financiero | Crítica | ✅ |
| M5 | Registro de gastos | Ítems con rubro, proyecto, concepto, NIT, empresa, valor, soporte y archivo | Crítica | ✅ |
| M6 | Pagos | Vista financiera de saldos, registro del valor transferido, estado financiero y liquidación | Crítica | ✅ |
| M7 | Reportes PDF | Documento de la legalización con sus gastos | Alta | ✅ |
| M8 | Indicadores | Dashboard: consumo por proyecto y distribución por estado, filtrados por rango de fecha de factura | Alta | ✅ |
| M9 | Notificaciones | Correo ante cambios de estado | Media | ⚠️ Opcional (DP-06) |
| M10 | OCR de soportes | Extracción automática de datos de comprobantes | Baja | ❌ Futuro |
| M11 | Google Chat | Tarjetas y comandos `/` | Baja | ❌ Futuro |

## 5. Actores del sistema

| Actor | Descripción |
| :--- | :--- |
| Viajero | Colaborador que viaja: crea la legalización, indica si usó recursos propios y registra sus gastos con comprobantes |
| Administrador (ADMIN) | **Operación interna** (DP-18 ✅): revisa comprobantes, controla el cumplimiento de políticas y **aprueba, rechaza o devuelve** legalizaciones. Gestiona usuarios y cargos. **No** representa finanzas: no registra valor transferido, no cambia el estado financiero, no gestiona pagos ni liquida |
| Financiero | **Tesorería** (DP-04 ✅, DP-18 ✅): flujo de caja, valor transferido, desembolsos, pagos, transferencias y liquidaciones. Es el único que cambia el estado financiero (`Estado_P`) |
| Superadministrador (SUPERADMIN) | Acceso completo para administración y soporte; administra los catálogos (DP-14 ✅) |
| Dirección General | Consume indicadores (se le asigna el rol FINANCIERO o ADMIN; no es un rol propio) |
| Administradores de Google Workspace (externo) | Gestionan las cuentas y contraseñas corporativas. La app no interviene |
| Sistema | Valida la identidad contra Usuarios, asigna el estado inicial, calcula el valor transferido efectivo y el saldo, genera folios, registra el historial y genera PDFs |

## 6. Roles y permisos (RBAC)

Hay cuatro roles, y cada usuario tiene **exactamente uno**: `VIAJERO`, `FINANCIERO`, `ADMIN` y `SUPERADMIN`. El rol se guarda en Usuarios y es lo único que determina los permisos.

Leyenda: C=crear, R=leer, U=editar, D=eliminar (lógico), — = denegado.

| Recurso / acción | VIAJERO | FINANCIERO | ADMIN | SUPERADMIN |
| :--- | :---: | :---: | :---: | :---: |
| Legalizaciones propias | C R U D¹ | C R U D¹ | C R U D¹ | C R U D |
| Legalizaciones de otros | — | R | R | C R U D |
| Gastos de legalizaciones propias | C R U D¹ | C R U D¹ | C R U D¹ | C R U D |
| Gastos y comprobantes de legalizaciones de otros | — | R | R | C R U D |
| Marcar "Recursos propios" (al crear; DP-17 ✅) | ✅ propias | ✅ propias | ✅ propias | ✅ |
| **Registrar o modificar el valor transferido** (DP-04 ✅) | — | ✅ | **—** | ✅ |
| **Estado operativo:** Aprobar / Rechazar / Devolver (DP-13 ✅, DP-18 ✅) | — | **—** | ✅² | ✅ |
| **Estado financiero** (`Estado_P`): Transferido / Pagado / Procesado (DP-13 ✅) | — | ✅² | **—** | ✅ |
| Módulo Pagos | — | R U | R³ | C R U D |
| Cargos | — | R | C R U D | C R U D |
| Usuarios | — | — | C R U D⁴ | C R U D |
| Catálogos (proyectos, rubros, células) | R | R | R | C R U D⁵ |
| Indicadores | — | R | R | R |
| Descargar PDF | propias | todas | todas | todas |

¹ El dueño edita la legalización y sus gastos **solo mientras el estado operativo es `PENDIENTE`** (incluida una legalización devuelta, que vuelve a `PENDIENTE`). Al aprobarla o rechazarla queda congelada para su dueño. Eliminar la legalización: solo en `PENDIENTE` y con estado financiero `PENDIENTE` (RN-09).
² Sobre legalizaciones **ajenas**: nadie salvo SUPERADMIN aprueba, valida financieramente ni paga su propia legalización (RN-27, regla definitiva). FINANCIERO y ADMIN nunca editan los gastos del viajero (separación de funciones; DP-12).
³ ADMIN consulta saldos en solo lectura; no gestiona pagos ni liquida (DP-18 ✅).
⁴ ADMIN no puede crear ni asignar el rol `SUPERADMIN`.
⁵ Los valores en uso no se eliminan: se desactivan (RN-24).

La autorización se aplica **en el backend**. El frontend solo oculta lo que no corresponde (ver `docs/architecture.md` §6).

## 7. Casos de uso principales

| ID | Caso de uso | Actor principal |
| :--- | :--- | :--- |
| CU-01 | Iniciar sesión con la cuenta corporativa de Google Workspace | Todos |
| CU-02 | Crear / editar / desactivar usuario y asignar rol, cargo, cédula y célula | ADMIN, SUPERADMIN |
| CU-03 | Gestionar catálogo de cargos | ADMIN, SUPERADMIN |
| CU-04 | Crear legalización (motivo y recursos propios). Los datos del colaborador se toman de su usuario; el sistema asigna el estado `PENDIENTE` | Todos |
| CU-05 | Registrar gasto: rubro, proyecto, concepto, CC/NIT, empresa, valor, fecha de factura, soporte (imagen) y/o archivo (PDF) | Dueño de la legalización |
| CU-06 | **Aprobar** legalización (estado operativo `APROBADO`) | ADMIN, SUPERADMIN |
| CU-07 | Revisar comprobantes y controlar el cumplimiento de políticas | ADMIN (FINANCIERO en consulta) |
| CU-08 | **Devolver** legalización para corrección, o **rechazarla** | ADMIN, SUPERADMIN |
| CU-09 | Gestionar el **estado financiero**: transferido, pagado, procesado (liquidación) | FINANCIERO, SUPERADMIN |
| CU-10 | Generar / descargar PDF de la legalización | Dueño, FINANCIERO, ADMIN |
| CU-11 | Consultar indicadores filtrando por rango de fecha de factura | FINANCIERO, ADMIN, SUPERADMIN |
| CU-12 | Migrar datos históricos de AppSheet (una sola vez) | SUPERADMIN / desarrollador |
| CU-13 | Registrar o modificar el valor transferido (desembolso) | **Solo FINANCIERO** (y SUPERADMIN para soporte) |
| CU-14 | Administrar catálogos de proyectos, rubros y células | **Solo SUPERADMIN** |

## 8. Reglas de negocio

| ID | Regla |
| :--- | :--- |
| RN-01 | **Aislamiento por dueño:** un VIAJERO solo ve y opera sus propias legalizaciones y gastos. FINANCIERO, ADMIN y SUPERADMIN ven todas. Se aplica en el backend en **todas** las consultas (equivale al Slice `SlicefiltrarporViajero`). |
| RN-02 | **Saldo** = `valor_transferido − Σ(gastos.valor)` de gastos no eliminados, donde `valor_transferido` es el valor **efectivo** de RN-14. Se calcula; no se almacena (en AppSheet `Total Gastos` y `Saldo` también son calculados). `saldo > 0` significa que el viajero debe reintegrar. `saldo < 0` significa que la empresa debe reembolsar y se muestra en rojo. |
| RN-03 | **Liquidación:** el estado financiero solo puede pasar a `PAGADO` o `PROCESADO` si el estado operativo es `APROBADO`, la legalización tiene al menos un gasto y todos sus gastos cumplen RN-21. |
| RN-04 | **Folios legibles** con prefijo y 6 dígitos secuenciales: `CA-000001` (cargos), `LG-000001` (legalizaciones). Son distintos de la clave primaria interna. Confirmar prefijos en DP-09. |
| RN-05 | **Estados** (DP-13 ✅). La legalización tiene **dos dimensiones independientes** y un espejo: (a) **`estado`** (operativo, AppSheet `Estado`): `PENDIENTE` → `APROBADO` / `RECHAZADO`, con *Devolver* que regresa a `PENDIENTE`; (b) **`estado_financiero`** (AppSheet `Estado_P`): `PENDIENTE`, `TRANSFERIDO`, `PAGADO`, `PROCESADO`; (c) `Estado legalizacion` **no es un estado propio**: es la fórmula `[Estado]` (RN-23). Ambos estados inician en `PENDIENTE`, que asigna el sistema al crear. Transiciones en `docs/user-flows.md`. |
| RN-06 | **Aprobar** exige al menos un gasto y que todos los gastos cumplan RN-21. Al aprobar, el dueño ya no puede editar. |
| RN-07 | **Fechas** (DP-16 ✅): la fecha de factura de cada gasto es obligatoria y no puede ser futura. La cabecera solo tiene `fecha_legalizacion`; **no se agregan fechas de viaje** en el MVP (no existen en AppSheet). |
| RN-08 | Los valores monetarios son **COP**, mayores que 0 en gastos y mayores o iguales a 0 en el valor asignado. Se guardan como decimal exacto; nunca como flotante. |
| RN-09 | **Eliminación lógica:** nada operativo se borra físicamente. Una legalización solo se puede eliminar con estado `PENDIENTE` y estado financiero `PENDIENTE`. |
| RN-10 | **Trazabilidad:** cada cambio de estado operativo o financiero, y cada cambio del valor asignado o de recursos propios, registra quién, cuándo, el valor anterior, el nuevo y un comentario. **Devolver y Rechazar exigen comentario.** |
| RN-11 | Un usuario desactivado no puede iniciar sesión, pero su historial se conserva. |
| RN-12 | **Control de acceso** (DP-01 ✅): para entrar se exigen las cuatro condiciones (a) cuenta de Google Workspace de Trulab con correo verificado, (b) correo registrado en Usuarios, (c) usuario activo y (d) rol asignado. Si falla cualquiera, el acceso se deniega. No hay autorregistro: los usuarios los crean ADMIN o SUPERADMIN. |
| RN-13 | **Tipos de adjunto** (DP-15 ✅): `soporte` = **imagen** (JPG, PNG, WEBP o HEIC; foto de factura o comprobante capturado desde el celular). `archivo` = **PDF** (documento digital). Máximo 10 MB por archivo. El tipo se valida por contenido (*magic bytes*), no por la extensión. |
| RN-14 | **Recursos propios** (DP-04 ✅, regla real de AppSheet): `valor_transferido = 0` si `recursos_propios = true`; en caso contrario, `valor_transferido = valor_asignado` (el `Valor_T` que registra FINANCIERO). Equivale a `IF([Recursos propios]=TRUE, 0, [Valor_T])`. Es un valor calculado; el sistema nunca permite fijarlo a mano. **Se mantiene exactamente igual en la migración.** |
| RN-15 | **Sin contraseñas** (DP-01 ✅): la app no almacena, crea, recupera, restablece ni cambia contraseñas. Los problemas de credenciales los atienden los administradores de Google Workspace de Trulab. |
| RN-16 | **Proyecto y rubro** (DP-02 ✅, DP-14 ✅): cada gasto se clasifica con un `proyecto` y un `rubro` elegidos de **listas cerradas** (catálogos de RN-24). No se acepta texto libre. El proyecto pertenece al **gasto**, no a la legalización, así que una legalización puede tener gastos de varios proyectos. |
| RN-17 | **Datos del colaborador automáticos** (DP-07 ✅): el nombre, el cargo, la cédula y la célula de la legalización se toman del usuario autenticado (en AppSheet, `LOOKUP(USEREMAIL())`). El viajero nunca los escribe. |
| RN-18 | **Filtro temporal de indicadores** (DP-02 ✅, DP-16 ✅): todos los dashboards e indicadores se calculan sobre **`gastos.fecha_factura`** con `fecha_factura BETWEEN desde AND hasta` (equivale a `Segmentador.Inicio/Fin`, que no se migra como entidad). **No** se usa `fecha_legalizacion` como fecha principal de análisis financiero. |
| RN-19 | Solo **FINANCIERO** (y SUPERADMIN para soporte) registra o modifica el valor asignado o transferido (DP-04 ✅). |
| RN-20 | **Estado operativo** (DP-13 ✅, DP-18 ✅): solo **ADMIN** (y SUPERADMIN) aprueba, rechaza o devuelve. VIAJERO y FINANCIERO no cambian el estado operativo. `RECHAZADO` es final en el MVP. *Devolver* desde `APROBADO` solo es posible si el estado financiero aún no es `PAGADO` ni `PROCESADO`. |
| RN-21 | **Adjunto mínimo** (DP-15 ✅): cada gasto debe tener **al menos uno** de `soporte` o `archivo` (`soporte OR archivo`); no es obligatorio cargar los dos. Un gasto sin ninguno se puede guardar (captura en campo), pero queda marcado "Falta comprobante" y **la legalización no puede continuar**: bloquea Aprobar (RN-06) y la liquidación (RN-03). |
| RN-22 | **Estado financiero** (DP-13 ✅): solo **FINANCIERO** (y SUPERADMIN) cambia `estado_financiero`. ADMIN y VIAJERO no. `PAGADO` y `PROCESADO` requieren RN-03. |
| RN-23 | **Estado legalizacion es un espejo** (DP-13 ✅): en AppSheet es la fórmula `[Estado]`. No se almacena como columna: reportes y filtros usan `estado`. En el ETL solo se usa para conciliar. |
| RN-24 | **Catálogos administrables** (DP-14 ✅): proyectos, rubros y células **no se escriben en el código**; viven en tablas maestras que administra **SUPERADMIN** desde el sistema. Un valor inactivo no se ofrece para registros nuevos pero se conserva en los existentes. Un valor en uso no se elimina; se desactiva. Los nombres son únicos por catálogo. Para el usuario no cambia nada respecto a AppSheet: elige el valor de una lista desplegable; internamente el gasto o el usuario guarda una referencia a la tabla maestra, no el texto. |
| RN-25 | **Recursos propios lo marca el VIAJERO** (DP-17 ✅) durante la **creación** de la legalización. Significa que el colaborador financió el viaje con dinero propio: `valor_transferido = 0` (RN-14) y la empresa debe **reembolsar** (saldo negativo). |
| RN-26 | **Separación de funciones** (DP-18 ✅): ADMIN = operación interna (aprobar, rechazar, devolver, revisar comprobantes, controlar políticas). FINANCIERO = tesorería (valor transferido, estado financiero, pagos, transferencias, liquidaciones). Ninguno ejecuta las acciones del otro. |
| RN-27 | **Sin autoaprobación** (✅ **definitiva y aprobada** por el negocio, 2026-11-11): **ningún usuario puede aprobar, validar financieramente ni pagar una legalización creada por sí mismo.** En la práctica, un ADMIN no aprueba, rechaza ni devuelve su propia legalización, y un FINANCIERO no registra su valor transferido ni cambia su estado financiero. **Única excepción: SUPERADMIN**, por soporte, contingencia, administración o pruebas controladas; cada uso queda auditado. *Justificación:* evita conflictos de interés, mantiene la segregación de funciones, sigue buenas prácticas de auditoría, protege la trazabilidad financiera y facilita las auditorías internas y externas. |

## 9. Requisitos funcionales

| ID | Requisito | Módulo | MVP |
| :--- | :--- | :--- | :---: |
| RF-001 | Autenticación **exclusiva** con Google Workspace de Trulab, validación contra Usuarios y rol, y emisión de sesión propia (JWT) | M1 | ✅ |
| RF-002 | ~~Login con correo y contraseña~~. **Eliminado por DP-01**; se conserva el ID para no renumerar | — | ❌ |
| RF-003 | CRUD de usuarios con rol, cargo, cédula, célula (catálogo) y estado activo/inactivo | M2 | ✅ |
| RF-004 | CRUD de cargos con folio automático | M3 | ✅ |
| RF-005 | CRUD de legalizaciones con filtros (estado, estado financiero, fechas, viajero) y datos del colaborador autocompletados (RN-17) | M4 | ✅ |
| RF-006 | CRUD de gastos con rubro y proyecto (catálogos), concepto, CC/NIT, empresa, fecha de factura, observaciones, soporte (imagen, con captura directa desde cámara en móvil) y archivo (PDF) | M5 | ✅ |
| RF-007 | Acciones de estado con historial: operativas (aprobar, rechazar, devolver; ADMIN) y financieras (estado financiero; FINANCIERO) | M4/M6 | ✅ |
| RF-008 | Vista de pagos: valor transferido efectivo, total gastado y saldo, con resaltado de negativos, filtros y orden | M6 | ✅ |
| RF-009 | Generación y descarga del PDF de la legalización con sus gastos | M7 | ✅ |
| RF-010 | Dashboard: consumo por **proyecto del gasto** (barras) y conteo por estado (dona), con filtro por rango de **fecha de factura** (Segmentador) | M8 | ✅ |
| RF-011 | Visualización segura de soportes y archivos (URL temporal) | M5 | ✅ |
| RF-012 | Migración de datos históricos desde AppSheet | — | ✅ |
| RF-013 | Notificación por correo al aprobar, devolver, rechazar y pagar | M9 | DP-06 |
| RF-014 | Registro de auditoría de acciones sensibles (roles, estados, valor transferido, catálogos, eliminaciones, accesos denegados) | Transversal | ✅ |
| RF-015 | Registro y modificación del valor asignado, con historial (RN-14, RN-19) | M6 | ✅ |
| RF-016 | Administración de catálogos (proyectos, rubros, células): crear, renombrar, activar y desactivar, solo SUPERADMIN (RN-24) | M3b | ✅ |

## 10. Requisitos no funcionales

| ID | Categoría | Requisito | Cómo se verifica |
| :--- | :--- | :--- | :--- |
| RNF-01 | Rendimiento | Carga inicial < 1,2 s (LCP en 4G), API p95 < 200 ms en operaciones CRUD | Lighthouse, logs de latencia |
| RNF-02 | Seguridad | TLS en tránsito, cifrado en reposo del proveedor (AES-256), autorización en backend y RLS como defensa en profundidad. Sin almacenamiento de credenciales | Pruebas de permisos, revisión de seguridad |
| RNF-03 | Compatibilidad | Últimas 2 versiones de Chrome, Safari (incluido iOS), Firefox y Edge | Prueba manual de matriz |
| RNF-04 | Responsivo | Usable desde 360 px de ancho; mobile-first | Revisión en 3 tamaños |
| RNF-05 | Accesibilidad | WCAG 2.1 AA en flujos críticos | Revisión con axe y teclado |
| RNF-06 | Mantenibilidad | Tipado estático en frontend y backend, lint en CI, migraciones versionadas | CI |
| RNF-07 | Pruebas | Las reglas de negocio y la matriz RBAC tienen pruebas automatizadas; cobertura ≥ 80 % en la capa de servicios | CI |
| RNF-08 | Disponibilidad | Horario laboral; respaldo diario de BD con retención de 7 días como mínimo | Política del proveedor |
| RNF-09 | Privacidad | Datos personales tratados según la Ley 1581 de 2012 (Colombia). La **cédula** solo la ven el titular, FINANCIERO, ADMIN y SUPERADMIN, y nunca aparece en logs. Los soportes nunca son públicos | Revisión |
| RNF-10 | Observabilidad | Logs estructurados con id de petición; errores 5xx registrados | Revisión de logs |

## 11. Flujos críticos

Los flujos completos paso a paso están en `docs/user-flows.md`. Estos son los críticos:

1. **Acceso:** Google → validación de dominio → existe en Usuarios → activo → rol → acceso. Cualquier fallo deniega el acceso.
2. **Ciclo de vida de una legalización:** el viajero crea (estado `PENDIENTE`, marca recursos propios) → agrega gastos con soporte o archivo → ADMIN revisa comprobantes → **aprueba** (o devuelve ↺ a `PENDIENTE`, o rechaza) → FINANCIERO registra el valor transferido y avanza el estado financiero hasta `PAGADO` / `PROCESADO`.
3. **Cálculo de saldo:** debe ser idéntico en la vista de pagos, en el detalle y en el PDF. Hay una sola vista en el backend, que incluye RN-14.
4. **Aislamiento de datos:** un VIAJERO nunca obtiene datos ajenos, ni siquiera adivinando IDs; responde 404.

## 12. Restricciones técnicas

- Un solo desarrollador y 4 semanas: se prefieren soluciones conocidas y "aburridas" sobre las novedosas.
- Monolito modular. Sin microservicios, sin colas en el MVP.
- Desarrollo local en Windows; ejecución en contenedores Linux (Docker) para paridad con producción.
- La **estructura** y el **comportamiento funcional** de AppSheet están validados (§17.1, §18). Para el ETL sigue haciendo falta la **exportación de los datos** (CSV y soportes, tarea P-2). Los valores iniciales de los catálogos se cargan desde esa exportación (DP-14 ✅).
- Sin dependencia de AppSheet tras el corte.
- La identidad depende de Google Workspace de Trulab. Hace falta un OAuth Client ID creado por un administrador de Workspace (tarea P-3).

## 13. Criterios de aceptación generales

Una funcionalidad está **terminada** cuando cumple todo lo siguiente:
1. Cumple su RF y las RN asociadas, con pruebas automatizadas de backend para la lógica y los permisos.
2. Respeta la matriz RBAC (§6). Hay pruebas para el rol permitido y al menos un rol denegado.
3. Funciona en móvil (360 px), tablet (768 px) y escritorio (1280 px).
4. Muestra estados de carga, vacío y error.
5. No introduce errores de lint ni de tipos, y las migraciones aplican desde cero.
6. `HANDOFF.md` está actualizado (y `CLAUDE.md` si cambió una decisión).

## 14. Tecnologías aprobadas

| Capa | Tecnología |
| :--- | :--- |
| Frontend | React 18 + Vite + **TypeScript**, Tailwind CSS, shadcn/ui (Radix), Lucide, TanStack Query, React Router, React Hook Form + Zod, Recharts, Google Identity Services |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3 |
| Seguridad | google-auth (verificación de ID token), PyJWT. **Sin librerías de hashing de contraseñas** (DP-01) |
| PDF | WeasyPrint + plantillas Jinja2 (en Docker) |
| Base de datos | PostgreSQL 16 |
| Archivos | Almacenamiento de objetos compatible con S3 o GCS (DP-05); en local, MinIO o el sistema de archivos |
| Pruebas | pytest + httpx, con Postgres real en Docker; Vitest + Testing Library; Playwright solo para flujos críticos |
| Calidad | ruff + mypy (backend), ESLint + Prettier + tsc (frontend), pre-commit |
| Infra | Docker Compose (local); hosting en DP-05 |

Cualquier tecnología nueva requiere un ADR en `docs/architecture.md` §13.

## 15. Alcance MVP (entrega de la semana 4)

Incluye M1 a M8 (con M3b), la migración de datos históricos, el despliegue en producción y las pruebas de RBAC y de reglas de negocio.

**Criterio de éxito del MVP:** el equipo de Trulab puede dejar de usar AppSheet. Todo viajero puede registrar sus gastos desde el celular, ADMIN puede aprobar, devolver o rechazar, financiero puede registrar transferencias y liquidar, y los datos históricos están disponibles.

## 16. Funcionalidades futuras (post-MVP, sin compromiso de fecha)

1. Notificaciones por correo (si no entran al MVP, DP-06).
2. OCR de soportes: precarga de valor, fecha y NIT; el usuario confirma.
3. Integración con Google Chat (tarjeta de bienvenida, comandos `/`).
4. Exportación a Excel/CSV de pagos y legalizaciones.
5. **Proyecto enriquecido:** la tabla maestra `proyectos` ya existe en el MVP (DP-14 ✅); a futuro se agregan código, responsable, cliente o convenio y vigencia.
6. Topes por rubro o por cargo.
7. Estados operativos adicionales `DEVUELTO` y `CANCELADO` como valores propios (DP-13 los deja como extensión futura; en el MVP *Devolver* regresa a `PENDIENTE`).
8. Registro del pago o reintegro (referencia bancaria y comprobante de transferencia).
9. PWA instalable y modo sin conexión para registrar gastos en campo.
10. Panel de auditoría para SUPERADMIN.

## 17. Decisiones

### 17.1 Resueltas: definitivas, no reabrir

Confirmadas entre el 2026-11-10 y el 2026-11-11 a partir de la configuración y del análisis funcional de la app AppSheet original. Solo se cambian con una decisión explícita del dueño del producto, registrada como un ADR nuevo.

| ID | Decisión | Resolución definitiva | ADR |
| :--- | :--- | :--- | :--- |
| **DP-01** ✅ | Autenticación | **Solo Google OAuth con cuentas de Google Workspace de Trulab.** En AppSheet: *Require user sign-in* = sí, *Identity Provider* = Google, *Allow all signed-in users* = no. Además de autenticarse, el correo debe existir en Usuarios, estar activo y tener rol (RN-12). **Sin** registro público, creación de cuentas, contraseñas, recuperación, restablecimiento ni cambio de contraseña (RN-15). | ADR-006 |
| **DP-02** ✅ | Proyectos y Segmentador | `Segmentador` (`Row ID`, `ID Fecha`, `Inicio`, `Fin`) **no** es proyectos, centros de costo, convenios ni clientes: es solo un **filtro temporal** del dashboard, que se reemplaza por parámetros `desde`/`hasta` (RN-18). Los **proyectos** son una **lista cerrada en cada gasto** (`Registro_Gastos.Proyecto`; por ejemplo "Rutas PDET 3", "Conexión Agro", "Taller Multipropósito"), no en la legalización. El mecanismo de la lista lo precisa DP-14. | ADR-017, ADR-018 |
| **DP-03** ✅ | Estado para devolver | **Absorbida por DP-13:** ADMIN *devuelve* la legalización a `PENDIENTE` con comentario obligatorio. | ADR-021 |
| **DP-04** ✅ | Valor transferido | **Solo FINANCIERO** registra y modifica el valor transferido, gestiona desembolsos y liquida (SUPERADMIN, acceso completo). VIAJERO y ADMIN no. Regla real: `valor_transferido = IF(recursos_propios, 0, Valor_T)` (RN-14, RN-19). | ADR-019 |
| **DP-07** ✅ | Estructura real de AppSheet | Validadas las 5 tablas: Cargos, Usuarios, Crear_legalizacion, Registro_Gastos y Segmentador (§18). Los datos del colaborador se obtienen con `LOOKUP(USEREMAIL())`, lo que confirma la compatibilidad con Google OAuth. | ADR-020 |
| **DP-13** ✅ | Estados | **`Estado`** (operativo, enum): `Pendiente ⛔` (inicial, lo asigna el sistema), `Aprobado`, `Rechazado`; extensiones futuras `Devuelto` y `Cancelado`. El viajero crea; **ADMIN aprueba, rechaza y devuelve**. **`Estado_P`** (financiero, enum): `Pendiente⌛` (inicial), `Pagado`, `Transferido`, `Procesado`; solo lo editan **FINANCIERO y SUPERADMIN**. **`Estado legalizacion`** = fórmula `[Estado]`: espejo para reportes y filtros, no es independiente (RN-05, RN-20, RN-22, RN-23). | ADR-021 |
| **DP-14** ✅ | Catálogos | Campos enum: `Usuarios.Rol`, `Usuarios.Celula`, `Registro_Gastos.Rubro`, `Registro_Gastos.Proyecto`. **No se escriben en el código:** se crean las tablas maestras `proyectos`, `rubros` y `celulas`, administrables por **SUPERADMIN**. Rubro es un catálogo contable estable (Hospedaje, Alimentación, Transporte, Combustible, Peajes…); Proyecto cambia ocasionalmente; Célula depende de la organización (Laboratorio, Operaciones, Campo, Administración…). `Rol` sigue siendo un enum fijo del sistema (4 roles). **Confirmada definitivamente por el negocio (2026-11-11).** *Justificación:* evitar valores escritos en el código; agregar proyectos, células y rubros sin modificar código; administración por SUPERADMIN; consistencia de datos; mejores reportes y dashboards; mantenimiento futuro. **No cambia el comportamiento funcional:** el usuario sigue eligiendo de una lista desplegable; la diferencia es solo interna (antes `Proyecto` = texto/enum; ahora `proyecto_id` = referencia a la tabla maestra; igual para rubros y células). | ADR-022 |
| **DP-15** ✅ | Adjuntos | `Soporte` = **imagen** (foto de la factura o del comprobante, capturada desde el celular). `Archivo` = **PDF** (documento digital). No es obligatorio cargar los dos; **debe existir al menos uno** (`Soporte OR Archivo`). Si ambos están vacíos, la legalización no puede continuar (RN-13, RN-21). | ADR-023 |
| **DP-16** ✅ | Fecha de análisis | Dashboards e indicadores se calculan sobre **`Fecha fact`** del gasto (fecha real del consumo; análisis fiscal correcto): `Segmentador Inicio/Fin → BETWEEN sobre Fecha fact`. No se usa `Fecha legalizacion` como fecha principal de análisis. No se agregan fechas de viaje (RN-07, RN-18). | ADR-024 |
| **DP-17** ✅ | Recursos propios | Lo marca el **VIAJERO** durante la **creación** de la legalización. Significa que financió el viaje con dinero propio: `valor transferido = 0` y luego la empresa reembolsa. La regla se mantiene exactamente igual en la migración (RN-14, RN-25). | ADR-019 |
| **DP-18** ✅ | Permisos de ADMIN | ADMIN = **operación interna**, no finanzas. Puede aprobar, rechazar y devolver legalizaciones, revisar comprobantes y controlar el cumplimiento de políticas. **No puede** registrar valor transferido, cambiar `Estado_P`, gestionar pagos ni liquidar. FINANCIERO = tesorería, flujo de caja, pagos, transferencias y liquidaciones (RN-20, RN-22, RN-26). | ADR-025 |

### 17.2 Abiertas (ninguna bloquea el Sprint 1)

Cada una tiene una recomendación por defecto. Si no hay respuesta antes de la fase indicada, se aplica esa recomendación y se registra como ADR.

| ID | Pregunta | Recomendación por defecto | Bloquea |
| :--- | :--- | :--- | :--- |
| DP-05 | Hosting y almacenamiento de archivos | Decidir antes de cerrar la semana 2 (gate de `SPRINTS.md`). Candidatos: Render/Railway + S3, o GCP (Cloud Run + Cloud SQL + GCS), que encaja con Google Workspace | Fase 10 (gate semana 2) |
| DP-06 | ¿Las notificaciones por correo entran al MVP? | Solo si sobra tiempo en la semana 3 | Fase 6 |
| DP-08 | Paleta, logo y tipografía corporativos | Usar los tokens provisionales de `docs/design-system.md` | Fase 4 (UI) |
| DP-09 | Formato de folios (`CA-`, `LG-`). ¿Coincide con el formato de `ID Cargo` e `ID legalizacion` de AppSheet? | Conservar los IDs históricos de AppSheet como folio si son legibles; si no, usar `CA-`/`LG-` | Fase 3 |
| DP-10 | ¿Qué se registra al pagar un saldo? | Negativo = la empresa reembolsa (lo confirma DP-17 para recursos propios); positivo = el viajero reintegra. En el MVP solo se registra el cambio de estado financiero con comentario | Fase 6 |
| DP-11 | Moneda | Solo COP | — |
| DP-12 | ¿FINANCIERO puede corregir valores de gastos ajenos? | No; pide a ADMIN que devuelva la legalización (separación de funciones, RN-26) | Fase 5 |

### 17.3 Supuestos de implementación derivados (no bloqueantes)

Las resoluciones de §17.1 dejan algunos detalles de comportamiento sin especificar. Se aplican estos supuestos, que se pueden ajustar sin ADR nuevo mientras no contradigan §17.1. Conviene validarlos con ADMIN y FINANCIERO durante la demo de la semana 2.

| ID | Supuesto | Origen |
| :--- | :--- | :--- |
| S-01 | **Devolver** (sin valor `DEVUELTO` en el MVP) regresa el estado operativo a `PENDIENTE`, exige comentario y marca `devuelta_at`; la UI muestra "Devuelta" y el comentario mientras siga `PENDIENTE`. Se puede devolver desde `PENDIENTE` o desde `APROBADO` (esto último solo si `estado_financiero` ∉ {`PAGADO`, `PROCESADO`}) | DP-13, DP-18 |
| S-02 | AppSheet no tiene un paso "enviar": la legalización está `PENDIENTE` desde que se crea y el viajero la edita hasta que ADMIN la aprueba o rechaza | DP-13 |
| S-03 | Semántica propuesta de `Estado_P`: `TRANSFERIDO` = desembolso enviado al viajero; `PAGADO` = saldo liquidado (reembolso o reintegro); `PROCESADO` = cierre contable. FINANCIERO elige el valor (como el enum editable de AppSheet); el sistema solo impone RN-03 para `PAGADO`/`PROCESADO`, no un orden estricto | DP-13 |
| S-04 | Un gasto sin soporte ni archivo se puede guardar, pero bloquea Aprobar y la liquidación (RN-21) | DP-15 |
| S-05 | El dueño puede corregir `recursos_propios` mientras la legalización esté `PENDIENTE` y su estado financiero sea `PENDIENTE`; después solo SUPERADMIN. FINANCIERO no lo cambia | DP-17 |
| ~~S-06~~ | ~~Sin autoaprobación~~ → **promovido a regla definitiva RN-27** (2026-11-11); ya no es un supuesto | DP-18 |
| S-07 | El dashboard de distribución por estado cuenta las legalizaciones con al menos un gasto cuya `fecha_factura` cae en el rango | DP-16 |
| S-08 | `PAGADO`/`PROCESADO` exigen `APROBADO`. Una legalización `RECHAZADA` con anticipo `TRANSFERIDO` se gestiona fuera del sistema en el MVP | DP-13 |

## 18. Estructura real de AppSheet (validada, DP-07 ✅)

Es la referencia para el modelo nuevo y para el ETL. La correspondencia campo a campo está en `docs/database-design.md` §1.

| Tabla AppSheet | Propósito | Campos |
| :--- | :--- | :--- |
| `Cargos` | Catálogo de cargos | `ID Cargo` (Key), `Cargo`. Relación: un cargo tiene N usuarios |
| `Usuarios` | Directorio y RBAC | `ID usuario` (Key), `Correo`, `Usuario`, `Cargo` (Ref), `Cedula`, `Celula` (Enum), `Rol` (Enum) |
| `Crear_legalizacion` | Cabecera del proceso | `ID legalizacion`, `Viajero`, `Nombre Colaborador`, `Cargo`, `Cedula`, `Celula` (estos cinco vía `LOOKUP(USEREMAIL())`), `Motivo del viaje`, `Valor_T`, `Valor transferido` (fórmula RN-14), `Fecha legalizacion`, `Estado` (Enum), `Estado_P` (Enum), `Recursos propios` (Yes/No), `Total Gastos` (calc.), `Estado legalizacion` (fórmula `[Estado]`), `Saldo` (calc.), `Related Registro_Gastos` |
| `Registro_Gastos` | Detalle de gastos | `ID Registro`, `R_legalizacion` (Ref), `Creador`, `Fecha fact`, `Rubro` (Enum), `Concepto`, `CC_Nit`, `Proyecto` (Enum), `Empresa`, `Valor`, `Soporte` (imagen), `Archivo` (PDF), `Observaciones`. Relación: una legalización tiene N gastos |
| `Segmentador` | Filtro temporal del dashboard | `Row ID`, `ID Fecha`, `Inicio`, `Fin`. **No** representa proyectos, centros de costo, convenios ni clientes |

**Estados reales** (DP-13 ✅):

| AppSheet | Valores reales | Nuevo modelo | Quién lo cambia |
| :--- | :--- | :--- | :--- |
| `Estado` | `Pendiente ⛔` (inicial), `Aprobado`, `Rechazado` | `estado`: `PENDIENTE`, `APROBADO`, `RECHAZADO` | Sistema (inicial); ADMIN y SUPERADMIN |
| `Estado_P` | `Pendiente⌛` (inicial), `Pagado`, `Transferido`, `Procesado` | `estado_financiero`: `PENDIENTE`, `PAGADO`, `TRANSFERIDO`, `PROCESADO` | Sistema (inicial); FINANCIERO y SUPERADMIN |
| `Estado legalizacion` | Fórmula `[Estado]` | No se almacena (espejo de `estado`) | — |

Los valores de AppSheet incluyen emojis (`⛔`, `⌛`); el ETL los normaliza a los códigos en mayúsculas (`docs/database-design.md` §12).
