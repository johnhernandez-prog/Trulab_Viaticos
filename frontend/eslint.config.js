// ESLint 10 (flat config). Reglas con tipos para TypeScript, hooks de React y Fast Refresh.
// El formato lo decide Prettier; ESLint no trae reglas de estilo.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // src/types/api.ts lo genera openapi-typescript (npm run gen:api): no se edita ni se revisa.
  { ignores: ["dist", "coverage", "src/types/api.ts"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  {
    // Rutas y primitivas de shadcn exportan también constantes y variantes (no afecta a HMR).
    files: ["src/app/rutas.tsx", "src/components/ui/**"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    files: ["**/*.js"],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
);
