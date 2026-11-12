import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { rutas } from "@/app/rutas";

/** Renderiza la app en `ruta` con un QueryClient de prueba (sin reintentos ni caché compartida). */
export function renderizarRuta(ruta = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(rutas, { initialEntries: [ruta] });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
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
