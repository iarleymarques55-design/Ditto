import { formatarDiaPorExtenso } from '../../../lib/datas.js'

function fraseDasCopias(copias) {
  if (copias === 0) return 'Hoje o Ditto ainda não tirou nenhuma cópia.'
  return copias === 1 ? 'Hoje o Ditto tirou 1 cópia.' : `Hoje o Ditto tirou ${copias} cópias.`
}

function fraseDosPedidos(pedidos) {
  if (pedidos === 0) return 'Nada espera por você.'
  return pedidos === 1 ? '1 pedido espera por você.' : `${pedidos} pedidos esperam por você.`
}

// O dia contado em uma frase, com a data escrita à mão no canto da folha.
function ResumoExecucoes({ copiasHoje, pedidos }) {
  return (
    <header className="relative">
      <p className="font-hand text-[24px] leading-none font-bold text-ink lg:absolute lg:top-0 lg:right-0 lg:rotate-[-1.5deg] lg:text-[26px]">
        {formatarDiaPorExtenso()}
      </p>
      <h1 className="mt-3 font-display text-[38px] leading-[1.08] font-bold text-balance text-navy sm:text-[46px] lg:mt-0 lg:max-w-[calc(100%-250px)] lg:text-[46px] xl:text-[52px]">
        {fraseDasCopias(copiasHoje)}
        <span className="mt-1 block font-normal text-ink">{fraseDosPedidos(pedidos)}</span>
      </h1>
    </header>
  )
}

export default ResumoExecucoes
