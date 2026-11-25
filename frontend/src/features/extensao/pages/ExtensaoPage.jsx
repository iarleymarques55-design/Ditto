import { useTituloPagina } from '../../../lib/useTituloPagina.js'
import { AtualizarExtensao, ProblemasExtensao } from '../components/AjudaExtensao.jsx'
import ExecutorChrome from '../components/ExecutorChrome.jsx'
import NesteChrome from '../components/NesteChrome.jsx'
import PassosInstalacao from '../components/PassosInstalacao.jsx'

function ExtensaoPage() {
  useTituloPagina('Extensão')

  return (
    <>
      <h1 className="font-display text-[34px] leading-[1.1] font-bold text-navy sm:text-[44px]">Extensão do Ditto</h1>

      <div className="mt-9 grid items-start gap-10 lg:grid-cols-[300px_minmax(0,1fr)] lg:gap-14">
        <div className="lg:sticky lg:top-7">
          <NesteChrome />
        </div>

        <div className="divide-y divide-dashed divide-tinta-media [&>section]:py-8 [&>section:first-child]:pt-0 [&>section:last-child]:pb-0">
          <PassosInstalacao />
          <ExecutorChrome />
          <AtualizarExtensao />
          <ProblemasExtensao />
        </div>
      </div>
    </>
  )
}

export default ExtensaoPage
