import { ShieldX } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";

/** Ruta conocida pero no permitida para el rol (equivale a un 403 de la API). */
export function SinAccesoPage() {
  return (
    <section className="mx-auto flex max-w-md flex-col items-center gap-4 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-warning-subtle">
        <ShieldX className="size-6 text-warning" aria-hidden="true" />
      </div>
      <h1 className="text-xl font-semibold sm:text-2xl">Sin acceso</h1>
      <p className="text-muted-foreground">
        Su rol no tiene permiso para ver esta sección. Si cree que es un error, contacte al
        administrador.
      </p>
      <Button asChild variant="secondary">
        <Link to="/">Ir al inicio</Link>
      </Button>
    </section>
  );
}
