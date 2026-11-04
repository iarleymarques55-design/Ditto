import { useConsulta } from '../../../lib/useConsulta.js'
import { obterFluxo } from '../api.js'

const INTERVALO_ANALISE_MS = 2000

// Enquanto o worker analisa a gravação, a tela continua consultando
export function useFluxo(id) {
  return useConsulta(() => obterFluxo(id), [id], {
    intervalo: (fluxo) => (fluxo?.situacao === 'analisando' ? INTERVALO_ANALISE_MS : null),
  })
}
