/**
 * Configuración del frontend leída de `import.meta.env` en un solo lugar.
 * El resto del código importa `env` y no lee `import.meta.env` directamente.
 */
const API_BASE_URL_POR_DEFECTO = "/api/v1";

function sinBarraFinal(valor: string): string {
  return valor.replace(/\/+$/, "");
}

export const env = {
  apiBaseUrl: sinBarraFinal(import.meta.env.VITE_API_BASE_URL?.trim() || API_BASE_URL_POR_DEFECTO),
  googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() ?? "",
} as const;
