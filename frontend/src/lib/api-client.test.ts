import { describe, expect, it, vi } from "vitest";

import { ApiError, SIN_CONEXION, api } from "@/lib/api-client";
import { alPerderSesion, guardarAccessToken, obtenerAccessToken } from "@/lib/sesion";
import { problema, respuestaJson, simularApi } from "@/test/utils";

function simularFetch(respuesta: Response | Error) {
  const fetchMock = vi.fn<typeof fetch>(() =>
    respuesta instanceof Error ? Promise.reject(respuesta) : Promise.resolve(respuesta),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("apiClient", () => {
  it("llama a la base /api/v1 con cookies y devuelve el JSON", async () => {
    const fetchMock = simularFetch(respuestaJson({ status: "ok" }));

    await expect(api.get("/health")).resolves.toEqual({ status: "ok" });

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/health");
    expect(init?.credentials).toBe("include");
    expect(init?.method).toBe("GET");
  });

  it("envía el cuerpo como JSON", async () => {
    const fetchMock = simularFetch(respuestaJson({ id: "1" }, 201));

    await api.post("/cargos", { nombre: "Analista" });

    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.body).toBe('{"nombre":"Analista"}');
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("convierte un problem+json en ApiError con code, request_id y errores de campo", async () => {
    simularFetch(
      respuestaJson(
        {
          type: "https://trulab.co/errores/validacion",
          title: "La solicitud tiene datos inválidos",
          status: 422,
          code: "VALIDACION",
          detail: null,
          request_id: "abc123",
          errors: [{ field: "nombre", code: "MISSING", message: "Field required" }],
        },
        422,
        "application/problem+json",
      ),
    );

    const error = await api.post("/cargos", {}).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "VALIDACION",
      message: "La solicitud tiene datos inválidos",
      requestId: "abc123",
      errors: [{ field: "nombre", code: "MISSING", message: "Field required" }],
    });
  });

  it("sin conexión lanza ApiError SIN_CONEXION con estado 0", async () => {
    simularFetch(new TypeError("Failed to fetch"));

    await expect(api.get("/health")).rejects.toMatchObject({ status: 0, code: SIN_CONEXION });
  });

  it("un error sin problem+json conserva el estado y el X-Request-ID", async () => {
    simularFetch(
      new Response("Bad Gateway", { status: 502, headers: { "x-request-id": "req-502" } }),
    );

    await expect(api.get("/health")).rejects.toMatchObject({
      status: 502,
      code: "ERROR_HTTP",
      requestId: "req-502",
    });
  });

  it("un 204 devuelve undefined", async () => {
    simularFetch(new Response(null, { status: 204 }));

    await expect(api.delete("/sesion")).resolves.toBeUndefined();
  });
});

describe("apiClient con sesión (S1-11)", () => {
  const sesion = (token: string) =>
    respuestaJson({ access_token: token, token_type: "Bearer", expires_in: 900, usuario: {} });

  it("envía el access token en memoria como Bearer", async () => {
    guardarAccessToken("t1");
    const servidor = simularApi({ "GET /cargos": respuestaJson({ items: [] }) });

    await api.get("/cargos");

    const init = servidor.llamadas[0]!.init;
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer t1");
  });

  it("tras un 401 renueva la sesión una vez y repite la petición con el token nuevo", async () => {
    guardarAccessToken("vencido");
    const servidor = simularApi({
      "GET /cargos": (init) =>
        new Headers(init.headers).get("Authorization") === "Bearer nuevo"
          ? respuestaJson({ items: [1] })
          : problema(401, "TOKEN_EXPIRADO"),
      "POST /auth/refresh": sesion("nuevo"),
    });

    await expect(api.get("/cargos")).resolves.toEqual({ items: [1] });

    expect(servidor.llamadas.map((l) => l.clave)).toEqual([
      "GET /cargos",
      "POST /auth/refresh",
      "GET /cargos",
    ]);
    expect(obtenerAccessToken()).toBe("nuevo");
  });

  it("varias peticiones que fallan a la vez comparten un solo refresh (es rotativo)", async () => {
    guardarAccessToken("vencido");
    const servidor = simularApi({
      "GET /cargos": (init) =>
        new Headers(init.headers).get("Authorization") === "Bearer nuevo"
          ? respuestaJson({ ok: true })
          : problema(401, "TOKEN_EXPIRADO"),
      "POST /auth/refresh": sesion("nuevo"),
    });

    await Promise.all([api.get("/cargos"), api.get("/cargos"), api.get("/cargos")]);

    expect(servidor.llamadas.filter((l) => l.clave === "POST /auth/refresh")).toHaveLength(1);
  });

  it("si el refresh falla, avisa que la sesión se perdió y propaga el 401 original", async () => {
    guardarAccessToken("vencido");
    simularApi({
      "GET /cargos": problema(401, "TOKEN_EXPIRADO"),
      "POST /auth/refresh": problema(401, "NO_AUTENTICADO"),
    });
    const perdida = vi.fn();
    const quitar = alPerderSesion(perdida);

    await expect(api.get("/cargos")).rejects.toMatchObject({ code: "TOKEN_EXPIRADO" });

    expect(perdida).toHaveBeenCalledOnce();
    expect(obtenerAccessToken()).toBeNull();
    quitar();
  });

  it("sin conexión durante el refresh no da la sesión por perdida", async () => {
    guardarAccessToken("vencido");
    const perdida = vi.fn();
    const quitar = alPerderSesion(perdida);
    vi.stubGlobal(
      "fetch",
      vi.fn((entrada: string) =>
        String(entrada).endsWith("/auth/refresh")
          ? Promise.reject(new TypeError("Failed to fetch"))
          : Promise.resolve(problema(401, "TOKEN_EXPIRADO")),
      ),
    );

    await expect(api.get("/cargos")).rejects.toMatchObject({ status: 401 });

    expect(perdida).not.toHaveBeenCalled();
    quitar();
  });

  it.each(["/auth/login", "/auth/password/change"])(
    "un 401 en %s no intenta renovar la sesión",
    async (ruta) => {
      const servidor = simularApi({ [`POST ${ruta}`]: problema(401, "CREDENCIALES_INVALIDAS") });

      await expect(api.post(ruta, {})).rejects.toMatchObject({ code: "CREDENCIALES_INVALIDAS" });

      expect(servidor.llamadas).toHaveLength(1);
    },
  );

  it("un 403 no intenta renovar la sesión", async () => {
    const servidor = simularApi({ "GET /usuarios": problema(403, "SIN_PERMISO") });

    await expect(api.get("/usuarios")).rejects.toMatchObject({ code: "SIN_PERMISO" });

    expect(servidor.llamadas).toHaveLength(1);
  });
});
