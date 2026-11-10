# Flujos de usuario — Trulab Viajes

> Cada flujo indica el actor, la precondición, los pasos, las reglas aplicadas y los caminos alternos.
> Referencias: reglas RN-xx en `SPEC.md` §8; endpoints en `docs/api-design.md`.

## Máquina de estados de la legalización

```
            crear                 legalizar (dueño)              pagar (F/A/S)
 (inicio) ────────▶ BORRADOR ─────────────────────▶ LEGALIZADA ─────────────────▶ PAGADA (final)
                       │                              │   ▲
          eliminar     │                    devolver  │   │ legalizar (dueño)
          (dueño)      ▼                    (F/A/S,   ▼   │
                   [eliminada]              comentario) DEVUELTA
```

- **Editable por el dueño:** `BORRADOR` y `DEVUELTA`.
- **Editable por F/A/S:** `valor_transferido` en `BORRADOR`, `LEGALIZADA` y `DEVUELTA` (DP-04).
- Cada flecha genera un registro en `legalizacion_eventos` (RN-10).

---

## F-01 · Inicio de sesión

**Actor:** cualquier usuario. **Precondición:** el usuario existe y está activo (lo creó ADMIN).

1. El usuario abre la app y ve la pantalla de login con el logo y el botón **"Ingresar con Google"**.
2. Pulsa el botón; Google muestra el selector de cuenta.
3. Elige su cuenta `@trulab.co` y la SPA recibe el ID token.
4. La SPA envía el token a `POST /auth/google`.
5. La API valida el token, el dominio y que el usuario esté activo, y emite la sesión.
6. La SPA carga `/me` y redirige a la **vista inicial del rol**: VIAJERO → Legalizaciones; FINANCIERO → Pagos; ADMIN y SUPERADMIN → Legalizaciones.
7. La sesión se renueva sola (refresh) mientras el usuario usa la app; vence a los 7 días sin uso.

**Alternos:**
- Cuenta de otro dominio: "Use su cuenta corporativa @trulab.co".
- Correo no registrado o inactivo: "Su cuenta no tiene acceso. Contacte al administrador."
- Si existe login con contraseña (DP-01): formulario de correo y contraseña. Tras 5 intentos fallidos por minuto, aparece "Demasiados intentos".
- **Cerrar sesión:** menú de perfil → "Cerrar sesión" → vuelve al login.

---

## F-02 · Gestión de usuarios

**Actor:** ADMIN o SUPERADMIN.

1. Menú → **Usuarios**. Se ve la tabla (escritorio) o las tarjetas (móvil) con nombre, rol, cargo, correo y estado.
2. Puede buscar por nombre o correo y filtrar por rol, cargo o activo.
3. **Crear:** botón "+ Nuevo usuario" → formulario con nombre completo, correo corporativo, rol y cargo → Guardar.
   - Validación: correo único y del dominio (RN-12). Un ADMIN no ve la opción `SUPERADMIN`.
4. **Editar:** clic en la fila → detalle → "Editar" → cambiar los campos → Guardar.
   - Si cambia el **rol**, aparece la confirmación "El usuario deberá volver a iniciar sesión". Se audita.
5. **Desactivar:** menú `⋯` → "Desactivar" → confirmación. El usuario ya no puede ingresar y su historial se conserva (RN-11).
6. **Reactivar:** filtro "Inactivos" → `⋯` → "Activar".

**Alternos:** no puede desactivarse a sí mismo; no puede desactivar ni degradar al último SUPERADMIN.

---

## F-03 · Gestión de cargos

**Actor:** ADMIN o SUPERADMIN (FINANCIERO solo consulta).

1. Menú → **Cargos**. Se ve la lista con folio (`CA-000001`), nombre y cantidad de usuarios.
2. **Crear:** "+ Añadir" → nombre (y descripción opcional) → Guardar. El sistema asigna el folio (RN-04).
3. **Editar:** clic → editar el nombre o la descripción → Guardar.
4. **Eliminar:** `⋯` → "Eliminar" → confirmación.
   - Si tiene usuarios asignados, aparece "No se puede eliminar: 4 usuarios tienen este cargo" (409).

---

## F-04 · Crear una legalización

**Actor:** cualquier rol (normalmente VIAJERO), siempre sobre una legalización propia.

1. **Legalizaciones** → FAB **"+"** (móvil) o "+ Nueva legalización" (escritorio).
2. Formulario (una columna en móvil):
   - Motivo del viaje (obligatorio)
   - Proyecto o centro de costo (selector, DP-02)
   - Fecha de inicio y fecha de fin (RN-07: fin ≥ inicio)
   - Destino (opcional)
3. Guardar. Se crea en estado **BORRADOR** con folio `LG-xxxxxx`.
4. La app abre el **detalle** de la legalización con la sección "Gastos" vacía y un CTA para agregar el primer gasto.
5. El valor transferido se muestra como "Pendiente de registrar por Financiero" si es 0 (DP-04).

**Alternos:** si cierra antes de guardar, el formulario pregunta "¿Descartar cambios?". Puede editar los datos mientras esté en BORRADOR o DEVUELTA.

---

## F-05 · Registrar un gasto

**Actor:** dueño de la legalización, en estado BORRADOR o DEVUELTA.

1. En el detalle de la legalización → **"+ Agregar gasto"**. En móvil se abre un Sheet inferior.
2. **Soporte primero** (el orden favorece la captura en campo):
   - "Tomar foto" abre la cámara trasera; o
   - "Elegir archivo" (imagen o PDF).
   - Se muestra la miniatura. La imagen se comprime en el cliente.
3. Datos:
   - Descripción (por ejemplo "Taxi aeropuerto")
   - Valor ($)
   - Fecha del gasto (por defecto hoy, o la de inicio si hoy queda fuera del rango)
4. Guardar. Se ve una barra de progreso de subida y luego un toast "Gasto guardado".
5. El detalle se actualiza: el gasto aparece en la lista y el **total gastado** y el **saldo** se recalculan.
6. Para agregar otro, se repite el flujo (el Sheet ofrece "Guardar y agregar otro").

**Alternos:**
- Sin soporte: se permite guardar, pero el gasto queda marcado "Falta soporte" (en `warning`) y bloquea Legalizar (RN-06).
- Archivo de más de 10 MB o de tipo no permitido: error en línea (RN-13).
- Fecha fuera del rango del viaje: advertencia no bloqueante (RN-07).
- Sin conexión o subida fallida: "No se pudo subir. Reintentar". Los datos del formulario se conservan.
- **Editar o eliminar** un gasto: en la tarjeta, `⋯` → Editar / Reemplazar soporte / Eliminar (con confirmación).

---

## F-06 · Legalizar (enviar a revisión)

**Actor:** dueño. **Precondición:** BORRADOR o DEVUELTA.

1. En el detalle, el resumen muestra transferido, gastado y saldo, más un checklist:
   - ✅ Al menos un gasto
   - ✅ Todos los gastos con soporte
2. Botón **"Legalizar"** (primario, fijo al pie en móvil). Queda deshabilitado, con el motivo visible, si el checklist no está completo.
3. Confirmación: "Después de enviar no podrá editar. ¿Enviar LG-000123 a revisión?"
4. Confirmar. El estado pasa a **LEGALIZADA** ("En revisión") y queda un evento en el historial.
5. La vista pasa a solo lectura, con el aviso "Enviada a revisión el dd/mm/aaaa".
6. (Si DP-06 aplica) Financiero recibe un correo.

**Alternos:** si al enviar el servidor detecta que falta un soporte (por concurrencia), responde 409 y la UI muestra qué gastos fallan.

---

## F-07 · Revisión financiera

**Actor:** FINANCIERO o ADMIN.

1. Menú → **Pagos**. Por defecto aparecen las legalizaciones en **LEGALIZADA**, ordenadas por fecha.
2. Filtra por viajero, proyecto, fechas o signo del saldo. El resumen superior muestra los totales a reembolsar y a reintegrar.
3. Clic en una fila abre el **detalle**:
   - Datos del viaje y del viajero
   - Lista de gastos; cada soporte se abre en un visor (imagen ampliable o PDF) con URL temporal
   - Resumen: transferido, gastado y **saldo** (rojo si es negativo)
   - Historial de estados
4. Si falta o cambió el valor transferido, usa **"Editar valor transferido"** → ingresa el monto → Guardar. Se registra un evento con el valor anterior y el nuevo.
5. Decide:
   - **Correcto** → F-08 (Pagar)
   - **Con errores** → **"Devolver"** → comentario obligatorio ("El soporte del hotel es ilegible") → Confirmar. El estado pasa a **DEVUELTA**, y el viajero ve el comentario en una alerta en su detalle y corrige (vuelve a F-05 y F-06).

**Reglas:** financiero **no** edita los gastos del viajero (DP-12).

---

## F-08 · Pago (liquidación)

**Actor:** FINANCIERO o ADMIN. **Precondición:** LEGALIZADA y RN-03 cumplida.

1. Hace la transferencia o el reintegro fuera del sistema (banca).
2. En el detalle → **"Marcar como pagada"**.
3. Confirmación con el resumen: "LG-000123 · Ana Pérez · Saldo −$120.000 (a reembolsar). ¿Confirmar pago?" y un campo de observación opcional (por ejemplo, la referencia de la transferencia).
4. Confirmar. El estado pasa a **PAGADA** (final), se registran `pagada_at` y el evento, y la fila sale del filtro por defecto de Pagos.
5. Toast "Legalización pagada".

**Alternos:** si alguien la pagó o devolvió al mismo tiempo, el servidor responde 409 "La legalización ya cambió de estado" y la vista se recarga.

---

## F-09 · Generar el PDF

**Actor:** el dueño (las suyas), o FINANCIERO, ADMIN y SUPERADMIN (todas).

1. En el detalle de cualquier legalización → **"Descargar PDF"** (botón secundario, o `⋯` en móvil).
2. El botón muestra "Generando…".
3. Se descarga `LG-000123.pdf` con el encabezado corporativo, los datos del viaje, la tabla de gastos, los totales, el saldo, el historial de estados y las miniaturas de los soportes.
4. En móvil se abre con el visor del sistema y se puede compartir.

**Alternos:** si falla la generación, aparece "No se pudo generar el PDF. Reintentar" (con `request_id` en el log).

---

## F-10 · Consultar indicadores

**Actor:** FINANCIERO, ADMIN o SUPERADMIN.

1. Menú → **Indicadores**.
2. Filtros: rango de fechas (por defecto el mes actual, con atajos "Este mes", "Trimestre" y "Año") y proyecto (opcional).
3. Se ven:
   - (Opcional MVP) KPIs: total transferido, total gastado, por reembolsar, por reintegrar y pendientes de revisión.
   - **Barras:** consumo por proyecto, de mayor a menor.
   - **Dona:** cantidad de legalizaciones por estado.
4. Clic en una barra o segmento abre la lista de legalizaciones filtrada (Pagos o Legalizaciones con ese proyecto o estado).
5. "Ver como tabla" ofrece la versión accesible de cada gráfico.

**Alternos:** si no hay datos en el rango, aparece "No hay legalizaciones en este período" con un botón para ampliar el rango.

---

## F-11 · Navegación general por rol

| Rol | Menú visible | Vista inicial |
| :--- | :--- | :--- |
| VIAJERO | Legalizaciones · Perfil | Legalizaciones (propias) |
| FINANCIERO | Legalizaciones · Pagos · Indicadores · Cargos (lectura) | Pagos |
| ADMIN | Legalizaciones · Pagos · Indicadores · Cargos · Usuarios | Legalizaciones (todas) |
| SUPERADMIN | Todo lo anterior (+ Auditoría, post-MVP) | Legalizaciones (todas) |

Para roles con acceso global, **Legalizaciones** tiene un selector "Mías / Todas".
