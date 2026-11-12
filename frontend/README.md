# frontend/

SPA de Trulab Viajes: React 18 + Vite 6 + TypeScript, Tailwind CSS 3 + shadcn/ui, React Router 7 y TanStack Query 5. Es *mobile-first* (`docs/design-system.md`) y corre en Docker con Node 24 LTS.

## Arquitectura

- **Organización por funcionalidad** (`docs/architecture.md` §2): cada dominio vive en `src/features/<dominio>/` con sus páginas, componentes y hooks de datos. `components/` solo tiene piezas sin dominio.
- **Estado del servidor en TanStack Query**, sin store global. `lib/query-client.ts` no reintenta los errores 4xx (permiso, validación, recurso ajeno o estado inválido) y reintenta hasta 2 veces los de red y 5xx.
- **Un solo cliente HTTP:** `lib/api-client.ts`. Envía JSON con `credentials: "include"` y convierte los `application/problem+json` (RFC 9457) en `ApiError` con `status`, `code` estable, `requestId` y `errors[]`. Sin conexión lanza `code = "SIN_CONEXION"` y `status = 0`. S1-08 agrega aquí el `Authorization: Bearer` (token en memoria) y el reintento tras un 401 con `/auth/refresh`.
- **Misma origen:** la SPA llama a `/api/v1` en su propia origen. En desarrollo, Vite reenvía `/api` al backend (`vite.config.ts`, `API_PROXY_TARGET`), así que no hace falta CORS en local y la cookie de refresh es de primera parte. Si se usa una URL absoluta en `VITE_API_BASE_URL`, la API debe permitir esa origen por CORS (`CORS_ORIGINS`).
- **Tipos de la API generados** desde `/api/v1/openapi.json` con `openapi-typescript` en `src/types/api.ts` (se versiona, no se edita a mano). Ejemplo: `components["schemas"]["Salud"]`.
- **Diseño:** tokens de color como variables CSS en `src/index.css` (formato shadcn, HSL), consumidos por Tailwind (`bg-primary`, `text-muted-foreground`, `text-destructive`, `bg-success-subtle`...). Los valores son provisionales (DP-08); los nombres no cambian. Fuente Inter variable servida desde el propio bundle (`@fontsource-variable/inter`, sin CDN externa).
- **Primitivas shadcn/ui** copiadas en `src/components/ui/` (`components.json` configura el CLI). Por ahora: `Button` (área táctil de 44 px en móvil) y `Skeleton`.

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
    ├── app/                 # App (providers), rutas.tsx, ErrorRuta, NoEncontradoPage
    ├── components/
    │   ├── ui/              # primitivas shadcn (button, skeleton)
    │   └── layout/          # AppShell (encabezado + contenido)
    ├── features/
    │   └── inicio/          # página principal TEMPORAL y tarjeta "Estado de la API"
    ├── lib/                 # api-client, query-client, env, utils (cn)
    ├── types/api.ts         # GENERADO desde OpenAPI (npm run gen:api)
    └── test/                # setup de Vitest y utilidades de prueba
```

**Rutas:** `/` (inicio temporal) y `*` (página no encontrada), dentro de `AppShell`. Cada feature agrega sus rutas en `src/app/rutas.tsx`. Las guardas de sesión y de rol, el login y el AppShell responsivo con menú por rol son de S1-08 y S1-11.

**Variables de entorno** (solo `VITE_*` llegan al navegador, así que nunca se ponen secretos):

| Variable | Por defecto | Uso |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `/api/v1` | Base de la API |
| `VITE_GOOGLE_CLIENT_ID` | vacío | OAuth Client ID (S1-08) |
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
