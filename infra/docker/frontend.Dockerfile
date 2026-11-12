# Imagen del frontend en desarrollo (Vite dev server).
# Contexto de build: raíz del repositorio (ver infra/docker-compose.yml).
# Node 24 LTS (S1-05): Node 20 llegó a fin de soporte en abril de 2026 y las herramientas actuales
# (ESLint 10, entre otras) exigen Node >= 20.19. Es la misma versión que el equipo de desarrollo.

FROM node:24.22.1-bookworm-slim AS dev
WORKDIR /app
RUN chown node:node /app
USER node

# Contrato con S1-05: frontend/package.json y frontend/package-lock.json.
COPY --chown=node:node frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# En producción el frontend se sirve como estáticos (docs/architecture.md §12); se define en F10.
