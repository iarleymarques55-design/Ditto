// Injetado só nas abas que estão sendo gravadas. Observa a página e nunca altera o que ela faz,
// exceto no modo de escolher um dado, em que o clique é só para apontar.
(() => {
  if (window.__dittoGravando) return
  window.__dittoGravando = true

  const NO_TOPO = window === window.top
  const SENSIVEL_AUTOCOMPLETE = /password|cc-|one-time-code/i
  const SENSIVEL_NOME = /senha|password|passwd|pwd|cvv|cvc|card.?number|numero.?cartao|token|secret/i
  // Siglas curtas só valem como palavra inteira: "pin" é senha, "spinner" não é
  const SENSIVEL_SIGLA = /(^|[^a-z])(pin|otp|2fa|mfa|cvv|cvc|csc)([^a-z]|$)/i
  // O que a pessoa lê na tela: rótulo, placeholder, aria-label
  const SENSIVEL_ROTULO =
    /senha|password|c[oó]digo (de )?(seguran[cç]a|verifica[cç][aã]o|acesso|confirma[cç][aã]o)|assinatura eletr[oô]nica|frase secreta|chave de seguran[cç]a|token|n[uú]mero do cart[aã]o/i
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
    const nomes = `${el.name ?? ''} ${el.id ?? ''}`
    if (SENSIVEL_NOME.test(nomes) || SENSIVEL_SIGLA.test(nomes)) return true
    // PIN, código do SMS e afins costumam vir em campo comum, sem nada no name: o rótulo entrega
    const naTela = `${el.getAttribute?.('aria-label') ?? ''} ${el.getAttribute?.('placeholder') ?? ''} ${rotulo(el) ?? ''}`
    return SENSIVEL_ROTULO.test(naTela) || SENSIVEL_SIGLA.test(naTela)
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

  // Planilhas desenhadas como imagem (Excel Online): as teclas vão para um campo escondido da
  // grade, que não serve na repetição. Cada célula vira "ir até ela pela Caixa de Nome" e
  // "escrever o valor na Barra de fórmulas", o caminho que o Ditto consegue repetir.
  const PLANILHA = {
    caixa: '#FormulaBar-NameBox-input',
    campos: '#gridKeyboardContentEditable_textElement, #formulaBarTextDivId_textElement',
    alvoCaixa: { css: '#FormulaBar-NameBox-input', tag: 'input', role: 'combobox', label: 'Caixa de Nome' },
    alvoBarra: { css: '#formulaBarTextDivId_textElement', tag: 'div', role: 'textbox', label: 'formula bar' },
  }
  const TECLAS_QUE_CONFIRMAM_A_CELULA = ['Enter', 'Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']
  // A célula sendo digitada agora: o endereço é lido da Caixa de Nome na primeira tecla
  let celulaEmEdicao = null

  function campoDePlanilha(origem) {
    return origem instanceof Element ? origem.closest(PLANILHA.campos) : null
  }

  function celulaAtiva() {
    const endereco = (document.querySelector(PLANILHA.caixa)?.value ?? '').replace(/[\u200e\u200f]/g, '').trim().toUpperCase()
    return /^[A-Z]{1,3}[1-9][0-9]{0,6}$/.test(endereco) ? endereco : null
  }

  function gravarCelula() {
    const celula = celulaEmEdicao
    celulaEmEdicao = null
    if (!celula?.endereco || !celula.valor) return
    // Uma quebra de linha no valor confirmaria a célula antes da hora na repetição
    const valor = celula.valor.replace(/\s*\n\s*/g, ' ').slice(0, 4990)
    const base = { action: 'fill', spreadsheet_cell: celula.endereco }
    gravar({ ...base, spreadsheet_part: 'address', target: PLANILHA.alvoCaixa, value: `${celula.endereco}\n` })
    gravar({ ...base, spreadsheet_part: 'value', target: PLANILHA.alvoBarra, value: `${valor}\n` })
  }

  document.addEventListener(
    'keydown',
    (evento) => {
      if (!evento.isTrusted || !celulaEmEdicao || naBarra(evento)) return
      if (evento.key === 'Escape') {
        celulaEmEdicao = null
        return
      }
      if (!TECLAS_QUE_CONFIRMAM_A_CELULA.includes(evento.key)) return
      // Na Barra de fórmulas as setas só andam pelo texto
      if (evento.key.startsWith('Arrow') && celulaEmEdicao.el.id.startsWith('formulaBar')) return
      // Lido antes de o Excel limpar o campo: este ouvinte roda primeiro
      celulaEmEdicao.valor = valorDe(celulaEmEdicao.el) || celulaEmEdicao.valor
      gravarCelula()
    },
    true,
  )

  document.addEventListener(
    'input',
    (evento) => {
      if (!evento.isTrusted || naBarra(evento)) return
      const planilha = campoDePlanilha(evento.composedPath()[0])
      if (planilha) {
        const endereco = celulaEmEdicao?.endereco ?? celulaAtiva()
        celulaEmEdicao = { endereco, el: planilha, valor: valorDe(planilha) }
        return
      }
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
      // Clicar em outra célula confirma a que estava sendo digitada; clicar na barra continua nela
      if (celulaEmEdicao && !campoDePlanilha(evento.composedPath()[0])) gravarCelula()
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
      // Célula de planilha já foi gravada pelo ouvinte dela
      if (campoDePlanilha(evento.composedPath()[0])) return
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
      suggestedName: nomeDoRotulo(achado?.anchor || nomeProprio(el)).slice(0, 120),
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
      // Clicar no cabeçalho é pedir a tabela inteira; numa célula comum, só aquele valor
      const celula = el.closest('th, td')
      pick.wholeTable = Boolean(celula && (celula.tagName === 'TH' || celula.parentElement === cabecalho))
      pick.tableName = nomeDaTabela(tabela)
    }
    return pick
  }

  // Sem rótulo ao lado, o nome vem do próprio elemento: o que um leitor de tela diria dele
  function nomeProprio(el) {
    for (const atributo of ['aria-label', 'title', 'placeholder', 'name']) {
      const texto = limpar(el.getAttribute(atributo))
      if (curto(texto)) return texto
    }
    return ''
  }

  function nomeDaTabela(tabela) {
    const legenda = limpar(tabela.caption?.innerText) || limpar(tabela.getAttribute('aria-label'))
    if (curto(legenda)) return legenda
    // O título mais próximo antes da tabela, como "Notas emitidas"
    let anterior = tabela.previousElementSibling
    for (let passos = 0; anterior && passos < 5; passos++, anterior = anterior.previousElementSibling) {
      if (/^H[1-6]$/.test(anterior.tagName) && curto(limpar(anterior.innerText))) return limpar(anterior.innerText)
    }
    return ''
  }

  // Ao salvar, os dados da tela final são guardados sozinhos: tabelas e pares "rótulo: valor".
  // Só entra o que a repetição sabe achar de novo pelo mesmo rótulo; menu e rodapé ficam de fora.

  const FORA_DO_CONTEUDO =
    'nav,header,footer,aside,[role=navigation],[role=banner],[role=contentinfo],[role=search],[aria-hidden=true],ditto-gravador'
  const MAX_DADOS_DA_TELA = 40
  const MAX_VALOR_DA_TELA = 200
  const TEM_LETRA = /\p{L}/u
  // "Razão social", "Nº do pedido (atual)". Não serve: código, JSON, hora ("Horário 10:30"), endereço web.
  const PARECE_ROTULO = /^\p{L}[\p{L}\p{N}\s.,()/ºª°-]*$/u
  const rotuloValido = (texto) => PARECE_ROTULO.test(texto) && !/\d$/.test(texto) && !/^https?$/i.test(texto)
  const DOIS_PONTOS_NO_FIM = /\s*:\s*$/

  const naTela = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'
  const noConteudo = (el) => naTela(el) && !el.closest(FORA_DO_CONTEUDO)
  const ehFolha = (el) => el.children.length === 0
  const nomeDoRotulo = (texto) => texto.replace(DOIS_PONTOS_NO_FIM, '')

  // Campo que a pessoa ainda pode editar é formulário, não resultado
  function editavel(el) {
    if (!['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) return false
    return !el.readOnly && !el.disabled
  }

  // Ficha: tabela de uma coluna de rótulos (th) e outra de valores, como "CNPJ | 12.345..."
  function ehFicha(tabela) {
    const linhas = [...tabela.rows]
    return linhas.length > 0 && linhas.every((linha) => linha.cells[0]?.tagName === 'TH' && linha.cells.length >= 2)
  }

  // Tabela de dados: cabeçalho com pelo menos duas colunas de nome curto, sem tabela dentro
  function ehTabelaDeDados(tabela) {
    if (tabela.rows.length < 2 || tabela.querySelector('table') || ehFicha(tabela)) return false
    const cabecalho = tabela.tHead?.rows[0] ?? tabela.rows[0]
    const nomes = [...cabecalho.cells].map((celula) => limpar(celula.innerText))
    return nomes.filter((nome) => curto(nome)).length >= 2 && nomes.every((nome) => !nome || curto(nome))
  }

  function varrerTela() {
    if (!document.body) return []

    // A repetição lê o primeiro texto igual da página: rótulo repetido apontaria para o dado errado
    const folhas = []
    const vezes = new Map()
    for (const el of document.body.querySelectorAll('*')) {
      if (!ehFolha(el) || (el.textContent ?? '').length > 300 || !naTela(el)) continue
      const texto = limpar(el.innerText)
      if (!texto) continue
      folhas.push([el, texto])
      vezes.set(texto, (vezes.get(texto) ?? 0) + 1)
    }
    const unico = (texto) => vezes.get(texto) === 1
    const prefixoUnico = (prefixo) => folhas.filter(([, texto]) => texto.startsWith(prefixo)).length === 1

    const achados = []
    const vistos = new Set()
    const tabelasGuardadas = new Set()
    const dentroDeTabelaGuardada = (el) => {
      const tabela = el.closest('table')
      return Boolean(tabela && [...tabelasGuardadas].some((guardada) => guardada.contains(tabela)))
    }
    const guardar = (el, pick) => {
      const chave = `${pick.target.anchor_kind ?? 'tabela'}|${pick.target.anchor ?? pick.target.css}`
      if (vistos.has(chave) || achados.length >= MAX_DADOS_DA_TELA) return
      vistos.add(chave)
      achados.push({ el, pick })
    }
    const parDeValor = (el, rotulo, kind, valorEl) => {
      if (!valorEl || !noConteudo(valorEl) || editavel(valorEl) || ehSensivel(valorEl) || valorEl.querySelector('table,input,select,textarea')) return
      const valor = valorDoDado(valorEl)
      // Um valor que é outro rótulo ("Endereço:") quer dizer que o campo estava vazio
      if (!valor || valor.length > MAX_VALOR_DA_TELA || DOIS_PONTOS_NO_FIM.test(valor)) return
      guardar(el, {
        target: { tag: valorEl.tagName.toLowerCase(), css: seletorCss(valorEl).slice(0, 1000) || undefined, anchor: rotulo.slice(0, 300), anchor_kind: kind },
        preview: valor,
        suggestedName: nomeDoRotulo(rotulo).slice(0, 120),
        hasAnchor: true,
      })
    }

    for (const tabela of document.body.querySelectorAll('table')) {
      if (achados.length >= MAX_DADOS_DA_TELA) break
      if (!noConteudo(tabela) || dentroDeTabelaGuardada(tabela) || !ehTabelaDeDados(tabela)) continue
      const cabecalho = tabela.tHead?.rows[0] ?? tabela.rows[0]
      const pick = descrever(cabecalho.cells[0])
      if (!pick.table) continue
      tabelasGuardadas.add(tabela)
      guardar(tabela, { ...pick, wholeTable: true })
    }

    for (const [el, texto] of folhas) {
      if (achados.length >= MAX_DADOS_DA_TELA) break
      if (!noConteudo(el) || dentroDeTabelaGuardada(el) || !TEM_LETRA.test(texto)) continue

      // "Situação: Ativa" no mesmo elemento
      const pedaco = /^([^:]{1,60}):\s*(.+)$/.exec(texto)
      if (pedaco) {
        const rotulo = pedaco[1].trim()
        if (rotuloValido(rotulo) && texto.startsWith(`${rotulo}:`) && prefixoUnico(`${rotulo}:`) && pedaco[2].length <= MAX_VALOR_DA_TELA) {
          guardar(el, {
            target: { tag: el.tagName.toLowerCase(), css: seletorCss(el).slice(0, 1000) || undefined, anchor: rotulo, anchor_kind: 'inline' },
            preview: pedaco[2].trim(),
            suggestedName: rotulo.slice(0, 120),
            hasAnchor: true,
          })
        }
        continue
      }
      if (!curto(texto) || !unico(texto) || !rotuloValido(nomeDoRotulo(texto))) continue

      // "Nome" com o valor no elemento seguinte: termo de definição, linha de ficha ou rótulo com dois-pontos
      if (el.tagName === 'DT') {
        if (el.nextElementSibling?.tagName === 'DD') parDeValor(el, texto, 'definition', el.nextElementSibling)
        continue
      }
      const linhaDeFicha = el.tagName === 'TH' && el.parentElement?.cells?.[0] === el && ehFicha(el.closest('table'))
      if (linhaDeFicha || DOIS_PONTOS_NO_FIM.test(texto)) {
        // Mesma ordem em que a repetição procura o valor
        parDeValor(el, texto, 'adjacent', el.nextElementSibling ?? el.parentElement?.nextElementSibling)
      }
    }

    // Campo só de leitura com rótulo, como um número de protocolo mostrado em um formulário
    for (const rotuloEl of document.body.querySelectorAll('label')) {
      if (achados.length >= MAX_DADOS_DA_TELA) break
      const campo = rotuloEl.control
      const texto = limpar(rotuloEl.innerText)
      if (!campo || editavel(campo) || !['INPUT', 'SELECT', 'TEXTAREA'].includes(campo.tagName)) continue
      if (!noConteudo(campo) || ehSensivel(campo) || !curto(texto) || !rotuloValido(nomeDoRotulo(texto))) continue
      const pick = descrever(campo)
      if (pick.target.anchor_kind === 'label' && pick.preview) guardar(campo, { ...pick, suggestedName: nomeDoRotulo(pick.suggestedName) })
    }

    // Na ordem em que aparecem na tela
    achados.sort((a, b) => (a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
    return achados.map(({ pick }) => pick)
  }

  // Chamado pelo serviço da extensão, que roda este código no mesmo mundo isolado do gravador
  globalThis.__dittoVarrerTela = varrerTela

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
  let relogio = null
  let partes = {}

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
      ${
        estado.picking
          ? `<div class="info"><b>Clique em cada dado que quer guardar.</b> Cada clique já fica salvo, com o nome do rótulo ao lado. Clicar no cabeçalho de uma tabela guarda a tabela inteira. Esc ou Pronto termina.</div>`
          : '<div class="info">Ao salvar, as tabelas e os dados da tela em que você estiver são guardados sozinhos.</div>'
      }
      ${estado.captures?.length ? `<div class="ultimo">Dados: ${escapar(estado.captures.join(', '))}</div>` : ''}
      ${estado.limitReached ? '<div class="aviso">Limite de 200 passos: novas ações não são gravadas.</div>' : ''}
      ${estado.warning ? `<div class="aviso">${escapar(estado.warning)}</div>` : ''}
      ${estado.error ? `<div class="erro" role="alert">${escapar(estado.error)}</div>` : ''}`,
    )

    const acoes = `<div class="acoes">
        ${estado.picking ? '<button data-acao="pronto" class="cheio">Pronto</button>' : '<button data-acao="capturar">Capturar dados</button>'}
        <button data-acao="parar" class="cheio" ${estado.sending ? 'disabled' : ''}>${estado.sending ? 'Salvando...' : 'Parar e salvar'}</button>
        <button data-acao="descartar" class="leve" ${estado.sending ? 'disabled' : ''}>Descartar</button>
      </div>`
    if (desenharParte('acoes', acoes)) {
      aoClicarNaBarra('[data-acao=capturar]', () => enviar({ type: 'ditto:pick-start' }))
      aoClicarNaBarra('[data-acao=pronto]', () => enviar({ type: 'ditto:pick-stop' }))
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

  chrome.runtime.onMessage.addListener((mensagem) => {
    if (mensagem.type === 'ditto:pick-start') comecarEscolha()
    if (mensagem.type === 'ditto:pick-stop') pararEscolha()
    if (!NO_TOPO) return

    if (mensagem.type === 'ditto:state') {
      estadoAtual = mensagem.state
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
