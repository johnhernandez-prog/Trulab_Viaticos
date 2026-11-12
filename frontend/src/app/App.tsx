import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { rutas } from "@/app/rutas";
import { crearQueryClient } from "@/lib/query-client";

const router = createBrowserRouter(rutas);

/** Providers de la app: estado del servidor (TanStack Query) y rutas. AuthProvider: S1-11. */
export function App() {
  const [queryClient] = useState(crearQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
