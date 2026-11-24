const conteudo = document.getElementById('conteudo')
// Aberta pela extensão quando o painel pede para ligar este Chrome: fecha sozinha depois da resposta
const JANELA_DE_CONFIRMACAO = new URLSearchParams(location.search).has('ligar')

function criar(tag, propriedades = {}, texto = '') {
  const el = document.createElement(tag)
  Object.assign(el, propriedades)
  if (texto) el.textContent = texto
  return el
}

const TEXTO_DO_EXECUTOR = {
  conectado: 'Executor ligado: as tarefas rodam neste Chrome.',
  conectando: 'Executor: procurando o worker do Ditto...',
  desconectado: 'Executor: o worker do Ditto não está no ar. As tarefas esperam na fila.',
  recusado: 'Executor desligado: a ligação expirou ou foi encerrada. Ligue de novo pela página da conta do painel.',
  'em-uso': 'Executor: outro Chrome já está ligado nesta conta. As tarefas rodam nele.',
  'sem-token': 'Executor desligado. Para rodar as tarefas neste Chrome, ligue pela página da conta do painel.',
  'aguardando-confirmacao': 'Executor: esperando você confirmar a conta.',
}

const LIGADO = ['conectado', 'conectando', 'desconectado', 'em-uso']

function blocoDoExecutor(estado) {
  const bloco = criar('div', { className: estado.runner === 'conectado' ? 'executor ligado' : 'executor' })
  bloco.append(criar('p', {}, TEXTO_DO_EXECUTOR[estado.runner] ?? ''))
  if (estado.runnerAccount && LIGADO.includes(estado.runner)) {
    bloco.append(criar('p', { className: 'conta' }, `Conta: ${estado.runnerAccount}`))
  }
  if (LIGADO.includes(estado.runner)) {
    const desligar = criar('button', { className: 'leve' }, 'Desligar este Chrome')
    desligar.addEventListener('click', async () => {
      desligar.disabled = true
      await chrome.runtime.sendMessage({ type: 'ditto:runner-off' })
      desenhar()
    })
    bloco.append(desligar)
  }
  return bloco
}

// O painel pediu para ligar este Chrome. A pessoa vê qual conta é antes de aceitar.
function desenharConfirmacao(estado) {
  const conta = estado.runnerPending.account
  conteudo.append(
    criar('h1', {}, 'Ligar este Chrome ao Ditto?'),
    criar(
      'p',
      {},
      conta
        ? `As tarefas da conta ${conta} vão rodar neste Chrome, com as contas que estão logadas nele.`
        : 'As tarefas de uma conta do Ditto vão rodar neste Chrome, com as contas que estão logadas nele.',
    ),
  )
  if (estado.runnerAccount && estado.runnerAccount !== conta) {
    conteudo.append(criar('p', { className: 'erro' }, `Hoje este Chrome está ligado à conta ${estado.runnerAccount}.`))
  }
  conteudo.append(criar('p', {}, 'Só aceite se foi você quem clicou em "Ligar neste Chrome" no painel.'))

  const acoes = criar('div', { className: 'acoes' })
  const ligar = criar('button', { className: 'cheio' }, 'Ligar')
  const cancelar = criar('button', { className: 'leve' }, 'Cancelar')
  ligar.addEventListener('click', async () => {
    ligar.disabled = true
    cancelar.disabled = true
    await chrome.runtime.sendMessage({ type: 'ditto:runner-confirm' })
    if (JANELA_DE_CONFIRMACAO) window.close()
    else desenhar()
  })
  cancelar.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ditto:runner-cancel' })
    if (JANELA_DE_CONFIRMACAO) window.close()
    else desenhar()
  })
  acoes.append(ligar, cancelar)
  conteudo.append(acoes)
}

async function desenhar() {
  const estado = await chrome.runtime.sendMessage({ type: 'ditto:status' })
  conteudo.replaceChildren()

  if (estado?.runnerPending) {
    desenharConfirmacao(estado)
    return
  }
  if (JANELA_DE_CONFIRMACAO) {
    // O pedido expirou ou já foi respondido em outra janela
    window.close()
    return
  }

  if (!estado?.recording) {
    conteudo.append(
      criar('h1', {}, 'Nenhuma gravação agora'),
      criar('p', {}, 'Para gravar, abra o painel do Ditto e clique em "Gravar tarefa". Só as abas iniciadas por lá são gravadas.'),
      blocoDoExecutor(estado ?? {}),
    )
    return
  }

  const passos = `${estado.steps} ${estado.steps === 1 ? 'passo' : 'passos'}`
  conteudo.append(criar('h1', {}, estado.name), criar('p', {}, `Gravando, ${passos}.`))
  if (estado.error) conteudo.append(criar('p', { className: 'erro', role: 'alert' }, estado.error))

  const acoes = criar('div', { className: 'acoes' })
  const parar = criar('button', { className: 'cheio', disabled: estado.sending }, estado.sending ? 'Salvando...' : 'Parar e salvar')
  parar.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ditto:stop' })
    desenhar()
  })
  const descartar = criar('button', { className: 'leve', disabled: estado.sending }, 'Descartar')
  descartar.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ditto:discard' })
    desenhar()
  })
  acoes.append(parar, descartar)
  conteudo.append(acoes, blocoDoExecutor(estado))
}

desenhar()
