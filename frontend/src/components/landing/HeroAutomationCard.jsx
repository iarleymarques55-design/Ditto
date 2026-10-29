import { Check, Clock, Repeat, Timer } from 'lucide-react'
import WindowDots from './WindowDots.jsx'

const passos = [
  { numero: 1, texto: 'Acessar o site', estado: 'feito' },
  { numero: 2, texto: 'Fazer login', estado: 'feito' },
  { numero: 3, texto: 'Preencher o formulário', estado: 'atual' },
  { numero: 4, texto: 'Enviar', estado: 'feito' },
  { numero: 5, texto: 'Verificar se o cadastro foi concluído', estado: 'pendente' },
]

const detalhes = [
  { Icone: Timer, rotulo: 'Duração', valor: '2 min 14 s' },
  { Icone: Repeat, rotulo: 'Repetições', valor: 'Ilimitadas' },
  { Icone: Clock, rotulo: 'Última execução', valor: 'hoje, 10:24' },
]

function IconePasso({ numero, estado }) {
  if (estado === 'pendente') {
    return <span className="size-[18px] shrink-0 rounded-full border border-muted/45" />
  }
  return (
    <span className="flex size-[18px] shrink-0 items-center justify-center rounded-full bg-navy text-[10px] font-medium text-white">
      {estado === 'atual' ? numero : <Check size={11} strokeWidth={3} />}
    </span>
  )
}

function Anotacao() {
  return (
    <div className="absolute top-3 left-[calc(100%+64px)] hidden xl:block">
      <p className="-rotate-12 font-hand text-[21px] leading-[1.05] font-medium text-navy">
        <span className="block">grava,</span>
        <span className="block pl-1.5">repete,</span>
        <span className="block pl-3">resolve.</span>
      </p>
      <svg
        viewBox="0 0 40 44"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="absolute top-[78px] -left-7 h-11 w-10 text-navy"
      >
        <path d="M36 2C38 18 28 34 5 40" />
        <path d="M12.5 34.5 5 40l8.5 2.5" />
      </svg>
    </div>
  )
}

function HeroAutomationCard() {
  return (
    <div aria-hidden="true" className="relative w-full max-w-[440px]">
      <div className="absolute inset-0 translate-x-[14px] translate-y-[16px] rotate-[2deg] rounded-xl border border-line bg-card shadow-card" />
      <div className="absolute inset-0 -translate-x-[6px] translate-y-[14px] -rotate-[1.5deg] rounded-xl border border-line bg-card shadow-card" />

      <div className="relative rounded-xl border border-line bg-card px-4 pt-3 pb-4 shadow-card">
        <WindowDots />

        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-[14px] font-medium text-navy">Automação: Cadastro no sistema</p>
          <span className="rounded-full bg-ok-soft px-2.5 py-0.5 text-[11px] font-medium text-ok">Concluída</span>
        </div>

        <ol className="mt-2">
          {passos.map((passo) => (
            <li
              key={passo.numero}
              className="flex h-[38px] items-center gap-3.5 border-b border-line pl-1.5 text-[12px] last:border-b-0"
            >
              <IconePasso numero={passo.numero} estado={passo.estado} />
              <span className="w-2 text-muted">{passo.numero}</span>
              <span>{passo.texto}</span>
            </li>
          ))}
        </ol>

        <div className="mt-3 rounded-lg bg-card-soft px-4 py-3.5">
          <p className="text-[11.5px] font-medium text-navy">Detalhes da gravação</p>
          <dl className="mt-2.5 grid grid-cols-3 gap-3">
            {detalhes.map(({ Icone, rotulo, valor }) => (
              <div key={rotulo} className="flex items-start gap-2">
                <Icone size={16} strokeWidth={1.6} className="mt-0.5 shrink-0 text-muted" />
                <div>
                  <dt className="text-[10.5px] text-muted">{rotulo}</dt>
                  <dd className="mt-0.5 text-[12px] font-medium text-navy">{valor}</dd>
                </div>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <Anotacao />
    </div>
  )
}

export default HeroAutomationCard
