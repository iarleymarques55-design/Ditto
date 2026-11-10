import { API_URL } from '../../config/env.js'
import { pedir } from '../../lib/http.js'

const ESPERA_RESPOSTA_MS = 15000

let proximoPedido = 0

// A extensão fala com o painel por mensagens na própria janela, por meio da ponte que ela injeta aqui
function falarComExtensao(tipo, payload = {}) {
  return new Promise((resolver) => {
    const requestId = ++proximoPedido
    let relogio = null

    function aoReceber(evento) {
      const mensagem = evento.data
      if (evento.source !== window || evento.origin !== window.location.origin) return
      if (mensagem?.source !== 'ditto-extension' || mensagem.requestId !== requestId) return
      window.removeEventListener('message', aoReceber)
      clearTimeout(relogio)
      resolver(mensagem)
    }

    window.addEventListener('message', aoReceber)
    relogio = setTimeout(() => {
      window.removeEventListener('message', aoReceber)
      resolver(null)
    }, ESPERA_RESPOSTA_MS)
    window.postMessage({ source: 'ditto-panel', type: tipo, requestId, payload }, window.location.origin)
  })
}

export function extensaoInstalada() {
  return Boolean(document.documentElement.dataset.dittoExtensao)
}

export function consultarExtensao() {
  return falarComExtensao('ping')
}

export async function iniciarGravacao({ nome, url }) {
  // Token curto, que só serve para enviar esta gravação: a extensão nunca recebe o token da sessão
  const { token } = await pedir('/auth/recording-token', { metodo: 'POST' })
  const resposta = await falarComExtensao('start', {
    name: nome,
    startUrl: url,
    token,
    apiUrl: new URL(API_URL, window.location.origin).href.replace(/\/$/, ''),
    panelUrl: window.location.origin,
  })
  if (!resposta) throw new Error('A extensão não respondeu. Recarregue a página e tente de novo.')
  if (!resposta.ok) throw new Error(resposta.error)
}
