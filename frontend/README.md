# frontend/

SPA de Trulab Viajes: React 18 + Vite 6 + TypeScript, Tailwind CSS 3 + shadcn/ui, React Router 7 y TanStack Query 5. Es *mobile-first* (`docs/design-system.md`) y corre en Docker con Node 24 LTS.

## Arquitectura

- **Organización por funcionalidad** (`docs/architecture.md` §2): cada dominio vive en `src/features/<dominio>/` con sus páginas, componentes y hooks de datos. `components/` solo tiene piezas sin dominio.
- **Estado del servidor en TanStack Query**, sin store global. `lib/query-client.ts` no reintenta los errores 4xx (permiso, validación, recurso ajeno o estado inválido) y reintenta hasta 2 veces los de red y 5xx.
- **Un solo cliente HTTP:** `lib/api-client.ts`. Envía JSON con `credentials: "include"` y convierte los `application/problem+json` (RFC 9457) en `ApiError` con `status`, `code` estable, `requestId` y `errors[]`. Sin conexión lanza `code = "SIN_CONEXION"` y `status = 0`. Envía `Authorization: Bearer` con el access token **en memoria** (`lib/sesion.ts`, nunca en `localStorage`) y, tras un 401 fuera de `/auth/*`, renueva **una vez** con `/auth/refresh` (un solo refresh compartido entre peticiones simultáneas, porque es rotativo) y repite la petición. Si el refresh también es rechazado, `notificarSesionPerdida()` devuelve al login; sin conexión no se da la sesión por perdida.
- **Misma origen:** la SPA llama a `/api/v1` en su propia origen. En desarrollo, Vite reenvía `/api` al backend (`vite.config.ts`, `API_PROXY_TARGET`), así que no hace falta CORS en local y la cookie de refresh es de primera parte. Si se usa una URL absoluta en `VITE_API_BASE_URL`, la API debe permitir esa origen por CORS (`CORS_ORIGINS`).
- **Tipos de la API generados** desde `/api/v1/openapi.json` con `openapi-typescript` en `src/types/api.ts` (se versiona, no se edita a mano). Ejemplo: `components["schemas"]["Salud"]`.
- **Diseño:** tokens de color como variables CSS en `src/index.css` (formato shadcn, HSL), consumidos por Tailwind (`bg-primary`, `text-muted-foreground`, `text-destructive`, `bg-success-subtle`...). Los valores son provisionales (DP-08); los nombres no cambian. Fuente Inter variable servida desde el propio bundle (`@fontsource-variable/inter`, sin CDN externa).
- **Primitivas shadcn/ui** copiadas en `src/components/ui/` (`components.json` configura el CLI). `Button` (44 px táctiles en móvil), `Skeleton`, `Input` (16 px en móvil, sin zoom de iOS), `Alert` (icono + texto) y `Campo` (etiqueta visible, ayuda, errores con `aria-describedby` y botón mostrar/ocultar en contraseñas).
- **Formularios:** React Hook Form + Zod (`features/auth/esquemas.ts`); los `errors[]` de la API se muestran en su campo (`lib/errores.ts::erroresDeCampo`) y los demás errores con un mensaje en lenguaje claro según `code` (`mensajeDeError`).

## Autenticación (S1-11, ADR-027)

- **`AuthProvider`** (`features/auth/AuthProvider.tsx`): al cargar intenta recuperar la sesión en silencio con la cookie de refresh; renueva el access token un minuto antes de que venza; al perder la sesión limpia la caché de TanStack Query. Hooks en `features/auth/contexto.ts`: `useAuth()`, `useUsuario()` y `usePermisos()` (`tiene(permiso)` con la lista `permisos` de `/me`).
- **Login dual** (`/login`): usuario y contraseña (operativos) y Google Identity Services para SUPERADMIN, que se carga solo si hay `VITE_GOOGLE_CLIENT_ID` (sin él, un aviso). En desarrollo (`import.meta.env.DEV`) aparece además "Acceso de desarrollo" contra `/auth/dev/login`; no entra en el build de producción. Cuando haya CSP, debe permitir `https://accounts.google.com/gsi/client`.
- **Contraseñas:** `/olvide-password` (siempre el mismo mensaje), `/restablecer-password?token=…` (quita el token de la URL al cargar) y `/cambiar-password` (obligatorio con contraseña temporal; también desde el perfil).
- **Guardas** (`features/auth/guardas.tsx`): `RequiereSesion` (sin sesión → `/login` recordando a dónde iba, solo rutas internas; con contraseña temporal → `/cambiar-password`), `SoloAnonimo`, `RequierePermiso` ("Sin acceso") y `VistaInicial` (VIAJERO y SUPERADMIN → Viáticos, ADMIN → Revisión, FINANCIERO → Pagos). Solo mejoran la experiencia: la API vuelve a autorizar.
- **AppShell** (`components/layout/`): BottomBar en móvil (hasta 4 destinos; si hay más, 3 y "Más"), Sidebar plegable en tablet (riel de 72 px que se expande a 240 px como overlay, Esc la cierra) y fija de 240 px en escritorio, con menú de perfil. El menú sale de `navegacion.ts`, donde cada módulo declara su permiso. Los módulos de las semanas siguientes muestran `ModuloPendientePage`.

## Estructura

```
frontend/
├── index.html               # lang es-CO, viewport-fit=cover (safe area)
├── vite.config.ts           # alias @ → src, proxy /api, polling en Docker, Vitest
├── tailwind.config.ts       # colores = tokens CSS; radios; Inter
├── components.json          # configuración de shadcn/ui
├── eslint.config.js         # ESLint 10 con reglas de tipos, hooks y Fast Refresh
└── src/
    ├── main.tsx             # punto de entrada
    ├── index.css            # Tailwind + tokens del design system
    ├── app/                 # App (providers), rutas.tsx, ErrorRuta, NoEncontrado, SinAcceso
    ├── components/
    │   ├── ui/              # primitivas (button, skeleton, input, alert, campo)
    │   └── layout/          # AppShell, BarraLateral, BarraInferior, MenuPerfil, navegacion
    ├── features/
    │   ├── auth/            # AuthProvider, guardas, login, contraseñas, Google, roles
    │   ├── perfil/          # Mi perfil
    │   └── modulos/         # ModuloPendientePage (marcador de los módulos por venir)
    ├── lib/                 # api-client, sesion, errores, query-client, env, utils (cn)
    ├── types/api.ts         # GENERADO desde OpenAPI (npm run gen:api)
    └── test/                # setup de Vitest y utilidades de prueba
```

**Rutas:** públicas `/olvide-password` y `/restablecer-password`; `/login` solo sin sesión; con sesión `/cambiar-password` y, dentro del `AppShell`, `/` (vista inicial del rol), un módulo por entrada de `navegacion.ts` (cada uno con su permiso), `/perfil` y `*`. Cada feature reemplaza su marcador en `src/app/rutas.tsx`.

**Pruebas:** `src/test/utils.tsx` trae `renderizarRuta()` (app completa con `AuthProvider` y router en memoria), `simularApi({"POST /auth/login": …})`, `usuarioDePrueba(rol)` con la matriz de permisos del backend, `SIN_SESION` y `conSesion(usuario)`. `src/test/setup.ts` omite el `signal` de `Request` (jsdom y undici no comparten `AbortSignal`) y borra el token entre pruebas.

**Variables de entorno** (solo `VITE_*` llegan al navegador, así que nunca se ponen secretos):

| Variable | Por defecto | Uso |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `/api/v1` | Base de la API |
| `VITE_GOOGLE_CLIENT_ID` | vacío | OAuth Client ID de Google (solo el login de SUPERADMIN). Vacío: el botón de Google muestra un aviso |
| `API_PROXY_TARGET` | `http://localhost:8000` (`http://api:8000` en Docker) | Destino del proxy de Vite; solo del lado del servidor |

Se leen en un solo lugar: `src/lib/env.ts`.

## Desarrollo (desde la raíz del repositorio)

```
docker compose up -d                          # db + migrate + api + frontend → http://localhost:5173
docker compose logs -f frontend
docker compose exec frontend npm run lint     # ESLint (sin advertencias permitidas)
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run format:check   # o `format` para corregir
docker compose exec frontend npm test         # Vitest + Testing Library (jsdom)
docker compose exec frontend npm run build    # tsc + build de producción en dist/
docker compose exec frontend npm run gen:api  # regenerar src/types/api.ts (API arriba)
```

- **Dependencias:** `docker compose exec frontend npm install <paquete>@<versión exacta>` actualiza a la vez `package.json`, `package-lock.json` y el volumen `node_modules` del contenedor. Después, `npm ci` también en el equipo y `docker compose build frontend`. Si otra persona cambió el lock, `docker compose run --rm frontend npm ci` actualiza el volumen.
- **Versiones exactas** (sin `^`). Las versiones mayores se eligieron por compatibilidad: React 18 (arquitectura), Vite 6 y Tailwind 3 (con soporte y compatibles con shadcn sobre React 18), ESLint 10 (la 9 ya no tiene soporte).
- **En el equipo (Windows), para el editor y pre-commit:** Node 24 y `npm ci` dentro de `frontend/`. Ese `node_modules` no lo ve el contenedor, que usa su propio volumen con binarios de Linux. Los hooks de pre-commit (Prettier, ESLint y `tsc`) usan el del equipo. npm 11 avisa que bloqueó el `postinstall` de esbuild; no hace falta, porque el binario llega como dependencia opcional.
- Sin Docker: `npm run dev` en `frontend/` sirve en `:5173` y reenvía `/api` a `http://localhost:8000`.
