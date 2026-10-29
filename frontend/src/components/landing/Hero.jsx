import { Link } from 'react-router'
import { ArrowRight, Check } from 'lucide-react'
import HeroAutomationCard from './HeroAutomationCard.jsx'
import RecordIcon from './RecordIcon.jsx'

const garantias = ['Funciona no Chrome', 'Sem código', 'Seguro e confiável']

function Hero() {
  return (
    <section aria-labelledby="hero-titulo" className="overflow-x-clip bg-hero">
      <div className="shell grid items-start gap-14 pt-10 pb-16 lg:grid-cols-[minmax(0,1fr)_520px] lg:gap-8 lg:pt-9 lg:pb-6">
        <div className="lg:pt-4">
          <h1
            id="hero-titulo"
            className="font-display text-[40px] leading-[1.06] font-bold text-navy sm:text-[48px] lg:text-[56px]"
          >
            Faça uma vez.
            <br />O Ditto repete
            <br />
            por você.
          </h1>

          <p className="mt-7 max-w-[450px] text-[15.5px] leading-[1.7]">
            O Ditto é um gravador de automações para o Chrome <br className="hidden lg:inline" />
            que transforma tarefas repetitivas em rotinas automáticas. <br className="hidden lg:inline" />
            Você grava, o Ditto repete.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-x-10 gap-y-3">
            <Link
              to="/painel"
              className="inline-flex h-[52px] items-center gap-3 rounded-full bg-rec px-7 text-[16px] font-medium text-white hover:brightness-95"
            >
              <RecordIcon className="size-5" />
              Começar agora — é grátis
            </Link>
            <a
              href="#como-funciona"
              className="inline-flex min-h-11 items-center gap-2 text-[15px] font-medium text-navy hover:text-ink"
            >
              Ver como funciona
              <ArrowRight size={16} />
            </a>
          </div>

          <ul className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-[12.5px] text-muted">
            {garantias.map((garantia) => (
              <li key={garantia} className="flex items-center gap-1.5">
                <Check size={14} strokeWidth={2.25} className="text-ok" />
                {garantia}
              </li>
            ))}
          </ul>
        </div>

        <HeroAutomationCard />
      </div>
    </section>
  )
}

export default Hero
