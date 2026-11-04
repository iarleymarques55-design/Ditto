import { Link } from 'react-router'
import mesaHero from '../../assets/fotos/mesa-hero.webp'
import DemoAdaptacao from './demo-adaptacao/DemoAdaptacao.jsx'
import Anotacao, { Seta } from './mesa/Anotacao.jsx'
import Fita from './mesa/Fita.jsx'
import RecordIcon from './RecordIcon.jsx'

function Hero() {
  return (
    <section id="demo" aria-labelledby="hero-titulo" className="relative overflow-x-clip bg-mesa lg:bg-transparent">
      {/* Até 1280px a foto inteira da mesa vira uma faixa no topo, com todos os objetos à vista.
          A borda de baixo (só madeira) se dissolve na cor da mesa. */}
      <img
        src={mesaHero}
        alt=""
        width={1536}
        height={864}
        fetchPriority="high"
        className="block aspect-[16/9] w-full object-cover [mask-image:linear-gradient(to_bottom,black_84%,transparent)] xl:hidden"
      />

      <div className="shell relative -mt-10 grid items-start gap-14 pb-20 sm:-mt-16 lg:pb-24 xl:mt-0 xl:grid-cols-[minmax(0,1fr)_520px] xl:gap-8 xl:pt-16">
        <div className="folha relative px-6 pt-10 pb-8 sm:px-9 lg:max-w-[540px] lg:-rotate-[0.8deg] lg:px-10 lg:pt-12 lg:pb-10">
          <Fita className="-top-2.5 left-1/2 -translate-x-1/2 -rotate-2" />
          <p className="post-it absolute -top-[100px] z-20 left-1/2 w-[132px] -translate-x-1/2 rotate-[4deg] px-3 py-2.5 font-hand text-[20px] leading-[1.05] font-bold text-navy sm:-top-[84px] sm:w-[150px] sm:text-[22px] xl:-top-8 xl:-right-6 xl:left-auto xl:translate-x-0">
            Menos trabalho repetitivo.
          </p>

          <h1
            id="hero-titulo"
            className="font-display text-[40px] leading-[1.06] font-bold text-navy sm:text-[48px] lg:text-[56px]"
          >
            Faça uma vez.
            <br />O Ditto faz as
            <br />
            próximas 300.
          </h1>

          <p className="mt-6 max-w-[450px] text-[15.5px] leading-[1.7]">
            Grave uma tarefa repetitiva do navegador do jeito que você já faz. O Ditto repete para cada loja, cliente ou
            CNPJ da sua planilha, e se adapta sozinho quando o site muda de layout.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-x-8 gap-y-3">
            <Link
              to="/painel"
              className="inline-flex h-[52px] items-center gap-3 rounded-full bg-rec px-7 text-[16px] font-medium text-white shadow-[0_6px_14px_-8px_rgba(150,40,30,0.7)] hover:brightness-95"
            >
              <RecordIcon className="size-5" />
              Gravar minha primeira tarefa
            </Link>
            <Link
              to="/painel"
              className="inline-flex min-h-11 items-center text-[15px] font-medium text-navy underline decoration-ink decoration-[1.5px] underline-offset-[5px] hover:text-ink"
            >
              Ver o painel
            </Link>
          </div>

          <div className="flex items-start gap-1 pl-12 text-ink">
            <Seta tipo="cima" className="h-12 w-8 shrink-0" />
            <p className="pt-5 font-hand text-[26px] leading-none font-bold">Grave uma vez.</p>
          </div>

          <p className="mt-4 border-t border-dashed border-line pt-4 text-[12.5px] text-muted">
            Código aberto. Sua senha nunca é enviada para a IA.
          </p>
        </div>

        {/* Entre 1024 e 1280px a folha e a demo empilham, com a demo deslocada para a direita */}
        <div className="w-full max-w-[560px] lg:justify-self-end xl:justify-self-auto">
          <DemoAdaptacao>
            <Anotacao seta="baixo" className="flex items-end gap-1 pl-6" classeSeta="h-14 w-6 shrink-0 order-first translate-y-3">
              O resto é automático.
            </Anotacao>
          </DemoAdaptacao>
        </div>
      </div>
    </section>
  )
}

export default Hero
