// Guarda a gravação. O Chrome desliga este arquivo quando fica ocioso, por isso tudo vai para o storage.

const CHAVE = 'gravacao'
const MAX_PASSOS = 200
const MAX_DOMINIOS = 20
const MIN_REFERENCIA = 3
const QUANTIDADE_DE_CANTOS = 4
const JANELA_DOWNLOAD_MS = 20000

// Folgado de propósito: com o computador ocupado, abrir uma aba pode levar vários segundos
const LIMITE_DA_TAREFA_MS = 20000
const LIMITE_DO_ENVIO_MS = 30000

function comLimite(promessa, limite) {
  return Promise.race([
    promessa,
    new Promise((_, recusar) => setTimeout(() => recusar(new Error('A tarefa da fila passou do limite.')), limite)),
  ])
}

// Mensagens são tratadas uma de cada vez: duas ao mesmo tempo poderiam perder um passo.
// Uma tarefa travada não pode segurar as outras: seria a gravação inteira parada, sem nenhum aviso.
let fila = Promise.resolve()
function enfileirar(tarefa, limite = LIMITE_DA_TAREFA_MS) {
  const resultado = fila.then(() => comLimite(tarefa(), limite))
  fila = resultado.catch(() => {})
  return resultado
}

const lerEstado = async () => (await chrome.storage.session.get(CHAVE))[CHAVE] ?? null
const salvarEstado = (estado) => chrome.storage.session.set({ [CHAVE]: estado })
const limparEstado = () => chrome.storage.session.remove(CHAVE)

function origensDoPainel() {
  return chrome.runtime
    .getManifest()
    .content_scripts.flatMap((script) => script.matches)
    .map((padrao) => new URL(padrao.replace('/*', '/')).origin)
}

function hostDe(url) {
  try {
    return new URL(url).hostname.toLowerCase()
  } catch {
    return ''
  }
}

const NOME_MAXIMO = 40

function descreverPasso(passo) {
  const alvo = passo.target ?? {}
  const nome = (passo.capture_name ?? alvo.text ?? alvo.label ?? alvo.placeholder ?? alvo.name ?? 'elemento').slice(0, NOME_MAXIMO)
  const descricoes = {
    navigate: 'abriu a página',
    click: `clique em "${nome}"`,
    fill: `digitou em "${nome}"`,
    select: `escolheu em "${nome}"`,
    check: `marcou "${nome}"`,
    press: `Enter em "${nome}"`,
    capture: `capturou "${nome}"`,
  }
  return descricoes[passo.action]
}

function resumo(estado) {
  if (!estado) return { recording: false }
  return {
    recording: true,
    name: estado.name,
    steps: estado.steps.length,
    startedAt: estado.startedAt,
    error: estado.error ?? null,
    sending: estado.sending ?? false,
    picking: estado.picking ?? false,
    captures: Object.keys(estado.examples),
    warning: estado.warning ?? null,
    corner: estado.corner ?? 0,
    last: descreverPasso(estado.steps.at(-1)),
    limitReached: estado.steps.length >= MAX_PASSOS,
  }
}

async function avisarAbas(estado) {
  for (const tabId of estado?.tabIds ?? []) {
    chrome.tabs.sendMessage(tabId, { type: 'ditto:state', state: resumo(estado) }, { frameId: 0 }).catch(() => {})
  }
}

async function injetar(tabId, frameId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId, frameIds: [frameId] },
      files: ['recorder.js'],
      injectImmediately: true,
    })
  } catch {
    // Páginas internas do navegador não aceitam scripts
  }
}

async function iniciar(mensagem) {
  if (await lerEstado()) return { ok: false, error: 'Já existe uma gravação em andamento. Termine ou descarte antes.' }

  let inicio
  try {
    inicio = new URL(mensagem.startUrl)
  } catch {
    return { ok: false, error: 'O endereço inicial não é válido.' }
  }
  if (!['http:', 'https:'].includes(inicio.protocol)) {
    return { ok: false, error: 'O endereço precisa começar com http:// ou https://.' }
  }

  // A navegação da aba só é tratada depois deste passo, porque as mensagens esperam na fila
  const aba = await chrome.tabs.create({ url: inicio.href, active: true })
  await salvarEstado({
    name: mensagem.name,
    token: mensagem.token,
    apiUrl: mensagem.apiUrl,
    panelUrl: mensagem.panelUrl,
    startUrl: inicio.href,
    startedAt: Date.now(),
    tabIds: [aba.id],
    steps: [{ action: 'navigate', url: inicio.href }],
    hosts: [inicio.hostname.toLowerCase()],
    examples: {},
    lastClickAt: 0,
    picking: false,
  })
  return { ok: true }
}

function mesmoAlvo(a, b) {
  return (a?.css && a.css === b?.css) || (a?.name && a.name === b?.name)
}

function adicionarPasso(estado, passo) {
  if (estado.steps.length >= MAX_PASSOS) return

  // Um valor que também foi capturado vem do dado, e não de um texto fixo
  if (passo.action === 'fill' || passo.action === 'select') {
    // Valores muito curtos, como "1", podem coincidir por acaso e ficam como texto fixo
    const dado = Object.entries(estado.examples).find(
      ([, exemplo]) => exemplo.length >= MIN_REFERENCIA && exemplo === passo.value,
    )
    if (dado && !passo.sensitive) {
      passo.value_from_capture = dado[0]
      delete passo.value
    }
    // Vários eventos no mesmo campo são uma ação só
    const ultimo = estado.steps.at(-1)
    if (ultimo?.action === passo.action && mesmoAlvo(ultimo.target, passo.target)) {
      estado.steps[estado.steps.length - 1] = passo
      return
    }
  }

  if (passo.action === 'capture') {
    estado.examples[passo.capture_name] = passo.capture_kind === 'table' ? '' : (passo.example ?? '')
    delete passo.example
  }
  if (passo.action === 'click') estado.lastClickAt = Date.now()
  estado.steps.push(passo)
}

async function enviar(estado) {
  estado.sending = true
  estado.error = null
  await salvarEstado(estado)
  await avisarAbas(estado)

  const corpo = {
    name: estado.name,
    start_url: estado.startUrl,
    allowed_hosts: estado.hosts,
    steps: estado.steps,
  }

  let resposta
  try {
    resposta = await fetch(`${estado.apiUrl}/flows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${estado.token}` },
      body: JSON.stringify(corpo),
      signal: AbortSignal.timeout(LIMITE_DO_ENVIO_MS - 2000),
    })
  } catch {
    return falhar(estado, 'Não foi possível falar com o Ditto. A gravação continua aqui: tente de novo.')
  }

  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}))
    if (resposta.status === 401) {
      return falhar(estado, 'A sessão desta gravação venceu. Comece uma nova gravação pelo painel.')
    }
    return falhar(estado, erro.detail ?? 'O Ditto recusou a gravação.')
  }

  const { id } = await resposta.json()
  const destino = `${estado.panelUrl}/painel/tarefas/${id}`
  const [abaFinal] = estado.tabIds
  await limparEstado()
  for (const tabId of estado.tabIds) {
    chrome.tabs.sendMessage(tabId, { type: 'ditto:state', state: { recording: false } }, { frameId: 0 }).catch(() => {})
  }
  try {
    await chrome.tabs.update(abaFinal, { url: destino, active: true })
  } catch {
    await chrome.tabs.create({ url: destino })
  }
  return { ok: true, id }
}

async function falhar(estado, mensagem) {
  estado.sending = false
  estado.error = mensagem
  await salvarEstado(estado)
  await avisarAbas(estado)
  return { ok: false, error: mensagem }
}

async function parar() {
  const estado = await lerEstado()
  if (!estado) return { ok: false, error: 'Nenhuma gravação em andamento.' }
  if (estado.steps.length < 2) return falhar(estado, 'Nada foi gravado ainda. Faça a tarefa antes de salvar.')
  return enviar(estado)
}

async function descartar() {
  const estado = await lerEstado()
  await limparEstado()
  for (const tabId of estado?.tabIds ?? []) {
    chrome.tabs.sendMessage(tabId, { type: 'ditto:state', state: { recording: false } }, { frameId: 0 }).catch(() => {})
  }
  return { ok: true }
}

async function tratarDaAba(mensagem, remetente) {
  const estado = await lerEstado()
  const tabId = remetente.tab?.id
  // Aba fora da gravação não escreve nada
  if (!estado || !estado.tabIds.includes(tabId)) return { recording: false }

  switch (mensagem.type) {
    case 'ditto:hello':
      return resumo(estado)
    case 'ditto:step':
      adicionarPasso(estado, mensagem.step)
      await salvarEstado(estado)
      await avisarAbas(estado)
      return { ok: true }
    case 'ditto:move':
      estado.corner = ((estado.corner ?? 0) + 1) % QUANTIDADE_DE_CANTOS
      await salvarEstado(estado)
      await avisarAbas(estado)
      return { ok: true }
    case 'ditto:warn':
      estado.warning = mensagem.text
      await salvarEstado(estado)
      await avisarAbas(estado)
      return { ok: true }
    case 'ditto:pick-start':
    case 'ditto:pick-stop': {
      estado.picking = mensagem.type === 'ditto:pick-start'
      await salvarEstado(estado)
      // Vai para todos os iframes: o dado pode estar em qualquer um
      chrome.tabs.sendMessage(tabId, { type: mensagem.type }).catch(() => {})
      await avisarAbas(estado)
      return { ok: true }
    }
    case 'ditto:picked':
      estado.picking = false
      await salvarEstado(estado)
      chrome.tabs.sendMessage(tabId, { type: 'ditto:pick-stop' }).catch(() => {})
      // O formulário para dar nome ao dado fica na barra, no topo da página
      chrome.tabs.sendMessage(tabId, { type: 'ditto:picked', pick: mensagem.pick }, { frameId: 0 }).catch(() => {})
      await avisarAbas(estado)
      return { ok: true }
    default:
      return { ok: false }
  }
}

function aoReceber(mensagem, remetente) {
  if (remetente.id !== chrome.runtime.id) return Promise.resolve({ ok: false })

  // O painel só fala pela ponte, que só existe nas origens do manifest
  if (['ditto:ping', 'ditto:start'].includes(mensagem.type)) {
    if (!origensDoPainel().includes(new URL(remetente.url).origin)) {
      return Promise.resolve({ ok: false, error: 'Origem não autorizada.' })
    }
    if (mensagem.type === 'ditto:ping') {
      return enfileirar(async () => ({
        ok: true,
        version: chrome.runtime.getManifest().version,
        ...resumo(await lerEstado()),
      }))
    }
    return enfileirar(() => iniciar(mensagem))
  }

  if (mensagem.type === 'ditto:status') return enfileirar(async () => resumo(await lerEstado()))
  if (mensagem.type === 'ditto:stop') return enfileirar(parar, LIMITE_DO_ENVIO_MS)
  if (mensagem.type === 'ditto:discard') return enfileirar(descartar)
  return enfileirar(() => tratarDaAba(mensagem, remetente))
}

chrome.runtime.onMessage.addListener((mensagem, remetente, responder) => {
  aoReceber(mensagem, remetente).then(responder, () =>
    responder({ ok: false, error: 'A extensão demorou demais para responder. Tente de novo.' }),
  )
  return true
})

// Fora da gravação, nada é injetado em nenhuma página
chrome.webNavigation.onCommitted.addListener((detalhes) => {
  enfileirar(async () => {
    const estado = await lerEstado()
    if (!estado?.tabIds.includes(detalhes.tabId)) return
    if (!/^https?:/.test(detalhes.url)) return

    // Fora da fila: injetar em uma página que está mudando pode demorar ou nunca responder
    injetar(detalhes.tabId, detalhes.frameId)
    if (detalhes.frameId !== 0) return

    const host = hostDe(detalhes.url)
    if (host && !estado.hosts.includes(host) && estado.hosts.length < MAX_DOMINIOS) estado.hosts.push(host)

    // Endereço digitado à mão é um passo. Navegação causada por clique já está no clique.
    const digitado = ['typed', 'generated', 'auto_bookmark'].includes(detalhes.transitionType)
    const ultimo = estado.steps.findLast((passo) => passo.action === 'navigate')
    if (digitado && estado.steps.length < MAX_PASSOS && ultimo?.url !== detalhes.url) {
      estado.steps.push({ action: 'navigate', url: detalhes.url })
    }
    await salvarEstado(estado)
    await avisarAbas(estado)
  })
})

// Só entra na gravação a janela que a própria página abriu. Uma aba aberta pela pessoa fica de fora,
// e por isso não dá para usar tabs.onCreated: o openerTabId também vem preenchido nesse caso.
chrome.webNavigation.onCreatedNavigationTarget.addListener((detalhes) => {
  enfileirar(async () => {
    const estado = await lerEstado()
    if (!estado?.tabIds.includes(detalhes.sourceTabId) || estado.tabIds.includes(detalhes.tabId)) return
    estado.tabIds.push(detalhes.tabId)
    await salvarEstado(estado)
  })
})

chrome.tabs.onRemoved.addListener((tabId) => {
  enfileirar(async () => {
    const estado = await lerEstado()
    if (!estado || estado.tabIds.length <= 1 || !estado.tabIds.includes(tabId)) return
    estado.tabIds = estado.tabIds.filter((id) => id !== tabId)
    await salvarEstado(estado)
  })
})

function extensaoDe(caminho) {
  const nome = caminho?.split(/[\\/]/).pop() ?? ''
  const extensao = nome.includes('.') ? nome.split('.').pop().toLowerCase() : ''
  return /^[a-z0-9]{1,12}$/.test(extensao) ? extensao : null
}

function extensaoDaUrl(url) {
  try {
    return extensaoDe(new URL(url).pathname)
  } catch {
    return null
  }
}

function marcarDownload(extensao, { confirmada }) {
  if (!extensao) return
  enfileirar(async () => {
    const estado = await lerEstado()
    if (!estado || Date.now() - estado.lastClickAt > JANELA_DOWNLOAD_MS) return

    const clique = estado.steps.findLast((passo) => passo.action === 'click')
    if (clique && (confirmada || !clique.downloaded_extension)) {
      clique.downloaded_extension = extensao
      await salvarEstado(estado)
    }
  })
}

// O endereço é só um palpite: o nome real do arquivo costuma chegar depois e tem prioridade
chrome.downloads.onCreated.addListener((item) => {
  const doArquivo = extensaoDe(item.filename)
  marcarDownload(doArquivo ?? extensaoDaUrl(item.finalUrl || item.url), { confirmada: Boolean(doArquivo) })
})
chrome.downloads.onChanged.addListener((mudanca) => {
  marcarDownload(extensaoDe(mudanca.filename?.current), { confirmada: true })
})
