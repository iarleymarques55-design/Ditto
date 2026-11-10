// Roda só nas páginas do painel (veja "matches" no manifest). É a ponte entre o painel e a extensão.
const PEDIDOS_DO_PAINEL = ['ping', 'start']

// Marca a página antes de ela carregar: o painel sabe na hora se o gravador está instalado
document.documentElement.dataset.dittoExtensao = chrome.runtime.getManifest().version

window.addEventListener('message', async (evento) => {
  if (evento.source !== window || evento.origin !== location.origin) return
  const mensagem = evento.data
  if (mensagem?.source !== 'ditto-panel' || !PEDIDOS_DO_PAINEL.includes(mensagem.type)) return

  let resposta
  try {
    resposta = await chrome.runtime.sendMessage({ ...mensagem.payload, type: `ditto:${mensagem.type}` })
  } catch {
    resposta = { ok: false, error: 'A extensão não respondeu. Recarregue a página do painel.' }
  }
  window.postMessage(
    { ...resposta, source: 'ditto-extension', requestId: mensagem.requestId },
    location.origin,
  )
})
