import { API_URL } from '../config/env.js'

const CHAVE_TOKEN = 'ditto.token'
export const EVENTO_SESSAO_ENCERRADA = 'ditto:sessao-encerrada'

// O armazenamento pode estar bloqueado (janela privada, política da empresa): sem ele, a sessão dura até recarregar
let tokenEmMemoria = null

export function lerToken() {
  try {
    return localStorage.getItem(CHAVE_TOKEN) ?? tokenEmMemoria
  } catch {
    return tokenEmMemoria
  }
}

export function salvarToken(token) {
  tokenEmMemoria = token
  try {
    localStorage.setItem(CHAVE_TOKEN, token)
  } catch {
    // fica só na memória
  }
}

export function apagarToken() {
  tokenEmMemoria = null
  try {
    localStorage.removeItem(CHAVE_TOKEN)
  } catch {
    // nada a apagar
  }
}

class ErroApi extends Error {
  constructor(mensagem, status, codigo) {
    super(mensagem)
    this.status = status
    this.codigo = codigo
  }
}

async function enviar(caminho, { metodo = 'GET', corpo, formulario } = {}) {
  const token = lerToken()
  const cabecalhos = {}
  if (token) cabecalhos.Authorization = `Bearer ${token}`
  if (corpo !== undefined) cabecalhos['Content-Type'] = 'application/json'

  let resposta
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      method: metodo,
      headers: cabecalhos,
      body: formulario ?? (corpo !== undefined ? JSON.stringify(corpo) : undefined),
    })
  } catch {
    throw new ErroApi('Não foi possível falar com o servidor. Confira se a API do Ditto está no ar.', 0, 'REDE')
  }

  if (resposta.ok) return resposta

  let erro = {}
  try {
    erro = await resposta.json()
  } catch {
    // resposta sem corpo: fica a mensagem genérica
  }

  // Token vencido ou inválido: a sessão acabou, menos em quem está tentando entrar
  if (resposta.status === 401 && token && erro.code === 'UNAUTHORIZED') {
    apagarToken()
    window.dispatchEvent(new Event(EVENTO_SESSAO_ENCERRADA))
  }

  throw new ErroApi(erro.detail ?? 'Algo deu errado. Tente de novo.', resposta.status, erro.code)
}

export async function pedir(caminho, opcoes) {
  const resposta = await enviar(caminho, opcoes)
  return resposta.status === 204 ? null : resposta.json()
}

export async function pedirArquivo(caminho) {
  const resposta = await enviar(caminho)
  return resposta.blob()
}

// Links comuns não levam o token, então o arquivo vem pelo fetch e o clique é simulado
export async function baixarArquivo(caminho, nome) {
  const url = URL.createObjectURL(await pedirArquivo(caminho))
  const link = document.createElement('a')
  link.href = url
  link.download = nome
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export const FUSO_DO_NAVEGADOR = Intl.DateTimeFormat().resolvedOptions().timeZone
