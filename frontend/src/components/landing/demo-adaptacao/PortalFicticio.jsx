import WindowDots from '../WindowDots.jsx'
import { LINHAS_TABELA, PORTAL_URL } from './demoRoteiro.js'

const botaoPortal = 'inline-flex h-7 items-center rounded-[3px] px-2.5 text-[11.5px] whitespace-nowrap'

function Campo({ rotulo, valor, vazio, seta = false, className = '' }) {
  return (
    <div className={className}>
      <p className="text-[10.5px] text-muted">{rotulo}</p>
      <p className="mt-1 flex h-8 items-center justify-between gap-2 rounded-[3px] border border-line px-2.5 text-[12px]">
        {valor ? (
          <span key={valor} className="truncate text-navy motion-safe:animate-surgir">
            {valor}
          </span>
        ) : (
          <span className="text-muted/70">{vazio}</span>
        )}
        {seta && <span className="text-[10px] text-muted">▾</span>}
      </p>
    </div>
  )
}

function ExportarLayoutA({ destaque }) {
  return (
    <div className="flex gap-1.5">
      <span className={`${botaoPortal} border border-line text-navy`}>Imprimir</span>
      <span
        className={`${botaoPortal} bg-navy text-white ${destaque ? 'ring-2 ring-tinta-media ring-offset-1 motion-safe:animate-piscar' : ''}`}
      >
        Exportar PDF
      </span>
      <span className={`${botaoPortal} border border-line text-navy`}>Excel</span>
    </div>
  )
}

function ExportarLayoutB({ menuAberto, destaque }) {
  const itens = ['Imprimir', 'Baixar como PDF', 'Baixar como Excel']
  return (
    <div className="relative inline-block">
      <span className={`${botaoPortal} border border-line text-navy ${menuAberto ? 'bg-card-soft' : ''}`}>Ações ▾</span>
      {menuAberto && (
        <div className="absolute top-full left-0 z-10 mt-1 w-[168px] rounded-[3px] border border-line bg-card p-1 shadow-card motion-safe:animate-surgir">
          {itens.map((item) => {
            const marcado = destaque && item === 'Baixar como PDF'
            return (
              <span
                key={item}
                className={`block rounded-[2px] border px-2 py-1 text-[11px] ${
                  marcado ? 'border-dashed border-ink bg-tinta-clara text-ink' : 'border-transparent text-navy'
                }`}
              >
                {item}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TabelaRelatorio({ visivel }) {
  return (
    <table className="mt-2.5 w-full text-left text-[11.5px]">
      <thead>
        <tr className="border-b border-line text-[10.5px] text-muted">
          <th className="pb-1 font-normal">Pedido</th>
          <th className="pb-1 font-normal">Data</th>
          <th className="pb-1 text-right font-normal">Valor</th>
        </tr>
      </thead>
      <tbody className={visivel ? 'text-navy motion-safe:animate-surgir' : 'invisible'}>
        {LINHAS_TABELA.map((linha) => (
          <tr key={linha.pedido} className="h-6 border-b border-line last:border-b-0">
            <td>{linha.pedido}</td>
            <td>{linha.data}</td>
            <td className="text-right">{linha.valor}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// Janela do portal fictício. É só ilustração: quem conta o que aconteceu é o registro.
function PortalFicticio({ layout, portal, className = '' }) {
  return (
    <div aria-hidden="true" className={`rounded-xl border border-line bg-card shadow-papel ${className}`}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        <WindowDots />
        <span className="min-w-0 flex-1 truncate rounded-full bg-card-soft px-3 py-1 text-[11px] text-muted">
          {PORTAL_URL}
        </span>
      </div>

      <div className="px-4 pt-3.5 pb-4 lg:pr-[96px]">
        <Campo rotulo="Loja" valor={portal.loja} seta />
        <div className="mt-2.5 flex items-end gap-2">
          <Campo rotulo="Mês" valor={portal.mes} vazio="mm/aaaa" className="w-[92px]" />
          <span
            className={`${botaoPortal} h-8 bg-navy text-white ${portal.destaque === 'gerar' ? 'ring-2 ring-tinta-media ring-offset-1' : ''}`}
          >
            Gerar relatório
          </span>
        </div>

        <div key={layout} className="mt-4 motion-safe:animate-surgir">
          {layout === 'A' ? (
            <ExportarLayoutA destaque={portal.destaque === 'pdf'} />
          ) : (
            <ExportarLayoutB menuAberto={portal.menuAberto} destaque={portal.destaque === 'pdf'} />
          )}
        </div>
        <TabelaRelatorio visivel={portal.tabela} />
      </div>
    </div>
  )
}

export default PortalFicticio
