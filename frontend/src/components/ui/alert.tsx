// Alerta en línea (docs/design-system.md §10): icono + texto, nunca solo color.
import { cva, type VariantProps } from "class-variance-authority";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "flex gap-3 rounded-lg border p-3 text-sm [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      variant: {
        info: "border-info/30 bg-info-subtle text-foreground [&>svg]:text-info",
        success: "border-success/30 bg-success-subtle text-foreground [&>svg]:text-success",
        warning: "border-warning/30 bg-warning-subtle text-foreground [&>svg]:text-warning",
        destructive:
          "border-destructive/30 bg-destructive-subtle text-foreground [&>svg]:text-destructive",
      },
    },
    defaultVariants: { variant: "info" },
  },
);

const ICONOS = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  destructive: CircleAlert,
} as const;

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof alertVariants> {
  titulo?: string;
}

export function Alert({ className, variant, titulo, children, ...props }: AlertProps) {
  const Icono = ICONOS[variant ?? "info"];
  return (
    <div
      role={variant === "destructive" || variant === "warning" ? "alert" : "status"}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    >
      <Icono aria-hidden="true" />
      <div className="space-y-1">
        {titulo && <p className="font-medium">{titulo}</p>}
        <div className="text-muted-foreground [&_p]:leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
