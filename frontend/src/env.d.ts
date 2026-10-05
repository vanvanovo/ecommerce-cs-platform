/// <reference types="vite/client" />

// Vite 环境变量类型（import.meta.env）
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}