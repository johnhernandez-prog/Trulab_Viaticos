# frontend/

SPA React 18 + Vite + TypeScript de Trulab Viajes, mobile-first (`docs/design-system.md`).

Estructura prevista (`docs/architecture.md` §2):

```
frontend/src/
├── app/           # router, providers, layout raíz
├── components/    # ui/ (shadcn) y layout/
├── features/      # un módulo por dominio
├── lib/           # apiClient, formatos, errores
└── types/         # tipos generados desde OpenAPI (no se escriben a mano)
```

El esqueleto se crea en **S1-05**.
