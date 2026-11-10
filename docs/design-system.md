# Sistema de diseño — Trulab Viajes

> Enfoque **mobile-first** con Tailwind CSS y shadcn/ui (Radix).
> Los colores de marca son **provisionales** hasta recibir la paleta y el logo corporativos (DP-08). Solo cambian los valores de los tokens; los nombres se mantienen.

---

## 1. Principios

1. **El celular primero:** el viajero registra gastos de pie, en campo y con una mano. Usa botones grandes, una columna y la cámara a un toque.
2. **El dinero se lee de inmediato:** las cifras van alineadas a la derecha, en tipografía tabular y con el signo y el color del saldo evidentes.
3. **El estado siempre visible:** cada legalización muestra su estado con color **y** texto (nunca solo color).
4. **Densidad según el rol:** el viajero ve tarjetas amplias y financiero ve tablas densas en escritorio.
5. **Accesible por defecto:** WCAG 2.1 AA, operable con teclado, contraste mínimo de 4,5:1 en texto.

## 2. Tokens de color

Se definen como variables CSS (formato shadcn, HSL) en `:root` y se consumen desde Tailwind (`bg-primary`, `text-muted-foreground`…). Nunca se usan colores hexadecimales sueltos en los componentes.

| Token | Uso | Valor provisional |
| :--- | :--- | :--- |
| `--primary` | Acciones principales, enlaces, navegación activa | Azul `#1D4ED8` (blue-700) |
| `--primary-foreground` | Texto sobre primary | `#FFFFFF` |
| `--secondary` | Botones secundarios, fondos de chips | `#F1F5F9` (slate-100) |
| `--background` | Fondo de página | `#F8FAFC` (slate-50) |
| `--card` | Superficie de tarjetas y tablas | `#FFFFFF` |
| `--foreground` | Texto principal | `#0F172A` (slate-900) |
| `--muted-foreground` | Texto secundario, etiquetas | `#475569` (slate-600) |
| `--border` / `--input` | Bordes | `#E2E8F0` (slate-200) / `#CBD5E1` (slate-300) |
| `--ring` | Foco visible | `#2563EB` (blue-600) |
| `--success` | Éxito, estado Pagada | `#15803D` (green-700) |
| `--warning` | Advertencias, estado Devuelta | `#B45309` (amber-700) |
| `--destructive` | Errores, eliminar, **saldo negativo** | `#B91C1C` (red-700) |
| `--info` | Información, estado Legalizada | `#0369A1` (sky-700) |

Cada color semántico tiene una variante `-subtle` (fondo claro, por ejemplo `#FEF2F2` para destructive) para insignias y alertas.

### Colores de estado de legalización

| Estado | Insignia (fondo / texto) | Icono Lucide | Etiqueta |
| :--- | :--- | :--- | :--- |
| `BORRADOR` | slate-100 / slate-700 | `FilePen` | Borrador |
| `LEGALIZADA` | sky-50 / sky-700 | `Send` | En revisión |
| `DEVUELTA` | amber-50 / amber-700 | `Undo2` | Devuelta |
| `PAGADA` | green-50 / green-700 | `CircleCheck` | Pagada |

### Saldo

| Condición | Presentación |
| :--- | :--- |
| `saldo < 0` (la empresa reembolsa) | `text-destructive`, con signo `−` y la etiqueta "A reembolsar" |
| `saldo > 0` (el viajero reintegra) | `text-warning`, con la etiqueta "A reintegrar" |
| `saldo = 0` | `text-muted-foreground`, con la etiqueta "Cuadrado" |

(Semántica pendiente de confirmar en DP-10.)

**Modo oscuro:** fuera del MVP. Los tokens lo permiten sin tocar componentes.

## 3. Tipografía

- **Familia:** `Inter` (variable), con respaldo `system-ui, -apple-system, Segoe UI, Roboto, sans-serif`.
- **Cifras:** `font-variant-numeric: tabular-nums` (clase `tabular-nums`) en tablas, montos y fechas.

| Rol | Clase Tailwind | Tamaño / línea | Peso |
| :--- | :--- | :--- | :--- |
| Título de página | `text-2xl` (móvil `text-xl`) | 24/32 (20/28) | 600 |
| Título de sección / card | `text-lg` | 18/28 | 600 |
| Cuerpo | `text-base` | 16/24 | 400 |
| Tabla densa (desktop) | `text-sm` | 14/20 | 400 |
| Etiqueta / ayuda | `text-sm` | 14/20 | 500 / 400 |
| Micro (metadatos) | `text-xs` | 12/16 | 400 |
| Monto destacado | `text-2xl tabular-nums` | 24/32 | 700 |

En inputs, **el mínimo es 16 px en móvil** para evitar el zoom automático de iOS.

## 4. Espaciado, radios y sombras

- **Escala base de 4 px** (la de Tailwind). En la práctica se usan `1, 2, 3, 4, 6, 8, 12` (4–48 px).
- Margen de página: `px-4` en móvil, `px-6` en tablet y `px-8` en escritorio.
- Separación entre secciones: `space-y-6`. Dentro de formularios: `space-y-4`.
- Radios: `--radius: 0.5rem` (8 px) en tarjetas e inputs; botones de 6 px; insignias con `rounded-full`.
- Sombras: `shadow-sm` en tarjetas y `shadow-lg` en modales y menús. Nada más.
- **Área táctil mínima: 44×44 px** en todos los elementos interactivos en móvil.

## 5. Botones

| Variante | Uso | Ejemplo |
| :--- | :--- | :--- |
| `default` (primary) | Una acción principal por vista | "Legalizar", "Guardar gasto" |
| `secondary` | Acciones alternativas | "Cancelar", "Descargar PDF" |
| `outline` | Acciones terciarias en barras | Filtros |
| `ghost` | Acciones en filas e iconos | Editar en una tabla |
| `destructive` | Acciones irreversibles; **siempre con confirmación** | "Eliminar" |
| `success` (custom) | Liquidación | "Marcar como pagada" |

- Tamaños: `sm` (32 px, solo escritorio), `default` (40 px) y `lg` (48 px, CTA en móvil).
- **Botón primario en móvil:** ocupa el ancho completo y va fijo al pie del formulario, por encima de la BottomBar.
- **FAB en móvil** para "+ Nueva legalización" y "+ Agregar gasto": 56 px, abajo a la derecha.
- Estado de carga: spinner más el texto "Guardando…", y el botón deshabilitado para evitar el doble envío.
- Los botones de solo icono llevan `aria-label` obligatorio.

## 6. Inputs y formularios

- La etiqueta va siempre visible encima del campo (no se usa el placeholder como etiqueta).
- El texto de ayuda va debajo, en `text-muted-foreground`. El error va debajo, en `text-destructive`, con icono y `aria-describedby`.
- **Monto:** `inputmode="decimal"`, prefijo `$`, formato de miles al salir del campo (`1.500.000`). Internamente se maneja como string decimal.
- **Fecha:** el selector nativo en móvil (`type="date"`); en escritorio, el date picker de shadcn. El formato visible es `DD/MM/AAAA`.
- **Soporte:** zona de carga con dos acciones, "Tomar foto" (`capture="environment"`) y "Elegir archivo". Hay vista previa en miniatura, se muestran el nombre y el tamaño, y una barra de progreso.
- **Selects** con búsqueda (Combobox) para usuario, proyecto y cargo cuando hay más de 10 opciones.
- La validación se hace con Zod en el cliente (las mismas reglas que Pydantic). El error del servidor (`errors[]`) se mapea al campo correspondiente.
- Una columna en móvil; dos columnas desde `md` en formularios de administración.

## 7. Tablas

- Solo en tablet y escritorio. **En móvil, toda tabla se convierte en lista de tarjetas.**
- Encabezado fijo (`sticky top-0`). Filas de 48 px (densa: 40 px en Pagos).
- Columnas numéricas alineadas a la derecha y con `tabular-nums`. Fechas en `DD/MM/AAAA`.
- Orden por columna con indicador; filtros en una barra superior; paginación al pie con "1–20 de 134".
- Acciones por fila en un menú `⋯` (DropdownMenu). La acción primaria puede ir visible.
- **Tabla de Pagos:** columnas Folio, Viajero, Motivo, Fechas, Transferido, Gastado, **Saldo** (coloreado) y Estado. Al pie, una fila de totales.
- Estado vacío: ilustración simple o icono, mensaje y CTA ("Aún no tienes legalizaciones. Crear la primera").

## 8. Cards

- **Tarjeta de legalización (móvil):** a la izquierda la insignia de estado y el folio; a la derecha el monto total. Debajo, el motivo en una o dos líneas, el viajero (si el rol ve todas), el rango de fechas y el saldo. Toda la tarjeta es pulsable y lleva al detalle.
- **Tarjeta de gasto:** miniatura del soporte (o icono de "sin soporte" en `warning`), descripción, fecha y valor.
- **Tarjeta KPI** (dashboard): etiqueta, valor grande y variación opcional.
- Padding `p-4`, `rounded-lg`, `border`, `shadow-sm`.

## 9. Modales y diálogos

- `Dialog` en escritorio y `Sheet` (panel inferior) en móvil para formularios cortos (agregar gasto, devolver con comentario).
- `AlertDialog` para confirmar acciones destructivas o de estado: "¿Marcar LG-000123 como pagada? Saldo: −$120.000 a reembolsar".
- Al abrir, el foco va al primer campo; `Esc` cierra; el foco vuelve al disparador al cerrar.
- No se usan modales anidados.

## 10. Alertas y feedback

| Tipo | Componente | Uso |
| :--- | :--- | :--- |
| Toast | `sonner` | Confirmaciones breves ("Gasto guardado"), 4 s, en la parte inferior del móvil y arriba a la derecha en escritorio |
| Alerta en línea | `Alert` | Mensajes persistentes de contexto: "Esta legalización fue devuelta: <comentario>" |
| Banner | `Alert` a todo el ancho | Problemas del sistema o sin conexión |
| Error de campo | Texto bajo el input | Validación |

Los errores de la API se muestran con un mensaje en lenguaje claro según `code` (`docs/api-design.md` §7), nunca con el texto técnico.

## 11. Estados de interfaz

Todo componente que consume datos implementa estos cinco estados:

1. **Cargando:** *skeletons* con la forma del contenido (no spinners de página completa).
2. **Vacío:** mensaje más CTA.
3. **Error:** mensaje y botón "Reintentar".
4. **Éxito o datos:** el contenido.
5. **Deshabilitado o solo lectura:** cuando el estado de la legalización no permite editar, se muestra el motivo ("Enviada a revisión el 06/11/2026").

Los estados interactivos (hover, focus-visible, active, disabled) usan un anillo de foco de 2 px `ring` con *offset*, y nunca se quita el *outline* sin un reemplazo.

## 12. Layouts

Puntos de quiebre de Tailwind: `sm` 640, `md` 768, `lg` 1024, `xl` 1280.

### Móvil (< 640 px), base

```
┌──────────────────────────┐
│ ☰ Trulab Viajes    (👤)  │  ← header de 56 px: título de la vista y menú de perfil
├──────────────────────────┤
│ [Filtro de estado ▾]     │
│ ┌──────────────────────┐ │
│ │ ● En revisión LG-0123│ │  ← tarjetas apiladas
│ │ Taller de campo      │ │
│ │ 02–05/11  $1.620.000 │ │
│ └──────────────────────┘ │
│                   (＋)   │  ← FAB
├──────────────────────────┤
│ 📄   💳   📊   ⋯         │  ← BottomBar de 64 px (máx. 4 + "Más")
└──────────────────────────┘
```

- La BottomBar muestra solo los módulos del rol. VIAJERO: Legalizaciones y Perfil. FINANCIERO: Legalizaciones, Pagos, Indicadores y Más (Cargos). ADMIN y SUPERADMIN: Legalizaciones, Pagos, Indicadores y Más (Cargos, Usuarios).
- Hay que respetar `env(safe-area-inset-bottom)`.

### Tablet (640–1023 px)

- Sidebar **plegable** (solo iconos, 72 px; se expande a 240 px como overlay).
- Las listas se muestran en grilla de 2 columnas de tarjetas, o tabla simplificada desde `md`.
- El dashboard va en rejilla de 1×2.
- Los formularios tienen ancho máximo de 640 px, centrados.

### Escritorio (≥ 1024 px)

```
┌────────────┬──────────────────────────────────────────────┐
│ TRULAB     │  Pagos                         [Exportar] ⋯ │
│            │  [Estado ▾][Proyecto ▾][Fechas][Buscar…]    │
│ 📄 Legal.  │ ┌──────────────────────────────────────────┐│
│ 💳 Pagos   │ │Folio │Viajero│…│Transf.│Gastado│ Saldo   ││
│ 📊 Indic.  │ │LG-123│Ana P. │…│1.500k │1.620k │ −120k 🔴││
│ 💼 Cargos  │ │…                                         ││
│ 👥 Usuarios│ └──────────────────────────────────────────┘│
│            │  1–20 de 134                     ‹ 1 2 3 ›   │
│ (👤 Perfil)│                                              │
└────────────┴──────────────────────────────────────────────┘
   240 px fijo                contenido con máx. 1440 px
```

- Sidebar fija de 240 px.
- Las tablas densas tienen paginación y filtros por columna.
- El detalle de legalización usa dos columnas: datos y gastos a la izquierda (2/3) y resumen de saldo, acciones e historial a la derecha (1/3, fijo).
- El dashboard es una rejilla de KPIs (4 columnas) con gráficos de 2 columnas.

## 13. Gráficos (Recharts)

- **Barras horizontales** para el consumo por proyecto (los nombres largos se leen mejor), ordenadas de mayor a menor, con el valor en la etiqueta.
- **Dona** de estados con los mismos colores de estado del §2 y la leyenda con conteo y porcentaje. El total va al centro.
- Tooltips con formato COP. Cada gráfico ofrece una tabla alternativa accesible (botón "Ver como tabla").

## 14. Formatos

| Dato | Formato | Implementación |
| :--- | :--- | :--- |
| Moneda | `$ 1.500.000` (sin decimales en la vista; con 2 en el PDF si existen) | `Intl.NumberFormat('es-CO', {style:'currency', currency:'COP'})` |
| Fecha | `05/11/2026` | `Intl.DateTimeFormat('es-CO')` |
| Fecha y hora | `05/11/2026 14:30` (America/Bogota) | |
| Rango | `02–05 nov 2026` en tarjetas | |
| Folio | `LG-000123` en fuente mono, `text-xs` | |

Toda la interfaz está en español de Colombia.

## 15. Iconografía

Se usa Lucide a 20 px en la navegación y 16 px en línea, con `stroke-width` de 2. Módulos: Legalizaciones `FileText`, Pagos `CreditCard`, Cargos `Briefcase`, Usuarios `Users`, Indicadores `ChartPie` (equivalentes a los emojis del menú AppSheet).
