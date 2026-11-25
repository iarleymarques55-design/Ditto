import { EM_DESENVOLVIMENTO } from '../../config/env.js'

// O nginx do painel publicado serve a extensão já configurada para este Ditto (frontend/Dockerfile)
export const ENDERECO_DOWNLOAD = '/downloads/ditto-extensao.zip'
export const NOME_DO_ARQUIVO = 'ditto-extensao.zip'
export const NOME_DA_PASTA = 'ditto-extensao'

// disponivel, indisponivel ou desenvolvimento
export async function situacaoDoDownload() {
  // No Vite não existe o pacote: quem desenvolve carrega a pasta extension/ do projeto
  if (EM_DESENVOLVIMENTO) return 'desenvolvimento'
  try {
    const resposta = await fetch(ENDERECO_DOWNLOAD, { method: 'HEAD', cache: 'no-store' })
    return resposta.ok ? 'disponivel' : 'indisponivel'
  } catch {
    return 'indisponivel'
  }
}
