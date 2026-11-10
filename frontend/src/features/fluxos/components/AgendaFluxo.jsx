import { useId, useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import { OPCOES_DIA_DA_SEMANA, montarCron } from '../../../lib/agenda.js'
import { formatarQuando } from '../../../lib/datas.js'
import { UploadLote } from '../../execucoes/index.js'
import { alternarAgenda, apagarAgenda, criarAgenda } from '../api.js'

const classeCampo = 'mt-1 min-h-11 w-full rounded-[2px] border border-grafite/60 bg-papel-folha px-3 text-[15px] text-navy'

function AgendaExistente({ agenda, aoMudar }) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function fazer(acao) {
    setEnviando(true)
    setErro(null)
    try {
      await acao()
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div>
      <p className="text-[15px] font-medium text-navy">{agenda.texto}</p>
      <p className="mt-0.5 text-[14px]">
        {agenda.ativa ? `Próxima: ${formatarQuando(agenda.proxima)}` : 'Pausada: não roda sozinha até você retomar.'}
      </p>
      <p className="text-[14px]">
        {agenda.linhas} {agenda.linhas === 1 ? 'linha' : 'linhas'} a cada vez
      </p>
      <div className="mt-1 flex flex-wrap gap-x-4">
        <Botao variante="discreto" disabled={enviando} onClick={() => fazer(() => alternarAgenda(agenda.id, !agenda.ativa))}>
          {agenda.ativa ? 'Pausar a agenda' : 'Retomar a agenda'}
        </Botao>
        <Botao variante="discreto" disabled={enviando} onClick={() => fazer(() => apagarAgenda(agenda.id))}>
          Apagar a agenda
        </Botao>
      </div>
      {erro && (
        <p role="alert" className="mt-1 text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </div>
  )
}

function NovaAgenda({ fluxoId, colunas, aoMudar }) {
  const [frequencia, setFrequencia] = useState('mensal')
  const [horario, setHorario] = useState('07:00')
  const [diaDoMes, setDiaDoMes] = useState(5)
  const [diaDaSemana, setDiaDaSemana] = useState(1)
  const [planilha, setPlanilha] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)
  const idFrequencia = useId()
  const idHorario = useId()
  const idDia = useId()
  const usaPlanilha = colunas.length > 0

  async function agendar(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro(null)
    try {
      const cron = montarCron({ frequencia, horario, diaDoMes, diaDaSemana })
      await criarAgenda({ fluxoId, cron, arquivo: planilha?.arquivo })
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={agendar} className="space-y-3">
      <p className="text-[14.5px]">Sem agenda, esta tarefa só roda quando você mandar.</p>
      <div>
        <label htmlFor={idFrequencia} className="text-[14px] font-medium text-navy">
          Repetir
        </label>
        <select id={idFrequencia} value={frequencia} onChange={(evento) => setFrequencia(evento.target.value)} className={classeCampo}>
          <option value="diaria">Todo dia</option>
          <option value="semanal">Toda semana</option>
          <option value="mensal">Todo mês</option>
        </select>
      </div>

      {frequencia === 'mensal' && (
        <div>
          <label htmlFor={idDia} className="text-[14px] font-medium text-navy">
            Dia do mês
          </label>
          <input
            id={idDia}
            type="number"
            min="1"
            max="28"
            required
            value={diaDoMes}
            onChange={(evento) => setDiaDoMes(evento.target.value)}
            className={classeCampo}
          />
        </div>
      )}
      {frequencia === 'semanal' && (
        <div>
          <label htmlFor={idDia} className="text-[14px] font-medium text-navy">
            Dia da semana
          </label>
          <select id={idDia} value={diaDaSemana} onChange={(evento) => setDiaDaSemana(evento.target.value)} className={classeCampo}>
            {OPCOES_DIA_DA_SEMANA.map(({ rotulo, valor }) => (
              <option key={valor} value={valor}>
                {rotulo}
              </option>
            ))}
          </select>
        </div>
      )}

      <div>
        <label htmlFor={idHorario} className="text-[14px] font-medium text-navy">
          Horário
        </label>
        <input
          id={idHorario}
          type="time"
          required
          value={horario}
          onChange={(evento) => setHorario(evento.target.value)}
          className={classeCampo}
        />
      </div>

      {usaPlanilha && (
        <div>
          <UploadLote colunas={colunas} aoCarregar={setPlanilha} />
          {planilha && <p className="mt-2 text-[14px] font-medium text-navy">{planilha.nome}</p>}
        </div>
      )}

      {erro && (
        <p role="alert" className="text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
      <Botao type="submit" variante="contorno" disabled={enviando || (usaPlanilha && !planilha)}>
        Agendar
      </Botao>
    </form>
  )
}

function AgendaFluxo({ fluxo, aoMudar }) {
  if (fluxo.agenda) return <AgendaExistente agenda={fluxo.agenda} aoMudar={aoMudar} />

  const colunas = fluxo.variaveis.filter((variavel) => variavel.coluna).map((variavel) => variavel.nome)
  return <NovaAgenda fluxoId={fluxo.id} colunas={colunas} aoMudar={aoMudar} />
}

export default AgendaFluxo
