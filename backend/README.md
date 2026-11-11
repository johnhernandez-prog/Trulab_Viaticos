# backend/

API FastAPI (Python 3.12) de Trulab Viajes. Se ejecuta siempre en Docker (ADR-016).

Estructura prevista (`docs/architecture.md` §3):

```
backend/
├── app/
│   ├── core/          # config, db, security, permissions, errors, storage, audit
│   ├── modules/       # un paquete por dominio: router → service → models
│   └── templates/pdf/
├── alembic/           # migraciones (únicas responsables del esquema)
└── tests/
```

El esqueleto se crea en **S1-03** y Alembic en **S1-04**.
