import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderizarRuta, respuestaJson } from "@/test/utils";

const saludOk = { status: "ok", version: "0.1.0", db: "ok" };

describe("rutas", () => {
  it("la página de inicio muestra el layout y el estado de la API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respuestaJson(saludOk))),
    );

    renderizarRuta("/");

    expect(screen.getByRole("link", { name: "Trulab Viajes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Trulab Viajes" })).toBeInTheDocument();
    expect(await screen.findByText("Conectada")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
  });

  it("con la BD caída (503) muestra 'Sin conexión' en la base de datos", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(respuestaJson({ ...saludOk, status: "error", db: "error" }, 503)),
      ),
    );

    renderizarRuta("/");

    expect(await screen.findByText("Sin conexión")).toBeInTheDocument();
    expect(screen.getByText("Con problemas")).toBeInTheDocument();
  });

  it("sin API muestra el error con 'Reintentar'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    renderizarRuta("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar con la API");
    await waitFor(() => expect(screen.getByRole("button", { name: "Reintentar" })).toBeEnabled());
  });

  it("una ruta desconocida muestra 'Página no encontrada' dentro del layout", () => {
    vi.stubGlobal("fetch", vi.fn());

    renderizarRuta("/no-existe");

    expect(screen.getByRole("heading", { name: "Página no encontrada" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver al inicio" })).toHaveAttribute("href", "/");
  });
});
