# ROADMAP — Trulab Viajes

> Visión por fases. El detalle por semana (tareas, riesgos, criterios) está en `SPRINTS.md`.
> Restricción: 1 desarrollador. Plan de 4 semanas **ampliado a 5** (semana 5 de holgura activada el 2026-11-12 por el nuevo alcance: SPEC v0.4, ADR-027 a ADR-030).

## Vista general

```
Semana 1                 Semana 2                Semana 3                          Semana 4      Semana 5
F1 ─▶ F2 ─▶ F3 ────────▶ F4 ─▶ F5 ─────────────▶ F6 ─▶ F7 ─▶ F8 ─────────────────▶ F9 ─▶ F10 ───▶ UAT + corte
Base   Auth  Usuarios/   Viáticos Gastos          Pagos  PDF   Dashboard           Pruebas  Producción  (holgura
técnica híbrida Cargos   +Tarifas                        ETL de migración (preparación)   en AWS      activada)
└──────────── F9 · Pruebas: continuas en cada fase (las reglas y el RBAC se prueban al implementarse) ───┘
```

## Fases

| Fase | Nombre | Objetivo | Depende de | Semana | Módulos / RF |
| :--- | :--- | :--- | :--- | :---: | :--- |
| F1 | Arquitectura y base técnica | Monorepo, Docker Compose, backend y frontend esqueleto, CI, BD con Alembic, convenciones | — | 1 | — |
| F2 | Autenticación y seguridad | **Acceso híbrido (DP-01 actualizada, ADR-027):** usuario/contraseña con Argon2id, recuperación por correo y cambio obligatorio para VIAJERO/ADMIN/FINANCIERO; Google `@trulab.co` exclusivo para SUPERADMIN. Sesión JWT y refresh, `/me`, matriz RBAC, roles de BD y RLS base, errores RFC 9457 | F1 | 1 | M1 · RF-001/002/014 |
| F3 | Usuarios y cargos | CRUD de cargos y usuarios (API y UI), contraseña temporal, gestión de SUPERADMIN, AppShell responsivo con navegación por rol (la UI de usuarios pasa a la semana 5) | F2 | 1 (UI: 5) | M2, M3 · RF-003/004 |
| F4 | Viáticos y tarifas | **Entidad unificada `viaticos` (`VT-`, ADR-029):** modalidades `CON_SOLICITUD` / `LEGALIZACION_DIRECTA`, etapas, trayectos, **tarifas de viáticos (ADR-030) y cálculo tarifario**, catálogos (DP-14 ✅), recursos propios y valor asignado (DP-04 ✅), máquina de estados con etapa (DP-13 ✅), historial, lista y detalle; UI de Solicitud en la semana 3 | F3 | 2 (UI Solicitud: 3) | M3c, M4, M4b · RF-005/007/015/017/018 |
| F5 | Registro de gastos | CRUD de gastos (etapa legalización), almacenamiento en S3, cámara, URLs prefirmadas, firma y formato adjunto, totales y saldo | F4 | 2 | M5 · RF-006/011 |
| F6 | Pagos | Vista de saldos, filtros y resumen, editar valor transferido, acción pagar | F5 | 3 | M6 · RF-007/008 |
| F7 | Reportes PDF | **PDF de solicitud (con firma) y PDF de legalización** con WeasyPrint | F5 (datos), F6 (estado pagada) | 3 | M7 · RF-009/017 |
| F8 | Dashboard e indicadores | Endpoints de agregación (semana 3) y dashboard Recharts (UI en la semana 5) | F6 | 3 (UI: 5) | M8 · RF-010 |
| F9 | Pruebas | Continuas en cada fase; en la semana 4: matriz RBAC completa, RLS, E2E críticos, responsivo, accesibilidad, revisión de seguridad (incluida la auth con contraseñas) | F1–F8 | 1–5 | RNF-02/03/04/05/07 |
| F10 | Producción y migración | **Infra en AWS (DP-05 ✅, ADR-028):** RDS, S3, SES, ECS/App Runner; ETL de AppSheet (ensayo y definitivo), despliegue, corte (AppSheet y Apps Script a solo lectura), soporte inicial | F9 (y ETL desde la semana 3) | 3–5 | RF-012 · RNF-08/10 |

## Dependencias críticas

1. **F2 antes que todo lo funcional:** sin auth ni RBAC no se pueden probar los permisos de ningún módulo.
2. **F4 → F5 → F6:** los gastos cuelgan de la legalización; el saldo de Pagos necesita los gastos.
3. ~~DP-07 antes de F4~~ → **resuelta ✅**: estructura real validada (`SPEC.md` §18). Sigue haciendo falta la **exportación de datos** (P-2) para el ETL.
4. ~~DP-02 antes de F4~~ → **resuelta ✅**: proyecto como lista cerrada en el gasto; Segmentador = filtro de fechas.
4b. ~~DP-13 a DP-18 antes de la migración de F4~~ → **resueltas ✅ (2026-11-11)**: estados operativo y financiero, catálogos administrables, soporte/archivo, fecha de factura para indicadores, recursos propios del viajero y permisos de ADMIN (`SPEC.md` §17.1). Ya no hay decisiones que bloqueen F4.
5. ~~DP-05 (hosting)~~ → **resuelta ✅ (AWS, ADR-028)**. Siguen haciendo falta P-6 (cuenta AWS, identidad SES verificada, bucket y RDS) antes de S3-07, y DP-21 (ECS Fargate o App Runner).
5b. **F4 depende de P-7:** las tarifas de los 22 destinos se extraen de `calcularGastos.html` y las valida el dueño del producto antes del seed (S2-01).
5c. **El correo de restablecimiento (SES) es parte de F2**, no opcional: sin él los operativos no recuperan su contraseña.
6. **El ETL (F10) depende de F4 y F5 terminados** (las tablas destino estables) y se ensaya contra la BD de *staging* en la semana 3.

## Hitos

| Hito | Cuándo | Evidencia |
| :--- | :--- | :--- |
| H1 · Base segura | Fin de la semana 1 | Login de operativos (con recuperación) y de SUPERADMIN (Google) funcionando; API de cargos y usuarios con RBAC probado; CI en verde |
| H2 · Flujo del viajero | Fin de la semana 2 | Backend de viáticos y tarifas completo; desde un celular: crear una legalización directa, agregar gastos con foto y verla aprobada |
| H3 · Sistema completo | Fin de la semana 3 | Solicitud con presupuesto y PDF firmado, Pagos y PDF de legalización operativos; staging en AWS; ETL ensayado con datos reales |
| H4 · Listo para UAT | Fin de la semana 4 | Producción AWS lista, RBAC/E2E/seguridad pasados |
| H5 · MVP en producción | Fin de la semana 5 | Usuarios reales (incluidos prestadores) en producción, datos históricos migrados, AppSheet y Apps Script en solo lectura |

## Post-MVP (orden sugerido, sin fecha)

| Fase | Contenido | Depende de |
| :--- | :--- | :--- |
| F11 | Notificaciones por correo de cambios de estado (si no entraron, DP-06; SES ya existe) | F4 |
| F12 | Exportación Excel/CSV de pagos y legalizaciones | F6 |
| F13 | PWA instalable y captura sin conexión | F5 |
| F14 | Categorías de gasto y topes por cargo | F5 |
| F15 | OCR de soportes (piloto con 50 soportes y luego integración) | F5 |
| F16 | Google Chat (avisos y comandos `/`) | F11 |
| F17 | Panel de auditoría (SUPERADMIN) y PDF inmutable al pagar | F2, F7 |
| F18 | Registro del pago o reintegro con comprobante bancario | F6 |
| F19 | Integración con Asana (tareas al solicitar hospedaje o tiquetes; heredada de `consumoApi.html`) | F4 |

## Plan de contingencia si el calendario se aprieta

Se recorta en este orden, sin tocar el flujo crítico (F2, F4, F5, F6):
1. KPIs del dashboard (quedan solo los dos gráficos).
2. Miniaturas de soportes en el PDF (queda la lista de gastos).
3. ~~Login con contraseña~~: **ya no se puede recortar** (ADR-027: es el acceso de los operativos). Lo que sí se puede recortar: la UI de Tarifas (SUPERADMIN edita por API) y el bloqueo temporal por intentos (queda el límite por IP).
4. Dashboard completo (pasa a post-MVP; financiero usa los filtros de Pagos).
5. RLS en BD (se mantiene la autorización en la app, con pruebas exhaustivas; RLS en la primera semana post-MVP).

**Nunca se recortan:** las pruebas de RBAC, la validación de archivos ni la migración de datos históricos.
