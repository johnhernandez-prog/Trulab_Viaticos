# scripts/etl_appsheet/

ETL de migración desde AppSheet (RF-012). Se implementa en **S3-06**; las reglas de mapeo están en `docs/database-design.md` §1.2 y §12.

- `input/`: exportaciones CSV y soportes de AppSheet (tarea P-2).
- `output/`: informes de conciliación.

Ambas carpetas están en `.gitignore`: contienen datos personales (RNF-09) y **nunca** se versionan.
