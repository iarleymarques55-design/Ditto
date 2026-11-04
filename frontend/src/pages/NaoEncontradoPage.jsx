import { Link } from 'react-router'
import { useTituloPagina } from '../lib/useTituloPagina.js'

function NaoEncontradoPage() {
  useTituloPagina('Página não encontrada')

  return (
    <main className="fundo-mesa flex min-h-dvh items-center justify-center p-4">
      <div className="folha max-w-[480px] -rotate-[0.6deg] px-7 py-8">
        <h1 className="font-display text-[32px] leading-tight font-bold text-navy">Esta folha não está na mesa</h1>
        <p className="mt-3 text-[15.5px] leading-relaxed text-grafite">O endereço pode estar errado ou a página pode ter mudado de lugar.</p>
        <Link to="/" className="mt-3 inline-flex min-h-11 items-center text-[15px] font-medium text-ink underline underline-offset-4">
          Ir para a página inicial
        </Link>
      </div>
    </main>
  )
}

export default NaoEncontradoPage
