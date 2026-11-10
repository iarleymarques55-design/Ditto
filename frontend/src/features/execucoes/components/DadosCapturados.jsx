import Botao from '../../../components/ui/Botao.jsx'
import Tabela from '../../../components/ui/Tabela.jsx'

const MAXIMO_NA_TELA = 100

export function rotuloLinhas(quantidade) {
  return quantidade === 1 ? '1 linha' : `${quantidade} linhas`
}

function celula(item, captura) {
  if (captura.tipo === 'tabela') {
    const linhas = item.linhasDeTabela[captura.chave]
    return linhas === undefined ? '' : rotuloLinhas(linhas)
  }
  return item.dados[captura.chave] ?? ''
}

// O que o Ditto leu da tela, com uma coluna por dado: a prévia do que vai para o Excel.
function DadosCapturados({ capturas, itens, aoBaixar }) {
  const visiveis = itens.slice(0, MAXIMO_NA_TELA)

  return (
    <section aria-labelledby="dados-titulo" className="mt-10">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <h2 id="dados-titulo" className="font-display text-[25px] leading-tight font-bold text-navy">
          Dados lidos da tela
        </h2>
        <Botao variante="contorno" onClick={aoBaixar}>
          Baixar em Excel
        </Botao>
      </div>
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex, jsx-a11y/prefer-tag-over-role -- área com rolagem precisa receber foco, para quem usa só o teclado */}
      <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-labelledby="dados-titulo">
        <Tabela legenda="Dados lidos da tela em cada linha">
          <thead>
            <tr>
              <th scope="col">Linha</th>
              {capturas.map((captura) => (
                <th key={captura.chave} scope="col">
                  {captura.rotulo}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visiveis.map((item) => (
              <tr key={item.id}>
                <td className="whitespace-nowrap text-grafite">
                  {item.posicao}. {item.rotulo}
                </td>
                {capturas.map((captura) => (
                  <td key={captura.chave} className="max-w-[320px] break-words text-navy">
                    {celula(item, captura)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </Tabela>
      </div>
      {itens.length > MAXIMO_NA_TELA && (
        <p className="mt-2 text-[14px]">
          Mostrando as primeiras {MAXIMO_NA_TELA} linhas. O Excel traz as {itens.length}.
        </p>
      )}
    </section>
  )
}

export default DadosCapturados
