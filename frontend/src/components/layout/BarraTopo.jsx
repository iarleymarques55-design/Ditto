import Logo from '../landing/Logo.jsx'
import Botao from '../ui/Botao.jsx'

// `perfil` e `acaoPrincipal` vêm de fora: quem monta o painel decide o que eles fazem.
function BarraTopo({ perfil, acaoPrincipal, aoSair }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-dashed border-tinta-media pb-3">
      <Logo />
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
        {perfil}
        <Botao variante="discreto" onClick={aoSair}>
          Sair
        </Botao>
        {acaoPrincipal}
      </div>
    </header>
  )
}

export default BarraTopo
