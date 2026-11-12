/// <reference types="vite/client" />

// Variables que Vite expone al navegador (solo VITE_*; ver /.env.example). Nunca secretos.
interface ImportMetaEnv {
  /** Base de la API. Por defecto `/api/v1` (misma origen; Vite reenvía `/api` en desarrollo). */
  readonly VITE_API_BASE_URL?: string;
  /** OAuth Client ID de Google Workspace (S1-08, P-3). */
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
