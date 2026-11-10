# SPEC — Trulab Viajes (Sistema de Gestión de Viáticos)

> **Fuente principal de verdad del proyecto.** Consolida y simplifica el documento *INFORME FINAL PARA PROYECTO TRULAB.md* (auditoría de la app AppSheet actual).
> Si este documento y el informe se contradicen, manda este documento. Si algo no está aquí, se decide y se agrega aquí antes de implementarlo.

| Campo | Valor |
| :--- | :--- |
| Versión | 0.1 (borrador inicial) |
| Fecha | 2026-11-10 |
| Estado | En revisión: hay decisiones abiertas (§17) que bloquean partes del MVP |

---

## 1. Resumen ejecutivo

Trulab Viajes es la reconstrucción, con código propio, de la app AppSheet "Trulab viajes". La usan los colaboradores de Trulab para **registrar los gastos de sus comisiones de viaje con soporte digital**, y el área financiera para **auditar los saldos y liquidarlos**.

La migración tiene cuatro objetivos:
- Quitar la dependencia y el costo por usuario de AppSheet.
- Mover la seguridad al backend.
- Dar una experiencia responsiva de verdad en móvil, tablet y escritorio.
- Dejar la base lista para OCR e integraciones.

**Restricción de ejecución:** 1 desarrollador full-stack, 4 semanas, entrega de un MVP operativo.

## 2. Objetivo del sistema

Garantizar trazabilidad entre **lo que la empresa transfiere** a un colaborador para un viaje y **lo que ese colaborador legaliza** con comprobantes. El sistema también debe calcular automáticamente el saldo resultante y registrar su liquidación.

## 3. Alcance

**Dentro del alcance (sistema completo):** cargos, usuarios con roles, legalizaciones (cabecera de viaje), registro de gastos con soportes, módulo de pagos con saldos, flujo de estados, reporte PDF, indicadores gerenciales y migración de datos históricos desde AppSheet.

**Fuera del alcance del MVP** (ver §16): OCR, Google Chat, exportación a Excel, flujos de aprobación multinivel, app nativa, multi-moneda.

**Fuera del alcance total:** contabilidad general, nómina, integración con ERP (salvo decisión futura).

## 4. Módulos del sistema

| # | Módulo | Propósito | Prioridad | En MVP |
| :- | :--- | :--- | :--- | :---: |
| M1 | Autenticación | Inicio de sesión corporativo, sesión, perfil propio | Crítica | ✅ |
| M2 | Usuarios | Directorio de personal, rol, cargo, activación | Crítica | ✅ |
| M3 | Cargos | Catálogo de puestos | Media | ✅ |
| M4 | Legalizaciones | Cabecera de viaje: motivo, fechas, valor transferido, estado | Crítica | ✅ |
| M5 | Registro de gastos | Ítems de gasto con soporte (imagen/PDF) | Crítica | ✅ |
| M6 | Pagos | Vista financiera de saldos y acción de liquidación | Crítica | ✅ |
| M7 | Reportes PDF | Documento de la legalización con sus gastos | Alta | ✅ |
| M8 | Indicadores | Dashboard: consumo por proyecto y distribución por estado | Alta | ✅ |
| M9 | Notificaciones | Correo ante cambios de estado | Media | ⚠️ Opcional (DP-06) |
| M10 | OCR de soportes | Extracción automática de datos de comprobantes | Baja | ❌ Futuro |
| M11 | Google Chat | Tarjetas y comandos `/` | Baja | ❌ Futuro |

## 5. Actores del sistema

| Actor | Descripción |
| :--- | :--- |
| Viajero | Colaborador que viaja, registra gastos y legaliza |
| Financiero | Audita soportes, valida saldos, liquida (marca "Pagada") |
| Administrador (ADMIN) | Gestiona usuarios y cargos, supervisa el flujo, resuelve inconsistencias |
| Superadministrador (SUPERADMIN) | Control técnico total, parámetros globales, auditoría |
| Dirección General | Consume indicadores (se le asigna el rol FINANCIERO o ADMIN; no es un rol propio) |
| Sistema | Calcula saldos, genera folios, registra el historial y genera PDFs |

## 6. Roles y permisos (RBAC)

Hay cuatro roles, y cada usuario tiene **exactamente uno**: `VIAJERO`, `FINANCIERO`, `ADMIN` y `SUPERADMIN`.

Leyenda: C=crear, R=leer, U=editar, D=eliminar (lógico), — = denegado.

| Recurso / acción | VIAJERO | FINANCIERO | ADMIN | SUPERADMIN |
| :--- | :---: | :---: | :---: | :---: |
| Legalizaciones propias | C R U D¹ | C R U D¹ | C R U D¹ | C R U D |
| Legalizaciones de otros | — | R U² | R U² D¹ | C R U D |
| Gastos de legalizaciones propias | C R U D¹ | C R U D¹ | C R U D¹ | C R U D |
| Gastos de legalizaciones de otros | — | R | R | C R U D |
| Fijar `valor_transferido` | — (DP-04) | ✅ | ✅ | ✅ |
| Acción **Legalizar** (enviar) | ✅ propias | ✅ propias | ✅ propias | ✅ |
| Acción **Devolver** (DP-03) | — | ✅ | ✅ | ✅ |
| Acción **Pagado** (liquidar) | — | ✅ | ✅ | ✅ |
| Módulo Pagos | — | R U | R U | C R U D |
| Cargos | — | R | C R U D | C R U D |
| Usuarios | — | — | C R U D³ | C R U D |
| Indicadores | — | R | R | R |
| Descargar PDF | propias | todas | todas | todas |

¹ Editar: solo mientras la legalización esté en `BORRADOR` o `DEVUELTA`. Eliminar la legalización: solo en `BORRADOR` (RN-09). Después de "Legalizar" queda congelada para su dueño.
² "U" para FINANCIERO/ADMIN sobre legalizaciones ajenas significa cambiar `valor_transferido`, observaciones y estado mediante acciones. **No** pueden editar los gastos del viajero (separación de funciones; DP-12).
³ ADMIN no puede crear ni asignar el rol `SUPERADMIN`.

La autorización se aplica **en el backend**. El frontend solo oculta lo que no corresponde (ver `docs/architecture.md` §6).

## 7. Casos de uso principales

| ID | Caso de uso | Actor principal |
| :--- | :--- | :--- |
| CU-01 | Iniciar sesión con cuenta corporativa | Todos |
| CU-02 | Crear / editar / desactivar usuario y asignar rol y cargo | ADMIN, SUPERADMIN |
| CU-03 | Gestionar catálogo de cargos | ADMIN, SUPERADMIN |
| CU-04 | Crear legalización (motivo, fechas, proyecto) | Todos |
| CU-05 | Registrar gasto con soporte (foto desde cámara o archivo) | Dueño de la legalización |
| CU-06 | Legalizar (enviar a revisión financiera) | Dueño |
| CU-07 | Revisar legalización: soportes, saldo, observaciones | FINANCIERO, ADMIN |
| CU-08 | Devolver legalización para corrección | FINANCIERO, ADMIN |
| CU-09 | Marcar como Pagada (liquidar saldo) | FINANCIERO, ADMIN |
| CU-10 | Generar / descargar PDF de la legalización | Dueño, FINANCIERO, ADMIN |
| CU-11 | Consultar indicadores | FINANCIERO, ADMIN, SUPERADMIN |
| CU-12 | Migrar datos históricos de AppSheet (una sola vez) | SUPERADMIN / desarrollador |

## 8. Reglas de negocio

| ID | Regla |
| :--- | :--- |
| RN-01 | **Aislamiento por dueño:** un VIAJERO solo ve y opera sus propias legalizaciones y gastos. FINANCIERO, ADMIN y SUPERADMIN ven todas. Se aplica en el backend en **todas** las consultas (equivale al Slice `SlicefiltrarporViajero`). |
| RN-02 | **Saldo** = `valor_transferido − Σ(gastos.valor)` de gastos no eliminados. Se calcula; no se almacena. `saldo > 0` significa que el viajero debe reintegrar. `saldo < 0` significa que la empresa debe reembolsar y se muestra en rojo. Confirmar la semántica en DP-10. |
| RN-03 | Una legalización **no puede marcarse Pagada** si no tiene al menos un gasto o si algún gasto no tiene soporte adjunto. |
| RN-04 | **Folios legibles** con prefijo y 6 dígitos secuenciales: `CA-000001` (cargos), `LG-000001` (legalizaciones). Son distintos de la clave primaria interna. Confirmar prefijos en DP-09. |
| RN-05 | **Máquina de estados:** `BORRADOR → LEGALIZADA → PAGADA`, con `LEGALIZADA → DEVUELTA → LEGALIZADA` (DP-03). No existen otras transiciones. `PAGADA` es final. |
| RN-06 | **Legalizar** exige al menos un gasto y que todos los gastos tengan soporte. Al legalizar, el dueño ya no puede editar. |
| RN-07 | `fecha_fin ≥ fecha_inicio`. La fecha de cada gasto debe caer dentro de [`fecha_inicio − 3 días`, `fecha_fin + 3 días`]. La tolerancia queda como parámetro configurable; si sale de rango, el sistema advierte pero no bloquea. |
| RN-08 | Los valores monetarios son **COP**, mayores que 0 en gastos y mayores o iguales a 0 en `valor_transferido`. Se guardan como decimal exacto; nunca como flotante. |
| RN-09 | **Eliminación lógica:** nada operativo se borra físicamente. Una legalización solo se puede eliminar en `BORRADOR`. |
| RN-10 | **Trazabilidad:** cada cambio de estado registra quién, cuándo, el estado anterior, el nuevo y un comentario. Devolver exige comentario. |
| RN-11 | Un usuario desactivado no puede iniciar sesión, pero su historial se conserva. |
| RN-12 | El correo es único y corporativo (dominio `trulab.co`, DP-01). |
| RN-13 | Soportes permitidos: JPG, PNG, HEIC/WEBP y PDF, con un máximo de 10 MB por archivo. El tipo se valida por contenido, no por la extensión. |

## 9. Requisitos funcionales

| ID | Requisito | Módulo | MVP |
| :--- | :--- | :--- | :---: |
| RF-001 | Autenticación con Google (dominio corporativo) y emisión de sesión propia (JWT) | M1 | ✅ |
| RF-002 | Login con correo y contraseña (bcrypt) como respaldo | M1 | DP-01 |
| RF-003 | CRUD de usuarios con rol, cargo y estado activo/inactivo | M2 | ✅ |
| RF-004 | CRUD de cargos con folio automático | M3 | ✅ |
| RF-005 | CRUD de legalizaciones con filtros (estado, fechas, viajero, proyecto) | M4 | ✅ |
| RF-006 | CRUD de gastos con carga de soporte y captura directa desde cámara en móvil | M5 | ✅ |
| RF-007 | Acciones de estado: Legalizar, Devolver, Pagado, con historial | M4/M6 | ✅ |
| RF-008 | Vista de pagos: transferido, total gastado y saldo, con resaltado de negativos, filtros y orden | M6 | ✅ |
| RF-009 | Generación y descarga del PDF de la legalización con sus gastos | M7 | ✅ |
| RF-010 | Dashboard: consumo por proyecto (barras) y conteo por estado (dona), con filtro por rango de fechas | M8 | ✅ |
| RF-011 | Visualización segura de soportes (URL temporal) | M5 | ✅ |
| RF-012 | Migración de datos históricos desde AppSheet | — | ✅ |
| RF-013 | Notificación por correo al legalizar, devolver y pagar | M9 | DP-06 |
| RF-014 | Registro de auditoría de acciones sensibles (roles, estados, eliminaciones) | Transversal | ✅ |

## 10. Requisitos no funcionales

| ID | Categoría | Requisito | Cómo se verifica |
| :--- | :--- | :--- | :--- |
| RNF-01 | Rendimiento | Carga inicial < 1,2 s (LCP en 4G), API p95 < 200 ms en operaciones CRUD | Lighthouse, logs de latencia |
| RNF-02 | Seguridad | TLS en tránsito, cifrado en reposo del proveedor (AES-256), autorización en backend y RLS como defensa en profundidad | Pruebas de permisos, revisión de seguridad |
| RNF-03 | Compatibilidad | Últimas 2 versiones de Chrome, Safari (incluido iOS), Firefox y Edge | Prueba manual de matriz |
| RNF-04 | Responsivo | Usable desde 360 px de ancho; mobile-first | Revisión en 3 tamaños |
| RNF-05 | Accesibilidad | WCAG 2.1 AA en flujos críticos | Revisión con axe y teclado |
| RNF-06 | Mantenibilidad | Tipado estático en frontend y backend, lint en CI, migraciones versionadas | CI |
| RNF-07 | Pruebas | Las reglas de negocio y la matriz RBAC tienen pruebas automatizadas; cobertura ≥ 80 % en la capa de servicios | CI |
| RNF-08 | Disponibilidad | Horario laboral; respaldo diario de BD con retención de 7 días como mínimo | Política del proveedor |
| RNF-09 | Privacidad | Datos personales tratados según la Ley 1581 de 2012 (Colombia); soportes nunca públicos | Revisión |
| RNF-10 | Observabilidad | Logs estructurados con id de petición; errores 5xx registrados | Revisión de logs |

## 11. Flujos críticos

Los flujos completos paso a paso están en `docs/user-flows.md`. Estos son los críticos:

1. **Ciclo de vida de una legalización:** crear → agregar gastos con soporte → legalizar → revisión financiera → (devolver ↺) → pagar.
2. **Cálculo de saldo:** debe ser idéntico en la vista de pagos, en el detalle y en el PDF. Hay una sola función o vista en el backend.
3. **Aislamiento de datos:** un VIAJERO nunca obtiene datos ajenos, ni siquiera adivinando IDs; responde 404.

## 12. Restricciones técnicas

- Un solo desarrollador y 4 semanas: se prefieren soluciones conocidas y "aburridas" sobre las novedosas.
- Monolito modular. Sin microservicios, sin colas en el MVP.
- Desarrollo local en Windows; ejecución en contenedores Linux (Docker) para paridad con producción.
- El esquema actual de AppSheet se dedujo por ingeniería inversa y **debe validarse con una exportación real** (DP-07) antes de cerrar el modelo de datos.
- Sin dependencia de AppSheet tras el corte.

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
| Frontend | React 18 + Vite + **TypeScript**, Tailwind CSS, shadcn/ui (Radix), Lucide, TanStack Query, React Router, React Hook Form + Zod, Recharts |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3 |
| Seguridad | google-auth (verificación de ID token), PyJWT, passlib/bcrypt |
| PDF | WeasyPrint + plantillas Jinja2 (en Docker) |
| Base de datos | PostgreSQL 16 |
| Archivos | Almacenamiento de objetos compatible con S3 o GCS (DP-05); en local, MinIO o el sistema de archivos |
| Pruebas | pytest + httpx, con Postgres real en Docker; Vitest + Testing Library; Playwright solo para flujos críticos |
| Calidad | ruff + mypy (backend), ESLint + Prettier + tsc (frontend), pre-commit |
| Infra | Docker Compose (local); hosting en DP-05 |

Cualquier tecnología nueva requiere un ADR en `docs/architecture.md` §13.

## 15. Alcance MVP (entrega de la semana 4)

Incluye M1 a M8, la migración de datos históricos, el despliegue en producción y las pruebas de RBAC y de reglas de negocio.

**Criterio de éxito del MVP:** el equipo de Trulab puede dejar de usar AppSheet. Todo viajero puede registrar y legalizar desde el celular, financiero puede liquidar, y los datos históricos están disponibles.

## 16. Funcionalidades futuras (post-MVP, sin compromiso de fecha)

1. Notificaciones por correo (si no entran al MVP, DP-06).
2. OCR de soportes: precarga de valor, fecha y NIT; el usuario confirma.
3. Integración con Google Chat (tarjeta de bienvenida, comandos `/`).
4. Exportación a Excel/CSV de pagos y legalizaciones.
5. Categorías de gasto (transporte, alimentación, hospedaje…) y topes por cargo.
6. Aprobación previa del viaje y anticipos solicitados desde la app.
7. Registro del pago o reintegro (referencia bancaria y comprobante de transferencia).
8. PWA instalable y modo sin conexión para registrar gastos en campo.
9. Panel de auditoría para SUPERADMIN.

## 17. Decisiones abiertas

Estas decisiones bloquean o condicionan el diseño. Cada una tiene una recomendación por defecto; si no hay respuesta antes de la fase indicada, se aplica esa recomendación y se registra como ADR.

| ID | Pregunta | Recomendación por defecto | Bloquea |
| :--- | :--- | :--- | :--- |
| DP-01 | ¿Login solo con Google o también con contraseña? El informe dice ambas cosas: hoy AppSheet usa Google OAuth y RF-001 pide bcrypt. | Google OAuth restringido a `trulab.co` como método principal; contraseña solo si hay usuarios sin cuenta Google | Fase 2 |
| DP-02 | El dashboard agrupa por "proyecto / centro de costo", pero ese campo no existe en el modelo. ¿Qué es la tabla `Segmentador`? | Crear la tabla `proyectos` y una FK obligatoria en la legalización; eliminar `Segmentador` si solo servía para filtros | Fase 4 |
| DP-03 | ¿Existe un estado para devolver al viajero con observaciones? | Sí: `DEVUELTA`, con comentario obligatorio | Fase 4 |
| DP-04 | ¿Quién registra `valor_transferido` y cuándo (anticipo antes del viaje o al liquidar)? | Lo registra FINANCIERO o ADMIN; el viajero solo lo ve | Fase 4 |
| DP-05 | Hosting y almacenamiento de archivos | Decidir antes de cerrar la semana 2 (gate de `SPRINTS.md`). Candidatos: Render/Railway + S3, o GCP (Cloud Run + Cloud SQL + GCS), que encaja con Google Workspace | Fase 10 |
| DP-06 | ¿Las notificaciones por correo entran al MVP? | Solo si sobra tiempo en la semana 3; si no, en la primera iteración post-MVP | Fase 6 |
| DP-07 | Esquema real y exportación de AppSheet: columnas reales, valores de estado y dónde están guardadas las imágenes (¿Google Drive?) | Obtener la exportación CSV y las imágenes **en la semana 1** | Fases 4 y 10 |
| DP-08 | Paleta, logo y tipografía corporativos | Usar los tokens provisionales de `docs/design-system.md` | Fase 4 (UI) |
| DP-09 | Formato de folios (`CA-`, `LG-`) | Confirmar prefijos. ¿Los gastos llevan folio? Recomendación: no | Fase 3 |
| DP-10 | ¿Qué significa un saldo negativo para el negocio y qué se registra al pagar? | Negativo = la empresa reembolsa. Al pagar se guarda fecha, usuario y observación; la referencia bancaria queda para el futuro | Fase 6 |
| DP-11 | Moneda | Solo COP | — |
| DP-12 | ¿FINANCIERO puede corregir valores de gastos ajenos? | No; devuelve la legalización (separación de funciones) | Fase 5 |
