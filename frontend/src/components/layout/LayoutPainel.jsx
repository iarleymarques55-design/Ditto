import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router'
import BarraTopo from './BarraTopo.jsx'
import MenuLateral from './MenuLateral.jsx'

// A folha de fichário sobre a mesa. Ela rola com a página; as abas acompanham a leitura.
function LayoutPainel({ pedidosPendentes, perfil, acaoPrincipal, aoSair }) {
  const { pathname } = useLocation()
  const conteudo = useRef(null)
  const primeiraRota = useRef(true)

  // Ao trocar de página: volta ao topo e leva o foco para o conteúdo novo (leitor de tela e teclado)
  useEffect(() => {
    if (primeiraRota.current) {
      primeiraRota.current = false
      return
    }
    window.scrollTo(0, 0)
    conteudo.current?.focus({ preventScroll: true })
  }, [pathname])

  return (
    <div className="fundo-mesa-painel min-h-dvh px-1.5 pt-2 pb-6 text-grafite sm:px-4 sm:pt-4 lg:px-6 lg:py-7">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-papel-folha focus:px-4 focus:py-2 focus:text-navy"
      >
        Ir para o conteúdo
      </a>

      <div className="mx-auto grid max-w-[1340px] lg:grid-cols-[minmax(0,1fr)_132px] lg:items-start">
        <MenuLateral
          pedidosPendentes={pedidosPendentes}
          className="sticky top-1.5 z-20 lg:top-7 lg:order-2 lg:mt-20"
        />

        <div className="folha folha-fichario relative min-w-0 px-4 pt-3 pb-12 sm:px-7 lg:order-1 lg:min-h-[calc(100dvh-3.5rem)] lg:pr-10 lg:pl-[84px]">
          <BarraTopo perfil={perfil} acaoPrincipal={acaoPrincipal} aoSair={aoSair} />
          <main id="conteudo" ref={conteudo} tabIndex={-1} className="pt-8 outline-none lg:pt-10">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}

export default LayoutPainel
