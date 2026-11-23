// Executor: liga este Chrome ao worker do Ditto, para as tarefas rodarem aqui, com as contas da pessoa.
// O worker manda comandos; cada linha abre uma aba ao lado da aba ativa, controlada por chrome.debugger.
// Só as abas abertas pelo Ditto (e as janelas que elas abrirem) são controladas. As outras nunca.

// RELE_URL vem de config.js
const CHAVE_TOKEN = 'dittoExecutorToken'
const CHAVE_ABAS = 'dittoExecutorAbas'
const PING_MS = 20000
const ESPERA_MAXIMA_MS = 30000
const DOWNLOAD_LIMITE_MS = 110000
const DOWNLOAD_RECENTE_MS = 10 * 60 * 1000
const FECHAMENTO_TOKEN_RECUSADO = 4401
const FECHAMENTO_CONTA_EM_USO = 4409

// O token e o controle das abas viajam por aqui: fora deste computador, só com criptografia
function releSeguro(endereco) {
  try {
    const url = new URL(endereco)
    if (url.protocol === 'wss:') return true
    return url.protocol === 'ws:' && ['127.0.0.1', 'localhost'].includes(url.hostname)
  } catch {
    return false
  }
}

let socket = null
let estadoExecutor = 'sem-token' // sem-token | conectando | conectado | desconectado | recusado | em-uso
let espera = 1000
let relogioPing = null
let relogioReconexao = null
const abasDoDitto = new Set()

const salvarAbas = () => chrome.storage.session.set({ [CHAVE_ABAS]: [...abasDoDitto] }).catch(() => {})

function statusDoExecutor() {
  return estadoExecutor
}

function enviarAoRele(mensagem) {
  if (socket?.readyState === WebSocket.OPEN && estadoExecutor === 'conectado') {
    socket.send(JSON.stringify(mensagem))
  }
}

// ─── Conexão com o worker ────────────────────────────────────────────────

// Uma conexão de cada vez. Duas chamadas juntas (o painel ligando e o alarme acordando) passavam
// as duas por "if (socket)" antes de qualquer uma abrir o socket: abriam dois, e o relé recusa o
// segundo da mesma conta
let conexaoEmAndamento = null

function conectarExecutor() {
  if (socket) return Promise.resolve()
  conexaoEmAndamento ??= abrirConexao().finally(() => {
    conexaoEmAndamento = null
  })
  return conexaoEmAndamento
}

async function abrirConexao() {
  const { [CHAVE_TOKEN]: token } = await chrome.storage.local.get(CHAVE_TOKEN)
  if (!token) {
    estadoExecutor = 'sem-token'
    return
  }
  if (!releSeguro(RELE_URL)) {
    estadoExecutor = 'recusado'
    return
  }

  estadoExecutor = 'conectando'
  const ws = new WebSocket(RELE_URL)
  socket = ws
  ws.onopen = () => ws.send(JSON.stringify({ type: 'hello', token, version: chrome.runtime.getManifest().version }))
  ws.onmessage = (evento) => {
    let mensagem
    try {
      mensagem = JSON.parse(evento.data)
    } catch {
      return
    }
    tratarDoRele(ws, mensagem)
  }
  ws.onclose = (evento) => {
    if (socket !== ws) return
    socket = null
    clearInterval(relogioPing)
    soltarTodas()
    if (evento.code === FECHAMENTO_TOKEN_RECUSADO) {
      estadoExecutor = 'recusado'
      return
    }
    // Outro Chrome já está ligado nesta conta: tenta de novo só no alarme de cada minuto
    if (evento.code === FECHAMENTO_CONTA_EM_USO) {
      estadoExecutor = 'em-uso'
      return
    }
    estadoExecutor = 'desconectado'
    agendarReconexao()
  }
}

function agendarReconexao() {
  clearTimeout(relogioReconexao)
  relogioReconexao = setTimeout(conectarExecutor, espera)
  espera = Math.min(espera * 2, ESPERA_MAXIMA_MS)
}

async function salvarTokenDoExecutor(token) {
  await chrome.storage.local.set({ [CHAVE_TOKEN]: token })
  espera = 1000
  // Uma conexão que já estava abrindo, com o token antigo, termina antes e depois dá lugar à nova
  await conexaoEmAndamento
  if (socket) {
    const antigo = socket
    socket = null
    antigo.close()
    soltarTodas()
  }
  await conectarExecutor()
}

function tratarDoRele(ws, mensagem) {
  if (mensagem.type === 'welcome') {
    estadoExecutor = 'conectado'
    espera = 1000
    clearInterval(relogioPing)
    // Mensagens no socket mantêm o service worker acordado
    relogioPing = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('{"type":"ping"}'), PING_MS)
    return
  }
  if (mensagem.id === undefined || !mensagem.method) return
  executar(mensagem.method, mensagem.params ?? {}).then(
    (result) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ id: mensagem.id, result: result ?? {} })),
    (erro) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ id: mensagem.id, error: String(erro?.message ?? erro) })),
  )
}

// ─── Comandos do worker ──────────────────────────────────────────────────

function exigirAbaDoDitto(tabId) {
  if (!abasDoDitto.has(tabId)) throw new Error('Esta aba não foi aberta pelo Ditto.')
}

async function adotar(tabId) {
  abasDoDitto.add(tabId)
  await salvarAbas()
  await chrome.debugger.attach({ tabId }, '1.3')
  const { targetInfo } = await chrome.debugger.sendCommand({ tabId }, 'Target.getTargetInfo')
  return { tabId, targetInfo }
}

async function executar(metodo, params) {
  switch (metodo) {
    case 'createTab': {
      // Ao lado da aba em que a pessoa está, na mesma janela
      const [ativa] = await chrome.tabs.query({ active: true, lastFocusedWindow: true })
      const posicao = ativa ? { windowId: ativa.windowId, index: ativa.index + 1 } : {}
      const aba = await chrome.tabs.create({ url: 'about:blank', active: true, ...posicao })
      return adotar(aba.id)
    }
    case 'closeTab':
      exigirAbaDoDitto(params.tabId)
      await chrome.tabs.remove(params.tabId)
      return {}
    case 'send':
      exigirAbaDoDitto(params.tabId)
      return chrome.debugger.sendCommand(
        params.sessionId ? { tabId: params.tabId, sessionId: params.sessionId } : { tabId: params.tabId },
        params.method,
        params.params,
      )
    case 'finishDownload':
      return esperarDownload(params.url)
    case 'readDownload':
      return lerDownload(params.downloadId)
    case 'removeDownload':
      await chrome.downloads.removeFile(params.downloadId).catch(() => {})
      await chrome.downloads.erase({ id: params.downloadId }).catch(() => {})
      return {}
    case 'detachAll':
      soltarTodas()
      return {}
    default:
      throw new Error(`Comando desconhecido: ${metodo}`)
  }
}

async function esperarDownload(url) {
  const limite = Date.now() + DOWNLOAD_LIMITE_MS
  while (Date.now() < limite) {
    const desde = new Date(Date.now() - DOWNLOAD_RECENTE_MS).toISOString()
    const [item] = await chrome.downloads.search({ url, startedAfter: desde, orderBy: ['-startTime'], limit: 1 })
    if (item?.state === 'complete' && item.filename) return { downloadId: item.id, path: item.filename }
    if (item?.state === 'interrupted') throw new Error('O download foi interrompido.')
    await new Promise((resolver) => setTimeout(resolver, 300))
  }
  throw new Error('O download não terminou a tempo.')
}

// ─── Envio do arquivo baixado ────────────────────────────────────────────
// Quando o worker roda em outra máquina (nuvem, Docker), ele não alcança a pasta Downloads
// daqui. A extensão não pode ler arquivos do disco, então busca o mesmo endereço de novo, com
// as contas logadas deste Chrome, e manda o conteúdo pela conexão.

const DOWNLOAD_MAXIMO_BYTES = 40 * 1024 * 1024

function paraBase64(bytes) {
  let binario = ''
  for (let inicio = 0; inicio < bytes.length; inicio += 0x8000) {
    binario += String.fromCharCode(...bytes.subarray(inicio, inicio + 0x8000))
  }
  return btoa(binario)
}

// Endereço blob: só existe dentro da página que o criou: a leitura roda na aba do Ditto
async function lerBlobNaAba(endereco) {
  const origem = new URL(endereco.slice('blob:'.length)).origin
  for (const tabId of abasDoDitto) {
    const aba = await chrome.tabs.get(tabId).catch(() => null)
    if (!aba?.url || new URL(aba.url).origin !== origem) continue
    const [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId },
      world: 'MAIN',
      args: [endereco],
      func: async (url) => {
        const bytes = new Uint8Array(await (await fetch(url)).arrayBuffer())
        let binario = ''
        for (let inicio = 0; inicio < bytes.length; inicio += 0x8000) {
          binario += String.fromCharCode(...bytes.subarray(inicio, inicio + 0x8000))
        }
        return btoa(binario)
      },
    })
    if (result) return result
  }
  throw new Error('O arquivo foi gerado pela página e ela já o descartou.')
}

async function lerDownload(downloadId) {
  const [item] = await chrome.downloads.search({ id: downloadId })
  if (!item) throw new Error('O download não foi encontrado.')
  if (item.fileSize > DOWNLOAD_MAXIMO_BYTES) throw new Error('O arquivo baixado passa de 40 MB.')
  const endereco = item.finalUrl || item.url
  if (endereco.startsWith('blob:')) return { base64: await lerBlobNaAba(endereco) }
  if (!/^(https?|data):/.test(endereco)) throw new Error('Este tipo de download não pode ser enviado ao Ditto.')

  const resposta = await fetch(endereco, { credentials: 'include' })
  if (!resposta.ok) throw new Error(`O site respondeu ${resposta.status} ao baixar o arquivo de novo.`)
  const bytes = new Uint8Array(await resposta.arrayBuffer())
  if (bytes.length > DOWNLOAD_MAXIMO_BYTES) throw new Error('O arquivo baixado passa de 40 MB.')
  return { base64: paraBase64(bytes) }
}

function soltarTodas() {
  for (const tabId of abasDoDitto) chrome.debugger.detach({ tabId }).catch(() => {})
  abasDoDitto.clear()
  salvarAbas()
}

// ─── Eventos do Chrome ───────────────────────────────────────────────────

chrome.debugger.onEvent.addListener((origem, method, params) => {
  if (!abasDoDitto.has(origem.tabId)) return
  enviarAoRele({ event: 'cdpEvent', tabId: origem.tabId, sessionId: origem.sessionId, method, params })
})

// A pessoa fechou a aba ou clicou em "Cancelar" na faixa do Chrome: a linha para
chrome.debugger.onDetach.addListener((origem) => {
  if (!abasDoDitto.delete(origem.tabId)) return
  salvarAbas()
  enviarAoRele({ event: 'tabDetached', tabId: origem.tabId })
})

chrome.tabs.onRemoved.addListener((tabId) => {
  if (!abasDoDitto.delete(tabId)) return
  salvarAbas()
  enviarAoRele({ event: 'tabDetached', tabId })
})

// Janela aberta pela própria aba do Ditto (link com target=_blank, window.open)
chrome.webNavigation.onCreatedNavigationTarget.addListener((detalhes) => {
  if (!abasDoDitto.has(detalhes.sourceTabId) || abasDoDitto.has(detalhes.tabId)) return
  adotar(detalhes.tabId).then(
    (info) => enviarAoRele({ event: 'tabAttached', ...info, openerTabId: detalhes.sourceTabId }),
    () => {},
  )
})

// ─── Início ──────────────────────────────────────────────────────────────

async function iniciarExecutor() {
  // O service worker pode ter reiniciado no meio de uma linha: solta as abas que ficaram presas
  const { [CHAVE_ABAS]: antigas = [] } = await chrome.storage.session.get(CHAVE_ABAS)
  for (const tabId of antigas) chrome.debugger.detach({ tabId }).catch(() => {})
  await chrome.storage.session.remove(CHAVE_ABAS)
  conectarExecutor()
}

// Acorda de tempos em tempos para tentar de novo quando o worker estava desligado
chrome.alarms.create('ditto-executor', { periodInMinutes: 1 })
chrome.alarms.onAlarm.addListener((alarme) => {
  if (alarme.name === 'ditto-executor' && !socket) conectarExecutor()
})

iniciarExecutor()
