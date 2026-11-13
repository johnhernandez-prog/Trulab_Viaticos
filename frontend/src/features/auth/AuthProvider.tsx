/**
 * Sesión de la SPA (ADR-005, ADR-027).
 *
 * - Al montar intenta **recuperar la sesión en silencio** con la cookie de refresh: recargar la
 *   página no obliga a iniciar sesión de nuevo.
 * - El access token vive solo en memoria (`lib/sesion.ts`); se renueva **antes de vencer**
 *   (un minuto antes) y, como respaldo, `apiClient` lo renueva tras un 401.
 * - Si la API rechaza la sesión y el refresh falla, vuelve a "anónimo" y limpia la caché de
 *   TanStack Query (no deben quedar datos de otro usuario en memoria).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, ApiError, ENCABEZADO_SPA, renovarSesion, type SesionApi } from "@/lib/api-client";
import { alPerderSesion, guardarAccessToken } from "@/lib/sesion";

import { ContextoAuth, type AuthContexto, type EstadoAuth } from "./contexto";

/** Margen para renovar antes de que venza el access token (15 min en la API). */
const MARGEN_RENOVACION_MS = 60_000;
const MINIMO_RENOVACION_MS = 5_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [auth, setAuth] = useState<EstadoAuth>({ estado: "cargando" });
  const [expiraEnMs, setExpiraEnMs] = useState<number | null>(null);
  const montado = useRef(true);

  const aplicarSesion = useCallback((sesion: SesionApi) => {
    guardarAccessToken(sesion.access_token);
    setExpiraEnMs(sesion.expires_in * 1000);
    setAuth({ estado: "autenticado", usuario: sesion.usuario });
    return sesion.usuario;
  }, []);

  const terminar = useCallback(
    (motivo?: "sesion_perdida" | "sin_conexion") => {
      guardarAccessToken(null);
      setExpiraEnMs(null);
      queryClient.clear();
      setAuth(motivo ? { estado: "anonimo", motivo } : { estado: "anonimo" });
    },
    [queryClient],
  );

  // Recuperación silenciosa al cargar la SPA.
  useEffect(() => {
    montado.current = true;
    renovarSesion()
      .then((sesion) => {
        if (montado.current) aplicarSesion(sesion);
      })
      .catch((error: unknown) => {
        if (!montado.current) return;
        const sinConexion = error instanceof ApiError && error.status === 0;
        terminar(sinConexion ? "sin_conexion" : undefined);
      });
    return () => {
      montado.current = false;
    };
  }, [aplicarSesion, terminar]);

  // La API rechazó la sesión y el refresh falló (revocada, vencida o usuario desactivado).
  useEffect(() => alPerderSesion(() => terminar("sesion_perdida")), [terminar]);

  // Renovación proactiva antes de que venza el access token.
  useEffect(() => {
    if (expiraEnMs === null) return;
    const espera = Math.max(expiraEnMs - MARGEN_RENOVACION_MS, MINIMO_RENOVACION_MS);
    const temporizador = window.setTimeout(() => {
      renovarSesion()
        .then(aplicarSesion)
        .catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 401) terminar("sesion_perdida");
        });
    }, espera);
    return () => window.clearTimeout(temporizador);
  }, [expiraEnMs, aplicarSesion, terminar]);

  const valor = useMemo<AuthContexto>(
    () => ({
      auth,
      iniciarSesion: async (username, password) =>
        aplicarSesion(await api.post<SesionApi>("/auth/login", { username, password })),
      iniciarSesionGoogle: async (idToken) =>
        aplicarSesion(await api.post<SesionApi>("/auth/google", { id_token: idToken })),
      iniciarSesionDesarrollo: async (correo) =>
        aplicarSesion(await api.post<SesionApi>("/auth/dev/login", { correo })),
      cambiarPassword: async (actual, nueva) =>
        aplicarSesion(
          await api.post<SesionApi>("/auth/password/change", {
            password_actual: actual,
            nueva_password: nueva,
          }),
        ),
      cerrarSesion: async () => {
        try {
          await api.post("/auth/logout", undefined, { headers: ENCABEZADO_SPA });
        } catch {
          // Aunque la API no responda, la sesión local se cierra (el refresh expira solo).
        }
        terminar();
      },
    }),
    [auth, aplicarSesion, terminar],
  );

  return <ContextoAuth.Provider value={valor}>{children}</ContextoAuth.Provider>;
}
