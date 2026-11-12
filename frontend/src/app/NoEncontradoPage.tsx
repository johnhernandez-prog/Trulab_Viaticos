import { Link } from "react-router";

import { Button } from "@/components/ui/button";

export function NoEncontradoPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold sm:text-2xl">Página no encontrada</h1>
      <p className="text-muted-foreground">La dirección que abrió no existe.</p>
      <Button asChild variant="outline">
        <Link to="/">Volver al inicio</Link>
      </Button>
    </div>
  );
}
