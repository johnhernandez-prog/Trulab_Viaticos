# Flujos de usuario — Trulab Viajes

> Cada flujo indica el actor, la precondición, los pasos, las reglas aplicadas y los caminos alternos.
> Referencias: reglas RN-xx y supuestos S-xx en `SPEC.md` v0.4 (§8 y §17.3); endpoints en `docs/api-design.md`.
> **Terminología:** el **viático** (`VT-000001`) es la entidad única. Tiene dos **etapas**: `SOLICITUD` (antes del viaje) y `LEGALIZACION` (carga de gastos). "Legalización" designa la etapa; el registro es el mismo.

## Modelo de estados del viático (DP-13 ✅, DP-19 ✅)

El viático tiene **tres dimensiones independientes** y un espejo:

| Dimensión | Columna | Origen | Quién la cambia |
| :--- | :--- | :--- | :--- |
| Etapa | `etapa` (`SOLICITUD` \| `LEGALIZACION`) | Nueva (Apps Script + AppSheet) | Sistema, por la acción *habilitar legalización* (dueño) |
| Operativa | `estado` | AppSheet `Estado` | Sistema (inicial) · **ADMIN** / SUPERADMIN. Rige en **ambas** etapas |
| Financiera | `estado_financiero` | AppSheet `Estado_P` | Sistema (inicial) · **FINANCIERO** / SUPERADMIN |
| Espejo | — | `Estado legalizacion` = `[Estado]` | — |

### Estado operativo (ADMIN), válido en cada etapa

```
                 crear (el sistema asigna PENDIENTE)
  (inicio) ───────────────────────────────▶ PENDIENTE ⛔ ──── aprobar (A/S) ────▶ APROBADO
                                              │  ▲  ▲                               │
                        eliminar (dueño, si   │  │  └── devolver (A/S, comentario) ──┘
                        estado_financiero =   │  │      solo si estado_financiero ∉ {PAGADO, PROCESADO}
                        PENDIENTE)            │  │      y (en SOLICITUD) la legalización aún no se habilitó
                              ▼               │  └──── devolver (A/S, comentario): queda PENDIENTE y "Devuelta"
                        [eliminado]           │
                                              └──── rechazar (A/S, comentario) ────▶ RECHAZADO (final)
```

### Estado financiero (FINANCIERO)

```
  PENDIENTE ⌛ ──▶ TRANSFERIDO ──▶ PAGADO ──▶ PROCESADO
  (FINANCIERO elige el valor; recorrido habitual, S-03)
  RN-03: PAGADO y PROCESADO solo si etapa = LEGALIZACION, estado = APROBADO y todos los gastos con comprobante.
```

### Diagrama unificado: las dos modalidades (RN-28)

**Modalidad `CON_SOLICITUD`** (pedir viáticos antes del viaje y legalizar después, sobre el mismo `VT-xxxxxx`):

```
 ETAPA SOLICITUD                                                         ETAPA LEGALIZACIÓN
 ─────────────────────────────────────────────────────────────────────   ──────────────────────────────────────────
 estado:      PENDIENTE ──aprobar(A)──▶ APROBADO ─┐                       PENDIENTE ──aprobar(A)──▶ APROBADO ─┐
                  ▲  └─devolver(A)─┘   └─rechazar(A)▶ RECHAZADO(fin)       ▲  └─devolver(A)─┘  └─rechazar▶ RECHAZADO
                                                    │                                                           │
 est. financ.: PENDIENTE ─────────valor asignado y──▶ TRANSFERIDO ────────── (se conserva) ───────────▶ PAGADO ─▶ PROCESADO
                                  TRANSFERIDO (F)        │                                              (F; RN-03)
                                                         │
                          habilitar legalización (dueño) ┘
          Condición: estado = APROBADO  y, si requiere_gastos_viaje, estado_financiero = TRANSFERIDO
          Efecto:    etapa → LEGALIZACION · estado → PENDIENTE · estado_financiero y valor_asignado se conservan (S-12)
```

**Modalidad `LEGALIZACION_DIRECTA`** (gastos ya realizados o recursos propios; flujo de AppSheet):

```
 ETAPA LEGALIZACIÓN (inicio directo)
 ─────────────────────────────────────────────────────────────────────────
 estado:       PENDIENTE ──aprobar(A)──▶ APROBADO          (devolver ↺ / rechazar ▶ RECHAZADO)
 est. financ.: PENDIENTE ──[valor asignado (F), salvo recursos propios]──▶ TRANSFERIDO ──▶ PAGADO ──▶ PROCESADO
```

### Tabla de estados y responsables

| Paso | Modalidad | Etapa | `estado` | `estado_financiero` | Responsable | Acción / endpoint |
| :-- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `CON_SOLICITUD` | `SOLICITUD` | `PENDIENTE` | `PENDIENTE` | VIAJERO | `POST /viaticos` (trayectos, firma, presupuesto calculado) |
| 2 | `CON_SOLICITUD` | `SOLICITUD` | `APROBADO` / devuelve a `PENDIENTE` / `RECHAZADO` | `PENDIENTE` | ADMIN/SUPERADMIN (no el dueño, RN-27) | `aprobar` · `devolver` · `rechazar`; `gestionar-tiquetes` |
| 3 | `CON_SOLICITUD` | `SOLICITUD` | `APROBADO` | `TRANSFERIDO` | FINANCIERO/SUPERADMIN | `valor-asignado` y `estado-financiero` |
| 4 | `CON_SOLICITUD` | `SOLICITUD` → `LEGALIZACION` | `APROBADO` → **`PENDIENTE`** | `TRANSFERIDO` (se conserva) | VIAJERO (dueño) | `habilitar-legalizacion` |
| 5 | ambas | `LEGALIZACION` | `PENDIENTE` | `PENDIENTE` / `TRANSFERIDO` | VIAJERO | `POST /viaticos` (directa) o continúa; carga gastos con soporte |
| 6 | ambas | `LEGALIZACION` | `APROBADO` / devuelve / `RECHAZADO` | sin cambio | ADMIN/SUPERADMIN (no el dueño) | `aprobar` · `devolver` · `rechazar` |
| 7 | ambas | `LEGALIZACION` | `APROBADO` | `PAGADO` → `PROCESADO` | FINANCIERO/SUPERADMIN (no el dueño) | `estado-financiero`; evento `LIQUIDAR` (saldo `> 0` reintegro, `< 0` reembolso) |

- **Editable por el dueño:** la etapa vigente solo con `estado = PENDIENTE` (incluida una devolución). Al habilitar la legalización, la **solicitud queda congelada** (trayectos, presupuesto, firma).
- **Recursos propios:** solo en `LEGALIZACION_DIRECTA`; transferido = 0 y la empresa reembolsa (RN-14, RN-25).
- **Valor asignado:** lo registra solo FINANCIERO/SUPERADMIN; el `presupuesto_solicitado` es una referencia sugerida (RN-19).
- **Separación de funciones** (DP-18) y **sin autoaprobación en ninguna etapa** (RN-27): nadie aprueba, valida financieramente ni liquida su propio viático; solo SUPERADMIN, con auditoría.
- Cada transición genera un registro en `viatico_eventos` con su etapa (RN-10). Devolver y Rechazar exigen comentario.

---

## F-01 · Inicio de sesión (acceso dual, ADR-027)

**Actor:** cualquier usuario. **Precondición:** el usuario existe, está activo y tiene rol. **Dos caminos según el rol.**

### F-01a · VIAJERO, ADMIN, FINANCIERO: usuario y contraseña

1. La pantalla de login muestra los campos **Usuario** y **Contraseña**, el enlace **"Olvidé mi contraseña"** y, aparte, el botón **"Soy administrador de Trulab: ingresar con Google"**.
2. Escribe su usuario y su contraseña → `POST /auth/login`.
3. La API valida usuario existente, activo, con rol operativo y contraseña (Argon2id). Registra `LOGIN_EXITOSO`.
4. **Primer acceso o contraseña temporal** (`debe_cambiar_password = true`): la SPA lo lleva a **"Cambiar contraseña"** (F-01c) antes de cualquier otra pantalla; mientras no la cambie, la API rechaza el resto de endpoints.
5. La SPA carga `/me` y redirige a la vista inicial del rol: VIAJERO → Viáticos; ADMIN → Revisión; FINANCIERO → Pagos.
6. La sesión se renueva sola (refresh); vence a los 7 días sin uso.

**Alternos:**
- Usuario o contraseña incorrectos, usuario inactivo o inexistente: el **mismo** mensaje, "Usuario o contraseña incorrectos" (no revela cuál falló). Se audita `LOGIN_FALLIDO`.
- 5 fallos seguidos: "Cuenta bloqueada temporalmente. Intente en 15 minutos" (S-14).
- Un SUPERADMIN que escribe su usuario en este formulario recibe el mismo mensaje genérico; debe usar Google.
- **Cerrar sesión:** menú de perfil → "Cerrar sesión".

### F-01b · SUPERADMIN: Google `@trulab.co`

1. Pulsa **"Ingresar con Google"**; Google muestra el selector de cuenta.
2. Elige su cuenta corporativa `@trulab.co`; la SPA recibe el ID token y llama a `POST /auth/google`.
3. La API valida token, correo verificado, dominio `@trulab.co`, que el correo exista, esté activo y tenga **rol `SUPERADMIN`**.
4. La SPA carga `/me` y abre Viáticos (todos).

**Alternos:** cuenta de otro dominio ("Use su cuenta corporativa @trulab.co"); correo no registrado o inactivo ("Su cuenta no tiene acceso. Contacte al administrador"), ambos con `ACCESO_DENEGADO`; si el correo pertenece a un usuario operativo: "Use su usuario y contraseña" (`METODO_ACCESO_NO_PERMITIDO`).

### F-01c · Recuperar, restablecer y cambiar la contraseña (RN-15)

**Actor:** VIAJERO, ADMIN, FINANCIERO.

1. **Olvidé mi contraseña** → escribe su usuario o correo → `POST /auth/password/forgot`. La pantalla siempre dice: "Si la cuenta existe, enviaremos un enlace al correo registrado". Se audita `PASSWORD_RECUPERACION_SOLICITADA`.
2. Si el usuario existe, está activo y es operativo, recibe un correo (Amazon SES; en local, el correo aparece en el log del backend) con un enlace de **un solo uso** que vence en 15–30 min.
3. El enlace abre **"Nueva contraseña"** → `POST /auth/password/reset`. La política exige 12+ caracteres. Al guardar: se invalidan el token y todas las sesiones, y se pide iniciar sesión (`PASSWORD_CAMBIADA`).
4. **Cambio voluntario u obligatorio:** menú de perfil → "Cambiar contraseña" (contraseña actual + nueva) → `POST /auth/password/change`. Se cierran las demás sesiones.

**Alternos:** enlace vencido, usado o inválido: "El enlace no es válido o venció. Solicite uno nuevo" (mensaje único, `TOKEN_INVALIDO`). Si el correo del usuario es incorrecto, ADMIN lo corrige y usa "Restablecer contraseña" (F-02). SUPERADMIN no tiene esta opción: sus credenciales las gestiona Google Workspace.

---

## F-02 · Gestión de usuarios

**Actor:** ADMIN o SUPERADMIN (operativos); solo SUPERADMIN para otros SUPERADMIN.

1. Menú → **Usuarios**: tabla (escritorio) o tarjetas (móvil) con nombre, usuario, rol, cargo, célula, correo, tipo de vinculación y estado. Búsqueda por nombre/correo/usuario y filtros por rol, cargo, célula, vinculación o activo.
2. **Crear usuario operativo:** "+ Nuevo usuario" → nombre completo, **correo de contacto** (personal o corporativo), **usuario**, cédula, célula, cargo, rol (VIAJERO/ADMIN/FINANCIERO), **¿es prestador de servicios?** y fecha de nacimiento (opcional) → Guardar. El sistema genera una **contraseña temporal** y la envía **por correo** al usuario; ADMIN no la ve. El usuario deberá cambiarla en su primer acceso (S-13).
3. **Crear o promover un SUPERADMIN** (solo SUPERADMIN): "+ Nuevo superadministrador" (o "Promover a superadministrador" en un usuario existente) → exige correo **`@trulab.co`**. No lleva usuario ni contraseña: ingresará con Google. Confirmación: "Tendrá acceso total". Se audita `SUPERADMIN_ASIGNADO`. ADMIN no ve estas opciones.
4. **Editar:** clic en la fila → "Editar". Si cambia el **rol**, se avisa "El usuario deberá volver a iniciar sesión". Promover a SUPERADMIN elimina su usuario y contraseña; degradar a un SUPERADMIN pide un usuario y genera una contraseña temporal.
5. **Restablecer contraseña** (operativos): `⋯` → "Restablecer contraseña" → se envía una temporal nueva por correo y se cierran sus sesiones.
6. **Desactivar / Reactivar:** `⋯`. El usuario inactivo no puede ingresar por ningún método y su historial se conserva (RN-11).

**Alternos:** no puede desactivarse a sí mismo; **no se puede desactivar ni degradar al último SUPERADMIN activo** ("Debe existir al menos un superadministrador activo", `409`).

---

## F-03 · Gestión de cargos, catálogos y tarifas

**F-03a · Cargos.** **Actor:** ADMIN o SUPERADMIN (FINANCIERO solo consulta). Lista con folio `CA-`, crear, editar y eliminar (409 si tiene usuarios).

**F-03b · Catálogos (proyectos, rubros, células).** **Actor:** solo SUPERADMIN. Pestañas con nombre, estado y cantidad de usos; crear, renombrar (se audita), desactivar/activar (sin eliminar). En **Proyectos**, un apartado *Escritos con "Otro"* lista los nombres escritos a mano y cuántos registros los usan, para decidir cuáles crear en el catálogo. En **Proyectos**, además: *código* y la casilla **"Exige formato de prestador"** (RN-33).

**F-03c · Tarifas de viáticos.** **Actor:** solo SUPERADMIN (FINANCIERO y ADMIN consultan) (RF-018).

1. Menú → **Catálogos** → pestaña **Tarifas de viáticos**. La tabla muestra ciudad, tipo (**Empleado** / **Prestador**) y los 6 valores: alimentación/día, otros gastos/día, transporte aeropuerto, transporte intermunicipal, transporte interno (1 día) y transporte interno (varios días).
2. Filtros por ciudad, tipo y activo.
3. **Crear:** "+ Añadir tarifa" → ciudad, tipo y los 6 valores → Guardar. Una combinación ciudad + tipo repetida muestra "Ya existe".
4. **Editar:** cambia los valores; aparece "Las solicitudes ya creadas conservan las tarifas con las que se calcularon". Se audita (`TARIFA_EDITAR`).
5. **Desactivar / Activar:** deja de ofrecerse la ciudad al solicitar; no se elimina.

---

## F-04 · Crear un viático (elección de modalidad)

**Actor:** cualquier rol (normalmente VIAJERO), siempre sobre un viático propio.

1. **Viáticos** → FAB **"+"** / "+ Nuevo viático". Se pregunta: **"¿Qué desea hacer?"**
   - **Pedir viáticos y tiquetes antes del viaje** → `CON_SOLICITUD` (F-04a).
   - **Cargar facturas y soportes de un viaje ya realizado** (o con recursos propios) → `LEGALIZACION_DIRECTA` (F-04b).
2. Se muestran, en solo lectura, los datos del colaborador tomados de su usuario: nombre, cargo, cédula, célula y tipo de vinculación (RN-17).

### F-04a · Solicitud de viáticos y tiquetes (`CON_SOLICITUD`)

1. **Datos generales:** proyecto (lista de proyectos activos más la opción **"Otro"**, que abre el campo obligatorio *Nombre del proyecto*; ADR-031), líder de proyecto, empresa (opcional), motivo del viaje.
2. **Opciones:** ☐ *Requiere tiquete* · ☐ *Requiere gastos de viaje*. Si marca tiquete y no tiene fecha de nacimiento en su perfil, el formulario la pide y la guarda (RN-31). Sin gastos de viaje, se omite el presupuesto (S-09).
3. **Trayectos (1 a 5):** "+ Agregar trayecto" → ciudad de origen, ciudad de destino (no puede ser igual al origen salvo "Otro"), fecha y hora de ida y de regreso, ¿requiere hospedaje? y **días de estadía**, que se sugieren como `ceil(regreso − ida) + 1` y se pueden editar (RN-30).
4. **Presupuesto calculado:** al completar un trayecto, la pantalla llama a `calcular-presupuesto` y muestra el desglose (alimentación, transporte interno, otros gastos × días + transporte aeropuerto + intermunicipal) y el **total**. Los importes **no son editables**; si necesita más dinero, lo justifica en **Comentarios** con la autorización del líder de proyecto (RN-29).
5. **Prestador con proyecto que exige formato** (RN-33): no se muestra el cálculo; en su lugar aparece **"Adjuntar formato diligenciado (PDF o Excel)"**, obligatorio.
6. **Firma** (RN-32): dibuja o sube su firma, o usa la guardada en su perfil.
7. Guardar. Se crea el viático `VT-xxxxxx` en etapa **SOLICITUD**, `estado = PENDIENTE`, `estado_financiero = PENDIENTE`. Puede editarlo mientras siga `PENDIENTE`.
8. Desde el detalle puede **Descargar PDF de solicitud** (incluye la firma).

**Alternos:** si cierra antes de guardar, "¿Descartar cambios?". Si falta algo para aprobar (firma, formato, fecha de nacimiento), el detalle muestra la lista de pendientes.

### F-04b · Legalización directa (`LEGALIZACION_DIRECTA`)

1. Formulario: motivo del viaje y **¿Viajó con recursos propios?** (Sí/No). Ayuda: "Si pagó el viaje con su dinero, la empresa le reembolsará el total de los gastos" (DP-17).
2. Guardar: el viático nace en etapa **LEGALIZACIÓN**, `PENDIENTE`/`PENDIENTE`, con folio `VT-xxxxxx`.
3. Se abre el detalle con la sección "Gastos" vacía y el CTA para agregar el primero (F-05).
4. Valor transferido: con recursos propios, "Recursos propios: $0 (a reembolsar)"; si no, "Pendiente de registrar por Financiero".

---

## F-05 · Registrar un gasto

**Actor:** dueño, con el viático en **etapa LEGALIZACIÓN** y estado `PENDIENTE`. (En etapa SOLICITUD no hay gastos.)

1. En el detalle → **"+ Agregar gasto"** (Sheet inferior en móvil).
2. **Comprobante primero.** Debe haber **al menos uno** (DP-15): **Soporte (imagen)** — "Tomar foto" o "Elegir imagen", comprimida en el cliente — o **Archivo (PDF)**.
3. Datos: fecha de factura (no futura), **rubro**, **proyecto** (lista o "Otro" + nombre escrito), concepto, CC/NIT y empresa del proveedor, valor, observaciones.
4. Guardar: progreso de subida y toast "Gasto guardado".
5. El detalle recalcula el total gastado y el saldo. "Guardar y agregar otro" repite el flujo.

**Alternos:** sin soporte ni archivo se puede guardar, pero queda "Falta comprobante" y la legalización no puede aprobarse (RN-21); PDF como soporte o imagen como archivo: error en línea (RN-13); archivo > 10 MB o de tipo no permitido; fecha futura (RN-07); fallo de subida: "Reintentar" conservando los datos. Editar, reemplazar o eliminar desde `⋯`.

---

## F-06 · Revisión operativa: aprobar, devolver o rechazar

**Actor:** ADMIN (o SUPERADMIN). **Precondición:** viático **ajeno** (RN-27) con `estado = PENDIENTE` (o `APROBADO` para devolver), en cualquiera de las dos etapas.

1. Menú → **Revisión**: viáticos `PENDIENTE` de ambas etapas, con filtro por etapa; un indicador muestra el avance (solicitudes completas, gastos con comprobante).
2. El detalle depende de la etapa:
   - **Solicitud:** datos del colaborador, proyecto, líder, trayectos, **presupuesto calculado** (o formato adjunto del prestador), firma, tiquetes y comentarios. Checklist: ✅ trayectos válidos · ✅ presupuesto o formato · ✅ firma · ✅ fecha de nacimiento si hay tiquete.
   - **Legalización:** gastos con soportes en visor (URL temporal), checklist ✅ al menos un gasto · ✅ todos con comprobante, saldo en solo lectura e historial.
3. ADMIN revisa y decide:
   - **Aprobar** → confirmación → `APROBADO`; el dueño ya no edita esa etapa (RN-06). Deshabilitado, con el motivo, si el checklist no está completo.
   - **Devolver** → comentario obligatorio → sigue `PENDIENTE` y "Devuelta"; el viajero corrige. En `APROBADO` solo mientras no esté pagado/procesado (y, en solicitud, antes de habilitar la legalización) (RN-20).
   - **Rechazar** → comentario obligatorio → `RECHAZADO` (final).
4. **Gestionar tiquetes** (solicitud con `requiere_tiquete`): ADMIN registra la emisión con un comentario (S-10).
5. (Si DP-06 aplica) el viajero recibe un correo.

**Reglas:** ADMIN no ve los botones de valor asignado ni de estado financiero (RN-26). Nadie modifica los gastos ni la solicitud del viajero (DP-12). ADMIN no revisa los suyos (RN-27). **Alterno:** 409 si cambió por concurrencia; la UI muestra qué falta.

---

## F-07 · Gestión financiera: valor asignado

**Actor:** FINANCIERO (o SUPERADMIN). **Precondición:** viático **ajeno** no rechazado.

1. Menú → **Pagos**. Por defecto: solicitudes `APROBADO` por desembolsar y legalizaciones `APROBADO` con estado financiero `PENDIENTE`/`TRANSFERIDO`. Filtros por viajero, proyecto, etapa, modalidad, fechas, estado financiero y signo del saldo; resumen con totales a reembolsar y reintegrar.
2. En una **solicitud aprobada** → **"Registrar valor asignado"**: la pantalla muestra el **presupuesto solicitado como referencia** (o el formato adjunto si es prestador) → ingresa el monto (`Valor_T`) → Guardar. Queda el evento con el valor anterior y el nuevo.
3. Tras el desembolso (banca, fuera del sistema), cambia el estado financiero a **TRANSFERIDO** (F-08). Con eso el viajero puede habilitar la legalización (F-12).
4. En una **legalización directa** sin recursos propios puede registrar el valor asignado como anticipo mientras esté `PENDIENTE`.

**Reglas:** FINANCIERO no aprueba, devuelve ni rechaza (RN-26); no edita gastos ni solicitudes (DP-12); no registra el valor de su propio viático (RN-27).

---

## F-08 · Estado financiero y liquidación

**Actor:** FINANCIERO (o SUPERADMIN).

1. Hace la transferencia, el reembolso o recibe el reintegro fuera del sistema.
2. En el detalle → **"Cambiar estado financiero"** → `Transferido`, `Pagado` o `Procesado` + observación opcional (referencia de la transferencia).
3. **Pagado/Procesado** solo en etapa **LEGALIZACIÓN**, `APROBADO` y con todos los comprobantes (RN-03). La confirmación muestra: "VT-000123 · Ana Pérez · Saldo −$120.000 (a reembolsar). ¿Confirmar?". `saldo > 0` = el viajero reintegra; `saldo < 0` = la empresa reembolsa.
4. Se registran `estado_financiero_at`, el evento de cambio y el evento `LIQUIDAR` con el sentido del saldo. La fila sale del filtro por defecto de Pagos.

**Alternos:** si ADMIN la devolvió al mismo tiempo, 409 y se recarga. Con recursos propios, el saldo es −total gastado (RN-25).

---

## F-09 · Generar los PDF

**Actor:** el dueño (los suyos), o FINANCIERO, ADMIN y SUPERADMIN (todos).

- **PDF de solicitud** (`CON_SOLICITUD`, desde el detalle): encabezado corporativo, folio, datos del colaborador, proyecto, líder, trayectos, presupuesto con desglose (o referencia al formato adjunto), tiquetes, comentarios, **firma del solicitante** y estado. Requiere la firma (RN-32).
- **PDF de legalización** (etapa LEGALIZACIÓN): colaborador, motivo, tabla de gastos (rubro, proyecto, valor), totales, saldo, ambos estados, historial y miniaturas de los soportes de imagen.

1. Detalle → **"Descargar PDF de solicitud"** / **"Descargar PDF de legalización"** (secundarios; `⋯` en móvil).
2. El botón muestra "Generando…" y se descarga `VT-000123-solicitud.pdf` o `VT-000123-legalizacion.pdf`.

**Alternos:** "No se pudo generar el PDF. Reintentar" (con `request_id`).

---

## F-10 · Consultar indicadores

**Actor:** FINANCIERO, ADMIN o SUPERADMIN.

1. Menú → **Indicadores**. Filtros: **fecha inicio y fin** (el Segmentador), aplicados sobre la **fecha de factura** de los gastos (DP-16), por defecto el mes actual con atajos; proyecto opcional.
2. Se ven (opcional MVP) KPIs; **barras** del consumo por proyecto y **dona** de viáticos por estado operativo (S-07).
3. Clic en una barra o segmento abre la lista filtrada. "Ver como tabla" es la alternativa accesible.

**Alterno:** sin datos, "No hay gastos en este período" con botón para ampliar el rango.

---

## F-11 · Navegación general por rol

| Rol | Menú visible | Vista inicial |
| :--- | :--- | :--- |
| VIAJERO | Viáticos · Perfil (firma, fecha de nacimiento, contraseña) | Viáticos (propios) |
| ADMIN | Viáticos · Revisión · Pagos (lectura) · Indicadores · Cargos · Usuarios · Tarifas (lectura: referencia al auditar solicitudes) | Revisión (pendientes) |
| FINANCIERO | Viáticos · Pagos · Indicadores · Cargos (lectura) · Tarifas (lectura) | Pagos |
| SUPERADMIN | Todo lo anterior + Catálogos y Tarifas (edición) + Superadministradores (+ Auditoría, post-MVP) | Viáticos (todos) |

El menú se arma con los `permisos` de `/me` (matriz RBAC del backend): cada módulo exige su permiso (`frontend/src/components/layout/navegacion.ts`), así que esta tabla y la matriz deben coincidir. Decisión del 2026-11-13: ADMIN conserva `tarifas:leer`.

Los roles con acceso global tienen un selector "Míos / Todos". "Revisión" es la lista de viáticos con `estado = PENDIENTE` preaplicado, no un módulo aparte.

---

## F-12 · Habilitar la legalización (paso de SOLICITUD a LEGALIZACIÓN)

**Actor:** el dueño (VIAJERO), en un viático `CON_SOLICITUD`. **Precondición:** etapa `SOLICITUD`, `estado = APROBADO` y, si `requiere_gastos_viaje`, `estado_financiero = TRANSFERIDO` (RN-28).

1. En el detalle aparece el aviso "Su solicitud fue aprobada y el desembolso registrado. Cuando regrese del viaje, cargue sus facturas" y el botón **"Iniciar legalización"**.
2. Si aún no se cumple la condición, el botón está deshabilitado y explica qué falta ("Esperando desembolso de Financiero").
3. Al confirmar: el **mismo `VT-xxxxxx`** pasa a etapa **LEGALIZACIÓN**, el `estado` vuelve a `PENDIENTE` para auditar las facturas, y `estado_financiero` y `valor_asignado` se conservan. La solicitud queda congelada y su PDF sigue disponible.
4. Continúa con F-05 (gastos) y F-06 (revisión) como en cualquier legalización.

**Alternos:** si el viaje no se realizó, la solicitud puede quedarse sin legalizar (la cancelación formal es post-MVP, §16); un anticipo `TRANSFERIDO` sin legalizar se gestiona fuera del sistema (S-08).
