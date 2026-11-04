// Tabela de caderno: só as linhas de pauta separam os registros.
function Tabela({ legenda, children, className = '' }) {
  return (
    <table
      className={`w-full text-left text-[14px] [&_tbody_tr]:border-b [&_tbody_tr]:border-pauta [&_td]:py-3 [&_td]:pr-3 [&_td:last-child]:pr-0 [&_th]:pr-3 [&_th]:pb-2 [&_th]:text-[13px] [&_th]:font-medium [&_th:last-child]:pr-0 [&_thead_tr]:border-b-[1.5px] [&_thead_tr]:border-navy/40 ${className}`}
    >
      <caption className="sr-only">{legenda}</caption>
      {children}
    </table>
  )
}

export default Tabela
