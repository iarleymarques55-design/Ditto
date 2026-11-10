import MatrizGravada from './MatrizGravada.jsx'
import PortalFicticio from './PortalFicticio.jsx'
import { useDemoAdaptacao } from './useDemoAdaptacao.js'

const LINHAS_VISIVEIS = 4

// Só o símbolo do começo da linha ganha cor; o texto fica legível em navy.
const corDoSimbolo = {
  ok: 'text-ok',
  falha: 'text-rec',
  busca: 'text-ink',
  achado: 'text-ink',
}

const corDaLinha = {
  loja: 'font-medium text-navy',
  info: 'text-muted',
}

function LinhaRegistro({ texto, tipo }) {
  const simbolo = corDoSimbolo[tipo]
  return (
    <p className={`break-words whitespace-pre-wrap ${corDaLinha[tipo] ?? 'text-navy'}`}>
      {simbolo ? (
        <>
          <span className={simbolo}>{texto[0]}</span>
          {texto.slice(1)}
        </>
      ) : (
        texto
      )}
    </p>
  )
}

const botaoDemo =
  'inline-flex h-10 items-center rounded-full px-5 text-[14px] font-medium disabled:cursor-not-allowed disabled:opacity-50'

// children: anotação opcional entre a mesa (janela + matriz) e o recibo com os controles.
function DemoAdaptacao({ children }) {
  const { estado, rodar, alternarLayout } = useDemoAdaptacao()

  return (
    <div className="w-full max-w-[560px]">
      {/* No desktop, janela e matriz dividem a coluna do meio (80px), e a linha cresce com a mais alta */}
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_80px_180px]">
        <PortalFicticio
          layout={estado.layout}
          portal={estado.portal}
          className="lg:col-span-2 lg:col-start-1 lg:row-start-1 lg:self-start"
        />
        <MatrizGravada
          passoAtual={estado.passoAtual}
          concluidos={estado.concluidos}
          reparado={estado.reparado}
          className="mt-6 mr-[10px] lg:col-span-2 lg:col-start-2 lg:row-start-1 lg:-mt-3.5 lg:mr-0 lg:rotate-2 lg:self-start"
        />
      </div>

      <div className="mt-5">{children}</div>

      {/* Recibo: controles em cima, registro impresso embaixo */}
      <div className="folha mt-2 px-4 pt-3.5 pb-3 lg:rotate-[0.4deg]">
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={rodar}
            disabled={estado.rodando}
            className={`${botaoDemo} bg-ink text-white hover:brightness-110`}
          >
            Rodar uma cópia
          </button>
          <button
            type="button"
            onClick={alternarLayout}
            disabled={estado.rodando}
            className={`${botaoDemo} border border-ink text-ink hover:bg-tinta-clara`}
          >
            {estado.layout === 'A' ? 'Mudar o layout do site' : 'Voltar ao layout antigo'}
          </button>
        </div>

        <div
          role="log"
          aria-live="polite"
          aria-label="Registro da demo"
          className="mt-3 flex min-h-[72px] flex-col justify-end border-t border-dashed border-line pt-2.5 font-mono text-[11.5px] leading-[18px]"
        >
          {estado.registro.slice(-LINHAS_VISIVEIS).map((linha) => (
            <LinhaRegistro key={linha.id} texto={linha.texto} tipo={linha.tipo} />
          ))}
        </div>
      </div>
    </div>
  )
}

export default DemoAdaptacao
