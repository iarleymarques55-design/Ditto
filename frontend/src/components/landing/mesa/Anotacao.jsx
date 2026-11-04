// Anotações de caneta: texto manuscrito e setas desenhadas à mão.

const SETAS = {
  // nome = para onde a ponta aponta
  'cima-esquerda': { viewBox: '0 0 72 52', corpo: 'M68 48C52 46 28 36 10 9', ponta: 'M7 23 10 9l14 4' },
  cima: { viewBox: '0 0 44 64', corpo: 'M30 60C37 44 33 24 17 7', ponta: 'M8 17 17 7l10 9' },
  direita: { viewBox: '0 0 84 32', corpo: 'M4 22C24 6 52 5 76 17', ponta: 'M63 7l13 10-15 6' },
  baixo: { viewBox: '0 0 32 84', corpo: 'M10 4C22 24 23 52 16 76', ponta: 'M6 64l10 12 9-13' },
}

export function Seta({ tipo, pontilhada = false, className = '' }) {
  const { viewBox, corpo, ponta } = SETAS[tipo]
  // A seta cheia se desenha uma vez ao carregar; a pontilhada é só um caminho entre folhas.
  const traco = pontilhada ? '[stroke-dasharray:3_6]' : '[stroke-dasharray:1] motion-safe:animate-desenhar'
  return (
    <svg
      aria-hidden="true"
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d={corpo} pathLength={pontilhada ? undefined : 1} className={traco} />
      <path d={ponta} pathLength={pontilhada ? undefined : 1} className={pontilhada ? '' : traco} />
    </svg>
  )
}

function Anotacao({ children, seta, className = '', classeSeta = '' }) {
  return (
    <div className={`pointer-events-none font-hand text-[26px] leading-none font-bold text-ink ${className}`}>
      <p>{children}</p>
      {seta && <Seta tipo={seta} className={classeSeta} />}
    </div>
  )
}

export default Anotacao
