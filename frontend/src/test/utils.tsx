import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { rutas } from "@/app/rutas";
import { AuthProvider } from "@/features/auth/AuthProvider";
import type { Permiso, Rol, UsuarioActual } from "@/features/auth/contexto";

/** Renderiza la app en `ruta` con un QueryClient de prueba (sin reintentos ni caché compartida). */
export function renderizarRuta(ruta = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(rutas, { initialEntries: [ruta] });
  const resultado = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { ...resultado, router, queryClient };
}

/** Respuesta JSON para simular `fetch`. */
export function respuestaJson(
  cuerpo: unknown,
  status = 200,
  tipo = "application/json",
  encabezados: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": tipo, ...encabezados },
  });
}

/** Error RFC 9457 como lo responde la API. */
export function problema(status: number, code: string, errors?: unknown[]): Response {
  return respuestaJson(
    { title: code, status, code, detail: null, request_id: "req-test", errors },
    status,
    "application/problem+json",
  );
}

// Matriz RBAC del backend (app/core/permissions.py) para fabricar usuarios de prueba.
const PROPIOS: Permiso[] = [
  "viaticos:leer_propios",
  "viaticos:crear",
  "viaticos:calcular_presupuesto",
  "viaticos:habilitar_legalizacion",
  "gastos:gestionar_propios",
  "catalogos:leer",
];
const LECTURA_INTERNA: Permiso[] = [
  "viaticos:leer_todos",
  "comprobantes:leer_todos",
  "pagos:leer",
  "cargos:leer",
  "tarifas:leer",
  "indicadores:leer",
];
export const PERMISOS_POR_ROL: Record<Rol, Permiso[]> = {
  VIAJERO: PROPIOS,
  FINANCIERO: [
    ...PROPIOS,
    ...LECTURA_INTERNA,
    "viaticos:registrar_valor_asignado",
    "viaticos:cambiar_estado_financiero",
  ],
  ADMIN: [
    ...PROPIOS,
    ...LECTURA_INTERNA,
    "viaticos:aprobar",
    "viaticos:rechazar",
    "viaticos:devolver",
    "viaticos:gestionar_tiquetes",
    "cargos:gestionar",
    "usuarios:gestionar_operativos",
  ],
  SUPERADMIN: [
    ...PROPIOS,
    ...LECTURA_INTERNA,
    "viaticos:aprobar",
    "viaticos:rechazar",
    "viaticos:devolver",
    "viaticos:gestionar_tiquetes",
    "viaticos:registrar_valor_asignado",
    "viaticos:cambiar_estado_financiero",
    "cargos:gestionar",
    "usuarios:gestionar_operativos",
    "usuarios:gestionar_superadmin",
    "catalogos:gestionar",
    "tarifas:gestionar",
    "auditoria:leer",
  ],
};

export function usuarioDePrueba(rol: Rol = "VIAJERO", campos: Partial<UsuarioActual> = {}) {
  const usuario: UsuarioActual = {
    id: "00000000-0000-4000-8000-000000000001",
    nombre_completo: "Ana Pérez Gómez",
    correo: rol === "SUPERADMIN" ? "ana.perez@trulab.co" : "ana@example.com",
    username: rol === "SUPERADMIN" ? null : "ana.perez",
    rol,
    es_prestador_servicios: false,
    debe_cambiar_password: false,
    cargo: { id: "00000000-0000-4000-8000-0000000000c1", nombre: "Profesional de campo" },
    celula: null,
    permisos: PERMISOS_POR_ROL[rol],
    ...campos,
  };
  if (usuario.debe_cambiar_password && !("permisos" in campos)) usuario.permisos = [];
  return usuario;
}

export function sesionDePrueba(usuario: UsuarioActual, token = "token-de-prueba") {
  return {
    access_token: token,
    token_type: "Bearer",
    expires_in: 900,
    debe_cambiar_password: usuario.debe_cambiar_password,
    usuario,
  };
}

type Manejador = (init: RequestInit, url: URL) => Response | Promise<Response>;

/**
 * Simula la API con un manejador por `"MÉTODO /ruta"` (sin `/api/v1`). Una ruta no simulada
 * responde 404. Devuelve el mock de `fetch` y las peticiones hechas, para afirmar sobre ellas.
 */
export function simularApi(manejadores: Record<string, Manejador | Response>) {
  const llamadas: { clave: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn<typeof fetch>((entrada, init = {}) => {
    const texto = entrada instanceof Request ? entrada.url : entrada.toString();
    const url = new URL(texto, "http://localhost");
    const ruta = url.pathname.replace(/^\/api\/v1/, "");
    const clave = `${init.method ?? "GET"} ${ruta}`;
    llamadas.push({ clave, init });
    const manejador = manejadores[clave];
    if (!manejador) return Promise.resolve(problema(404, "NO_ENCONTRADO"));
    if (manejador instanceof Response) return Promise.resolve(manejador.clone());
    return Promise.resolve(manejador(init, url));
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, llamadas, cuerpo: (clave: string) => cuerpoDe(llamadas, clave) };
}

function cuerpoDe(llamadas: { clave: string; init: RequestInit }[], clave: string): unknown {
  const llamada = [...llamadas].reverse().find((l) => l.clave === clave);
  const cuerpo = llamada?.init.body;
  return typeof cuerpo === "string" ? (JSON.parse(cuerpo) as unknown) : undefined;
}

/** Sin sesión: el refresh silencioso del arranque responde 401. */
export const SIN_SESION = { "POST /auth/refresh": () => problema(401, "NO_AUTENTICADO") };

/** Con sesión: el refresh silencioso del arranque devuelve `usuario`. */
export function conSesion(usuario: UsuarioActual) {
  return { "POST /auth/refresh": () => respuestaJson(sesionDePrueba(usuario)) };
}
