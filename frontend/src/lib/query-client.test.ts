import { describe, expect, it } from "vitest";

import { ApiError, SIN_CONEXION } from "@/lib/api-client";
import { debeReintentar } from "@/lib/query-client";

describe("debeReintentar", () => {
  it.each([400, 401, 403, 404, 409, 422])("no reintenta un %i", (status) => {
    expect(debeReintentar(0, new ApiError(status, "X", "x"))).toBe(false);
  });

  it("reintenta errores de red y 5xx hasta 2 veces", () => {
    const red = new ApiError(0, SIN_CONEXION, "x");
    const servidor = new ApiError(503, "X", "x");

    expect(debeReintentar(0, red)).toBe(true);
    expect(debeReintentar(1, servidor)).toBe(true);
    expect(debeReintentar(2, servidor)).toBe(false);
  });
});
