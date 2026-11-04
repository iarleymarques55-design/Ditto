import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import Botao from '../../../components/ui/Botao.jsx'
import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import { formatarDuracao, formatarQuando } from '../../../lib/datas.js'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { ListaPedidos, usePedidos } from '../../reparos/index.js'
import { baixarRelatorio, cancelarExecucao, exportarPlanilha } from '../api.js'
import DetalheCopia from '../components/DetalheCopia.jsx'
import LogExecucao from '../components/LogExecucao.jsx'
import ProgressoLote from '../components/ProgressoLote.jsx'
import StatusExecucao from '../components/StatusExecucao.jsx'
import { useExecucao } from '../hooks/useExecucao.js'
import { emAndamento } from '../situacoes.js'

const PRIORIDADE_INICIAL = ['espera', 'falhou', 'rodando', 'reparado', 'ok']

function itemEmDestaque(itens) {
  for (const situacao of PRIORIDADE_INICIAL) {
    const item = itens.find((candidato) => candidato.situacao === situacao)
    if (item) return item.id
  }
  return itens[0]?.id
}

function frasePrincipal(execucao) {
  const { concluidas, total, reparos, falhas } = execucao
  const partes = [`${concluidas} de ${total} cópias prontas`]
  if (reparos > 0) partes.push(reparos === 1 ? '1 com reparo' : `${reparos} com reparo`)
  if (falhas > 0) partes.push(falhas === 1 ? '1 falhou' : `${falhas} falharam`)
  return `${partes.join(', ')}.`
}

function Detalhe({ execucao, aoMudar }) {
  useTituloPagina(execucao.fluxoNome)
  const [escolhido, setEscolhido] = useState(null)
  const consultaPedidos = usePedidos()
  const { recarregar: recarregarPedidos } = consultaPedidos

  // Assim que a execução para esperando alguém, o post-it aparece sem aguardar a próxima consulta
  useEffect(() => {
    if (execucao.situacao === 'espera') recarregarPedidos()
  }, [execucao.situacao, recarregarPedidos])

  const [cancelando, setCancelando] = useState(false)
  const pedidos = (consultaPedidos.dados ?? []).filter((pedido) => pedido.execucaoId === execucao.id)

  // Sem escolha da pessoa, os detalhes acompanham o que está acontecendo
  const selecionado = escolhido ?? itemEmDestaque(execucao.itens)
  const item = execucao.itens.find((candidato) => candidato.id === selecionado)
  const aberta = emAndamento(execucao.situacao)
  const [erroDownload, setErroDownload] = useState(null)

  async function cancelar() {
    setCancelando(true)
    setErroDownload(null)
    try {
      await cancelarExecucao(execucao.id)
    } catch (falha) {
      setErroDownload(falha.message)
    }
    setCancelando(false)
    aoMudar()
  }

  async function baixar(acao) {
    setErroDownload(null)
    try {
      await acao(execucao.id)
    } catch (falha) {
      setErroDownload(falha.message)
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="font-display text-[32px] leading-[1.1] font-bold text-navy sm:text-[44px]">{execucao.fluxoNome}</h1>
          <p className="mt-2 text-[15px]">
            {execucao.disparo === 'agendada' ? 'Rodou pela agenda' : 'Disparada à mão'}, {formatarQuando(execucao.inicio)},{' '}
            {execucao.fim ? `levou ${formatarDuracao(execucao.duracaoS)}` : `há ${formatarDuracao(execucao.duracaoS)}`}.{' '}
            <Link
              to={`/painel/tarefas/${execucao.fluxoId}`}
              className="text-navy underline decoration-ink/60 underline-offset-[3px] hover:text-ink"
            >
              Ver a tarefa
            </Link>
          </p>
        </div>
        <StatusExecucao situacao={execucao.situacao} carimbo />
      </div>

      {pedidos.length > 0 && (
        <section aria-label="Esperando você" className="mt-8">
          <ListaPedidos
            pedidos={pedidos}
            aoResponder={() => {
              consultaPedidos.recarregar()
              setEscolhido(null)
              aoMudar()
            }}
          />
        </section>
      )}

      <section aria-labelledby="copias-titulo" className="mt-9">
        <h2 id="copias-titulo" className="font-display text-[25px] leading-tight font-bold text-navy" aria-live="polite">
          {frasePrincipal(execucao)}
        </h2>
        <p className="mt-1 text-[14px]">Cada folha é uma linha da planilha. Escolha uma para ver o que aconteceu.</p>
        <div className="mt-4">
          <ProgressoLote itens={execucao.itens} selecionado={selecionado} aoSelecionar={setEscolhido} />
        </div>
      </section>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section aria-label="Detalhes da cópia escolhida">{item && <DetalheCopia item={item} passos={execucao.passos} />}</section>

        <section aria-labelledby="registro-titulo">
          <h2 id="registro-titulo" className="font-display text-[19px] font-bold text-navy">
            Registro
          </h2>
          <div className="mt-3">
            <LogExecucao linhas={execucao.log} />
          </div>
          {aberta && (
            <Botao variante="contorno" className="mt-5" disabled={cancelando} onClick={cancelar}>
              Cancelar esta execução
            </Botao>
          )}
          {!aberta && (
            <div className="mt-5 flex flex-wrap gap-x-4 gap-y-1">
              <Botao variante="discreto" onClick={() => baixar(baixarRelatorio)}>
                Baixar relatório em PDF
              </Botao>
              <Botao variante="discreto" onClick={() => baixar(exportarPlanilha)}>
                Exportar em CSV
              </Botao>
            </div>
          )}
          {erroDownload && (
            <p role="alert" className="mt-2 text-[14px] font-medium text-rec-texto">
              {erroDownload}
            </p>
          )}
        </section>
      </div>
    </>
  )
}

function ExecucaoDetalhePage() {
  const { id } = useParams()
  const consulta = useExecucao(id)

  return (
    <EstadoConsulta consulta={consulta} paginaInteira>
      {(execucao) => <Detalhe key={execucao.id} execucao={execucao} aoMudar={consulta.recarregar} />}
    </EstadoConsulta>
  )
}

export default ExecucaoDetalhePage
