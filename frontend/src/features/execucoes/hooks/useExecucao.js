import { useConsulta } from '../../../lib/useConsulta.js'
import { obterExecucao } from '../api.js'
import { emAndamento } from '../situacoes.js'

const INTERVALO_MS = 1000

export function useExecucao(id) {
  return useConsulta(() => obterExecucao(id), [id], {
    intervalo: (execucao) => (execucao && emAndamento(execucao.situacao) ? INTERVALO_MS : null),
  })
}
