# HANDOFF — Trulab Viajes

> Documento vivo para retomar entre sesiones. Se actualiza al final de **cada** sesión (skill `claude-mem:handoff`).
> Formato: se sobrescriben las secciones de estado. El historial se acumula al final (lo más reciente arriba).

## Estado actual

| Campo | Valor |
| :--- | :--- |
| Fase | **Hito 0 alcanzado: documentación base completada.** Siguiente: resolver las decisiones abiertas (semana 0) |
| Semana del sprint | El Sprint 1 aún no inicia. **No se inicia hasta resolver las decisiones abiertas** |
| Código | No existe todavía (decisión explícita: primero documentación) |
| Repositorio | Git local con `origin` = `https://github.com/johnhernandez-prog/Trulab_Viaticos.git`. Primer commit local con la documentación base (sin push) |
| Última actualización | 2026-11-10 |

## Última actividad

Se analizó el *INFORME FINAL PARA PROYECTO TRULAB.md*, se generó la documentación base, se revisaron las referencias cruzadas y se registró como primer hito oficial en un commit (`docs: initialize project specification, architecture, roadmap and project memory`). El informe original no se guardó en el repositorio.

## Trabajo completado

- [x] Repositorio git local con identidad corporativa y remote configurados
- [x] `SPEC.md`: especificación maestra con RN, RF, RNF, RBAC, MVP y decisiones abiertas
- [x] `CLAUDE.md`: memoria del proyecto
- [x] `ROADMAP.md`: fases F1–F10, dependencias, hitos y contingencia
- [x] `SPRINTS.md`: plan de 4 semanas con tareas, estimaciones, riesgos, criterios y gates
- [x] `docs/architecture.md`, con 16 ADR
- [x] `docs/database-design.md`
- [x] `docs/api-design.md`
- [x] `docs/design-system.md`
- [x] `docs/user-flows.md`
- [x] `docs/skills-strategy.md`
- [x] Revisión de consistencia y referencias cruzadas entre documentos
- [x] Commit local del hito 0 (documentación base)

## Trabajo pendiente

- [ ] **Resolver las decisiones abiertas**, como mínimo DP-01, DP-02, DP-04 y DP-07 (`SPEC.md` §17). Siguen **pendientes a propósito**
- [ ] Push del commit a `origin/main`
- [ ] Revisión de la documentación por el dueño del producto
- [ ] Semana 0: tareas P-1 a P-5 (`SPRINTS.md`)
- [ ] Semanas 1 a 4 completas

## Próxima tarea sugerida

**Resolver las decisiones abiertas antes de iniciar el Sprint 1.**
1. Responder DP-01 (método de login), DP-02 (proyecto o `Segmentador`), DP-04 (quién registra `valor_transferido`) y DP-07 (exportación real de AppSheet). El resto puede quedarse con su valor por defecto.
2. Registrar cada respuesta en `SPEC.md` §17 y, si cambia la arquitectura, como ADR en `docs/architecture.md` §13.
3. Pedir la **exportación de AppSheet** (CSV de las 5 tablas y soportes): es el principal riesgo del proyecto.
4. Solo entonces, empezar **S1-01** (estructura del monorepo) con `agent-skills:build`.

## Decisiones pendientes (detalle y recomendación en `SPEC.md` §17)

| ID | Tema | Bloquea | Estado |
| :--- | :--- | :--- | :--- |
| DP-01 | Login solo Google o también contraseña | F2 | Abierta (por defecto: Google + `trulab.co`) |
| DP-02 | Proyecto o centro de costo; qué es `Segmentador` | F4 | Abierta |
| DP-03 | Estado `DEVUELTA` en el MVP | F4 | Abierta (por defecto: sí) |
| DP-04 | Quién registra `valor_transferido` | F4 | Abierta (por defecto: FINANCIERO/ADMIN) |
| DP-05 | Hosting y almacenamiento | F10 (decidir en la semana 2) | Abierta |
| DP-06 | Correos en el MVP | F6 | Abierta (por defecto: opcional en la semana 3) |
| DP-07 | Esquema real y exportación de AppSheet | F4, F10 | **Abierta, crítica** |
| DP-08 | Paleta y logo corporativos | UI | Abierta (tokens provisionales) |
| DP-09 | Prefijos de folio | F3 | Abierta |
| DP-10 | Semántica del saldo negativo y datos al pagar | F6 | Abierta |
| DP-11 | Moneda solo COP | — | Por defecto: COP |
| DP-12 | Financiero edita gastos ajenos | F5 | Abierta (por defecto: no) |

## Riesgos conocidos

1. **Calendario ajustado:** déficit de unas 20 h en las semanas 1 y 2 (`SPRINTS.md`, resumen de capacidad). Plan B: una semana 5 de holgura.
2. **Modelo de datos deducido por ingeniería inversa:** puede no coincidir con AppSheet (DP-07).
3. **Migración de soportes** desde AppSheet o Google Drive: volumen y permisos desconocidos.
4. **Dependencia externa** para el OAuth Client ID (admin de Google Workspace).
5. **WeasyPrint en Windows:** mitigado ejecutando el backend en Docker.
6. **Campo "proyecto" ausente** en el modelo pero requerido por el dashboard (DP-02).

## Inconsistencias detectadas en el informe original (registradas en SPEC como DP; pendientes de decisión)

- Autenticación: dice Google OAuth (actual) y también JWT con bcrypt (RF-001) → DP-01.
- Dashboard por proyecto sin campo de proyecto en el modelo; `Segmentador` sin definir → DP-02.
- Estados: menciona "Pendiente", "Borrador", "Legalizado" y "Pagado" sin una máquina de estados formal → RN-05 y DP-03.
- La matriz RBAC permite D/U del viajero sin considerar el estado → aclarado en `SPEC.md` §6 (nota ¹).
- El ETL, las notificaciones por correo y Google Chat no tienen sprint asignado coherente → ETL en la semana 3 y 4; correo opcional; Chat a futuro.

---

## Historial de sesiones

### 2026-11-10 · Sesión 1: inicialización y documentación base
- Git inicializado, identidad local `John.Hernandez@trulab.co`, remote `origin` configurado (repositorio remoto vacío).
- Generada toda la documentación estratégica a partir del informe. Sin código.
- Revisión de consistencia: unificado el plazo de DP-05 (antes de cerrar la semana 2), DP-07 apunta a F4 y F10, aclarada la nota ¹ de RBAC (editar vs eliminar).
- Commit local del hito 0. Las decisiones DP-01, DP-02, DP-04 y DP-07 siguen abiertas.
