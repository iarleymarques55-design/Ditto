import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import AcessosConta from '../components/AcessosConta.jsx'
import AvisosConta from '../components/AvisosConta.jsx'
import Cracha from '../components/Cracha.jsx'
import DadosConta from '../components/DadosConta.jsx'
import ExcluirConta from '../components/ExcluirConta.jsx'
import SenhaConta from '../components/SenhaConta.jsx'

function ContaPage() {
  useTituloPagina('Sua conta')

  return (
    <>
      <h1 className="font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">Sua conta</h1>

      <div className="mt-9 grid items-start gap-10 lg:grid-cols-[300px_minmax(0,1fr)] lg:gap-14">
        <div className="lg:sticky lg:top-7">
          <Cracha />
        </div>

        <div className="divide-y divide-dashed divide-tinta-media [&>section]:py-8 [&>section:first-child]:pt-0 [&>section:last-child]:pb-0">
          <DadosConta />
          <AvisosConta />
          <SenhaConta />
          <AcessosConta />
          <ExcluirConta />
        </div>
      </div>
    </>
  )
}

export default ContaPage
