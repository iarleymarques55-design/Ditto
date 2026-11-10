import { useCallback, useEffect, useReducer, useRef } from 'react'
import {
  ESPERA_AUTOPLAY_MS,
  LOJAS,
  MES,
  PASSO_EXPORTAR,
  PASSO_MS,
  PASSOS,
  REGISTRO,
  TEMPO_REPARO,
  TENTATIVA_MS,
  TENTATIVAS,
  linhaLoja,
  linhaSalvo,
} from './demoRoteiro.js'

const PORTAL_VAZIO = { loja: null, mes: null, tabela: false, menuAberto: false, destaque: null }

const ESTADO_INICIAL = {
  layout: 'A',
  reparado: false,
  rodando: false,
  passoAtual: null,
  concluidos: 0,
  indiceLoja: 0,
  lojaAtual: null,
  portal: PORTAL_VAZIO,
  registro: [],
  proximoId: 0,
}

// O registro guarda só o fim; a tela mostra no máximo 6 linhas.
const MAX_REGISTRO = 12

function registrar(estado, texto, tipo) {
  const linha = { id: estado.proximoId, texto, tipo }
  return { registro: [...estado.registro, linha].slice(-MAX_REGISTRO), proximoId: estado.proximoId + 1 }
}

// O que a janela do portal mostra em cada passo da matriz.
function portalNoPasso(estado, numero) {
  const { portal } = estado
  switch (numero) {
    case 1:
      return PORTAL_VAZIO
    case 2:
      return { ...portal, loja: estado.lojaAtual.nome }
    case 3:
      return { ...portal, mes: MES }
    case 4:
      return { ...portal, destaque: 'gerar' }
    case 5:
      return { ...portal, destaque: null, tabela: true }
    case PASSO_EXPORTAR:
      if (estado.layout === 'A') return { ...portal, destaque: 'pdf' }
      // No layout B sem reparo, quem abre o menu são as tentativas.
      return estado.reparado ? { ...portal, menuAberto: true, destaque: 'pdf' } : portal
    default:
      return { ...portal, destaque: null, menuAberto: false }
  }
}

function reducer(estado, acao) {
  switch (acao.type) {
    case 'iniciar':
      return {
        ...estado,
        ...registrar(estado, linhaLoja(acao.loja), 'loja'),
        rodando: true,
        passoAtual: null,
        concluidos: 0,
        lojaAtual: acao.loja,
      }
    case 'passo':
      return {
        ...estado,
        passoAtual: acao.numero,
        concluidos: acao.numero - 1,
        portal: portalNoPasso(estado, acao.numero),
      }
    case 'registrar':
      return { ...estado, ...registrar(estado, acao.texto, acao.tipo) }
    case 'tentativa': {
      const { texto, tipo, efeito } = acao.linha
      const proximo = { ...estado, ...registrar(estado, texto, tipo) }
      if (efeito === 'abrirMenu') proximo.portal = { ...estado.portal, menuAberto: true, destaque: 'pdf' }
      if (efeito === 'reparar') proximo.reparado = true
      return proximo
    }
    case 'finalizar':
      return {
        ...estado,
        ...registrar(estado, acao.texto, 'ok'),
        rodando: false,
        passoAtual: null,
        concluidos: PASSOS.length,
        indiceLoja: estado.indiceLoja + 1,
      }
    case 'mudarLayout':
      return {
        ...estado,
        ...registrar(estado, REGISTRO.mudouLayout, 'info'),
        layout: 'B',
        portal: { ...estado.portal, menuAberto: false, destaque: null },
      }
    case 'restaurar':
      return ESTADO_INICIAL
    default:
      return estado
  }
}

// Monta a sequência de ações de uma cópia a partir do estado em que ela começa.
function montarCopia({ layout, reparado, indiceLoja }) {
  const loja = LOJAS[indiceLoja % LOJAS.length]
  const reparando = layout === 'B' && !reparado
  const roteiro = [{ espera: 0, acao: { type: 'iniciar', loja } }]

  PASSOS.forEach((_, indice) => {
    const numero = indice + 1
    roteiro.push({ espera: numero === 1 ? 0 : PASSO_MS, acao: { type: 'passo', numero } })
    if (numero !== PASSO_EXPORTAR) return

    if (reparando) {
      TENTATIVAS.forEach((linha) => roteiro.push({ espera: TENTATIVA_MS, acao: { type: 'tentativa', linha } }))
    } else {
      const texto = layout === 'A' ? REGISTRO.exportouA : REGISTRO.caminhoReparado
      roteiro.push({ espera: PASSO_MS, acao: { type: 'registrar', texto, tipo: 'ok' } })
    }
  })

  const segundos = loja.tempo + (reparando ? TEMPO_REPARO : 0)
  roteiro.push({ espera: PASSO_MS, acao: { type: 'finalizar', texto: linhaSalvo(loja, segundos) } })
  return roteiro
}

function prefereMenosMovimento() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function useDemoAdaptacao() {
  const [estado, dispatch] = useReducer(reducer, ESTADO_INICIAL)
  const timers = useRef([])

  const cancelar = useCallback(() => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }, [])

  const executar = useCallback(
    (roteiro) => {
      cancelar()
      // Com movimento reduzido, tudo acontece de uma vez, com o mesmo resultado final.
      const semAtraso = prefereMenosMovimento()
      let tempo = 0
      roteiro.forEach(({ espera, acao }) => {
        tempo += espera
        if (semAtraso || tempo === 0) dispatch(acao)
        else timers.current.push(setTimeout(() => dispatch(acao), tempo))
      })
    },
    [cancelar],
  )

  // Roda uma cópia sozinha ao carregar. Qualquer clique antes disso cancela.
  useEffect(() => {
    timers.current.push(setTimeout(() => executar(montarCopia(ESTADO_INICIAL)), ESPERA_AUTOPLAY_MS))
    return cancelar
  }, [executar, cancelar])

  function rodar() {
    if (estado.rodando) return
    executar(montarCopia(estado))
  }

  function alternarLayout() {
    if (estado.rodando) return
    cancelar()
    dispatch({ type: estado.layout === 'A' ? 'mudarLayout' : 'restaurar' })
  }

  return { estado, rodar, alternarLayout }
}
