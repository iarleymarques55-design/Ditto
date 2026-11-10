import { descreverCron } from '../../lib/agenda.js'
import { FUSO_DO_NAVEGADOR, pedir } from '../../lib/http.js'
import { mapearExecucao, mapearResumoExecucao } from '../execucoes/index.js'
import { mapearPedido } from '../reparos/index.js'

export async function obterResumo() {
  const resumo = await pedir(`/dashboard/summary?timezone=${encodeURIComponent(FUSO_DO_NAVEGADOR)}`)
  return {
    copiasHoje: resumo.copies_today,
    pedidos: resumo.help_requests.map(mapearPedido),
    destaque: resumo.highlight ? mapearExecucao(resumo.highlight) : null,
    recentes: resumo.recent_runs.map(mapearResumoExecucao),
    agenda: resumo.upcoming.map((item) => ({
      id: item.flow_id,
      nome: item.flow_name,
      proxima: item.next_run_at,
      texto: descreverCron(item.cron),
    })),
  }
}
