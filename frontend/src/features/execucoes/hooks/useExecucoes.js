import { useConsulta } from '../../../lib/useConsulta.js'
import { listarExecucoes } from '../api.js'
import { emAndamento } from '../situacoes.js'

const INTERVALO_MS = 1500

export function useExecucoes({ fluxoId } = {}) {
  return useConsulta(() => listarExecucoes({ fluxoId }), [fluxoId], {
    intervalo: (execucoes) => (execucoes?.some((execucao) => emAndamento(execucao.situacao)) ? INTERVALO_MS : null),
  })
}
