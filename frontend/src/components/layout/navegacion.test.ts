import { describe, expect, it } from "vitest";

import {
  MAXIMO_BARRA_INFERIOR,
  MODULOS,
  modulosVisibles,
  repartirBarraInferior,
} from "@/components/layout/navegacion";
import type { Rol } from "@/features/auth/contexto";
import { destinoTrasLogin, iniciales, vistaInicial } from "@/features/auth/roles";
import { PERMISOS_POR_ROL } from "@/test/utils";

const visibles = (rol: Rol) => modulosVisibles((p) => PERMISOS_POR_ROL[rol].includes(p));

describe("navegación", () => {
  it("todos los módulos declaran un permiso que existe en la matriz", () => {
    const todos = new Set(PERMISOS_POR_ROL.SUPERADMIN);
    for (const modulo of MODULOS) {
      expect(modulo.permiso === null || todos.has(modulo.permiso)).toBe(true);
    }
  });

  it("SUPERADMIN ve todos los módulos", () => {
    expect(visibles("SUPERADMIN")).toHaveLength(MODULOS.length);
  });

  it.each(["VIAJERO", "FINANCIERO", "ADMIN", "SUPERADMIN"] as const)(
    "%s: la BottomBar nunca supera 4 destinos y no pierde ninguno",
    (rol) => {
      const modulos = visibles(rol);
      const { barra, mas } = repartirBarraInferior(modulos);

      expect(barra.length + (mas.length > 0 ? 1 : 0)).toBeLessThanOrEqual(MAXIMO_BARRA_INFERIOR);
      expect([...barra, ...mas].map((m) => m.ruta)).toEqual([
        ...modulos.map((m) => m.ruta),
        "/perfil",
      ]);
    },
  );
});

describe("roles", () => {
  it.each([
    ["VIAJERO", "/viaticos"],
    ["ADMIN", "/revision"],
    ["FINANCIERO", "/pagos"],
    ["SUPERADMIN", "/viaticos"],
  ] as const)("vista inicial de %s: %s", (rol, ruta) => {
    expect(vistaInicial({ rol })).toBe(ruta);
  });

  it.each([
    [undefined, "/pagos"],
    ["/cargos?page=2", "/cargos?page=2"],
    ["//sitio-externo.com", "/pagos"],
    ["https://sitio-externo.com", "/pagos"],
    ["/login", "/pagos"],
  ])("después del login, desde=%s → %s (sin redirecciones externas)", (desde, esperado) => {
    expect(destinoTrasLogin(desde, "/pagos")).toBe(esperado);
  });

  it.each([
    ["Ana Pérez Gómez", "AG"],
    ["  laura  ", "L"],
    ["", "?"],
  ])("iniciales de '%s': %s", (nombre, esperado) => {
    expect(iniciales(nombre)).toBe(esperado);
  });
});
