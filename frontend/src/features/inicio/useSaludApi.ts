import { useQuery } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

/** Respuesta de `GET /api/v1/health` (tipo generado desde OpenAPI). */
export type Salud = components["schemas"]["Salud"];

export const claveSalud = ["salud"] as const;

/** `GET /health`. Un 503 trae el mismo esquema (`db: "error"`): se devuelve como dato, no como error. */
export async function obtenerSalud(signal?: AbortSignal): Promise<Salud> {
  try {
    return await api.get<Salud>("/health", { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 503 && error.cuerpo) {
      return error.cuerpo as Salud;
    }
    throw error;
  }
}

export function useSaludApi() {
  return useQuery({ queryKey: claveSalud, queryFn: ({ signal }) => obtenerSalud(signal) });
}
