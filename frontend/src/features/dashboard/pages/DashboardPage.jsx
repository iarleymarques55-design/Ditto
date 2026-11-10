import { Link } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import EstadoVazio from '../../../components/ui/EstadoVazio.jsx'
import { formatarQuando } from '../../../lib/datas.js'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { LogExecucao, ProgressoLote, StatusExecucao } from '../../execucoes/index.js'
import { ListaPedidos } from '../../reparos/index.js'
import ExecucoesRecentes from '../components/ExecucoesRecentes.jsx'
import ResumoExecucoes from '../components/ResumoExecucoes.jsx'
import { useResumo } from '../hooks/useResumo.js'

function NaMaquina({ execucao }) {
  const rodando = execucao.situacao === 'rodando'

  return (
    <section aria-labelledby="maquina-titulo" className="mt-14">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <h2 id="maquina-titulo" className="font-display text-[25px] font-bold text-navy">
          {rodando ? 'Na máquina agora' : 'Última a sair da máquina'}
        </h2>
        <StatusExecucao situacao={execucao.situacao} />
      </div>

      <p className="mt-1.5 text-[15px]">
        <Link
          to={`/painel/execucoes/${execucao.id}`}
          className="font-medium text-navy underline decoration-ink/40 underline-offset-[3px] hover:text-ink hover:decoration-ink"
        >
          {execucao.fluxoNome}
        </Link>
        : {execucao.concluidas} de {execucao.total} cópias prontas
      </p>

      <div className="mt-4 grid items-start gap-8 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] xl:gap-10">
        <ProgressoLote itens={execucao.itens} />
        <LogExecucao linhas={execucao.log} />
      </div>
    </section>
  )
}

function Agenda({ agenda }) {
  if (agenda.length === 0) return <EstadoVazio titulo="Nada agendado." />
  return (
    <ul>
      {agenda.map(({ id, nome, proxima, texto }) => (
        <li key={id} className="border-b border-pauta py-3">
          <p className="font-display text-[16px] leading-snug font-bold text-ink">{formatarQuando(proxima)}</p>
          <Link
            to={`/painel/tarefas/${id}`}
            className="mt-1 inline-block text-[14.5px] font-medium text-navy underline decoration-ink/40 underline-offset-[3px] hover:text-ink hover:decoration-ink"
          >
            {nome}
          </Link>
          <p className="text-[13.5px]">{texto}</p>
        </li>
      ))}
    </ul>
  )
}

function DashboardPage() {
  useTituloPagina('Mesa')
  const consulta = useResumo()

  return (
    <EstadoConsulta consulta={consulta} paginaInteira>
      {({ copiasHoje, pedidos, destaque, recentes, agenda }) => (
        <>
          <ResumoExecucoes copiasHoje={copiasHoje} pedidos={pedidos.length} />

          {pedidos.length > 0 && (
            <section aria-label="Pedidos esperando você" className="mt-10">
              <ListaPedidos pedidos={pedidos} aoResponder={consulta.recarregar} />
            </section>
          )}

          {destaque ? (
            <NaMaquina execucao={destaque} />
          ) : (
            <section aria-labelledby="maquina-titulo" className="mt-14">
              <h2 id="maquina-titulo" className="font-display text-[25px] font-bold text-navy">
                Na máquina agora
              </h2>
              <EstadoVazio titulo="A máquina está parada.">Quando uma tarefa rodar, as cópias aparecem aqui, uma a uma.</EstadoVazio>
            </section>
          )}

          <div className="mt-14 grid items-start gap-10 xl:grid-cols-[minmax(0,1fr)_280px] xl:gap-12">
            <section aria-labelledby="recentes-titulo">
              <div className="flex flex-wrap items-center justify-between gap-x-4">
                <h2 id="recentes-titulo" className="font-display text-[23px] font-bold text-navy">
                  Últimas execuções
                </h2>
                {recentes.length > 0 && (
                  <Botao variante="discreto" para="/painel/execucoes">
                    Ver todas
                  </Botao>
                )}
              </div>
              <div className="mt-2">
                {recentes.length > 0 ? <ExecucoesRecentes execucoes={recentes} /> : <EstadoVazio titulo="Nenhuma execução ainda." />}
              </div>
            </section>

            <section aria-labelledby="agenda-titulo">
              <h2 id="agenda-titulo" className="font-display text-[23px] font-bold text-navy">
                Na agenda
              </h2>
              <div className="mt-2 border-t-[1.5px] border-navy/40">
                <Agenda agenda={agenda} />
              </div>
            </section>
          </div>
        </>
      )}
    </EstadoConsulta>
  )
}

export default DashboardPage
