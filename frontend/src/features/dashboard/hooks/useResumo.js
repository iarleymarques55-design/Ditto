import { useConsulta } from '../../../lib/useConsulta.js'
import { obterResumo } from '../api.js'

const INTERVALO_RODANDO_MS = 1500
const INTERVALO_PARADO_MS = 5000

export function useResumo() {
  return useConsulta(obterResumo, [], {
    intervalo: (resumo) => (resumo?.destaque?.situacao === 'rodando' ? INTERVALO_RODANDO_MS : INTERVALO_PARADO_MS),
  })
}
