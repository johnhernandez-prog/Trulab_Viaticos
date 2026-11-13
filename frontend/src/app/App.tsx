import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { rutas } from "@/app/rutas";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { crearQueryClient } from "@/lib/query-client";

const router = createBrowserRouter(rutas);

/** Providers de la app: estado del servidor (TanStack Query), sesión y rutas. */
export function App() {
  const [queryClient] = useState(crearQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
