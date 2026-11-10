import EstadoConsulta from '../../../components/ui/EstadoConsulta.jsx'
import EstadoVazio from '../../../components/ui/EstadoVazio.jsx'
import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import ListaPedidos from '../components/ListaPedidos.jsx'
import ReparoItem from '../components/ReparoItem.jsx'
import TaxaReparoPorCamada from '../components/TaxaReparoPorCamada.jsx'
import { useReparos } from '../hooks/useReparos.js'

function resumoDosReparos(reparos) {
  const sozinho = reparos.filter((reparo) => reparo.camada < 4).length
  if (reparos.length === 0) return 'Nenhum site mudou por enquanto.'
  if (sozinho === reparos.length) {
    return reparos.length === 1 ? 'O Ditto consertou 1 caminho sozinho.' : `O Ditto consertou ${sozinho} caminhos sozinho.`
  }
  return `O Ditto consertou ${sozinho} de ${reparos.length} caminhos sozinho.`
}

function ReparosPage() {
  useTituloPagina('Reparos')
  const consulta = useReparos()

  return (
    <EstadoConsulta consulta={consulta} paginaInteira>
      {({ reparos, resolvidos, pedidos }) => (
        <>
          <h1 className="max-w-[20ch] font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">
            {resumoDosReparos(reparos)}
          </h1>

          <section aria-labelledby="pedidos-titulo" className="mt-10">
            <h2 id="pedidos-titulo" className="font-display text-[23px] font-bold text-navy">
              Esperando você
            </h2>
            {pedidos.length > 0 ? (
              <div className="mt-4">
                <ListaPedidos pedidos={pedidos} aoResponder={consulta.recarregar} />
              </div>
            ) : (
              <EstadoVazio titulo="Nenhum pedido aberto." />
            )}
          </section>

          {resolvidos.length > 0 && (
            <section aria-labelledby="quem-resolveu-titulo" className="mt-14 max-w-[760px]">
              <h2 id="quem-resolveu-titulo" className="font-display text-[23px] font-bold text-navy">
                Quem resolveu cada passo
              </h2>
              <div className="mt-3">
                <TaxaReparoPorCamada resolvidos={resolvidos} />
              </div>
            </section>
          )}

          <section aria-labelledby="historico-titulo" className="mt-14">
            <h2 id="historico-titulo" className="font-display text-[23px] font-bold text-navy">
              Caminhos que mudaram
            </h2>
            {reparos.length > 0 ? (
              <ul className="border-t-[1.5px] border-navy/40 mt-3">
                {reparos.map((reparo) => (
                  <ReparoItem key={reparo.id} reparo={reparo} />
                ))}
              </ul>
            ) : (
              <EstadoVazio titulo="Nada mudou até agora." />
            )}
          </section>
        </>
      )}
    </EstadoConsulta>
  )
}

export default ReparosPage
