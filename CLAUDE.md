# CLAUDE.md — Memoria del proyecto Trulab Viajes

> Lee este archivo primero y después `HANDOFF.md`. Con ambos deberías poder retomar el trabajo sin releer el informe original.
> Mantenlo corto y actualizado: los detalles viven en `SPEC.md` y `docs/`.

## Qué es

Reconstrucción con código propio de la app AppSheet **"Trulab viajes"**, el sistema de viáticos de Trulab. Los colaboradores registran los gastos de sus viajes con soporte digital. Financiero audita el saldo (transferido − gastado) y liquida.

**Objetivo:** reemplazar AppSheet con un MVP responsivo (móvil, tablet y escritorio) y con seguridad en el backend. Lo hace **1 desarrollador en 4 semanas**.

## Mapa de documentos

| Archivo | Para qué |
| :--- | :--- |
| `SPEC.md` | **Fuente de verdad:** alcance, roles y permisos (§6), reglas RN-xx (§8), RF y RNF, MVP, **decisiones abiertas DP-xx (§17)** |
| `HANDOFF.md` | Estado actual y próxima tarea; se actualiza en cada sesión |
| `ROADMAP.md` | Fases F1–F10, dependencias, hitos, contingencia |
| `SPRINTS.md` | Tareas por semana con estimación, riesgos, criterios y gates |
| `docs/architecture.md` | Arquitectura y **registro de ADR (§13)** |
| `docs/database-design.md` | Tablas, relaciones, índices, RLS, auditoría, nomenclatura |
| `docs/api-design.md` | Contrato REST, errores, paginación, permisos por endpoint |
| `docs/design-system.md` | Tokens, componentes, layouts mobile-first |
| `docs/user-flows.md` | Flujos F-01 a F-11 y máquina de estados |
| `docs/skills-strategy.md` | Qué skill usar para cada tipo de trabajo |

El informe original de auditoría de AppSheet (*INFORME FINAL PARA PROYECTO TRULAB.md*) **no está en el repo**; todo lo útil se consolidó en `SPEC.md`.

## Stack

- **Frontend:** React 18 + Vite + TypeScript, Tailwind + shadcn/ui, TanStack Query, React Router, React Hook Form + Zod, Recharts, Lucide.
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (síncrono), Alembic, psycopg 3, WeasyPrint.
- **Datos:** PostgreSQL 16 con RLS; archivos en un bucket privado compatible con S3 o GCS.
- **Herramientas:** Docker Compose, GitHub Actions, ruff, mypy, pytest, ESLint, Vitest, Playwright.

## Arquitectura en una frase

Monolito modular: la SPA React habla REST (`/api/v1`) con FastAPI (`routers → services → models`), que usa PostgreSQL y un bucket privado. La autenticación es con Google y una sesión propia (access JWT de 15 min en memoria más refresh rotativo en cookie httpOnly). La autorización va en el service, con RLS como defensa en profundidad.

## Estructura (prevista; aún no existe)

```
backend/app/{core,modules/<dominio>,templates/pdf}   backend/{alembic,tests}
frontend/src/{app,components/{ui,layout},features/<dominio>,lib,types}
infra/  scripts/etl_appsheet/  docs/
```

Dominios: `auth`, `usuarios`, `cargos`, `proyectos`, `legalizaciones`, `gastos`, `pagos`, `reportes`, `indicadores`.

## Roles y módulos

- **Roles** (uno por usuario): `VIAJERO` (solo lo suyo), `FINANCIERO` (audita y paga; ve todo), `ADMIN` (además gestiona usuarios y cargos), `SUPERADMIN` (todo). Matriz completa en `SPEC.md` §6.
- **Módulos MVP:** Auth, Usuarios, Cargos, Legalizaciones, Gastos, Pagos, PDF, Indicadores. Las notificaciones son opcionales. OCR y Google Chat quedan para el futuro.
- **Estados:** `BORRADOR → LEGALIZADA → PAGADA`, con `LEGALIZADA ⇄ DEVUELTA`.

## Decisiones clave (ver ADR en `docs/architecture.md` §13)

1. Las transiciones de estado son **acciones** (`POST /legalizaciones/{id}/legalizar|devolver|pagar`) que pasan por una única función `transicionar()`, la cual registra el historial en la misma transacción.
2. **El saldo nunca se almacena:** sale de la vista `v_legalizacion_saldos` (`valor_transferido − Σ gastos`).
3. **Recurso ajeno → 404**, sin permiso → 403, estado inválido → 409. Los errores siguen RFC 9457 con `code` estable.
4. **Dinero:** `NUMERIC(14,2)` en BD y *string* en JSON. Moneda COP.
5. **PK UUID** más folio legible (`LG-000001`, `CA-000001`).
6. **Eliminación lógica** (`deleted_at`); los usuarios se desactivan, no se borran.
7. **Soportes** en un bucket privado, validados por *magic bytes*, con máximo de 10 MB y servidos con URL firmada de 5 min.
8. El backend siempre corre en Docker (por WeasyPrint y la paridad con producción).

## Convenciones técnicas

- **Idioma:** dominio, BD, API y UI en **español**. Código de infraestructura y nombres técnicos genéricos en inglés (`router`, `service`, `schemas`).
- **Nombres:** tablas en `snake_case` plural; JSON en `snake_case`; componentes React en `PascalCase`; hooks como `useX`. Más detalle en `docs/database-design.md` §9.
- **Reglas de negocio solo en `services`**; routers delgados; nada de lógica de negocio en componentes React.
- **TDD obligatorio** para reglas RN-xx y permisos. Una prueba parametrizada recorre la matriz RBAC.
- **Migraciones solo con Alembic.** Los tipos TS se generan desde OpenAPI; no se escriben a mano.
- **Git:** rama `main` protegida; ramas `feat/<fase>-<tema>`, `fix/...`; commits convencionales en español (`feat(gastos): subir soporte`).
- **Secretos** solo en `.env` (no versionado); se mantiene `.env.example` al día.
- **Identidad git local:** `John Hernandez <John.Hernandez@trulab.co>`; remote `origin` en GitHub (`johnhernandez-prog/Trulab_Viaticos`).

## Estado actual

**Fase:** planificación terminada (documentación base creada el 2026-11-10). **No hay código.** Siguiente paso: semana 0 (respuestas a las DP y exportación de AppSheet) y luego la semana 1 (`SPRINTS.md`). El detalle vivo está en `HANDOFF.md`.

## Cómo retomar

1. Lee `HANDOFF.md`: estado, próxima tarea y bloqueos.
2. Abre solo la sección de la semana actual en `SPRINTS.md`.
3. Consulta `SPEC.md` y el `docs/` relevante a la tarea (no todo).
4. Si dudas de una decisión pasada, revisa los ADR y luego usa `claude-mem:mem-search`.
5. Trabaja con la skill indicada en la tarea (`docs/skills-strategy.md`).
6. Al cerrar, actualiza `HANDOFF.md` (`claude-mem:handoff`) y este archivo si cambió una decisión, el stack o el estado.

## Orden recomendado de desarrollo

F1 Base técnica → F2 Auth/RBAC → F3 Usuarios/Cargos → F4 Legalizaciones → F5 Gastos → F6 Pagos → F7 PDF → F8 Dashboard → F9 Pruebas (continuas y cierre) → F10 Producción + ETL. Nunca se empieza un módulo funcional antes de que F2 esté probado.
