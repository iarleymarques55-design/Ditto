import { Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Menu, UserPlus, X } from 'lucide-react'
import Logo from './Logo.jsx'
import { INFORMACOES, INICIO, navLinks, propsDoLink } from './navLinks.js'
import { useSecaoAtiva } from './useSecaoAtiva.js'

const linksBarra = [INICIO, ...navLinks, INFORMACOES]
const idDoLink = (link) => link.href.slice(1)

// O rodapé é baixo demais para chegar ao meio da tela: ele é tratado à parte no hook
const SECOES = [INICIO, ...navLinks].map(idDoLink)
const ID_RODAPE = idDoLink(INFORMACOES)

function Separador() {
  return <span aria-hidden="true" className="block h-6 w-px shrink-0 bg-tinta-media md:mx-2 lg:mx-3.5 xl:mx-5" />
}

function TextoLink({ ativo, children }) {
  return (
    <span
      className={`relative leading-6 after:absolute after:inset-x-0 after:-bottom-2 after:h-0.5 after:origin-left after:bg-ink motion-safe:after:transition-transform motion-safe:after:duration-200 ${
        ativo ? 'after:scale-x-100' : 'after:scale-x-0'
      }`}
    >
      {children}
    </span>
  )
}

function classeCorLink(ativo) {
  return `${ativo ? 'text-ink' : 'text-navy'} hover:text-ink motion-safe:transition-colors`
}

function Navbar() {
  const [menuAberto, setMenuAberto] = useState(false)
  const botaoMenu = useRef(null)
  const secaoAtiva = useSecaoAtiva(SECOES, ID_RODAPE)

  const estaAtivo = (link) => idDoLink(link) === secaoAtiva
  const fecharMenu = () => setMenuAberto(false)

  useEffect(() => {
    if (!menuAberto) return undefined

    function aoTeclar(evento) {
      if (evento.key !== 'Escape') return
      setMenuAberto(false)
      botaoMenu.current?.focus()
    }

    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [menuAberto])

  return (
    <header className="sticky top-0 z-30 bg-card-soft py-3">
      <div className="mx-auto w-full px-4 sm:px-8 xl:w-[82%] xl:max-w-[1240px] xl:px-0">
        {/* A altura fica reservada aqui: o menu do celular cresce por cima da página, sem empurrá-la */}
        <div className="relative h-14 md:h-16">
          <div className="absolute inset-x-0 top-0 rounded-[28px] border border-line bg-papel-folha shadow-barra">
            <div className="flex h-[54px] items-center justify-between gap-1 px-2.5 md:h-[62px] md:gap-3 md:px-4 xl:grid xl:grid-cols-[1fr_auto_1fr]">
              <div className="justify-self-start">
                <Logo tamanho="navbar" />
              </div>

              <nav aria-label="Principal" className="hidden md:block">
                <ul className="flex items-center text-[15px] font-medium whitespace-nowrap lg:text-[16px]">
                  {linksBarra.map((link, indice) => (
                    <Fragment key={link.label}>
                      {indice > 0 && (
                        <li aria-hidden="true">
                          <Separador />
                        </li>
                      )}
                      <li>
                        <a
                          href={link.href}
                          {...propsDoLink(link)}
                          aria-current={estaAtivo(link) ? 'true' : undefined}
                          className={`inline-flex min-h-11 items-center ${classeCorLink(estaAtivo(link))}`}
                        >
                          <TextoLink ativo={estaAtivo(link)}>{link.label}</TextoLink>
                        </a>
                      </li>
                    </Fragment>
                  ))}
                </ul>
              </nav>

              <div className="flex items-center justify-end gap-1 md:gap-2 lg:gap-3">
                <Link
                  to="/entrar"
                  className="hidden h-12 items-center rounded-full border border-line px-3 text-[15px] font-medium text-navy hover:bg-card-soft motion-safe:transition-colors md:inline-flex lg:px-6 lg:text-[16px]"
                >
                  Entrar
                </Link>
                <Link
                  to="/criar-conta"
                  className="inline-flex h-11 items-center gap-3 rounded-full bg-linear-to-r from-ink-claro to-ink px-3.5 text-[15px] font-semibold whitespace-nowrap text-white shadow-botao hover:brightness-95 motion-safe:transition md:h-12 md:px-4 lg:px-7 lg:text-[16px]"
                >
                  <UserPlus aria-hidden="true" className="hidden size-5 lg:block" />
                  Criar conta
                </Link>
                {/* O botão de tema claro/escuro entra aqui quando o site tiver modo escuro */}
                <button
                  ref={botaoMenu}
                  type="button"
                  onClick={() => setMenuAberto((aberto) => !aberto)}
                  aria-expanded={menuAberto}
                  aria-controls="menu-celular"
                  aria-label={menuAberto ? 'Fechar menu' : 'Abrir menu'}
                  className="inline-flex size-11 items-center justify-center rounded-full text-navy md:hidden"
                >
                  {menuAberto ? <X aria-hidden="true" size={22} /> : <Menu aria-hidden="true" size={22} />}
                </button>
              </div>
            </div>

            {menuAberto && (
              <nav id="menu-celular" aria-label="Principal" className="border-t border-tinta-clara px-4 py-1.5 md:hidden">
                <ul className="text-[16px] font-medium">
                  {linksBarra.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        {...propsDoLink(link)}
                        onClick={fecharMenu}
                        aria-current={estaAtivo(link) ? 'true' : undefined}
                        className={`flex min-h-11 items-center ${classeCorLink(estaAtivo(link))}`}
                      >
                        <TextoLink ativo={estaAtivo(link)}>{link.label}</TextoLink>
                      </a>
                    </li>
                  ))}
                  <li aria-hidden="true" className="my-1.5 h-px bg-tinta-clara" />
                  <li>
                    <Link to="/entrar" onClick={fecharMenu} className={`flex min-h-11 items-center ${classeCorLink(false)}`}>
                      Entrar
                    </Link>
                  </li>
                </ul>
              </nav>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}

export default Navbar
