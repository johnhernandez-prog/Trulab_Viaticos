/**
 * Access token **en memoria** (ADR-005): nunca en `localStorage` ni `sessionStorage`, así un XSS
 * no lo puede leer de un almacenamiento persistente. Al recargar la página se pierde y la sesión
 * se recupera con la cookie httpOnly de refresh (`/auth/refresh`).
 *
 * `alPerderSesion` avisa al `AuthProvider` cuando la API rechaza la sesión y el refresh también
 * falla (sesión revocada, vencida o usuario desactivado).
 */
let accessToken: string | null = null;
const oyentes = new Set<() => void>();

export function obtenerAccessToken(): string | null {
  return accessToken;
}

export function guardarAccessToken(token: string | null): void {
  accessToken = token;
}

export function alPerderSesion(oyente: () => void): () => void {
  oyentes.add(oyente);
  return () => {
    oyentes.delete(oyente);
  };
}

export function notificarSesionPerdida(): void {
  accessToken = null;
  for (const oyente of oyentes) oyente();
}
