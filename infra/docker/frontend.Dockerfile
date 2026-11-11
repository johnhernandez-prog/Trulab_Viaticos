# Imagen del frontend en desarrollo (Vite dev server, Node 20 LTS).
# Contexto de build: raíz del repositorio (ver infra/docker-compose.yml).

FROM node:20.18.0-bookworm-slim AS dev
WORKDIR /app
RUN chown node:node /app
USER node

# Contrato con S1-05: frontend/package.json y frontend/package-lock.json.
COPY --chown=node:node frontend/package.json frontend/package-lock.json ./
RUN npm ci

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# En producción el frontend se sirve como estáticos (docs/architecture.md §12); se define en F10.
