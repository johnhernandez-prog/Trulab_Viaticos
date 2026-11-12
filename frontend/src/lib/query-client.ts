import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api-client";

const MAX_REINTENTOS = 2;

/** Un error 4xx no mejora reintentando (permiso, validación, recurso ajeno o estado inválido). */
export function debeReintentar(intentos: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return intentos < MAX_REINTENTOS;
}

/** QueryClient de la app: el estado del servidor vive aquí, no en un store global. */
export function crearQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: debeReintentar,
        // En el celular, volver a la pestaña no debe disparar recargas en cascada.
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}
