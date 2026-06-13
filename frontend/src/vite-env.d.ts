/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** When "true", the app boots the MSW mock layer (dev / E2E only). */
  readonly VITE_ENABLE_MSW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
