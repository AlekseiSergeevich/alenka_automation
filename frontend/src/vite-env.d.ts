/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DISABLE_AUTH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
