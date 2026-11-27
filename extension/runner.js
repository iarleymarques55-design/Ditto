// Executor: liga este Chrome ao worker do Ditto, para as tarefas rodarem aqui, com as contas da pessoa.
// O worker manda comandos; cada linha abre uma aba ao lado da aba ativa, controlada por chrome.debugger.
// Só as abas abertas pelo Ditto (e as janelas que elas abrirem) são controladas. As outras nunca.
// Mesmo nas abas do Ditto, o worker não pode tudo: comandos que leem os cookies do navegador,
// mexem em outras abas ou no navegador inteiro são recusados aqui (veja COMANDOS_BLOQUEADOS).
// Assim, um worker invadido não consegue levar as sessões da pessoa para fora deste Chrome.

// RELE_URL vem de config.js
const CHAVE_TOKEN = 'dittoExecutorToken'
const CHAVE_CONTA = 'dittoExecutorConta'
const CHAVE_PENDENTE = 'dittoExecutorPendente'
const CHAVE_ABAS = 'dittoExecutorAbas'
const PING_MS = 20000
const ESPERA_MAXIMA_MS = 30000
const DOWNLOAD_LIMITE_MS = 110000
const DOWNLOAD_RECENTE_MS = 10 * 60 * 1000
const PEDIDO_VALIDO_MS = 5 * 60 * 1000
const FECHAMENTO_TOKEN_RECUSADO = 4401
const FECHAMENTO_CONTA_EM_USO = 4409

// Comandos que o Ditto nunca usa nas abas dele e que dariam acesso além da página da tarefa:
// cookies (inclusive os HttpOnly, que nenhum script da página lê), outras abas e o navegador
const DOMINIOS_BLOQUEADOS = ['Storage.', 'Browser.', 'SystemInfo.']
const COMANDOS_BLOQUEADOS = new Set([
  'Network.getAllCookies',
  'Network.getCookies',
  'Network.setCookie',
  'Network.setCookies',
  'Network.deleteCookies',
  'Network.clearBrowserCookies',
  'Page.setDownloadBehavior',
  'Target.createTarget',
  'Target.closeTarget',
  'Target.activateTarget',
  'Target.attachToTarget',
  'Target.attachToBrowserTarget',
  'Target.exposeDevToolsProtocol',
  'Target.getTargets',
  'Target.setDiscoverTargets',
  'Target.createBrowserContext',
  'Target.disposeBrowserContext',
  'Target.getBrowserContexts',
])

function comandoPermitido(metodo) {
  if (typeof metodo !== 'string' || COMANDOS_BLOQUEADOS.has(metodo)) return false
  return !DOMINIOS_BLOQUEADOS.some((dominio) => metodo.startsWith(dominio))
}

// As abas do Ditto só abrem páginas da web. Arquivos do computador (file:), páginas internas do
// Chrome (chrome:, chrome-extension:, devtools:) e endereços que viram código ficam de fora.
function enderecoPermitido(endereco) {
  if (endereco === 'about:blank') return true
  try {
    return ['http:', 'https:'].includes(new URL(endereco).protocol)
  } catch {
    return false
  }
}

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
// Downloads que nasceram nas abas do Ditto: endereço → quando começou. Só esses podem ser
// entregues ao worker. Os downloads da pessoa, nas abas dela, nunca saem deste Chrome.
const downloadsAnunciados = new Map()
const downloadsDoDitto = new Set()

const salvarAbas = () => chrome.storage.session.set({ [CHAVE_ABAS]: [...abasDoDitto] }).catch(() => {})

// ─── Filtro de domínios ──────────────────────────────────────────────────
// A aba do Ditto só navega pelos domínios da tarefa. Quem barra é o próprio Chrome, com uma regra
// que vale só para as abas do Ditto: antes, cada pedido da página (imagem, script, chamada) ia até o
// worker e voltava antes de seguir, e com o worker na nuvem isso deixava cada passo muito mais lento.
// null: o worker ainda não mandou a lista (ou é uma versão antiga dele, que filtra por conta própria).
const REGRA_DOMINIOS = 1
const MAXIMO_DOMINIOS = 200
const DOMINIO_VALIDO = /^[a-z0-9.-]{1,253}$/
let dominiosPermitidos = null

async function aplicarFiltroDeDominios() {
  const abas = [...abasDoDitto]
  const remover = { removeRuleIds: [REGRA_DOMINIOS] }
  if (dominiosPermitidos === null || abas.length === 0) {
    await chrome.declarativeNetRequest.updateSessionRules(remover)
    return
  }
  const condicao = { resourceTypes: ['main_frame'], tabIds: abas }
  // Sem nenhum domínio liberado, nada passa
  if (dominiosPermitidos.length) condicao.excludedRequestDomains = dominiosPermitidos
  await chrome.declarativeNetRequest.updateSessionRules({
    ...remover,
    addRules: [{ id: REGRA_DOMINIOS, priority: 1, action: { type: 'block' }, condition: condicao }],
  })
}

function definirDominios(dominios) {
  if (!Array.isArray(dominios) || dominios.length > MAXIMO_DOMINIOS) throw new Error('Lista de domínios inválida.')
  if (!dominios.every((dominio) => typeof dominio === 'string' && DOMINIO_VALIDO.test(dominio))) {
    throw new Error('Lista de domínios inválida.')
  }
  dominiosPermitidos = [...new Set(dominios)]
  return aplicarFiltroDeDominios()
}

const atualizarFiltro = () => aplicarFiltroDeDominios().catch(() => {})

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
    // Depois de uma recusa, o aviso continua até a pessoa ligar de novo pelo painel
    if (estadoExecutor !== 'recusado') estadoExecutor = 'sem-token'
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
      // Token vencido ou revogado: apagar, para não tentar de novo a cada minuto para sempre
      estadoExecutor = 'recusado'
      chrome.storage.local.remove([CHAVE_TOKEN, CHAVE_CONTA]).catch(() => {})
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

async function fecharConexao() {
  // Uma conexão que já estava abrindo termina antes e depois é fechada
  await conexaoEmAndamento
  clearTimeout(relogioReconexao)
  if (socket) {
    const antigo = socket
    socket = null
    clearInterval(relogioPing)
    antigo.close()
  }
  soltarTodas()
}

async function salvarTokenDoExecutor(token, conta = null) {
  await chrome.storage.local.set({ [CHAVE_TOKEN]: token, [CHAVE_CONTA]: conta })
  espera = 1000
  await fecharConexao()
  await conectarExecutor()
}

// "Desligar este Chrome": apaga o token e fecha a conexão. As tarefas voltam a esperar na fila.
async function desligarExecutor() {
  await chrome.storage.local.remove([CHAVE_TOKEN, CHAVE_CONTA])
  await chrome.storage.session.remove(CHAVE_PENDENTE).catch(() => {})
  await fecharConexao()
  estadoExecutor = 'sem-token'
}

async function contaLigada() {
  const { [CHAVE_CONTA]: conta = null } = await chrome.storage.local.get(CHAVE_CONTA)
  return conta
}

async function ligacaoPendente() {
  const { [CHAVE_PENDENTE]: pendente = null } = await chrome.storage.session.get(CHAVE_PENDENTE)
  if (!pendente || Date.now() - pendente.pedidoEm > PEDIDO_VALIDO_MS) return null
  return pendente
}

// O painel pede para ligar este Chrome a uma conta, mas quem decide é a pessoa, com um clique na
// janela da extensão. Uma página que se passasse pelo painel não consegue ligar este Chrome (com
// as contas logadas nele) à conta de outra pessoa sem que ela veja e aceite.
async function pedirLigacao(token, _contaInformadaPelaPagina) {
  // O e-mail mostrado na confirmação sai do próprio token, assinado pelo servidor. O que a página
  // informa é ignorado: uma página mal-intencionada poderia dizer "sua conta" e mandar o token de
  // outra pessoa. Se ela mexer no e-mail do token, a assinatura quebra e o relé recusa a ligação
  await chrome.storage.session.set({
    [CHAVE_PENDENTE]: { token, conta: emailDoToken(token), pedidoEm: Date.now() },
  })
  await chrome.windows
    .create({ url: chrome.runtime.getURL('popup.html?ligar=1'), type: 'popup', width: 380, height: 360, focused: true })
    .catch(() => {})
  return 'aguardando-confirmacao'
}

function emailDoToken(token) {
  try {
    const parte = String(token).split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const dados = JSON.parse(atob(parte.padEnd(parte.length + ((4 - (parte.length % 4)) % 4), '=')))
    return typeof dados.email === 'string' ? dados.email.slice(0, 200) : null
  } catch {
    return null
  }
}

async function confirmarLigacao() {
  const pendente = await ligacaoPendente()
  await chrome.storage.session.remove(CHAVE_PENDENTE)
  if (!pendente) return false
  await salvarTokenDoExecutor(pendente.token, pendente.conta)
  return true
}

async function recusarLigacao() {
  await chrome.storage.session.remove(CHAVE_PENDENTE)
}

async function resumoDoExecutor() {
  const pendente = await ligacaoPendente()
  return {
    runner: pendente ? 'aguardando-confirmacao' : statusDoExecutor(),
    runnerAccount: await contaLigada(),
    // Só o e-mail: o token pendente nunca sai do serviço da extensão
    runnerPending: pendente ? { account: pendente.conta } : null,
  }
}

function tratarDoRele(ws, mensagem) {
  if (mensagem.type === 'welcome') {
    estadoExecutor = 'conectado'
    espera = 1000
    // Se o relé informar a conta do token, é ela que aparece na janela da extensão
    if (typeof mensagem.email === 'string') chrome.storage.local.set({ [CHAVE_CONTA]: mensagem.email }).catch(() => {})
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

function exigirDownloadDoDitto(downloadId) {
  if (!downloadsDoDitto.has(downloadId)) throw new Error('Este download não foi feito por uma aba do Ditto.')
}

async function adotar(tabId) {
  // A aba só vira do Ditto depois que o controle dá certo. Se o Chrome recusar (DevTools aberto,
  // outra extensão depurando), ela não fica marcada como do Ditto.
  await chrome.debugger.attach({ tabId }, '1.3')
  abasDoDitto.add(tabId)
  await salvarAbas()
  // A regra passa a valer para a aba nova antes de o worker mandar navegar
  await aplicarFiltroDeDominios()
  const { targetInfo } = await chrome.debugger.sendCommand({ tabId }, 'Target.getTargetInfo')
  return { tabId, targetInfo }
}

async function executar(metodo, params) {
  switch (metodo) {
    case 'createTab': {
      // Ao lado da aba em que a pessoa está, na mesma janela. Ela abre na frente de propósito:
      // numa aba em segundo plano o Chrome para de desenhar a página, e os cliques da tarefa travam.
      const [ativa] = await chrome.tabs.query({ active: true, lastFocusedWindow: true })
      const posicao = ativa ? { windowId: ativa.windowId, index: ativa.index + 1 } : {}
      const aba = await chrome.tabs.create({ url: 'about:blank', active: true, ...posicao })
      try {
        return await adotar(aba.id)
      } catch (erro) {
        // Sem controle, a aba não serve para nada: não fica aberta à toa
        await chrome.tabs.remove(aba.id).catch(() => {})
        throw erro
      }
    }
    case 'closeTab':
      exigirAbaDoDitto(params.tabId)
      await chrome.tabs.remove(params.tabId)
      return {}
    case 'send':
      exigirAbaDoDitto(params.tabId)
      if (!comandoPermitido(params.method)) throw new Error(`${params.method} não é permitido nas abas do Ditto.`)
      if (params.method === 'Page.navigate' && !enderecoPermitido(params.params?.url)) {
        throw new Error('As abas do Ditto só abrem endereços http:// ou https://.')
      }
      return chrome.debugger.sendCommand(
        params.sessionId ? { tabId: params.tabId, sessionId: params.sessionId } : { tabId: params.tabId },
        params.method,
        params.params,
      )
    case 'finishDownload':
      return esperarDownload(params.url)
    case 'readDownload':
      exigirDownloadDoDitto(params.downloadId)
      return lerDownload(params.downloadId)
    case 'removeDownload':
      exigirDownloadDoDitto(params.downloadId)
      downloadsDoDitto.delete(params.downloadId)
      await chrome.downloads.removeFile(params.downloadId).catch(() => {})
      await chrome.downloads.erase({ id: params.downloadId }).catch(() => {})
      return {}
    case 'detachAll':
      soltarTodas()
      return {}
    case 'setAllowedDomains':
      await definirDominios(params.domains)
      return {}
    default:
      throw new Error(`Comando desconhecido: ${metodo}`)
  }
}

function anunciarDownload(url) {
  if (typeof url !== 'string' || !url) return
  const agora = Date.now()
  for (const [endereco, quando] of downloadsAnunciados) {
    if (agora - quando > DOWNLOAD_RECENTE_MS) downloadsAnunciados.delete(endereco)
  }
  downloadsAnunciados.set(url, agora)
}

async function esperarDownload(url) {
  // Só um download que a própria aba do Ditto anunciou. Aceitar qualquer endereço seria um jeito
  // de pegar arquivos que a pessoa baixou nas abas dela.
  const anunciado = downloadsAnunciados.get(url)
  if (anunciado === undefined || Date.now() - anunciado > DOWNLOAD_RECENTE_MS) {
    throw new Error('Este download não foi feito por uma aba do Ditto.')
  }
  // Um download do mesmo endereço feito antes, pela pessoa, fica de fora
  const desde = new Date(anunciado - 5000).toISOString()
  const limite = Date.now() + DOWNLOAD_LIMITE_MS
  while (Date.now() < limite) {
    const [item] = await chrome.downloads.search({ url, startedAfter: desde, orderBy: ['-startTime'], limit: 1 })
    if (item?.state === 'complete' && item.filename) {
      downloadsAnunciados.delete(url)
      downloadsDoDitto.add(item.id)
      return { downloadId: item.id, path: item.filename }
    }
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
  dominiosPermitidos = null
  atualizarFiltro()
}

// ─── Eventos do Chrome ───────────────────────────────────────────────────

chrome.debugger.onEvent.addListener((origem, method, params) => {
  if (!abasDoDitto.has(origem.tabId)) return
  if (method === 'Page.downloadWillBegin') anunciarDownload(params?.url)
  enviarAoRele({ event: 'cdpEvent', tabId: origem.tabId, sessionId: origem.sessionId, method, params })
})

// A pessoa fechou a aba ou clicou em "Cancelar" na faixa do Chrome: a linha para
chrome.debugger.onDetach.addListener((origem) => {
  if (!abasDoDitto.delete(origem.tabId)) return
  salvarAbas()
  atualizarFiltro()
  enviarAoRele({ event: 'tabDetached', tabId: origem.tabId })
})

chrome.tabs.onRemoved.addListener((tabId) => {
  if (!abasDoDitto.delete(tabId)) return
  salvarAbas()
  atualizarFiltro()
  enviarAoRele({ event: 'tabDetached', tabId })
})

// Uma aba do Ditto que for parar num endereço fora da web (arquivo do computador, página interna
// do Chrome) é fechada na hora, e a linha para
chrome.webNavigation.onBeforeNavigate.addListener((detalhes) => {
  if (detalhes.frameId !== 0 || !abasDoDitto.has(detalhes.tabId) || enderecoPermitido(detalhes.url)) return
  chrome.tabs.remove(detalhes.tabId).catch(() => {})
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
  // Uma regra de antes do reinício não pode ficar valendo para abas que já não são do Ditto
  await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [REGRA_DOMINIOS] }).catch(() => {})
  conectarExecutor()
}

// Acorda de tempos em tempos para tentar de novo quando o worker estava desligado
chrome.alarms.create('ditto-executor', { periodInMinutes: 1 })
chrome.alarms.onAlarm.addListener((alarme) => {
  if (alarme.name === 'ditto-executor' && !socket) conectarExecutor()
})

iniciarExecutor()
