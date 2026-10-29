import { Check, MousePointer2, Pause } from 'lucide-react'
import RecordIcon from './RecordIcon.jsx'
import WindowDots from './WindowDots.jsx'

const etapas = [
  {
    numero: 1,
    titulo: 'Você grava',
    descricao: 'Clique em Gravar, faça a tarefa no seu navegador e pronto. O Ditto registra tudo.',
    Mockup: MockupGravar,
  },
  {
    numero: 2,
    titulo: 'O Ditto entende',
    descricao: 'Ele descobre o que muda a cada vez e pergunta antes de assumir.',
    Mockup: MockupEntender,
  },
  {
    numero: 3,
    titulo: 'Ele repete',
    descricao: 'Execute quantas vezes quiser. O Ditto faz tudo no seu lugar, com a mesma precisão.',
    Mockup: MockupRepetir,
  },
]

const itensEntendidos = ['Acessos e navegações', 'Campos e formulários', 'Lógica da tarefa']

function MockupGravar() {
  return (
    <div className="flex h-[98px] max-w-[300px] flex-col rounded-lg border border-line bg-card px-3 pt-2.5 shadow-card">
      <WindowDots />
      <div className="flex flex-1 items-center justify-center pb-2">
        <span className="relative inline-flex h-[31px] items-center gap-2 rounded-full bg-rec pr-4 pl-2.5 text-[12.5px] font-medium text-white">
          <RecordIcon className="size-3.5" />
          Gravar
          <MousePointer2 size={18} strokeWidth={1.5} className="absolute -right-2.5 -bottom-3 fill-navy text-white" />
        </span>
      </div>
    </div>
  )
}

function MockupEntender() {
  return (
    <div className="max-w-[305px] rounded-lg border border-line bg-card p-4 shadow-card">
      <p className="text-[12px] font-medium text-navy">Entendendo sua gravação...</p>
      <div className="mt-3 flex items-start justify-between gap-3">
        <ul className="space-y-2 text-[11.5px]">
          {itensEntendidos.map((item) => (
            <li key={item} className="flex items-center gap-2">
              <Check size={12} strokeWidth={2.5} className="text-ok" />
              {item}
            </li>
          ))}
        </ul>
        <div className="flex flex-col gap-2.5 pt-1">
          <span className="rounded bg-card-soft px-2.5 py-1 text-[11px] text-ink">Confirmar</span>
          <span className="rounded bg-card-soft px-2.5 py-1 text-[11px] text-ink">Confirmar</span>
        </div>
      </div>
    </div>
  )
}

function MockupRepetir() {
  return (
    <div className="max-w-[285px] rounded-lg border border-line bg-card p-4 shadow-card">
      <p className="text-[12px] font-medium text-navy">Executando...</p>
      <div className="mt-3.5 h-[7px] rounded-full bg-line">
        <div className="h-full w-[65%] rounded-full bg-ok" />
      </div>
      <div className="mt-2.5 flex items-center justify-between">
        <span className="text-[12px]">Repetições: 12 / ∞</span>
        <span className="flex size-[30px] items-center justify-center rounded-full bg-card-soft text-navy">
          <Pause size={12} className="fill-navy" />
        </span>
      </div>
    </div>
  )
}

function HowItWorks() {
  return (
    <section id="como-funciona" aria-labelledby="como-funciona-titulo" className="pt-12 pb-12">
      <div className="shell">
        <h2 id="como-funciona-titulo" className="font-display text-[28px] leading-[1.15] font-bold text-navy sm:text-[34px]">
          Uma gravação. Nenhum código.
        </h2>
        <p className="mt-3 text-[15.5px] leading-[1.7]">
          Em poucos minutos você cria uma automação, mesmo sem experiência.
          <br className="hidden sm:inline" /> É simples, direto e funciona de verdade.
        </p>

        <ol className="mt-9 grid gap-x-8 gap-y-12 md:grid-cols-2 lg:grid-cols-3 lg:gap-x-0">
          {etapas.map(({ numero, titulo, descricao, Mockup }) => (
            <li key={numero} className="flex gap-4 lg:pr-6 lg:[&+&]:border-l lg:[&+&]:border-line lg:[&+&]:pl-2">
              <span
                aria-hidden="true"
                className="flex size-[42px] shrink-0 items-center justify-center rounded-full bg-line text-[19px] font-medium text-navy"
              >
                {numero}
              </span>
              <div className="min-w-0 flex-1 pt-2">
                <h3 className="text-[17px] font-medium text-navy">{titulo}</h3>
                <p className="mt-3 max-w-[310px] text-[13px] leading-[1.65]">{descricao}</p>
                <div aria-hidden="true" className="mt-8">
                  <Mockup />
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

export default HowItWorks
