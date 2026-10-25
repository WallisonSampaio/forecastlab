/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  /** Optional white-label logo (e.g. /brand/client-logo.png), kept out of git. */
  readonly VITE_CLIENT_LOGO_URL?: string;
  readonly VITE_CLIENT_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
