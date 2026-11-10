import { useState } from 'react'
import Botao from '../../../components/ui/Botao.jsx'
import Tabela from '../../../components/ui/Tabela.jsx'
import { obterDadosDaLinha } from '../api.js'
import { rotuloLinhas } from './DadosCapturados.jsx'

const MAXIMO_NA_TELA = 50

// Uma tabela pode ter muitas linhas: o conteúdo só é buscado quando alguém pede para ver.
function TabelaCapturada({ execucaoId, itemId, captura, linhas }) {
  const [conteudo, setConteudo] = useState(null)
  const [erro, setErro] = useState(null)
  const [buscando, setBuscando] = useState(false)

  async function abrir() {
    setBuscando(true)
    setErro(null)
    try {
      const dados = await obterDadosDaLinha(execucaoId, itemId)
      setConteudo(dados[captura.chave] ?? [])
    } catch (falha) {
      setErro(falha.message)
    } finally {
      setBuscando(false)
    }
  }

  if (!conteudo) {
    return (
      <div className="mt-2">
        <Botao variante="discreto" disabled={buscando} onClick={abrir}>
          {buscando ? 'Buscando...' : `Ver ${captura.rotulo} (${rotuloLinhas(linhas)})`}
        </Botao>
        {erro && (
          <p role="alert" className="text-[14px] font-medium text-rec-texto">
            {erro}
          </p>
        )}
      </div>
    )
  }

  // As colunas são as da gravação, na ordem do site. Coluna nova no site entra no fim.
  const colunas = [...new Set([...captura.colunas, ...conteudo.flatMap((linha) => Object.keys(linha))])]

  return (
    <div className="mt-3">
      <h4 className="font-display text-[16px] font-bold text-navy">{captura.rotulo}</h4>
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex, jsx-a11y/prefer-tag-over-role -- área com rolagem precisa receber foco, para quem usa só o teclado */}
      <div className="mt-1 overflow-x-auto" tabIndex={0} role="region" aria-label={`Tabela ${captura.rotulo}`}>
        <Tabela legenda={`Tabela ${captura.rotulo}`}>
          <thead>
            <tr>
              {colunas.map((coluna) => (
                <th key={coluna} scope="col">
                  {coluna}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {conteudo.slice(0, MAXIMO_NA_TELA).map((linha, indice) => (
              // As linhas não têm identificador próprio, e esta lista nunca muda de ordem
              // oxlint-disable-next-line react/no-array-index-key
              <tr key={indice}>
                {colunas.map((coluna) => (
                  <td key={coluna} className="max-w-[260px] break-words text-navy">
                    {linha[coluna] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </Tabela>
      </div>
      {conteudo.length > MAXIMO_NA_TELA && (
        <p className="mt-1 text-[14px]">
          Mostrando {MAXIMO_NA_TELA} de {conteudo.length} linhas. O Excel traz todas.
        </p>
      )}
    </div>
  )
}

export default TabelaCapturada
