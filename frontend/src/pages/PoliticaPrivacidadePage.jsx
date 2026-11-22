import { useEffect } from 'react'
import { Link } from 'react-router'
import Logo from '../components/landing/Logo.jsx'
import Fita from '../components/landing/mesa/Fita.jsx'
import { useSecaoAtiva } from '../components/landing/useSecaoAtiva.js'
import RegistroDoDitto from '../components/privacidade/RegistroDoDitto.jsx'
import { ATUALIZADA_EM, Email, secoes } from '../components/privacidade/secoesPolitica.jsx'
import { useTituloPagina } from '../lib/useTituloPagina.js'

const ANO_ATUAL = new Date().getFullYear()
// Constante: o useSecaoAtiva observa a mesma lista a cada renderização
const IDS_SECOES = secoes.map((secao) => secao.id)
const ID_CONTATO = 'contato'

function Sumario({ idTitulo, ativa }) {
  return (
    <nav aria-labelledby={idTitulo}>
      <h2 id={idTitulo} className="text-[13.5px] font-semibold text-navy">
        Nesta página
      </h2>
      <ul className="mt-2 border-l border-line">
        {secoes.map((secao) => {
          const atual = secao.id === ativa
          return (
            <li key={secao.id}>
              <a
                href={`#${secao.id}`}
                aria-current={atual ? 'location' : undefined}
                className={`-ml-px flex min-h-11 items-center border-l-2 py-1 pl-3 text-[14px] leading-snug pointer-fine:min-h-0 pointer-fine:py-1.5 ${
                  atual ? 'border-ink font-medium text-navy' : 'border-transparent text-grafite hover:text-ink'
                }`}
              >
                {secao.titulo}
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function PoliticaPrivacidadePage() {
  useTituloPagina('Política de privacidade')
  const ativa = useSecaoAtiva(IDS_SECOES, ID_CONTATO)

  // A página é montada depois que o navegador procura a âncora: o salto para a seção é feito aqui.
  // Sem âncora, a leitura começa do topo (quem vem da landing chega com a página rolada).
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1))
    const secao = id && document.getElementById(id)
    if (secao) secao.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [])

  return (
    <div className="fundo-mesa min-h-dvh">
      <main className="shell pt-4 pb-16 sm:pt-8">
        <article className="folha mx-auto max-w-[1040px] px-5 pt-4 pb-14 sm:px-10 sm:pt-6 lg:px-14">
          {/* Papel timbrado: a marca no alto da própria folha, como no cabeçalho do painel */}
          <header className="flex flex-wrap items-center justify-between gap-x-6 border-b border-dashed border-tinta-media pb-3">
            <Logo />
            <Link
              to="/"
              className="inline-flex min-h-11 items-center text-[15px] font-medium text-navy underline decoration-ink/40 decoration-[1.5px] underline-offset-4 hover:text-ink hover:decoration-ink"
            >
              Voltar para o início
            </Link>
          </header>

          <div className="mt-9 max-w-[60ch] sm:mt-12">
            <h1 className="font-display text-[36px] leading-[1.05] font-bold text-navy sm:text-[52px]">
              Política de privacidade
            </h1>
            <p className="mt-4 text-[17px] leading-relaxed text-grafite">
              O Ditto grava o que você faz para repetir depois. Esta página mostra o que fica anotado, o que ele nunca
              toca e para onde cada coisa vai.
            </p>
            <p className="mt-3 text-[14px] text-muted">Atualizada em {ATUALIZADA_EM}</p>
          </div>

          <RegistroDoDitto />

          <div className="mt-14 grid gap-10 lg:grid-cols-[210px_minmax(0,1fr)] lg:gap-14">
            {/* No computador, o sumário fica na margem e acompanha a leitura; no celular, recolhido no topo */}
            <aside className="hidden lg:block">
              <div className="sticky top-8">
                <Sumario idTitulo="sumario-margem" ativa={ativa} />
              </div>
            </aside>
            <details className="rounded-[2px] border border-line px-4 py-1 lg:hidden">
              <summary className="flex min-h-11 cursor-pointer items-center text-[15px] font-medium text-navy">
                Ir para uma seção
              </summary>
              <div className="pb-3">
                <Sumario idTitulo="sumario-recolhido" ativa={ativa} />
              </div>
            </details>

            <div className="max-w-[70ch] text-[16px] leading-[1.7] text-grafite">
              {secoes.map((secao) => (
                <section
                  key={secao.id}
                  id={secao.id}
                  aria-labelledby={`${secao.id}-titulo`}
                  className="scroll-mt-8 border-t border-line pt-9 pb-10 first:border-t-0 first:pt-0"
                >
                  <h2
                    id={`${secao.id}-titulo`}
                    className="font-display text-[24px] leading-tight font-bold text-navy sm:text-[28px]"
                  >
                    {secao.titulo}
                  </h2>
                  <div className="mt-4 space-y-4">{secao.conteudo}</div>
                </section>
              ))}

              <aside
                id={ID_CONTATO}
                aria-labelledby="contato-titulo"
                className="post-it relative mt-4 max-w-[440px] px-6 pt-7 pb-6 sm:rotate-[0.6deg]"
              >
                <Fita className="-top-2.5 left-1/2 -translate-x-1/2 rotate-2" />
                <h2 id="contato-titulo" className="font-display text-[20px] leading-snug font-bold text-navy">
                  Ficou alguma dúvida sobre os seus dados?
                </h2>
                <p className="mt-2 text-[15.5px] leading-relaxed text-navy">
                  Escreva para <Email />. A resposta vem em até 15 dias.
                </p>
              </aside>
            </div>
          </div>
        </article>

        <p className="mx-auto mt-6 max-w-[1040px] text-center text-[13px] text-navy">
          © {ANO_ATUAL} Ditto. Projeto de código aberto.
        </p>
      </main>
    </div>
  )
}

export default PoliticaPrivacidadePage
