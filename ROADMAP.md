# ROADMAP — Trulab Viajes

> Visión por fases. El detalle por semana (tareas, riesgos, criterios) está en `SPRINTS.md`.
> Restricción: 1 desarrollador, 4 semanas para el MVP (fases 1 a 10).

## Vista general

```
Semana 1                 Semana 2                Semana 3                          Semana 4
F1 ─▶ F2 ─▶ F3 ────────▶ F4 ─▶ F5 ─────────────▶ F6 ─▶ F7 ─▶ F8 ─────────────────▶ F9 ─▶ F10
Base   Auth  Usuarios/   Legaliz. Gastos          Pagos  PDF   Dashboard           Pruebas  Producción
técnica      Cargos                                      ETL de migración (preparación)    + corte
└──────────── F9 · Pruebas: continuas en cada fase (las reglas y el RBAC se prueban al implementarse) ───┘
```

## Fases

| Fase | Nombre | Objetivo | Depende de | Semana | Módulos / RF |
| :--- | :--- | :--- | :--- | :---: | :--- |
| F1 | Arquitectura y base técnica | Monorepo, Docker Compose, backend y frontend esqueleto, CI, BD con Alembic, convenciones | — | 1 | — |
| F2 | Autenticación y seguridad | Login Google, sesión JWT y refresh, `/me`, matriz RBAC, roles de BD y RLS base, errores RFC 9457 | F1 | 1 | M1 · RF-001/002/014 |
| F3 | Usuarios y cargos | CRUD de cargos y usuarios (API y UI), AppShell responsivo con navegación por rol | F2 | 1 | M2, M3 · RF-003/004 |
| F4 | Legalizaciones | Modelo, CRUD, proyectos (DP-02), máquina de estados (legalizar y devolver), historial, lista y detalle | F3 | 2 | M4 · RF-005/007 |
| F5 | Registro de gastos | CRUD de gastos, almacenamiento de soportes, cámara, URLs firmadas, totales y saldo | F4 | 2 | M5 · RF-006/011 |
| F6 | Pagos | Vista de saldos, filtros y resumen, editar valor transferido, acción pagar | F5 | 3 | M6 · RF-007/008 |
| F7 | Reportes PDF | Plantilla WeasyPrint y descarga | F5 (datos), F6 (estado pagada) | 3 | M7 · RF-009 |
| F8 | Dashboard e indicadores | Endpoints de agregación y dashboard Recharts | F6 | 3 | M8 · RF-010 |
| F9 | Pruebas | Continuas en cada fase; en la semana 4: matriz RBAC completa, RLS, E2E críticos, responsivo, accesibilidad, revisión de seguridad | F1–F8 | 1–4 | RNF-02/03/04/05/07 |
| F10 | Producción y migración | Infra de producción (DP-05), ETL de AppSheet (ensayo y definitivo), despliegue, corte, soporte inicial | F9 (y ETL desde la semana 3) | 3–4 | RF-012 · RNF-08/10 |

## Dependencias críticas

1. **F2 antes que todo lo funcional:** sin auth ni RBAC no se pueden probar los permisos de ningún módulo.
2. **F4 → F5 → F6:** los gastos cuelgan de la legalización; el saldo de Pagos necesita los gastos.
3. **DP-07 (exportación real de AppSheet) antes de cerrar el modelo de F4.** Si el esquema real difiere, se ajusta la migración de F4, no después del ETL.
4. **DP-02 (proyectos) antes de F4.** Afecta al formulario de legalización y a F8.
5. **DP-05 (hosting) antes de cerrar la semana 2** (gate de `SPRINTS.md`): hacen falta las credenciales del bucket para probar F5 en un entorno real y preparar F10.
6. **El ETL (F10) depende de F4 y F5 terminados** (las tablas destino estables) y se ensaya contra la BD de *staging* en la semana 3.

## Hitos

| Hito | Cuándo | Evidencia |
| :--- | :--- | :--- |
| H1 · Base segura | Fin de la semana 1 | Login Google funcionando; CRUD de cargos y usuarios con RBAC probado; CI en verde |
| H2 · Flujo del viajero | Fin de la semana 2 | Desde un celular: crear una legalización, agregar gastos con foto y legalizar |
| H3 · Sistema completo | Fin de la semana 3 | Pagos, PDF y dashboard operativos; ETL ensayado con datos reales en staging |
| H4 · MVP en producción | Fin de la semana 4 | Usuarios reales en producción, datos históricos migrados, AppSheet en solo lectura |

## Post-MVP (orden sugerido, sin fecha)

| Fase | Contenido | Depende de |
| :--- | :--- | :--- |
| F11 | Notificaciones por correo (si no entraron, DP-06) | F4 |
| F12 | Exportación Excel/CSV de pagos y legalizaciones | F6 |
| F13 | PWA instalable y captura sin conexión | F5 |
| F14 | Categorías de gasto y topes por cargo | F5 |
| F15 | OCR de soportes (piloto con 50 soportes y luego integración) | F5 |
| F16 | Google Chat (avisos y comandos `/`) | F11 |
| F17 | Panel de auditoría (SUPERADMIN) y PDF inmutable al pagar | F2, F7 |
| F18 | Registro del pago o reintegro con comprobante bancario | F6 |

## Plan de contingencia si el calendario se aprieta

Se recorta en este orden, sin tocar el flujo crítico (F2, F4, F5, F6):
1. KPIs del dashboard (quedan solo los dos gráficos).
2. Miniaturas de soportes en el PDF (queda la lista de gastos).
3. Login con contraseña (solo Google).
4. Dashboard completo (pasa a post-MVP; financiero usa los filtros de Pagos).
5. RLS en BD (se mantiene la autorización en la app, con pruebas exhaustivas; RLS en la primera semana post-MVP).

**Nunca se recortan:** las pruebas de RBAC, la validación de archivos ni la migración de datos históricos.
