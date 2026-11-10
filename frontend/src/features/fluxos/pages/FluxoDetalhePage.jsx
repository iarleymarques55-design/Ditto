import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import EstadoVazio from '../../../components/ui/EstadoVazio.jsx'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { TabelaExecucoes, useExecucoes } from '../../execucoes/index.js'
import { arquivarFluxo, ativarFluxo } from '../api.js'
import AcessoPortal from '../components/AcessoPortal.jsx'
import AgendaFluxo from '../components/AgendaFluxo.jsx'
import ListaPassos from '../components/ListaPassos.jsx'
import VariaveisFluxo from '../components/VariaveisFluxo.jsx'
import { useFluxo } from '../hooks/useFluxo.js'

function Historico({ fluxoId }) {
  const consulta = useExecucoes({ fluxoId })
  return (
    <EstadoConsulta consulta={consulta}>
      {(execucoes) =>
        execucoes.length > 0 ? (
          <TabelaExecucoes execucoes={execucoes} legenda="Execuções desta tarefa" mostrarTarefa={false} />
        ) : (
          <EstadoVazio titulo="Ainda não rodou." />
        )
      }
    </EstadoConsulta>
  )
}

function Ativar({ fluxo, perguntas, aoMudar }) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState(null)

  async function ativar() {
    setEnviando(true)
    setErro(null)
    try {
      await ativarFluxo(fluxo.id)
      aoMudar()
    } catch (falha) {
      setErro(falha.message)
      setEnviando(false)
    }
  }

  return (
    <div>
      <p className="text-[14.5px]">
        {perguntas > 0 ? 'Responda as perguntas para poder ativar.' : 'Tudo respondido. Confira os passos e ative.'}
      </p>
      <Botao className="mt-3" disabled={perguntas > 0 || enviando} onClick={ativar}>
        Ativar tarefa
      </Botao>
      {erro && (
        <p role="alert" className="mt-2 text-[14px] font-medium text-rec-texto">
          {erro}
        </p>
      )}
    </div>
  )
}

function Detalhe({ fluxo, aoMudar }) {
  useTituloPagina(fluxo.nome)
  const navegar = useNavigate()
  const [erroArquivar, setErroArquivar] = useState(null)
  const emRevisao = fluxo.situacao === 'revisao'
  const ativa = fluxo.situacao === 'ativa'
  const perguntas = fluxo.variaveis.filter((variavel) => !variavel.confirmada).length

  async function arquivar() {
    // oxlint-disable-next-line no-alert -- confirmação simples para uma ação de baixo risco: o histórico fica guardado
    if (!window.confirm(`Arquivar "${fluxo.nome}"? A agenda dela para, e o histórico continua guardado.`)) return
    try {
      await arquivarFluxo(fluxo.id)
      navegar('/painel/tarefas')
    } catch (falha) {
      setErroArquivar(falha.message)
    }
  }

  if (fluxo.situacao === 'analisando') {
    return (
      <>
        <h1 className="font-display text-[32px] leading-[1.1] font-bold text-navy sm:text-[44px]">{fluxo.nome}</h1>
        <EstadoVazio titulo="O Ditto está lendo a gravação.">
          Em instantes aparecem os passos e as perguntas. Se demorar, confira se o worker está rodando.
        </EstadoVazio>
      </>
    )
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="font-display text-[32px] leading-[1.1] font-bold break-words text-navy sm:text-[44px]">{fluxo.nome}</h1>
          <p className="mt-2 text-[15px] break-all">{fluxo.portal}</p>
        </div>
        {ativa && (
          <Botao para={`/painel/execucoes/nova?tarefa=${fluxo.id}`}>
            Rodar agora
          </Botao>
        )}
      </div>

      <div className="mt-9 grid items-start gap-10 lg:grid-cols-[minmax(0,1.25fr)_minmax(280px,1fr)] lg:gap-12">
        <section aria-label="Passos gravados">
          <ListaPassos fluxo={fluxo} aoMudar={aoMudar} />
        </section>

        <div className="space-y-9">
          <section aria-labelledby="variaveis-titulo">
            <h2 id="variaveis-titulo" className="font-display text-[22px] leading-snug font-bold text-navy">
              {perguntas > 0 ? (perguntas === 1 ? 'Falta 1 pergunta' : `Faltam ${perguntas} perguntas`) : 'O que muda a cada cópia'}
            </h2>
            <div className="mt-3">
              <VariaveisFluxo fluxoId={fluxo.id} variaveis={fluxo.variaveis} aoMudar={aoMudar} />
            </div>
          </section>

          {emRevisao && <Ativar fluxo={fluxo} perguntas={perguntas} aoMudar={aoMudar} />}

          {fluxo.usaAcesso && (
            <section aria-labelledby="acesso-titulo">
              <h2 id="acesso-titulo" className="font-display text-[22px] font-bold text-navy">
                Acesso ao portal
              </h2>
              <div className="mt-2">
                <AcessoPortal dominios={fluxo.dominios} precisaAcesso={fluxo.precisaAcesso} aoMudar={aoMudar} />
              </div>
            </section>
          )}

          {ativa && (
            <section aria-labelledby="agenda-titulo">
              <h2 id="agenda-titulo" className="font-display text-[22px] font-bold text-navy">
                Agenda
              </h2>
              <div className="mt-2">
                <AgendaFluxo fluxo={fluxo} aoMudar={aoMudar} />
              </div>
            </section>
          )}
        </div>
      </div>

      <section aria-labelledby="historico-titulo" className="mt-14">
        <h2 id="historico-titulo" className="font-display text-[23px] font-bold text-navy">
          Cópias já tiradas
        </h2>
        <div className="mt-3">
          <Historico fluxoId={fluxo.id} />
        </div>
      </section>

      <div className="mt-10">
        <Botao variante="discreto" onClick={arquivar}>
          Arquivar esta tarefa
        </Botao>
        {erroArquivar && (
          <p role="alert" className="mt-1 text-[14px] font-medium text-rec-texto">
            {erroArquivar}
          </p>
        )}
      </div>
    </>
  )
}

function FluxoDetalhePage() {
  const { id } = useParams()
  const consulta = useFluxo(id)

  return (
    <EstadoConsulta consulta={consulta} paginaInteira>
      {(fluxo) => <Detalhe fluxo={fluxo} aoMudar={consulta.recarregar} />}
    </EstadoConsulta>
  )
}

export default FluxoDetalhePage
