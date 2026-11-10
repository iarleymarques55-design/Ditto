import { useConsulta } from '../../../lib/useConsulta.js'
import { listarFluxos } from '../api.js'

export function useFluxos() {
  return useConsulta(listarFluxos)
}
