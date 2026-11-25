import { NOME_DA_PASTA } from '../download.js'
import { classeCodigo, classeTexto, classeTitulo } from './campos.js'

export function AtualizarExtensao() {
  return (
    <section aria-labelledby="atualizar-titulo">
      <h2 id="atualizar-titulo" className={classeTitulo}>
        Atualizar a extensão
      </h2>
      <ol className={`mt-3 list-decimal space-y-2 pl-5 ${classeTexto}`}>
        <li>Baixe o arquivo de novo, no quadro Neste Chrome.</li>
        <li>
          Extraia por cima da pasta <code className={classeCodigo}>{NOME_DA_PASTA}</code> que você já tem e aceite
          substituir os arquivos. Mantenha a pasta no mesmo lugar.
        </li>
        <li>
          Na página de extensões do Chrome, clique no botão de recarregar (a setinha em círculo) no cartão do Ditto.
        </li>
      </ol>
      <p className={`mt-3 ${classeTexto}`}>Não precisa remover a extensão nem ligar o executor de novo.</p>
    </section>
  )
}

const PROBLEMAS = [
  {
    pergunta: 'Esta página continua dizendo que a extensão não está instalada.',
    resposta:
      'Recarregue esta página. Se não mudar, abra a página de extensões e confira se a chave no cartão do Ditto está ligada.',
  },
  {
    pergunta: 'O Chrome diz que a extensão já foi carregada.',
    resposta:
      'Existe outra cópia do Ditto instalada, de outra pasta. Clique em Remover no cartão antigo e carregue a pasta nova.',
  },
  {
    pergunta: 'Apareceu um botão "Erros" no cartão do Ditto.',
    resposta:
      'Costuma ser a extensão tentando falar com o Ditto enquanto ele estava fora do ar. Se as tarefas rodam, clique em Limpar tudo e siga. Se não rodam, ligue o executor de novo logo acima.',
  },
  {
    pergunta: 'Quero remover a extensão.',
    resposta:
      'Na página de extensões, clique em Remover no cartão do Ditto e depois apague a pasta. Remover desliga o executor deste Chrome.',
  },
]

export function ProblemasExtensao() {
  return (
    <section aria-labelledby="problemas-titulo">
      <h2 id="problemas-titulo" className={classeTitulo}>
        Se algo não funcionar
      </h2>
      <dl className="mt-3 space-y-4">
        {PROBLEMAS.map(({ pergunta, resposta }) => (
          <div key={pergunta}>
            <dt className="text-[15px] font-bold text-navy">{pergunta}</dt>
            <dd className={`mt-1 ${classeTexto}`}>{resposta}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
