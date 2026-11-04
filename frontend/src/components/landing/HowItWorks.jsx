import { useState } from 'react'
import { Seta } from './mesa/Anotacao.jsx'
import Fita from './mesa/Fita.jsx'

const eventos = [
  'clicou em Relatórios',
  'escolheu Loja 07 - Centro',
  'digitou 09/2026',
  'clicou em Gerar relatório',
  'baixou relatorio_839201.pdf',
]

const perguntas = [
  { valor: 'Loja 07 - Centro', variavel: 'loja', origem: <>vinda de <span className="font-medium text-navy">lojas.csv</span></> },
  { valor: '09/2026', variavel: 'mês', origem: 'sempre o mês anterior' },
]

const TOTAL_LOJAS = 25

// Número escrito à mão, com um círculo de caneta em volta.
function NumeroCirculado({ children }) {
  return (
    <span
      aria-hidden="true"
      className="relative inline-flex size-12 shrink-0 items-center justify-center font-hand text-[30px] leading-none font-bold text-ink"
    >
      {children}
      <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="absolute inset-0">
        <path d="M33 7C22 2 7 9 5 22s8 22 20 21 18-11 16-23C39 10 30 5 21 7" />
      </svg>
    </span>
  )
}

// Cada etapa é uma folha solta sobre a mesa, ligada à próxima por uma seta pontilhada.
function Etapa({ numero, titulo, ultima = false, className = '', children }) {
  return (
    <li className={`folha relative px-6 pt-5 pb-7 ${className}`}>
      <div className="flex items-center gap-2.5">
        <NumeroCirculado>{numero}</NumeroCirculado>
        <h3 className="font-display text-[19px] leading-tight font-bold text-navy">{titulo}</h3>
      </div>
      {children}
      {!ultima && (
        <>
          <Seta tipo="direita" pontilhada className="absolute top-12 -right-[52px] hidden h-8 w-16 text-navy/60 lg:block" />
          <Seta tipo="baixo" pontilhada className="absolute -bottom-12 left-12 h-11 w-6 text-navy/60 lg:hidden" />
        </>
      )}
    </li>
  )
}

function Bilhete({ valor, variavel, origem, className }) {
  const [confirmado, setConfirmado] = useState(false)
  return (
    <li className={`post-it px-4 pt-3.5 pb-3.5 ${className}`}>
      <p className="font-display text-[15px] text-navy italic">"{valor}" muda a cada vez?</p>
      <p className="mt-1 text-[12.5px] leading-snug">
        Vira a variável <strong className="font-medium text-ink">{variavel}</strong>, {origem}.
      </p>
      <button
        type="button"
        aria-pressed={confirmado}
        onClick={() => setConfirmado((atual) => !atual)}
        className={`mt-2.5 inline-flex h-8 items-center rounded-full border border-ink px-3 text-[12px] font-medium ${
          confirmado ? 'bg-ink text-white' : 'bg-papel-folha/60 text-ink hover:bg-papel-folha'
        }`}
      >
        Confirmar
      </button>
    </li>
  )
}

function HowItWorks() {
  return (
    <section id="como-funciona" aria-labelledby="como-funciona-titulo" className="py-20 lg:py-28">
      <div className="shell">
        {/* Título num cartão de fichário preso com fita */}
        <div className="folha relative max-w-[640px] px-6 pt-8 pb-7 sm:px-8 lg:-rotate-[0.6deg]">
          <Fita className="-top-2.5 left-10 -rotate-3" />
          <h2 id="como-funciona-titulo" className="font-display text-[28px] leading-[1.15] font-bold text-navy sm:text-[34px]">
            Uma gravação. Duas perguntas. Nenhum código.
          </h2>
          <p className="mt-3 text-[15.5px] leading-[1.7]">
            Você faz a tarefa uma vez, como sempre faz. O Ditto anota cada passo e pergunta o que muda de uma vez para
            outra.
          </p>
        </div>

        <ol className="mt-14 grid items-start gap-14 lg:grid-cols-3 lg:gap-12">
          <Etapa numero={1} titulo="Você grava" className="folha-pautada pl-11 lg:-rotate-[1.2deg]">
            <p className="mt-4 flex items-center gap-2 text-[13px] font-medium text-navy">
              <span aria-hidden="true" className="size-2.5 rounded-full bg-rec" />
              Gravando 00:47
            </p>
            <ul className="relative mt-3 space-y-2 pl-4 before:absolute before:top-3 before:bottom-3 before:left-1 before:w-px before:bg-tinta-media">
              {eventos.map((evento) => (
                <li
                  key={evento}
                  className="relative w-fit rounded-[3px] border border-line bg-card px-2 py-1 text-[12px] text-navy before:absolute before:top-1/2 before:-left-3 before:h-px before:w-3 before:bg-tinta-media"
                >
                  {evento}
                </li>
              ))}
            </ul>
          </Etapa>

          <Etapa numero={2} titulo="O Ditto pergunta" className="lg:mt-10 lg:rotate-[0.9deg]">
            <ul className="mt-4 space-y-4">
              {perguntas.map((pergunta, indice) => (
                <Bilhete
                  key={pergunta.variavel}
                  {...pergunta}
                  className={indice === 0 ? '-ml-2 -rotate-[1.5deg]' : 'ml-3 -mr-5 rotate-[1.8deg]'}
                />
              ))}
            </ul>
          </Etapa>

          <Etapa numero={3} titulo="Ele tira as cópias" ultima className="lg:mt-4 lg:-rotate-[0.5deg]">
            <div aria-hidden="true" className="mt-5 grid w-fit grid-cols-5 gap-1.5">
              {Array.from({ length: TOTAL_LOJAS }, (_, indice) => (
                <span key={indice} className="h-[22px] w-4 rounded-[1px] bg-ink" />
              ))}
            </div>
            <p className="mt-4 max-w-[240px] text-[13px] leading-snug">
              25 lojas, <mark className="bg-marca-texto px-0.5 text-body">4 min 38 s</mark>, salvas em relatorios/09-2026
            </p>
          </Etapa>
        </ol>
      </div>
    </section>
  )
}

export default HowItWorks
