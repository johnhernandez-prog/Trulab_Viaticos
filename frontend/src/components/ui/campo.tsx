// Campo de formulario (docs/design-system.md §6): etiqueta siempre visible encima, ayuda debajo
// y error con icono enlazado por `aria-describedby`.
import { CircleAlert, Eye, EyeOff } from "lucide-react";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface CampoProps extends React.InputHTMLAttributes<HTMLInputElement> {
  etiqueta: string;
  ayuda?: string;
  /** Uno o varios mensajes de error (cliente o `errors[]` del servidor). */
  error?: string | string[];
}

export const Campo = React.forwardRef<HTMLInputElement, CampoProps>(
  ({ etiqueta, ayuda, error, id, className, ...props }, ref) => {
    const generado = React.useId();
    const idCampo = id ?? generado;
    const errores = (Array.isArray(error) ? error : error ? [error] : []).filter(Boolean);
    const idAyuda = ayuda ? `${idCampo}-ayuda` : undefined;
    const idError = errores.length ? `${idCampo}-error` : undefined;

    return (
      <div className={cn("space-y-1.5", className)}>
        <label htmlFor={idCampo} className="block text-sm font-medium">
          {etiqueta}
        </label>
        <EntradaConVisibilidad
          ref={ref}
          id={idCampo}
          aria-invalid={errores.length > 0 || undefined}
          aria-describedby={[idAyuda, idError].filter(Boolean).join(" ") || undefined}
          {...props}
        />
        {ayuda && (
          <p id={idAyuda} className="text-sm text-muted-foreground">
            {ayuda}
          </p>
        )}
        {idError && (
          <div id={idError} className="space-y-0.5">
            {errores.map((mensaje) => (
              <p key={mensaje} className="flex items-start gap-1.5 text-sm text-destructive">
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {mensaje}
              </p>
            ))}
          </div>
        )}
      </div>
    );
  },
);
Campo.displayName = "Campo";

/** Un `type="password"` lleva un botón para mostrar u ocultar (útil al teclear en el celular). */
const EntradaConVisibilidad = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ type, className, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false);
  if (type !== "password") return <Input ref={ref} type={type} className={className} {...props} />;

  return (
    <div className="relative">
      <Input
        ref={ref}
        type={visible ? "text" : "password"}
        className={cn("pr-12", className)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {visible ? (
          <EyeOff className="size-4" aria-hidden="true" />
        ) : (
          <Eye className="size-4" aria-hidden="true" />
        )}
      </button>
    </div>
  );
});
EntradaConVisibilidad.displayName = "EntradaConVisibilidad";
