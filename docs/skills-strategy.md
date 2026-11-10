# Estrategia de uso de skills — Trulab Viajes

> Qué skill de Claude Code usar para cada tipo de trabajo en este proyecto. Los nombres aparecen tal como se invocan (`/nombre` o mediante la herramienta Skill).
> Regla general: **una skill por tipo de trabajo, no todas a la vez.** Cada skill carga instrucciones y consume contexto.

## 1. Mapa rápido: tipo de trabajo → skill

| Tipo de trabajo | Skill principal | Complementarias |
| :--- | :--- | :--- |
| Funcionalidad nueva o requisito poco claro | `agent-skills:spec-driven-development` | `agent-skills:interview-me`, `agent-skills:idea-refine` |
| Cambio estructural (capas, módulos, stack) | `engineering:architecture` | `agent-skills:documentation-and-adrs` (registrar el ADR) |
| Módulo complejo (máquina de estados, pagos, ETL) | `engineering:system-design` | `agent-skills:doubt-driven-development` |
| Dividir una fase en tareas | `agent-skills:planning-and-task-breakdown` | `claude-mem:make-plan` |
| Implementar una tarea del sprint | `agent-skills:build` | `agent-skills:incremental-implementation` |
| Ejecutar un plan de varias tareas con subagentes | `claude-mem:do` | — |
| Lógica de negocio, reglas RN-xx, permisos | `agent-skills:test-driven-development` | `engineering:testing-strategy` |
| Diseñar o cambiar endpoints o contratos | `agent-skills:api-and-interface-design` | — |
| Pantallas y componentes React | `agent-skills:frontend-ui-engineering` | `design:design-system`, `design:ux-copy` |
| Tokens, colores, tipografía, componentes base | `design:design-system` | `design:design-critique` |
| Accesibilidad | `design:accessibility-review` | — |
| Gráficos del dashboard | `dataviz` | — |
| Autenticación, archivos, RLS, dependencias | `agent-skills:security-and-hardening` | `security-review` (antes de fusionar) |
| Errores o comportamiento inesperado | `agent-skills:debugging-and-error-recovery` | `engineering:debug` |
| Revisión antes de fusionar | `agent-skills:review` | `code-review`, `simplify` |
| Rendimiento (RNF-01) | `agent-skills:webperf` | `agent-skills:performance-optimization` |
| CI/CD y despliegue | `agent-skills:ci-cd-and-automation` | — |
| Migración de AppSheet (ETL) y corte | `agent-skills:deprecation-and-migration` | — |
| Preparación de producción | `agent-skills:ship` | `agent-skills:shipping-and-launch`, `engineering:deploy-checklist` |
| Commits, ramas y PR | `agent-skills:git-workflow-and-versioning` | — |
| Documentar decisiones | `agent-skills:documentation-and-adrs` | — |
| Probar en el navegador | `agent-skills:browser-testing-with-devtools` | `run` |
| Contexto de sesión o reglas del proyecto | `agent-skills:context-engineering` | — |
| Cierre de sesión | `claude-mem:handoff` | — |
| Recuperar decisiones de sesiones anteriores | `claude-mem:mem-search` | — |
| Actualizar el conocimiento del código | `claude-mem:learn-codebase` | `claude-mem:smart-explore` |
| Auditar la arquitectura o detectar duplicación | `claude-mem:pathfinder` | — |

## 2. Cuándo aplica cada skill en este proyecto

### Planificación y especificación
- **`agent-skills:spec-driven-development`**: antes de cualquier funcionalidad que no esté en `SPEC.md`, o al resolver una DP que cambie el alcance. El resultado se agrega a `SPEC.md`; no se crean especificaciones sueltas.
- **`agent-skills:planning-and-task-breakdown`**: al empezar cada semana, para convertir las filas de `SPRINTS.md` en tareas de 1 a 3 h con criterios verificables.
- **`engineering:architecture`**: solo si se toca un ADR existente o se agrega tecnología. Siempre se termina con un ADR en `docs/architecture.md` §13.
- **`engineering:system-design`**: máquina de estados (S2-04), pagos con concurrencia (S3-01), ETL (S3-06).

### Construcción
- **`agent-skills:build`**: la skill de trabajo diario. Implementa, prueba, verifica y hace commit, una tarea a la vez.
- **`agent-skills:test-driven-development`**: obligatoria para RN-01 a RN-13 y para la matriz RBAC. La prueba se escribe primero, a partir de la regla de `SPEC.md`.
- **`agent-skills:api-and-interface-design`**: antes de agregar o cambiar endpoints. Se contrasta con `docs/api-design.md`.
- **`agent-skills:frontend-ui-engineering`** con **`design:design-system`**: en cada pantalla; se contrasta con `docs/design-system.md` y `docs/user-flows.md`.
- **`agent-skills:security-and-hardening`**: en S1-08 (auth), S2-03 (RLS), S2-06 (archivos) y S4-03.

### Calidad y entrega
- **`agent-skills:review`** o **`code-review`**: al terminar cada módulo, antes de fusionar a `main`.
- **`security-review`**: antes de fusionar cambios en `core/security.py`, `core/permissions.py` o `core/storage.py`.
- **`agent-skills:ship`**: una sola vez, en S4-08 (go/no-go).

### Memoria y continuidad
- **`claude-mem:handoff`**: al **terminar cada sesión de trabajo**. Actualiza `HANDOFF.md`, que es la puerta de entrada de la sesión siguiente.
- **`claude-mem:mem-search`**: cuando surja "¿por qué decidimos X?" y la respuesta no esté en los ADR. Primero se buscan los docs del repo; mem-search va después.
- **`claude-mem:learn-codebase`**: **todavía no aplica** (no hay código). Úsese a partir de la semana 2, cuando una sesión nueva necesite el panorama del código, o tras cambios grandes.
- **`claude-mem:pathfinder`**: **todavía no aplica.** Úsese al final de la semana 3 o en el post-MVP para detectar duplicación entre módulos antes de refactorizar.
- **`agent-skills:context-engineering`**: si las sesiones empiezan a perder calidad o a releer demasiado. Sirve para ajustar `CLAUDE.md`.

## 3. Rutina recomendada por sesión

```
1. Inicio:     leer CLAUDE.md → HANDOFF.md (→ SPRINTS.md, solo la semana actual)
2. Si hay duda sobre una decisión pasada: claude-mem:mem-search
3. Planificar la tarea:     agent-skills:planning-and-task-breakdown (si la tarea pasa de 3 h)
4. Implementar:             agent-skills:build (+ test-driven-development para reglas)
5. Antes de fusionar:       agent-skills:review  (+ security-review si tocó seguridad)
6. Cierre:                  claude-mem:handoff → actualizar HANDOFF.md (y CLAUDE.md si cambió una decisión)
```

## 4. Antipatrones

- Cargar muchas skills "por si acaso": cuesta contexto y produce instrucciones en conflicto.
- Usar `learn-codebase` para leer documentación: los docs se leen directamente.
- Implementar sin pasar por `SPEC.md` cuando la funcionalidad no está especificada.
- Cerrar una sesión sin `handoff`: la siguiente sesión pierde el hilo.
- Usar `ship` como revisión de rutina: es para el lanzamiento.
