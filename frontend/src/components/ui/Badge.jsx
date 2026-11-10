const TONS = {
  ok: 'border-ok-texto text-ok-texto',
  tinta: 'border-ink text-ink',
  perigo: 'border-rec-texto text-rec-texto',
  neutro: 'border-grafite text-grafite',
}

// Sempre com texto, para o estado nunca depender só da cor. `carimbo` inclina e bate na folha, como um carimbo.
function Badge({ tom = 'neutro', Icone, carimbo = false, className = '', children }) {
  const inclinacao = carimbo ? '-rotate-2 border-2 px-2.5 py-1 text-[14px] motion-safe:animate-carimbar' : 'border-[1.5px] px-1.5 py-0.5 text-[12.5px]'
  return (
    <span className={`inline-flex w-fit items-center gap-1 rounded-[2px] bg-papel-folha/70 font-medium whitespace-nowrap ${inclinacao} ${TONS[tom]} ${className}`}>
      {Icone && <Icone aria-hidden="true" className={carimbo ? 'size-4' : 'size-3.5'} />}
      {children}
    </span>
  )
}

export default Badge
