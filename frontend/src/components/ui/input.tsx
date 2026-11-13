// Primitiva de shadcn/ui ajustada a docs/design-system.md §6: 16 px en móvil (sin zoom de iOS),
// 44 px de alto táctil y estado de error con `aria-invalid`.
import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type = "text", ...props }, ref) => (
  <input
    type={type}
    ref={ref}
    className={cn(
      "flex min-h-11 w-full rounded-md border border-input bg-card px-3 py-2 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive sm:min-h-10 sm:text-sm",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";
