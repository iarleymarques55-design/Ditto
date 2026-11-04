import { useId, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import Carregando from '../../../components/ui/Carregando.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import EstadoVazio from '../../../components/ui/EstadoVazio.jsx'
import { useConsulta } from '../../../lib/useConsulta.js'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { criarExecucao, listarTarefasDisponiveis, obterColunasDaTarefa } from '../api.js'
import UploadLote from '../components/UploadLote.jsx'

const LINHAS_NA_PREVIA = 5

function Previa({ planilha, colunas }) {
  if (!planilha.linhas) {
    return <p className="mt-4 text-[14.5px] font-medium text-navy">{planilha.nome}: as colunas são conferidas ao enviar.</p>
  }

  return (
    <div className="mt-4 overflow-x-auto">
      <p className="text-[14.5px] font-medium text-navy">
        {planilha.nome}: {planilha.linhas.length} {planilha.linhas.length === 1 ? 'linha' : 'linhas'}
      </p>
      <table className="mt-2 w-full max-w-[560px] text-left text-[14px]">
        <caption className="sr-only">Primeiras linhas da planilha</caption>
        <thead>
          <tr className="border-b-[1.5px] border-navy/40">
            {colunas.map((coluna) => (
              <th key={coluna} scope="col" className="py-1.5 pr-4 text-[13px] font-medium">
                {coluna}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {planilha.linhas.slice(0, LINHAS_NA_PREVIA).map((linha, indice) => (
            // oxlint-disable-next-line react/no-array-index-key -- a prévia não muda de ordem
            <tr key={indice} className="border-b border-pauta">
              {colunas.map((coluna) => (
                <td key={coluna} className="py-1.5 pr-4 text-navy">
                  {linha[coluna]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EtapasDaTarefa({ tarefaId }) {
  const navegar = useNavigate()
  const consulta = useConsulta(() => obterColunasDaTarefa(tarefaId), [tarefaId])
  const [planilha, setPlanilha] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  if (consulta.carregando) return <li><Carregando /></li>
  if (consulta.erro) {
    return (
      <li>
        <p role="alert" className="text-[14.5px] font-medium text-rec-texto">
          {consulta.erro.message}
        </p>
      </li>
    )
  }

  const { colunas, automaticas, precisaAcesso } = consulta.dados
  const usaPlanilha = colunas.length > 0
  const quantas = planilha?.linhas?.length ?? null

  let rotulo = 'Tirar as cópias'
  if (!usaPlanilha) rotulo = 'Tirar 1 cópia'
  else if (quantas) rotulo = `Tirar ${quantas} ${quantas === 1 ? 'cópia' : 'cópias'}`

  async function iniciar() {
    setEnviando(true)
    setErro(null)
    try {
      const { id } = await criarExecucao({ fluxoId: tarefaId, arquivo: planilha?.arquivo })
      navegar(`/painel/execucoes/${id}`)
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <>
      {automaticas.length > 0 && (
        <li className="!mt-2 text-[14px]">
          {automaticas.map((variavel) => `${variavel.rotulo}: ${variavel.origem}`).join('; ')}.
        </li>
      )}
      {precisaAcesso && (
        <li role="alert" className="text-[14.5px] font-medium text-rec-texto">
          Esta tarefa pede login. Salve o acesso ao portal na página da tarefa antes de rodar.
        </li>
      )}
      {usaPlanilha && (
        <li>
          <h2 className="font-display text-[21px] font-bold text-navy">2. Para quais linhas?</h2>
          <div className="mt-2.5">
            <UploadLote colunas={colunas} aoCarregar={setPlanilha} />
          </div>
          {planilha && <Previa planilha={planilha} colunas={colunas} />}
        </li>
      )}
      <li>
        <Botao disabled={(usaPlanilha && !planilha) || precisaAcesso || enviando} onClick={iniciar}>
          {rotulo}
        </Botao>
        {erro && (
          <p role="alert" className="mt-2 text-[14.5px] font-medium text-rec-texto">
            {erro}
          </p>
        )}
      </li>
    </>
  )
}

function FormularioExecucao({ tarefas, tarefaInicial }) {
  const [tarefaId, setTarefaId] = useState(tarefas.some(({ id }) => id === tarefaInicial) ? tarefaInicial : tarefas[0]?.id)
  const idTarefa = useId()

  if (tarefas.length === 0) {
    return (
      <EstadoVazio titulo="Nenhuma tarefa pronta para rodar." acao={<Botao para="/painel/tarefas">Ver as tarefas</Botao>}>
        Uma tarefa aparece aqui depois de gravada e revisada.
      </EstadoVazio>
    )
  }

  return (
    <ol className="mt-8 max-w-[680px] space-y-9">
      <li>
        <label htmlFor={idTarefa} className="block font-display text-[21px] font-bold text-navy">
          1. Qual tarefa?
        </label>
        <select
          id={idTarefa}
          value={tarefaId}
          onChange={(evento) => setTarefaId(evento.target.value)}
          className="mt-2.5 min-h-11 w-full rounded-[2px] border border-grafite/60 bg-papel-folha px-3 text-[15px] text-navy"
        >
          {tarefas.map(({ id, nome }) => (
            <option key={id} value={id}>
              {nome}
            </option>
          ))}
        </select>
      </li>
      {/* A chave limpa a planilha escolhida ao trocar de tarefa */}
      <EtapasDaTarefa key={tarefaId} tarefaId={tarefaId} />
    </ol>
  )
}

function NovaExecucaoPage() {
  useTituloPagina('Nova execução')
  const [parametros] = useSearchParams()
  const consulta = useConsulta(listarTarefasDisponiveis)

  return (
    <>
      <h1 className="font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">Nova execução</h1>
      <EstadoConsulta consulta={consulta}>
        {(tarefas) => <FormularioExecucao tarefas={tarefas} tarefaInicial={parametros.get('tarefa')} />}
      </EstadoConsulta>
    </>
  )
}

export default NovaExecucaoPage
