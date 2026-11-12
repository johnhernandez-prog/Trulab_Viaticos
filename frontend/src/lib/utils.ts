import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Combina clases de Tailwind resolviendo conflictos (convención de shadcn/ui). */
export function cn(...entradas: ClassValue[]): string {
  return twMerge(clsx(entradas));
}
