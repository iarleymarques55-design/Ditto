// Injetado só nas abas que estão sendo gravadas. Observa a página e nunca altera o que ela faz,
// exceto no modo de escolher um dado, em que o clique é só para apontar.
(() => {
  if (window.__dittoGravando) return
  window.__dittoGravando = true

  const NO_TOPO = window === window.top
  const SENSIVEL_AUTOCOMPLETE = /password|cc-|one-time-code/i
  const SENSIVEL_NOME = /senha|password|passwd|pwd|cvv|cvc|card.?number|numero.?cartao|token|secret/i
  const CLICAVEL =
    'a,button,summary,input[type=submit],input[type=button],input[type=reset],input[type=image],' +
    '[role=button],[role=link],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],[role=tab],[role=option],' +
    '[role=checkbox],[role=radio],[role=switch],[role=treeitem],[role=combobox],[onclick]'
  const ATRIBUTOS_DE_TESTE = ['data-testid', 'data-test-id', 'data-test', 'data-cy', 'data-qa']
  const CAMPOS_DE_TEXTO = ['text', 'email', 'tel', 'url', 'search', 'number', 'date', 'datetime-local', 'month', 'time', 'week']

  let host = null
  let escolhendo = false
  let realce = null

  const limpar = (texto) => (texto ?? '').replace(/\s+/g, ' ').trim()
  const cortar = (texto, tamanho) => limpar(texto).slice(0, tamanho) || undefined
  // O serviço da extensão dorme quando fica ocioso, e a mensagem pode chegar enquanto ele acorda
  async function enviar(mensagem, tentativas = 3) {
    for (let tentativa = 1; tentativa <= tentativas; tentativa++) {
      try {
        return await chrome.runtime.sendMessage(mensagem)
      } catch {
        await new Promise((resolver) => setTimeout(resolver, 200 * tentativa))
      }
    }
    if (NO_TOPO && estadoAtual?.recording) {
      estadoAtual.warning = 'Uma ação não foi anotada. Confira os passos e, se faltar algo, grave de novo.'
      desenhar()
    }
    return null
  }

  // Eventos da própria barra de gravação não são parte da tarefa
  const naBarra = (evento) => host && evento.composedPath().includes(host)

  function ehSensivel(el) {
    if (el.type === 'password') return true
    const autocomplete = el.getAttribute?.('autocomplete') ?? ''
    if (SENSIVEL_AUTOCOMPLETE.test(autocomplete)) return true
    return SENSIVEL_NOME.test(`${el.name ?? ''} ${el.id ?? ''}`)
  }

  function papel(el) {
    const explicito = el.getAttribute('role')
    if (explicito) return explicito
    const tag = el.tagName
    if (tag === 'A') return 'link'
    if (tag === 'BUTTON' || tag === 'SUMMARY') return 'button'
    if (tag === 'SELECT') return 'combobox'
    if (tag === 'TEXTAREA' || el.isContentEditable) return 'textbox'
    if (tag === 'INPUT') {
      if (['submit', 'button', 'reset', 'image'].includes(el.type)) return 'button'
      if (el.type === 'checkbox' || el.type === 'radio') return el.type
      if (el.type === 'search') return 'searchbox'
      if (el.type === 'number') return 'spinbutton'
      return 'textbox'
    }
    return 'generic'
  }

  function textoVisivel(el) {
    if (el.tagName === 'INPUT') {
      // Só em botões o "value" é um texto da tela. Em campos, é o que a pessoa digitou.
      return ['submit', 'button', 'reset'].includes(el.type) ? el.getAttribute('value') : ''
    }
    if (el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' || el.isContentEditable) return ''
    return el.innerText
  }

  function rotulo(el) {
    const aria = el.getAttribute('aria-label')
    if (aria) return aria
    const referencia = el.getAttribute('aria-labelledby')
    if (referencia) {
      const alvo = document.getElementById(referencia.split(' ')[0])
      if (alvo) return alvo.innerText
    }
    return el.labels?.[0]?.innerText ?? ''
  }

  function ehUnico(seletor, raiz) {
    try {
      return raiz.querySelectorAll(seletor).length === 1
    } catch {
      return false
    }
  }

  const idEstavel = (el) => el.id && /^[A-Za-z][\w-]*$/.test(el.id) && !/\d{3,}/.test(el.id)

  // O seletor precisa apontar para um elemento só: botões iguais em uma lista só se distinguem por ele
  function seletorCss(el) {
    const raiz = el.getRootNode()
    for (const atributo of ATRIBUTOS_DE_TESTE) {
      const valor = el.getAttribute(atributo)
      const seletor = valor && `[${atributo}="${CSS.escape(valor)}"]`
      if (seletor && ehUnico(seletor, raiz)) return seletor
    }

    let caminho = ''
    let no = el
    while (no?.nodeType === 1 && no !== document.documentElement && no !== document.body) {
      let parte
      if (idEstavel(no) && ehUnico(`#${no.id}`, raiz)) {
        parte = `#${no.id}`
      } else {
        const iguais = no.parentElement ? [...no.parentElement.children].filter((irmao) => irmao.tagName === no.tagName) : []
        const nome = no.tagName.toLowerCase()
        parte = iguais.length > 1 ? `${nome}:nth-of-type(${iguais.indexOf(no) + 1})` : nome
      }
      caminho = caminho ? `${parte} > ${caminho}` : parte
      if (ehUnico(caminho, raiz)) return caminho
      no = no.parentElement
    }
    return caminho
  }

  function vizinhos(el) {
    if (!el.parentElement) return []
    return [...el.parentElement.querySelectorAll(CLICAVEL)]
      .filter((outro) => outro !== el && outro.getClientRects().length > 0)
      .map((outro) => limpar(textoVisivel(outro) || rotulo(outro)).slice(0, 200))
      .filter(Boolean)
      .slice(0, 5)
  }

  function impressaoDigital(el) {
    const alvo = {
      role: papel(el) === 'generic' ? undefined : papel(el),
      tag: el.tagName.toLowerCase(),
      text: cortar(textoVisivel(el), 300),
      label: cortar(rotulo(el), 300),
      placeholder: cortar(el.getAttribute('placeholder'), 300),
      name: cortar(el.getAttribute('name'), 200),
      test_id: cortar(el.getAttribute('data-testid'), 200),
      css: seletorCss(el).slice(0, 1000) || undefined,
      input_type: el.tagName === 'INPUT' ? el.type : undefined,
      autocomplete: cortar(el.getAttribute('autocomplete'), 80),
    }
    const perto = vizinhos(el)
    if (perto.length) alvo.neighbors = perto
    return Object.fromEntries(Object.entries(alvo).filter(([, valor]) => valor !== undefined))
  }

  function gravar(passo) {
    enviar({ type: 'ditto:step', step: passo })
  }

  // Enter e "change" avisam do mesmo preenchimento: o que já foi gravado não é gravado de novo
  const jaGravado = new WeakMap()
  // O valor é guardado a cada tecla: o site pode trocar o campo antes de a pessoa sair dele
  let digitando = null

  function campoDe(origem) {
    if (!(origem instanceof Element)) return null
    if (origem.isContentEditable) {
      let raiz = origem
      while (raiz.parentElement?.isContentEditable) raiz = raiz.parentElement
      return raiz
    }
    if (origem.tagName === 'TEXTAREA') return origem
    if (origem.tagName === 'INPUT' && (CAMPOS_DE_TEXTO.includes(origem.type) || origem.type === 'password')) return origem
    return null
  }

  function valorDe(el) {
    if (!el.isContentEditable) return el.value
    // Editores colocam marcas invisíveis e linhas em branco entre os blocos
    return el.innerText.replace(/[\uFEFF\u200B]/g, '').replace(/\n{2,}/g, '\n').replace(/\n+$/, '')
  }

  function comecarDigitacao(el) {
    // O valor de um campo sensível nunca é lido
    const sensivel = ehSensivel(el)
    const alvo = digitando?.el === el ? digitando.alvo : impressaoDigital(el)
    digitando = { el, sensivel, alvo, valor: sensivel ? '' : valorDe(el) }
  }

  function terminarDigitacao() {
    if (!digitando) return
    const { el, sensivel, alvo, valor } = digitando
    digitando = null
    if (!sensivel && !valor) return

    const marca = sensivel ? 'sensivel' : valor
    if (jaGravado.get(el) === marca) return
    jaGravado.set(el, marca)
    enviar({
      type: 'ditto:step',
      step: sensivel ? { action: 'fill', sensitive: true, target: alvo } : { action: 'fill', value: valor.slice(0, 5000), target: alvo },
    })
  }

  // O que foi digitado vem antes de qualquer outra ação
  function gravar(passo) {
    terminarDigitacao()
    enviar({ type: 'ditto:step', step: passo })
  }

  function gravarCampo(el) {
    if (digitando && digitando.el !== el) terminarDigitacao()
    comecarDigitacao(el)
    terminarDigitacao()
  }

  document.addEventListener(
    'input',
    (evento) => {
      if (!evento.isTrusted || naBarra(evento)) return
      const el = campoDe(evento.composedPath()[0])
      if (!el) return
      if (digitando && digitando.el !== el) terminarDigitacao()
      jaGravado.delete(el)
      comecarDigitacao(el)
    },
    true,
  )
  document.addEventListener(
    'focusout',
    (evento) => {
      if (evento.isTrusted && !naBarra(evento)) terminarDigitacao()
    },
    true,
  )
  window.addEventListener('pagehide', terminarDigitacao, true)

  // Sites modernos fazem botões com elementos comuns: o sinal é a mãozinha do mouse
  const JANELA_SEM_CLIQUE_MS = 300
  const AREA_MAXIMA_DE_BOTAO = 0.5

  function comMaozinha(el) {
    return getComputedStyle(el).cursor === 'pointer'
  }

  function alvoClicavel(origem) {
    if (origem.closest('select,textarea,[contenteditable=true],[contenteditable=""]')) return null
    if (origem.matches('input') && !origem.matches('[type=submit],[type=button],[type=reset],[type=image]')) return null
    // O clique no rótulo aciona o próprio campo, que é gravado pela mudança
    if (origem.closest('label')?.control) return null

    const semantico = origem.closest(CLICAVEL)
    if (semantico) return semantico.matches('[disabled]') ? null : semantico
    if (!comMaozinha(origem)) return null

    // A mãozinha é herdada: o botão é o elemento mais de fora que ainda parece um botão
    let el = origem
    const areaDaTela = window.innerWidth * window.innerHeight
    for (let nivel = 0; nivel < 6; nivel++) {
      const pai = el.parentElement
      if (!pai || pai === document.body || !comMaozinha(pai)) break
      const caixa = pai.getBoundingClientRect()
      if (caixa.width * caixa.height > areaDaTela * AREA_MAXIMA_DE_BOTAO) break
      el = pai
    }
    return el === document.documentElement || el === document.body ? null : el
  }

  // A impressão digital sai no apertar do botão: menus costumam mudar ou sumir antes do clique
  let apertado = null

  document.addEventListener(
    'pointerdown',
    (evento) => {
      if (!evento.isTrusted || escolhendo || evento.button !== 0 || naBarra(evento)) return
      terminarDigitacao()
      // O clique anterior agiu e sumiu da página, e o próximo chegou antes do fim da espera
      if (apertado && !apertado.el.isConnected) gravar({ action: 'click', target: apertado.alvo })
      const origem = evento.composedPath()[0]
      const el = origem instanceof Element ? alvoClicavel(origem) : null
      apertado = el ? { el, alvo: impressaoDigital(el) } : null
    },
    true,
  )

  document.addEventListener(
    'pointerup',
    (evento) => {
      if (!evento.isTrusted || !apertado) return
      const esperado = apertado
      // Opção que age no apertar e some da página: o clique nunca chega
      setTimeout(() => {
        if (apertado !== esperado) return
        apertado = null
        if (!esperado.el.isConnected) gravar({ action: 'click', target: esperado.alvo })
      }, JANELA_SEM_CLIQUE_MS)
    },
    true,
  )

  // Enter em um campo faz o navegador "clicar" sozinho no botão de enviar. Esse clique não é da pessoa.
  let enterEm = 0
  const JANELA_DO_ENTER_MS = 100

  document.addEventListener(
    'click',
    (evento) => {
      if (!evento.isTrusted || escolhendo || naBarra(evento)) return
      if (evento.detail === 0 && performance.now() - enterEm < JANELA_DO_ENTER_MS) return

      const anterior = apertado
      apertado = null
      const origem = evento.composedPath()[0]
      if (anterior && (!anterior.el.isConnected || (origem instanceof Node && anterior.el.contains(origem)))) {
        gravar({ action: 'click', target: anterior.alvo })
        return
      }
      // Clique pelo teclado, sem botão apertado antes
      const el = origem instanceof Element ? alvoClicavel(origem) : null
      if (el) gravar({ action: 'click', target: impressaoDigital(el) })
    },
    true,
  )

  document.addEventListener(
    'change',
    (evento) => {
      if (!evento.isTrusted || naBarra(evento)) return
      const el = evento.composedPath()[0]
      if (el.type === 'file') {
        enviar({ type: 'ditto:warn', text: 'Envio de arquivo ainda não é gravado. Esta parte precisará ser feita à mão.' })
      } else if (el.tagName === 'SELECT') {
        const opcao = el.selectedOptions[0]?.text.trim().slice(0, 5000)
        if (opcao) gravar({ action: 'select', value: opcao, target: impressaoDigital(el) })
      } else if (el.type === 'checkbox' || el.type === 'radio') {
        gravar({ action: el.checked ? 'check' : 'click', target: impressaoDigital(el) })
      } else if (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && CAMPOS_DE_TEXTO.concat('password').includes(el.type))) {
        gravarCampo(el)
      }
    },
    true,
  )

  const JANELA_DO_ENVIO_MS = 80

  document.addEventListener(
    'keydown',
    (evento) => {
      if (!evento.isTrusted || evento.key !== 'Enter' || naBarra(evento)) return
      const el = campoDe(evento.composedPath()[0])
      if (!el) return

      if (el.tagName === 'INPUT') {
        enterEm = performance.now()
        // Enter pode enviar o formulário antes do "change": o valor precisa vir primeiro
        gravarCampo(el)
        gravar({ action: 'press', value: 'Enter', target: impressaoDigital(el) })
        return
      }

      // Em um texto longo, Enter é só uma linha nova. Em um chat, ele envia e o campo esvazia.
      if (evento.shiftKey || ehSensivel(el)) return
      const antes = valorDe(el)
      const alvo = impressaoDigital(el)
      setTimeout(() => {
        if (!antes || (el.isConnected && valorDe(el))) return
        digitando = { el, sensivel: false, alvo, valor: antes }
        jaGravado.delete(el)
        gravar({ action: 'press', value: 'Enter', target: alvo })
      }, JANELA_DO_ENVIO_MS)
    },
    true,
  )

  // Modo de escolher um dado da tela

  const REALCE = 'position:fixed;z-index:2147483646;pointer-events:none;border:2px solid #4b37a0;background:rgba(75,55,160,.15);border-radius:2px;display:none'

  function mostrarRealce(el) {
    if (!realce) {
      realce = document.createElement('div')
      realce.style.cssText = REALCE
      document.documentElement.appendChild(realce)
    }
    const caixa = el.getBoundingClientRect()
    Object.assign(realce.style, {
      display: 'block',
      left: `${caixa.left}px`,
      top: `${caixa.top}px`,
      width: `${caixa.width}px`,
      height: `${caixa.height}px`,
    })
  }

  function valorDoDado(el) {
    if (['INPUT', 'TEXTAREA'].includes(el.tagName)) return limpar(el.value)
    if (el.tagName === 'SELECT') return limpar(el.selectedOptions[0]?.text)
    return limpar(el.innerText)
  }

  const curto = (texto) => texto && texto.length <= 60

  function ancoraDe(el) {
    const celula = el.closest('td')
    const tabela = celula?.closest('table')
    if (celula && tabela) {
      const cabecalho = tabela.tHead?.rows[0] ?? tabela.rows[0]
      const titulo = limpar(cabecalho?.cells[celula.cellIndex]?.innerText)
      if (cabecalho && cabecalho !== celula.parentElement && curto(titulo)) {
        const linhas = [...tabela.rows].filter((linha) => linha !== cabecalho)
        return { anchor: titulo, anchor_kind: 'table_header', row_index: linhas.indexOf(celula.parentElement) }
      }
    }

    const descricao = el.closest('dd')
    if (descricao?.previousElementSibling?.tagName === 'DT') {
      return { anchor: limpar(descricao.previousElementSibling.innerText), anchor_kind: 'definition' }
    }

    if (el.labels?.[0] && curto(limpar(el.labels[0].innerText))) {
      return { anchor: limpar(el.labels[0].innerText), anchor_kind: 'label' }
    }

    const texto = limpar(el.innerText)
    const pedaco = /^([^:]{1,60}):\s*(.+)$/.exec(texto)
    if (pedaco && el.children.length === 0) {
      return { anchor: pedaco[1].trim(), anchor_kind: 'inline', valor: pedaco[2].trim() }
    }

    const antes = el.previousElementSibling
    if (antes?.children.length === 0 && curto(limpar(antes.innerText))) {
      return { anchor: limpar(antes.innerText), anchor_kind: 'adjacent' }
    }
    const antesDoPai = el.parentElement?.previousElementSibling
    if (antesDoPai?.children.length === 0 && curto(limpar(antesDoPai.innerText)) && el.parentElement.children.length === 1) {
      return { anchor: limpar(antesDoPai.innerText), anchor_kind: 'adjacent', elemento: el.parentElement }
    }
    return null
  }

  function descrever(el) {
    if (ehSensivel(el)) return { recusado: 'Este campo é sigiloso e não pode ser capturado.' }

    const achado = ancoraDe(el)
    const alvo = {
      tag: el.tagName.toLowerCase(),
      css: seletorCss(el).slice(0, 1000) || undefined,
      test_id: cortar(el.getAttribute('data-testid'), 200),
    }
    if (achado) {
      alvo.anchor = achado.anchor.slice(0, 300)
      alvo.anchor_kind = achado.anchor_kind
      if (achado.row_index !== undefined) alvo.row_index = achado.row_index
    }

    const pick = {
      target: Object.fromEntries(Object.entries(alvo).filter(([, valor]) => valor !== undefined)),
      preview: (achado?.valor ?? valorDoDado(achado?.elemento ?? el)).slice(0, 200),
      suggestedName: achado?.anchor ?? '',
      hasAnchor: Boolean(achado),
    }

    const tabela = el.closest('table')
    if (tabela) {
      const cabecalho = tabela.tHead?.rows[0] ?? tabela.rows[0]
      pick.table = {
        target: {
          tag: 'table',
          css: seletorCss(tabela).slice(0, 1000),
          neighbors: [...(cabecalho?.cells ?? [])].map((celula) => limpar(celula.innerText).slice(0, 200)).filter(Boolean).slice(0, 10),
        },
        rows: Math.max(tabela.rows.length - 1, 0),
      }
    }
    return pick
  }

  function aoMover(evento) {
    const el = evento.composedPath()[0]
    if (el instanceof Element && !naBarra(evento)) mostrarRealce(el)
  }

  // Bloqueia só durante a escolha: o clique não pode acionar nada na página
  function aoApontar(evento) {
    if (!evento.isTrusted || naBarra(evento)) return
    evento.preventDefault()
    evento.stopImmediatePropagation()
    if (evento.type !== 'click') return
    const el = evento.composedPath()[0]
    if (el instanceof Element) enviar({ type: 'ditto:picked', pick: descrever(el) })
  }

  function aoTeclar(evento) {
    if (evento.key === 'Escape') enviar({ type: 'ditto:pick-stop' })
  }

  const EVENTOS_DE_CLIQUE = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']

  function comecarEscolha() {
    if (escolhendo) return
    escolhendo = true
    document.addEventListener('mousemove', aoMover, true)
    document.addEventListener('keydown', aoTeclar, true)
    for (const nome of EVENTOS_DE_CLIQUE) window.addEventListener(nome, aoApontar, true)
  }

  function pararEscolha() {
    escolhendo = false
    document.removeEventListener('mousemove', aoMover, true)
    document.removeEventListener('keydown', aoTeclar, true)
    for (const nome of EVENTOS_DE_CLIQUE) window.removeEventListener(nome, aoApontar, true)
    if (realce) realce.style.display = 'none'
  }

  // A barra de gravação, só no topo da página

  const ESTILO = `
    :host { all: initial; }
    .barra[data-canto="0"] { bottom: 12px; right: 12px; }
    .barra[data-canto="1"] { bottom: 12px; left: 12px; }
    .barra[data-canto="2"] { top: 12px; left: 12px; }
    .barra[data-canto="3"] { top: 12px; right: 12px; }
    .barra { position: fixed; z-index: 2147483647; width: 320px; box-sizing: border-box;
      background: #fdfdfb; color: #13104f; border: 1px solid rgba(70,48,20,.15); border-radius: 3px; padding: 12px 14px;
      font: 14px/1.4 system-ui, -apple-system, 'Segoe UI', sans-serif; box-shadow: 8px 14px 26px -12px rgba(70,48,20,.55); }
    .topo { display: flex; align-items: center; gap: 8px; font-weight: 600; }
    .topo span[data-tempo] { flex: 1; }
    .topo button { min-height: 28px; padding: 0 8px; font-size: 12.5px; border-color: rgba(71,86,127,.5); color: #47567f; }
    .ultimo { margin-top: 2px; font-size: 13px; color: #1c7355; font-weight: 500; overflow-wrap: anywhere; }
    .ponto { width: 10px; height: 10px; border-radius: 50%; background: #ad2a1e; flex: none; }
    .info { color: #47567f; font-size: 13px; margin-top: 2px; }
    .acoes { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    button { font: inherit; font-size: 13.5px; font-weight: 500; min-height: 36px; padding: 0 12px; border-radius: 999px; cursor: pointer;
      border: 1px solid #4b37a0; background: transparent; color: #4b37a0; }
    button.cheio { background: #4b37a0; color: #fff; }
    button.leve { border-color: transparent; text-decoration: underline; padding: 0 6px; color: #47567f; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    button:focus-visible, input:focus-visible { outline: 2px solid #4b37a0; outline-offset: 2px; }
    .erro { margin-top: 8px; color: #ad2a1e; font-size: 13px; font-weight: 500; }
    .form { margin-top: 10px; border-top: 1px dashed #b7a9dc; padding-top: 10px; }
    .previa { font-size: 13px; color: #47567f; word-break: break-word; }
    .previa b { color: #13104f; font-weight: 600; }
    label.campo { display: block; font-size: 13px; font-weight: 500; margin-top: 8px; }
    input[type=text] { display: block; width: 100%; box-sizing: border-box; margin-top: 3px; min-height: 36px; padding: 0 8px; font: inherit;
      color: #13104f; background: #fff; border: 1px solid rgba(71,86,127,.6); border-radius: 2px; }
    label.opcao { display: flex; gap: 6px; align-items: center; font-size: 13px; margin-top: 6px; cursor: pointer; }
    .aviso { margin-top: 6px; font-size: 12.5px; color: #ad2a1e; }
  `

  function criarBarra() {
    host = document.createElement('ditto-gravador')
    // Fechada: os scripts da página não alcançam os botões da gravação
    const sombra = host.attachShadow({ mode: 'closed' })
    sombra.innerHTML = `<style>${ESTILO}</style><div class="barra" part="barra"></div>`
    document.documentElement.appendChild(host)
    return sombra.querySelector('.barra')
  }

  let barra = null
  let estadoAtual = null
  let formulario = null
  let relogio = null
  let partes = {}
  let ultimoFormulario = 0

  const tempo = (inicio) => {
    const segundos = Math.max(0, Math.floor((Date.now() - inicio) / 1000))
    return `${String(Math.floor(segundos / 60)).padStart(2, '0')}:${String(segundos % 60).padStart(2, '0')}`
  }

  const escapar = (texto) => {
    const div = document.createElement('div')
    div.textContent = texto
    return div.innerHTML
  }

  function desenhar() {
    const estado = estadoAtual
    if (!estado?.recording) {
      host?.remove()
      host = null
      barra = null
      clearInterval(relogio)
      return
    }
    if (!barra) {
      barra = criarBarra()
      barra.innerHTML = `
        <div class="topo"><span class="ponto"></span><span data-tempo></span><button data-acao="mover" title="Mudar a barra de canto, se ela cobrir algo do site">Mover</button></div>
        <div data-parte="info"></div>
        <div data-parte="acoes"></div>`
      partes = {}
      aoClicarNaBarra('[data-acao=mover]', () => enviar({ type: 'ditto:move' }))
    }
    barra.dataset.canto = estado.corner ?? 0
    barra.querySelector('[data-tempo]').textContent = `Gravando ${tempo(estado.startedAt)}`

    const passos = `${estado.steps} ${estado.steps === 1 ? 'passo' : 'passos'}`
    desenharParte(
      'info',
      `<div class="info">${escapar(estado.name)}, ${passos}</div>
      ${estado.last ? `<div class="ultimo">Anotado: ${escapar(estado.last)}</div>` : ''}
      ${estado.picking ? '<div class="info"><b>Clique no dado que quer capturar.</b> Esc cancela.</div>' : ''}
      ${estado.limitReached ? '<div class="aviso">Limite de 200 passos: novas ações não são gravadas.</div>' : ''}
      ${estado.warning ? `<div class="aviso">${escapar(estado.warning)}</div>` : ''}
      ${estado.error ? `<div class="erro" role="alert">${escapar(estado.error)}</div>` : ''}`,
    )

    if (formulario) {
      // O formulário só é refeito quando é outro dado: a pessoa pode estar digitando nele
      if (desenharParte('acoes', desenharFormulario(), `formulario-${formulario.id}`)) ligarFormulario()
      return
    }
    const acoes = `<div class="acoes">
        <button data-acao="capturar" ${estado.picking ? 'disabled' : ''}>Capturar dado</button>
        <button data-acao="parar" class="cheio" ${estado.sending ? 'disabled' : ''}>${estado.sending ? 'Salvando...' : 'Parar e salvar'}</button>
        <button data-acao="descartar" class="leve" ${estado.sending ? 'disabled' : ''}>Descartar</button>
      </div>`
    if (desenharParte('acoes', acoes)) {
      aoClicarNaBarra('[data-acao=capturar]', () => enviar({ type: 'ditto:pick-start' }))
      aoClicarNaBarra('[data-acao=parar]', () => enviar({ type: 'ditto:stop' }))
      aoClicarNaBarra('[data-acao=descartar]', () => {
        if (window.confirm('Descartar esta gravação? O que foi feito até agora se perde.')) enviar({ type: 'ditto:discard' })
      })
    }
  }

  // Um botão refeito entre apertar e soltar o mouse perde o clique: só muda o que mudou de verdade
  function desenharParte(nome, html, chave = html) {
    if (partes[nome] === chave) return false
    partes[nome] = chave
    barra.querySelector(`[data-parte=${nome}]`).innerHTML = html
    return true
  }

  // Só um clique de verdade aciona a barra
  function aoClicarNaBarra(seletor, acao) {
    barra.querySelector(seletor)?.addEventListener('click', (evento) => {
      if (evento.isTrusted) acao()
    })
  }

  function desenharFormulario() {
    if (formulario.recusado) {
      return `<div class="form"><div class="erro">${escapar(formulario.recusado)}</div><div class="acoes"><button data-form="cancelar">Entendi</button></div></div>`
    }
    const tabela = formulario.table
    return `<div class="form">
      <div class="previa">Valor agora: <b>${escapar(formulario.preview || '(vazio)')}</b></div>
      ${formulario.hasAnchor ? '' : '<div class="aviso">Não achei um rótulo perto deste dado. Se o site mudar, o Ditto pode não encontrá-lo.</div>'}
      <label class="campo">Como chamar este dado?<input type="text" data-form="nome" maxlength="120" value="${escapar(formulario.nome).replaceAll('"', '&quot;')}"></label>
      ${
        tabela
          ? `<label class="opcao"><input type="radio" name="tipo" value="value" ${formulario.tipo === 'value' ? 'checked' : ''}> Só este valor</label>
             <label class="opcao"><input type="radio" name="tipo" value="table" ${formulario.tipo === 'table' ? 'checked' : ''}> A tabela inteira (${tabela.rows} ${tabela.rows === 1 ? 'linha' : 'linhas'})</label>`
          : ''
      }
      <div class="erro" data-form="erro" hidden></div>
      <div class="acoes"><button class="cheio" data-form="salvar">Salvar</button><button class="leve" data-form="cancelar">Cancelar</button></div>
    </div>`
  }

  function ligarFormulario() {
    aoClicarNaBarra('[data-form=cancelar]', () => {
      formulario = null
      desenhar()
    })
    const nome = barra.querySelector('[data-form=nome]')
    if (!nome) return
    nome.focus()
    nome.addEventListener('input', () => {
      formulario.nome = nome.value
    })
    for (const opcao of barra.querySelectorAll('input[name=tipo]')) {
      opcao.addEventListener('change', () => {
        formulario.tipo = opcao.value
      })
    }
    aoClicarNaBarra('[data-form=salvar]', () => {
      const texto = limpar(nome.value)
      const erro = barra.querySelector('[data-form=erro]')
      if (!texto) {
        erro.hidden = false
        erro.textContent = 'Escreva um nome para o dado.'
        return
      }
      if (estadoAtual.captures.some((nomeJaUsado) => nomeJaUsado.toLowerCase() === texto.toLowerCase())) {
        erro.hidden = false
        erro.textContent = 'Já existe um dado com este nome.'
        return
      }
      const ehTabela = formulario.tipo === 'table'
      gravar({
        action: 'capture',
        capture_name: texto,
        capture_kind: ehTabela ? 'table' : 'value',
        target: ehTabela ? formulario.table.target : formulario.target,
        example: ehTabela ? '' : formulario.preview,
      })
      formulario = null
      desenhar()
    })
  }

  chrome.runtime.onMessage.addListener((mensagem) => {
    if (mensagem.type === 'ditto:pick-start') comecarEscolha()
    if (mensagem.type === 'ditto:pick-stop') pararEscolha()
    if (!NO_TOPO) return

    if (mensagem.type === 'ditto:state') {
      estadoAtual = mensagem.state
      desenhar()
    }
    if (mensagem.type === 'ditto:picked') {
      const pick = mensagem.pick
      formulario = { ...pick, nome: pick.suggestedName ?? '', tipo: 'value', id: ++ultimoFormulario }
      desenhar()
    }
  })

  if (NO_TOPO) {
    // O script entra antes de a página existir: a barra espera o documento para aparecer
    const anunciar = () =>
      chrome.runtime.sendMessage({ type: 'ditto:hello' }).then((estado) => {
        if (estado?.recording) {
          estadoAtual = estado
          desenhar()
          if (estado.picking) comecarEscolha()
          relogio = setInterval(() => {
            const rotuloTempo = barra?.querySelector('[data-tempo]')
            if (rotuloTempo && estadoAtual?.recording) rotuloTempo.textContent = `Gravando ${tempo(estadoAtual.startedAt)}`
          }, 1000)
        }
      }, () => {})
    if (document.documentElement) anunciar()
    else document.addEventListener('readystatechange', anunciar, { once: true })
  } else {
    chrome.runtime.sendMessage({ type: 'ditto:hello' }).then((estado) => {
      if (estado?.picking) comecarEscolha()
    }, () => {})
  }
})()
