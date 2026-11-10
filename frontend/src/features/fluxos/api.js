import { descreverCron } from '../../lib/agenda.js'
import { FUSO_DO_NAVEGADOR, pedir } from '../../lib/http.js'
import { mapearVariavel } from '../../lib/variaveis.js'
import { mapearResumoExecucao } from '../execucoes/index.js'

const MAXIMO_POR_PAGINA = 100

const SITUACAO_FLUXO = {
  draft: 'analisando',
  analyzing: 'analisando',
  awaiting_confirmation: 'revisao',
  active: 'ativa',
  archived: 'arquivada',
}

function descreverPosCondicao({ type: tipo, extension: extensao, value: valor } = {}) {
  switch (tipo) {
    case 'download':
      return extensao ? `um arquivo .${extensao} é baixado` : 'um arquivo é baixado'
    case 'field_value':
      return 'o campo mostra o valor certo'
    case 'page_changed':
      return 'a página responde'
    case 'url_contains':
      return `o endereço contém "${valor}"`
    case 'text_visible':
      return `aparece "${valor}" na tela`
    default:
      return 'sem verificação automática'
  }
}

function mapearAgenda(agenda) {
  if (!agenda) return null
  return {
    id: agenda.id,
    texto: descreverCron(agenda.cron),
    ativa: agenda.enabled,
    proxima: agenda.next_run_at,
    linhas: agenda.row_count,
  }
}

function mapearResumo(fluxo) {
  return {
    id: fluxo.id,
    nome: fluxo.name,
    situacao: SITUACAO_FLUXO[fluxo.status],
    portal: fluxo.portal,
    passosTotal: fluxo.step_count,
    gravadaEm: fluxo.created_at,
    agenda: mapearAgenda(fluxo.schedule),
    ultimaExecucao: fluxo.last_run ? mapearResumoExecucao(fluxo.last_run) : null,
  }
}

function mapearCaptura(passo) {
  if (!passo.capture_key) return null
  return { chave: passo.capture_key, rotulo: passo.capture_label, tipo: passo.capture_kind === 'table' ? 'tabela' : 'valor' }
}

function mapearPasso(passo) {
  return {
    id: passo.id,
    posicao: passo.position,
    acao: passo.action,
    intencao: passo.intent,
    posCondicao: descreverPosCondicao(passo.postcondition),
    usaAcesso: passo.uses_credential,
    irreversivel: passo.irreversible,
    autoConfirma: passo.auto_confirm,
    captura: mapearCaptura(passo),
    digitaDado: passo.filled_from_capture,
    reparo: passo.repaired_at ? { em: passo.repaired_at, caminho: passo.current_path } : null,
  }
}

// Um passo que digita um dado capturado mostra o nome dele, e não a chave interna
function comNomeDoDado(passos) {
  const nomes = new Map(passos.filter((passo) => passo.captura).map((passo) => [passo.captura.chave, passo.captura.rotulo]))
  return passos.map((passo) => ({ ...passo, digitaDado: nomes.get(passo.digitaDado) ?? null }))
}

function mapearDetalhe(fluxo) {
  return {
    ...mapearResumo(fluxo),
    dominios: fluxo.allowed_domains,
    usaAcesso: fluxo.uses_credential,
    precisaAcesso: fluxo.needs_credential,
    passos: comNomeDoDado(fluxo.steps.map(mapearPasso)),
    variaveis: fluxo.variables.map(mapearVariavel),
  }
}

export async function listarFluxos() {
  const { items } = await pedir(`/flows?limit=${MAXIMO_POR_PAGINA}`)
  return items.map(mapearResumo)
}

export async function obterFluxo(id) {
  return mapearDetalhe(await pedir(`/flows/${id}`))
}

export function responderVariavel(fluxoId, variavelId, muda) {
  return pedir(`/flows/${fluxoId}/variables/${variavelId}/answer`, {
    metodo: 'POST',
    corpo: { is_variable: muda },
  })
}

export function ativarFluxo(fluxoId) {
  return pedir(`/flows/${fluxoId}/confirm`, { metodo: 'POST' })
}

export function arquivarFluxo(fluxoId) {
  return pedir(`/flows/${fluxoId}`, { metodo: 'DELETE' })
}

export function editarPasso(fluxoId, passoId, campos) {
  return pedir(`/flows/${fluxoId}/steps/${passoId}`, {
    metodo: 'PATCH',
    corpo: {
      ...(campos.irreversivel !== undefined ? { irreversible: campos.irreversivel } : {}),
      ...(campos.autoConfirma !== undefined ? { auto_confirm: campos.autoConfirma } : {}),
    },
  })
}

export function salvarAcesso({ dominio, usuario, senha }) {
  return pedir('/credentials', {
    metodo: 'POST',
    corpo: { domain: dominio, username: usuario || null, password: senha },
  })
}

export function criarAgenda({ fluxoId, cron, arquivo }) {
  const formulario = new FormData()
  formulario.append('flow_id', fluxoId)
  formulario.append('cron', cron)
  formulario.append('timezone', FUSO_DO_NAVEGADOR)
  if (arquivo) formulario.append('file', arquivo)
  return pedir('/schedules', { metodo: 'POST', formulario })
}

export function alternarAgenda(agendaId, ativa) {
  return pedir(`/schedules/${agendaId}`, { metodo: 'PATCH', corpo: { enabled: ativa } })
}

export function apagarAgenda(agendaId) {
  return pedir(`/schedules/${agendaId}`, { metodo: 'DELETE' })
}
