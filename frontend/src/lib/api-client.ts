/**
 * Cliente HTTP de la API (`/api/v1`). Único punto por el que el frontend llama al backend.
 *
 * - Envía y recibe JSON; los errores llegan como RFC 9457 `application/problem+json` con `code`
 *   estable (docs/api-design.md §7) y se convierten en `ApiError`.
 * - `credentials: "include"`: la cookie httpOnly de refresh viajará con las peticiones (S1-08).
 * - S1-08 agrega aquí el encabezado `Authorization: Bearer` (token en memoria, nunca en
 *   localStorage) y el reintento único tras un 401 llamando a `/auth/refresh`.
 */
import { env } from "@/lib/env";

/** Error de un campo en una respuesta 422 (`errors[]`). */
export interface ErrorCampo {
  field: string;
  code: string;
  message: string;
}

/** Cuerpo `application/problem+json` de la API (docs/api-design.md §7). */
export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  code: string;
  detail?: string | null;
  request_id?: string | null;
  errors?: ErrorCampo[];
}

/** Código propio del cliente cuando no hubo respuesta del servidor. */
export const SIN_CONEXION = "SIN_CONEXION";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly errors: ErrorCampo[];
  /** Cuerpo de la respuesta tal como llegó (problem+json u otro JSON), si lo hubo. */
  readonly cuerpo: unknown;

  constructor(
    status: number,
    code: string,
    mensaje: string,
    opciones: Partial<ApiErrorExtra> = {},
  ) {
    super(mensaje);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = opciones.requestId ?? null;
    this.errors = opciones.errors ?? [];
    this.cuerpo = opciones.cuerpo;
  }
}

interface ApiErrorExtra {
  requestId: string | null;
  errors: ErrorCampo[];
  cuerpo: unknown;
}

export interface OpcionesPeticion extends Omit<RequestInit, "body"> {
  /** Cuerpo a enviar como JSON. */
  json?: unknown;
}

function esProblema(valor: unknown): valor is ProblemDetails {
  return (
    typeof valor === "object" &&
    valor !== null &&
    typeof (valor as ProblemDetails).code === "string" &&
    typeof (valor as ProblemDetails).title === "string"
  );
}

async function leerJson(respuesta: Response): Promise<unknown> {
  const tipo = respuesta.headers.get("content-type") ?? "";
  if (!tipo.includes("json")) return undefined;
  try {
    return await respuesta.json();
  } catch {
    return undefined;
  }
}

function errorDesdeRespuesta(respuesta: Response, cuerpo: unknown): ApiError {
  const requestId = respuesta.headers.get("x-request-id");
  if (esProblema(cuerpo)) {
    return new ApiError(respuesta.status, cuerpo.code, cuerpo.detail ?? cuerpo.title, {
      requestId: cuerpo.request_id ?? requestId,
      errors: cuerpo.errors ?? [],
      cuerpo,
    });
  }
  return new ApiError(respuesta.status, "ERROR_HTTP", `Error HTTP ${respuesta.status}`, {
    requestId,
    cuerpo,
  });
}

/**
 * Hace una petición a la API. `ruta` es relativa a la base (`/health`, `/legalizaciones`).
 * Devuelve el JSON de la respuesta (o `undefined` en un 204) y lanza `ApiError` si falla.
 */
export async function apiRequest<T>(ruta: string, opciones: OpcionesPeticion = {}): Promise<T> {
  const { json, headers, ...resto } = opciones;
  const encabezados = new Headers(headers);
  encabezados.set("Accept", "application/json, application/problem+json");
  if (json !== undefined) encabezados.set("Content-Type", "application/json");

  let respuesta: Response;
  try {
    respuesta = await fetch(`${env.apiBaseUrl}${ruta}`, {
      credentials: "include",
      ...resto,
      headers: encabezados,
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });
  } catch (causa) {
    if (causa instanceof DOMException && causa.name === "AbortError") throw causa;
    throw new ApiError(0, SIN_CONEXION, "No se pudo conectar con el servidor");
  }

  if (respuesta.status === 204) return undefined as T;
  const cuerpo = await leerJson(respuesta);
  if (!respuesta.ok) throw errorDesdeRespuesta(respuesta, cuerpo);
  return cuerpo as T;
}

export const api = {
  get: <T>(ruta: string, opciones?: OpcionesPeticion) =>
    apiRequest<T>(ruta, { ...opciones, method: "GET" }),
  post: <T>(ruta: string, json?: unknown, opciones?: OpcionesPeticion) =>
    apiRequest<T>(ruta, { ...opciones, method: "POST", json }),
  patch: <T>(ruta: string, json?: unknown, opciones?: OpcionesPeticion) =>
    apiRequest<T>(ruta, { ...opciones, method: "PATCH", json }),
  delete: <T>(ruta: string, opciones?: OpcionesPeticion) =>
    apiRequest<T>(ruta, { ...opciones, method: "DELETE" }),
};
