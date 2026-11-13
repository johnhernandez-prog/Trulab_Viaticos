/**
 * AppShell y guardas (S1-11; docs/user-flows.md F-11, docs/design-system.md §12): menú filtrado
 * por permisos, BottomBar con "Más", Sidebar plegable, rutas sin permiso y no encontradas.
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { conSesion, renderizarRuta, simularApi, usuarioDePrueba } from "@/test/utils";

/** Etiquetas de la Sidebar (tablet y escritorio), en orden. */
function modulosDeLaBarraLateral() {
  const lateral = screen.getByRole("complementary", { name: "Navegación principal" });
  const modulos = within(lateral).getByRole("navigation", { name: "Módulos" });
  return within(modulos)
    .getAllByRole("link")
    .map((enlace) => enlace.textContent);
}

function barraInferior() {
  return screen.getByRole("navigation", { name: "Navegación inferior" });
}

describe("menú por rol", () => {
  it.each([
    ["VIAJERO", ["Viáticos"]],
    ["FINANCIERO", ["Viáticos", "Pagos", "Indicadores", "Cargos", "Tarifas"]],
    ["ADMIN", ["Viáticos", "Revisión", "Pagos", "Indicadores", "Cargos", "Usuarios", "Tarifas"]],
    [
      "SUPERADMIN",
      [
        "Viáticos",
        "Revisión",
        "Pagos",
        "Indicadores",
        "Cargos",
        "Usuarios",
        "Tarifas",
        "Catálogos",
      ],
    ],
  ] as const)("%s ve solo sus módulos", async (rol, esperados) => {
    simularApi(conSesion(usuarioDePrueba(rol)));

    renderizarRuta("/perfil");
    await screen.findByRole("heading", { level: 1, name: "Mi perfil" });

    expect(modulosDeLaBarraLateral()).toEqual(esperados);
  });

  it("VIAJERO: la BottomBar muestra Viáticos y Perfil, sin 'Más'", async () => {
    simularApi(conSesion(usuarioDePrueba("VIAJERO")));

    renderizarRuta("/viaticos");
    await screen.findByRole("heading", { level: 1, name: "Viáticos" });

    const barra = barraInferior();
    expect(
      within(barra)
        .getAllByRole("link")
        .map((e) => e.textContent),
    ).toEqual(["Viáticos", "Perfil"]);
    expect(within(barra).queryByRole("button", { name: "Más" })).not.toBeInTheDocument();
  });

  it("ADMIN: la BottomBar agrupa el resto en 'Más' y el panel lleva a otro módulo", async () => {
    simularApi(conSesion(usuarioDePrueba("ADMIN")));
    const user = userEvent.setup();

    renderizarRuta("/revision");
    await screen.findByRole("heading", { level: 1, name: "Revisión" });
    const barra = barraInferior();
    expect(
      within(barra)
        .getAllByRole("link")
        .map((e) => e.textContent),
    ).toEqual(["Viáticos", "Revisión", "Pagos"]);

    await user.click(within(barra).getByRole("button", { name: "Más" }));
    const panel = screen.getByRole("dialog", { name: "Más secciones" });
    await user.click(within(panel).getByRole("link", { name: /Usuarios/ }));

    expect(await screen.findByRole("heading", { level: 1, name: "Usuarios" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Más secciones" })).not.toBeInTheDocument();
  });

  it("marca el módulo actual en la navegación", async () => {
    simularApi(conSesion(usuarioDePrueba("FINANCIERO")));

    renderizarRuta("/pagos");
    await screen.findByRole("heading", { level: 1, name: "Pagos" });

    const lateral = screen.getByRole("complementary", { name: "Navegación principal" });
    expect(within(lateral).getByRole("link", { name: "Pagos" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("la Sidebar de la tablet se expande, y Esc la contrae", async () => {
    simularApi(conSesion(usuarioDePrueba("ADMIN")));
    const user = userEvent.setup();

    renderizarRuta("/revision");
    const expandir = await screen.findByRole("button", { name: "Expandir menú" });
    await user.click(expandir);

    expect(screen.getByRole("button", { name: "Contraer menú" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Expandir menú" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("el menú de perfil ofrece cambiar contraseña a operativos, no a SUPERADMIN", async () => {
    simularApi(conSesion(usuarioDePrueba("SUPERADMIN")));
    const user = userEvent.setup();

    renderizarRuta("/viaticos");
    const [boton] = await screen.findAllByRole("button", { name: "Menú de Ana Pérez Gómez" });
    await user.click(boton!);

    const menu = screen.getByRole("menu", { name: "Opciones de la cuenta" });
    expect(within(menu).getByRole("menuitem", { name: "Mi perfil" })).toHaveFocus();
    expect(within(menu).queryByRole("menuitem", { name: "Cambiar contraseña" })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("guardas", () => {
  it.each([
    ["VIAJERO", "/usuarios"],
    ["VIAJERO", "/pagos"],
    ["FINANCIERO", "/revision"],
    ["FINANCIERO", "/usuarios"],
    ["ADMIN", "/catalogos"],
  ] as const)("%s en %s ve 'Sin acceso'", async (rol, ruta) => {
    simularApi(conSesion(usuarioDePrueba(rol)));

    renderizarRuta(ruta);

    expect(await screen.findByRole("heading", { name: "Sin acceso" })).toBeInTheDocument();
  });

  it("una ruta desconocida muestra 'Página no encontrada' dentro del layout", async () => {
    simularApi(conSesion(usuarioDePrueba("VIAJERO")));

    renderizarRuta("/no-existe");

    expect(
      await screen.findByRole("heading", { name: "Página no encontrada" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver al inicio" })).toHaveAttribute("href", "/");
  });

  it("mientras recupera la sesión muestra la pantalla de carga", () => {
    simularApi({ "POST /auth/refresh": () => new Promise<Response>(() => {}) });

    renderizarRuta("/viaticos");

    expect(screen.getByText("Cargando la sesión…")).toBeInTheDocument();
  });
});
