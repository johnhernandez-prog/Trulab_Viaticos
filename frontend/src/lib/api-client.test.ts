import { describe, expect, it, vi } from "vitest";

import { ApiError, SIN_CONEXION, api } from "@/lib/api-client";
import { respuestaJson } from "@/test/utils";

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
