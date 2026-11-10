import Botao from '../../../components/ui/Botao.jsx'
import { formatarDuracao } from '../../../lib/datas.js'
import { ROTULO_CAMADA } from '../../reparos/index.js'
import { baixarArtefato } from '../api.js'
import { SITUACOES_ITEM } from '../situacoes.js'
import ScreenshotPasso from './ScreenshotPasso.jsx'
import TabelaCapturada from './TabelaCapturada.jsx'

function resultadoDoPasso(item, posicao) {
  const problema = item.passoProblema
  const concluida = item.situacao === 'ok' || item.situacao === 'reparado'

  if (posicao === problema) {
    if (item.situacao === 'reparado') return { texto: `Reparado por: ${ROTULO_CAMADA[item.camada]}`, classe: 'font-medium text-ink' }
    if (item.situacao === 'falhou') return { texto: 'Falhou aqui', classe: 'font-medium text-rec-texto' }
    if (item.situacao === 'espera') return { texto: 'Parado, espera você', classe: 'font-medium text-rec-texto' }
  }
  if (concluida || (problema && posicao < problema)) return { texto: 'Caminho gravado', classe: '' }
  return { texto: 'Não chegou aqui', classe: 'text-grafite/90' }
}

// O que aconteceu em uma linha da planilha, passo a passo.
function DetalheCopia({ execucaoId, item, passos, capturas }) {
  const semPassos = item.situacao === 'pendente' || item.situacao === 'rodando'

  return (
    <div>
      <h3 className="font-display text-[19px] leading-snug font-bold break-words text-navy">
        Linha {item.posicao}: {item.rotulo}
      </h3>
      <p className="mt-1 text-[14px]">
        {SITUACOES_ITEM[item.situacao]}
        {item.duracaoS ? `, em ${formatarDuracao(item.duracaoS)}` : ''}
      </p>
      {item.erro && <p className="mt-2 text-[14.5px] font-medium text-rec-texto">{item.erro}</p>}
      {item.arquivoId && (
        <Botao variante="discreto" className="mt-1 !justify-start !whitespace-normal break-all" onClick={() => baixarArtefato(item.arquivoId, item.arquivo)}>
          Baixar {item.arquivo}
        </Botao>
      )}

      {capturas
        .filter((captura) => captura.tipo === 'tabela' && item.linhasDeTabela[captura.chave] !== undefined)
        .map((captura) => (
          <TabelaCapturada
            key={`${item.id}-${captura.chave}`}
            execucaoId={execucaoId}
            itemId={item.id}
            captura={captura}
            linhas={item.linhasDeTabela[captura.chave]}
          />
        ))}

      {semPassos ? (
        <p className="mt-4 font-hand text-[24px] font-bold text-ink">
          {item.situacao === 'rodando' ? 'Saindo da máquina agora.' : 'Ainda na fila.'}
        </p>
      ) : item.situacao === 'pulado' ? (
        <p className="mt-4 text-[14.5px]">Esta linha não rodou, então não há passos para mostrar.</p>
      ) : (
        <ol className="mt-4">
          {passos.map((passo) => {
            const { texto, classe } = resultadoDoPasso(item, passo.posicao)
            return (
              <li key={passo.posicao} className="grid grid-cols-[22px_minmax(0,1fr)] gap-x-2 border-t border-pauta py-2 text-[14px] sm:grid-cols-[22px_minmax(0,1fr)_auto] sm:gap-x-3">
                <span className="font-display text-ink tabular-nums">{passo.posicao}</span>
                <span className="text-navy">{passo.intencao}</span>
                <span className={`col-start-2 text-[13px] sm:col-start-3 sm:text-right ${classe}`}>{texto}</span>
              </li>
            )
          })}
        </ol>
      )}

      {item.telaId && (
        <div className="mt-5">
          <ScreenshotPasso key={item.telaId} telaId={item.telaId} descricao={`Tela do portal na linha ${item.posicao}`} />
        </div>
      )}
    </div>
  )
}

export default DetalheCopia
