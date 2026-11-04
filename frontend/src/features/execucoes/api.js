import { FUSO_DO_NAVEGADOR, baixarArquivo, pedir, pedirArquivo } from '../../lib/http.js'
import { mapearVariavel } from '../../lib/variaveis.js'

const MAXIMO_POR_PAGINA = 100

const SITUACAO_EXECUCAO = {
  queued: 'fila',
  running: 'rodando',
  waiting_human: 'espera',
  succeeded: 'concluida',
  partial: 'parcial',
  failed: 'falhou',
  canceled: 'cancelada',
}

const SITUACAO_ITEM = {
  pending: 'pendente',
  running: 'rodando',
  succeeded: 'ok',
  repaired: 'reparado',
  waiting_human: 'espera',
  failed: 'falhou',
  skipped: 'pulado',
}

const LOG = {
  info: { tipo: 'info', simbolo: '' },
  ok: { tipo: 'ok', simbolo: '✔ ' },
  failure: { tipo: 'falha', simbolo: '✘ ' },
  search: { tipo: 'busca', simbolo: '⟳ ' },
}

export function mapearResumoExecucao(execucao) {
  return {
    id: execucao.id,
    fluxoId: execucao.flow_id,
    fluxoNome: execucao.flow_name,
    situacao: SITUACAO_EXECUCAO[execucao.status],
    disparo: execucao.trigger === 'schedule' ? 'agendada' : 'manual',
    inicio: execucao.created_at,
    fim: execucao.finished_at,
    total: execucao.total,
    concluidas: execucao.done,
    reparos: execucao.repaired,
    falhas: execucao.failed,
    duracaoS: execucao.duration_seconds,
  }
}

function mapearItem(item) {
  return {
    id: item.id,
    posicao: item.position,
    rotulo: item.label,
    situacao: SITUACAO_ITEM[item.status],
    duracaoS: item.duration_ms ? item.duration_ms / 1000 : null,
    erro: item.error_message,
    passoProblema: item.problem_step_position,
    camada: item.resolved_layer,
    arquivo: item.file_name,
    arquivoId: item.file_artifact_id,
    telaId: item.screenshot_artifact_id,
  }
}

export function mapearExecucao(execucao) {
  return {
    ...mapearResumoExecucao(execucao),
    portal: execucao.portal,
    itens: execucao.items.map(mapearItem),
    passos: execucao.steps.map((passo) => ({ posicao: passo.position, intencao: passo.intent })),
    log: execucao.log.map((linha) => ({
      id: linha.id,
      tipo: LOG[linha.level].tipo,
      texto: `${LOG[linha.level].simbolo}${linha.message}`,
    })),
  }
}

export async function listarExecucoes({ fluxoId } = {}) {
  const filtro = fluxoId ? `&flow_id=${fluxoId}` : ''
  const { items } = await pedir(`/runs?limit=${MAXIMO_POR_PAGINA}${filtro}`)
  return items.map(mapearResumoExecucao)
}

export async function obterExecucao(id) {
  return mapearExecucao(await pedir(`/runs/${id}`))
}

export async function criarExecucao({ fluxoId, arquivo }) {
  const formulario = new FormData()
  formulario.append('flow_id', fluxoId)
  formulario.append('timezone', FUSO_DO_NAVEGADOR)
  if (arquivo) formulario.append('file', arquivo)
  return mapearExecucao(await pedir('/runs', { metodo: 'POST', formulario }))
}

export function cancelarExecucao(id) {
  return pedir(`/runs/${id}/cancel`, { metodo: 'POST' })
}

export function baixarRelatorio(id) {
  return baixarArquivo(`/runs/${id}/report`, `relatorio-${id}.pdf`)
}

export function exportarPlanilha(id) {
  return baixarArquivo(`/runs/${id}/export`, `execucao-${id}.csv`)
}

export function baixarArtefato(id, nome) {
  return baixarArquivo(`/artifacts/${id}`, nome)
}

export function buscarImagem(id) {
  return pedirArquivo(`/artifacts/${id}`)
}

// Para a tela de nova execução: só as tarefas prontas para rodar
export async function listarTarefasDisponiveis() {
  const { items } = await pedir(`/flows?limit=${MAXIMO_POR_PAGINA}`)
  return items
    .filter((tarefa) => tarefa.status === 'active')
    .map((tarefa) => ({ id: tarefa.id, nome: tarefa.name }))
}

export async function obterColunasDaTarefa(id) {
  const tarefa = await pedir(`/flows/${id}`)
  const variaveis = tarefa.variables.map(mapearVariavel)
  return {
    colunas: variaveis.filter((variavel) => variavel.coluna).map((variavel) => variavel.nome),
    automaticas: variaveis.filter((variavel) => !variavel.coluna),
    precisaAcesso: tarefa.needs_credential,
  }
}
