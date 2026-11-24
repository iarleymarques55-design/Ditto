import { useSyncExternalStore } from 'react'
import { useConsulta } from '../../../lib/useConsulta.js'
import { listarPedidos, listarReparos, obterResolvidosPorCamada } from '../api.js'

// Com alguém esperando resposta, a lista acompanha de perto; sem pedidos, olha de vez em quando
const COM_PEDIDOS_MS = 3000
const SEM_PEDIDOS_MS = 15000
const CARREGANDO = { dados: null, erro: null, carregando: true }

async function buscarPaginaReparos() {
  const [reparos, resolvidos, pedidos] = await Promise.all([listarReparos(), obterResolvidosPorCamada(), listarPedidos()])
  return { reparos, resolvidos, pedidos }
}

export function useReparos() {
  return useConsulta(buscarPaginaReparos)
}

// Uma consulta só para o painel inteiro: o menu e a página da execução leem o mesmo resultado,
// em vez de cada um repetir o pedido. Com a aba escondida, para; ao voltar, consulta na hora.
const pedidos = { estado: CARREGANDO, ouvintes: new Set(), temporizador: null, consultando: false, repetir: false, geracao: 0 }

function publicar(estado) {
  pedidos.estado = estado
  for (const ouvinte of pedidos.ouvintes) ouvinte()
}

function parar() {
  clearTimeout(pedidos.temporizador)
  pedidos.temporizador = null
}

function agendar() {
  parar()
  if (!pedidos.ouvintes.size || document.visibilityState === 'hidden') return
  const espera = pedidos.estado.dados?.length ? COM_PEDIDOS_MS : SEM_PEDIDOS_MS
  pedidos.temporizador = setTimeout(consultarPedidos, espera)
}

async function consultarPedidos() {
  parar()
  // Um pedido de "recarregar" no meio de uma consulta vira uma consulta logo depois dela
  if (pedidos.consultando) {
    pedidos.repetir = true
    return
  }
  pedidos.consultando = true
  // Resposta de uma sessão que já acabou (saiu e entrou com outra conta) é descartada
  const geracao = pedidos.geracao
  const atual = () => pedidos.ouvintes.size && geracao === pedidos.geracao
  try {
    const dados = await listarPedidos()
    if (atual()) publicar({ dados, erro: null, carregando: false })
  } catch (erro) {
    // Uma falha passageira não apaga o que já está na tela
    if (atual() && !pedidos.estado.dados) publicar({ dados: null, erro, carregando: false })
  } finally {
    pedidos.consultando = false
  }
  if (pedidos.repetir) {
    pedidos.repetir = false
    consultarPedidos()
    return
  }
  agendar()
}

function aoMudarVisibilidade() {
  if (document.visibilityState === 'visible') consultarPedidos()
  else parar()
}

function assinar(ouvinte) {
  pedidos.ouvintes.add(ouvinte)
  if (pedidos.ouvintes.size === 1) {
    document.addEventListener('visibilitychange', aoMudarVisibilidade)
    consultarPedidos()
  }
  return () => {
    pedidos.ouvintes.delete(ouvinte)
    if (pedidos.ouvintes.size) return
    document.removeEventListener('visibilitychange', aoMudarVisibilidade)
    parar()
    // Saiu do painel (ou trocou de conta): nada da sessão anterior fica guardado
    pedidos.estado = CARREGANDO
    pedidos.geracao += 1
  }
}

const lerPedidos = () => pedidos.estado

export function usePedidos() {
  const estado = useSyncExternalStore(assinar, lerPedidos)
  return { ...estado, recarregar: consultarPedidos }
}
