import { useRouteError } from "react-router";

import { Button } from "@/components/ui/button";

/** Error no controlado al renderizar una ruta: mensaje claro, sin detalles técnicos. */
export function ErrorRuta() {
  const error = useRouteError();
  if (import.meta.env.DEV) console.error(error);

  return (
    <div role="alert" className="mx-auto max-w-xl space-y-4 px-4 py-10">
      <h1 className="text-xl font-semibold">Algo salió mal</h1>
      <p className="text-muted-foreground">
        Ocurrió un error inesperado. Intente recargar la página.
      </p>
      <Button onClick={() => window.location.reload()}>Recargar</Button>
    </div>
  );
}
