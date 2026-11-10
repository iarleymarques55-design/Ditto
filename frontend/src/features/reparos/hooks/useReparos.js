import { useConsulta } from '../../../lib/useConsulta.js'
import { listarPedidos, listarReparos, obterResolvidosPorCamada } from '../api.js'

const INTERVALO_PEDIDOS_MS = 3000

async function buscarPaginaReparos() {
  const [reparos, resolvidos, pedidos] = await Promise.all([listarReparos(), obterResolvidosPorCamada(), listarPedidos()])
  return { reparos, resolvidos, pedidos }
}

export function useReparos() {
  return useConsulta(buscarPaginaReparos)
}

export function usePedidos() {
  return useConsulta(listarPedidos, [], { intervalo: () => INTERVALO_PEDIDOS_MS })
}
