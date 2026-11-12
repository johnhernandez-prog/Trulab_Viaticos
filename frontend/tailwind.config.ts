import animate from "tailwindcss-animate";
import type { Config } from "tailwindcss";

// Los colores son variables CSS (src/index.css, docs/design-system.md §2): los componentes usan
// solo tokens (`bg-primary`, `text-muted-foreground`...), nunca hexadecimales sueltos.
const token = (nombre: string) => `hsl(var(--${nombre}) / <alpha-value>)`;

const semantico = (nombre: string) => ({
  DEFAULT: token(nombre),
  foreground: token(`${nombre}-foreground`),
  subtle: token(`${nombre}-subtle`),
});

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        background: token("background"),
        foreground: token("foreground"),
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        popover: { DEFAULT: token("popover"), foreground: token("popover-foreground") },
        success: semantico("success"),
        warning: semantico("warning"),
        destructive: semantico("destructive"),
        info: semantico("info"),
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: [
          '"Inter Variable"',
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
      },
      maxWidth: { contenido: "1440px" },
    },
  },
  plugins: [animate],
} satisfies Config;
