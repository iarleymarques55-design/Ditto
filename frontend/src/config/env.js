// Tudo aqui vai para o navegador: é público, nunca coloque segredos em variáveis VITE_.
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? ''
export const EM_DESENVOLVIMENTO = import.meta.env.DEV
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
