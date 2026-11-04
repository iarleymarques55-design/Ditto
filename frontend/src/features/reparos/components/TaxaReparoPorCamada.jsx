const NUMERO = new Intl.NumberFormat('pt-BR')
const PERCENTUAL = new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 })

// Uma série só, em tinta: é a própria tabela, com a barra ao lado do número.
// A escala é linear de propósito: a diferença de tamanho entre as barras é a mensagem.
function TaxaReparoPorCamada({ resolvidos }) {
  const total = resolvidos.reduce((soma, linha) => soma + linha.quantidade, 0)
  const maior = Math.max(...resolvidos.map((linha) => linha.quantidade), 1)
  const [gravado] = resolvidos

  return (
    <figure>
      <figcaption className="max-w-[60ch] text-[15px] leading-relaxed">
        Neste mês, {PERCENTUAL.format(gravado.quantidade / total)} dos {NUMERO.format(total)} passos seguiram o caminho
        gravado, sem custo de IA.
      </figcaption>
      <table className="mt-4 w-full text-left text-[14px]">
        <caption className="sr-only">Passos concluídos no mês, por quem resolveu cada um</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Quem resolveu</th>
            <th scope="col">Distribuição</th>
            <th scope="col">Passos</th>
          </tr>
        </thead>
        <tbody>
          {resolvidos.map(({ camada, rotulo, quantidade }) => {
            const parte = quantidade / total
            return (
              <tr key={camada} title={`${rotulo}: ${NUMERO.format(quantidade)} passos (${PERCENTUAL.format(parte)})`}>
                <th scope="row" className="w-[140px] py-2 pr-3 font-normal text-navy sm:w-[170px]">
                  {rotulo}
                </th>
                <td className="py-2">
                  <span
                    aria-hidden="true"
                    className="block h-2.5 min-w-[3px] rounded-r-[4px] bg-ink"
                    style={{ width: `${(quantidade / maior) * 100}%` }}
                  />
                </td>
                <td className="w-[64px] py-2 pl-3 text-right font-medium text-navy tabular-nums">
                  {NUMERO.format(quantidade)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </figure>
  )
}

export default TaxaReparoPorCamada
