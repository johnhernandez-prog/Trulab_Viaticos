/**
 * Flujos de acceso (S1-11; docs/user-flows.md F-01): login dual, recuperación silenciosa,
 * cambio obligatorio, recuperación y restablecimiento de contraseña, y cierre de sesión.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api-client";
import { obtenerAccessToken } from "@/lib/sesion";
import {
  SIN_SESION,
  conSesion,
  problema,
  renderizarRuta,
  respuestaJson,
  sesionDePrueba,
  simularApi,
  usuarioDePrueba,
} from "@/test/utils";

const PASSWORD_NUEVA = "Una-frase-larga-2026";

async function escribirLogin(usuario: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Usuario"), usuario);
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.click(screen.getByRole("button", { name: "Ingresar" }));
  return user;
}

describe("login con usuario y contraseña", () => {
  it.each([
    ["VIAJERO", "Viáticos"],
    ["ADMIN", "Revisión"],
    ["FINANCIERO", "Pagos"],
  ] as const)("%s entra y llega a su vista inicial (%s)", async (rol, titulo) => {
    const usuario = usuarioDePrueba(rol);
    const servidor = simularApi({
      ...SIN_SESION,
      "POST /auth/login": respuestaJson(sesionDePrueba(usuario)),
    });

    renderizarRuta("/");
    await escribirLogin("  ana.perez ", "Viaje-a-Cali-2026");

    expect(await screen.findByRole("heading", { level: 1, name: titulo })).toBeInTheDocument();
    expect(servidor.cuerpo("POST /auth/login")).toEqual({
      username: "ana.perez",
      password: "Viaje-a-Cali-2026",
    });
    expect(obtenerAccessToken()).toBe("token-de-prueba");
  });

  it("sin sesión, una ruta protegida lleva al login y, al entrar, vuelve a ella", async () => {
    simularApi({
      ...SIN_SESION,
      "POST /auth/login": respuestaJson(sesionDePrueba(usuarioDePrueba("ADMIN"))),
    });

    renderizarRuta("/cargos");
    await escribirLogin("ana.perez", "Viaje-a-Cali-2026");

    expect(await screen.findByRole("heading", { level: 1, name: "Cargos" })).toBeInTheDocument();
  });

  it("valida en el cliente sin llamar a la API", async () => {
    const servidor = simularApi(SIN_SESION);
    const user = userEvent.setup();

    renderizarRuta("/login");
    await user.click(await screen.findByRole("button", { name: "Ingresar" }));

    expect(await screen.findByText("Escriba su usuario")).toBeInTheDocument();
    expect(screen.getByText("Escriba su contraseña")).toBeInTheDocument();
    expect(screen.getByLabelText("Usuario")).toHaveAttribute("aria-invalid", "true");
    expect(servidor.llamadas.map((l) => l.clave)).toEqual(["POST /auth/refresh"]);
  });

  it.each([
    ["CREDENCIALES_INVALIDAS", 401, "Usuario o contraseña incorrectos."],
    ["CUENTA_BLOQUEADA_TEMPORALMENTE", 429, "Cuenta bloqueada temporalmente"],
    ["DEMASIADAS_SOLICITUDES", 429, "Demasiados intentos seguidos"],
  ])("muestra un mensaje claro ante %s", async (code, status, mensaje) => {
    simularApi({ ...SIN_SESION, "POST /auth/login": problema(status, code) });

    renderizarRuta("/login");
    await escribirLogin("ana.perez", "incorrecta");

    expect(await screen.findByRole("alert")).toHaveTextContent(mensaje);
    expect(screen.getByRole("button", { name: "Ingresar" })).toBeEnabled();
  });

  it("sin conexión con la API al cargar, avisa en el login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    renderizarRuta("/login");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se pudo conectar con el servidor",
    );
  });

  it("el enlace de Google avisa que no está configurado si falta el Client ID", async () => {
    simularApi(SIN_SESION);

    renderizarRuta("/login");

    expect(
      await screen.findByText("El ingreso con Google todavía no está configurado en este entorno."),
    ).toBeInTheDocument();
  });
});

describe("acceso de desarrollo de SUPERADMIN", () => {
  it("entra por correo con /auth/dev/login y abre Viáticos", async () => {
    const usuario = usuarioDePrueba("SUPERADMIN");
    const servidor = simularApi({
      ...SIN_SESION,
      "POST /auth/dev/login": respuestaJson(sesionDePrueba(usuario)),
    });
    const user = userEvent.setup();

    renderizarRuta("/login");
    await user.click(await screen.findByText("Acceso de desarrollo (solo local)"));
    await user.type(screen.getByLabelText("Correo del superadministrador"), "ana.perez@trulab.co");
    await user.click(screen.getByRole("button", { name: "Entrar como superadministrador" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Viáticos" })).toBeInTheDocument();
    expect(servidor.cuerpo("POST /auth/dev/login")).toEqual({ correo: "ana.perez@trulab.co" });
  });

  it("un operativo recibe el mensaje de método no permitido", async () => {
    simularApi({
      ...SIN_SESION,
      "POST /auth/dev/login": problema(403, "METODO_ACCESO_NO_PERMITIDO"),
    });
    const user = userEvent.setup();

    renderizarRuta("/login");
    await user.click(await screen.findByText("Acceso de desarrollo (solo local)"));
    await user.type(screen.getByLabelText("Correo del superadministrador"), "ana@trulab.co");
    await user.click(screen.getByRole("button", { name: "Entrar como superadministrador" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Use su usuario y contraseña");
  });
});

describe("sesión", () => {
  it("se recupera en silencio con la cookie de refresh al recargar", async () => {
    const servidor = simularApi(conSesion(usuarioDePrueba("FINANCIERO")));

    renderizarRuta("/");

    expect(await screen.findByRole("heading", { level: 1, name: "Pagos" })).toBeInTheDocument();
    const refresh = servidor.llamadas.find((l) => l.clave === "POST /auth/refresh");
    expect(new Headers(refresh?.init.headers).get("X-Requested-With")).toBe("trulab-spa");
  });

  it("con sesión, /login lleva a la vista inicial", async () => {
    simularApi(conSesion(usuarioDePrueba("ADMIN")));

    renderizarRuta("/login");

    expect(await screen.findByRole("heading", { level: 1, name: "Revisión" })).toBeInTheDocument();
  });

  it("cerrar sesión revoca en la API, borra el token y vuelve al login", async () => {
    const servidor = simularApi({
      ...conSesion(usuarioDePrueba("VIAJERO")),
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();

    renderizarRuta("/perfil");
    const principal = await screen.findByRole("main");
    await user.click(within(principal).getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    const logout = servidor.llamadas.find((l) => l.clave === "POST /auth/logout");
    expect(new Headers(logout?.init.headers).get("Authorization")).toBe("Bearer token-de-prueba");
    expect(obtenerAccessToken()).toBeNull();
  });

  it("si la API rechaza la sesión y el refresh falla, vuelve al login con aviso", async () => {
    simularApi(conSesion(usuarioDePrueba("VIAJERO")));
    const { router } = renderizarRuta("/viaticos");
    await screen.findByRole("heading", { level: 1, name: "Viáticos" });

    // La sesión se revoca en el servidor (p. ej., un ADMIN desactiva al usuario).
    simularApi({
      "GET /me": problema(401, "TOKEN_EXPIRADO"),
      "POST /auth/refresh": problema(401, "NO_AUTENTICADO"),
    });
    await expect(api.get("/me")).rejects.toMatchObject({ code: "TOKEN_EXPIRADO" });

    expect(
      await screen.findByText("Su sesión terminó. Inicie sesión de nuevo."),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });
});

describe("contraseña temporal (cambio obligatorio)", () => {
  it("lleva a crear la contraseña antes de cualquier pantalla y luego a la vista inicial", async () => {
    const temporal = usuarioDePrueba("VIAJERO", { debe_cambiar_password: true });
    const servidor = simularApi({
      ...conSesion(temporal),
      "POST /auth/password/change": respuestaJson(sesionDePrueba(usuarioDePrueba("VIAJERO"), "t2")),
    });
    const user = userEvent.setup();

    renderizarRuta("/usuarios");

    expect(await screen.findByRole("heading", { name: "Cree su contraseña" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Contraseña temporal"), "temporal-del-correo");
    await user.type(screen.getByLabelText("Contraseña nueva"), PASSWORD_NUEVA);
    await user.type(screen.getByLabelText("Confirme la contraseña nueva"), PASSWORD_NUEVA);
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Viáticos" })).toBeInTheDocument();
    expect(servidor.cuerpo("POST /auth/password/change")).toEqual({
      password_actual: "temporal-del-correo",
      nueva_password: PASSWORD_NUEVA,
    });
    expect(obtenerAccessToken()).toBe("t2");
  });

  it("valida longitud y confirmación en el cliente", async () => {
    simularApi(conSesion(usuarioDePrueba("VIAJERO", { debe_cambiar_password: true })));
    const user = userEvent.setup();

    renderizarRuta("/");
    await user.type(await screen.findByLabelText("Contraseña temporal"), "x");
    await user.type(screen.getByLabelText("Contraseña nueva"), "corta");
    await user.type(screen.getByLabelText("Confirme la contraseña nueva"), "otra");
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));

    expect(await screen.findByText("Use al menos 12 caracteres")).toBeInTheDocument();
    expect(screen.getByText("Las contraseñas no coinciden")).toBeInTheDocument();
  });

  it("muestra en el campo las reglas que la API rechaza (PASSWORD_DEBIL)", async () => {
    simularApi({
      ...conSesion(usuarioDePrueba("VIAJERO", { debe_cambiar_password: true })),
      "POST /auth/password/change": problema(422, "PASSWORD_DEBIL", [
        {
          field: "nueva_password",
          code: "PASSWORD_DEBIL",
          message: "Es una contraseña demasiado común",
        },
      ]),
    });
    const user = userEvent.setup();

    renderizarRuta("/");
    await user.type(await screen.findByLabelText("Contraseña temporal"), "temporal");
    await user.type(screen.getByLabelText("Contraseña nueva"), PASSWORD_NUEVA);
    await user.type(screen.getByLabelText("Confirme la contraseña nueva"), PASSWORD_NUEVA);
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));

    expect(await screen.findByText("Es una contraseña demasiado común")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña nueva")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("recuperar y restablecer la contraseña", () => {
  it("'Olvidé mi contraseña' siempre confirma con el mismo mensaje", async () => {
    const servidor = simularApi({
      ...SIN_SESION,
      "POST /auth/password/forgot": respuestaJson({ detail: "ok" }, 202),
    });
    const user = userEvent.setup();

    renderizarRuta("/login");
    await user.click(await screen.findByRole("link", { name: "Olvidé mi contraseña" }));
    await user.type(await screen.findByLabelText("Usuario o correo"), "ana.perez");
    await user.click(screen.getByRole("button", { name: "Enviar enlace" }));

    expect(await screen.findByText("Revise su correo")).toBeInTheDocument();
    expect(servidor.cuerpo("POST /auth/password/forgot")).toEqual({ identificador: "ana.perez" });
  });

  it("restablece con el token del enlace y lo quita de la URL", async () => {
    const servidor = simularApi({
      ...SIN_SESION,
      "POST /auth/password/reset": respuestaJson({ detail: "ok" }),
    });
    const user = userEvent.setup();

    const { router } = renderizarRuta("/restablecer-password?token=abc123");
    await waitFor(() => expect(router.state.location.search).toBe(""));
    await user.type(await screen.findByLabelText("Contraseña nueva"), PASSWORD_NUEVA);
    await user.type(screen.getByLabelText("Confirme la contraseña nueva"), PASSWORD_NUEVA);
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));

    expect(await screen.findByText("Contraseña actualizada")).toBeInTheDocument();
    expect(servidor.cuerpo("POST /auth/password/reset")).toEqual({
      token: "abc123",
      nueva_password: PASSWORD_NUEVA,
    });
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  });

  it("un token vencido o usado muestra cómo pedir otro", async () => {
    simularApi({ ...SIN_SESION, "POST /auth/password/reset": problema(422, "TOKEN_INVALIDO") });
    const user = userEvent.setup();

    renderizarRuta("/restablecer-password?token=vencido");
    await user.type(await screen.findByLabelText("Contraseña nueva"), PASSWORD_NUEVA);
    await user.type(screen.getByLabelText("Confirme la contraseña nueva"), PASSWORD_NUEVA);
    await user.click(screen.getByRole("button", { name: "Guardar contraseña" }));

    expect(await screen.findByText("El enlace no es válido o venció")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Olvidé mi contraseña" })).toBeInTheDocument();
  });

  it("sin token en el enlace no muestra el formulario", async () => {
    simularApi(SIN_SESION);

    renderizarRuta("/restablecer-password");

    expect(await screen.findByText("El enlace no es válido o venció")).toBeInTheDocument();
    expect(screen.queryByLabelText("Contraseña nueva")).not.toBeInTheDocument();
  });
});
