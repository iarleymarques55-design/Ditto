// Folha de caderno em que a IA anota cada passo, à mão, no ritmo em que faz.
// A altura da linha (28px) é a mesma da pauta, para a letra assentar nas linhas.
// As dúvidas entram como bilhetes entre os passos, na ordem em que aconteceram.
function Pergunta({ linha }) {
  return (
    <li className="my-[28px] ml-7 border-l-2 border-ink/40 pl-3 text-[14px] leading-[28px]">
      <p className="text-grafite">A IA perguntou: {linha.texto}</p>
      <p className="font-medium text-ink">{linha.resposta === null ? 'Esperando sua resposta.' : `Você: ${linha.resposta}`}</p>
    </li>
  )
}

function FolhaPassos({ pedido, trabalhando }) {
  const ultima = pedido.linhas.length - 1

  return (
    <article className="folha folha-pautada relative min-h-[420px] pt-[28px] pr-5 pb-[56px] pl-[44px]">
      <h2 className="font-display text-[15px] leading-[28px] font-bold text-navy">O pedido</h2>
      <p className="max-w-[62ch] text-[15px] leading-[28px] text-navy">“{pedido.texto}”</p>

      <h2 className="mt-[28px] font-display text-[15px] leading-[28px] font-bold text-navy">Passos anotados</h2>
      {pedido.linhas.length === 0 ? (
        <p className="font-hand text-[23px] leading-[28px] text-grafite">{trabalhando ? 'Abrindo o site...' : 'Nenhum passo.'}</p>
      ) : (
        <ol className="list-none">
          {pedido.linhas.map((linha, indice) => {
            // As linhas só crescem no fim: a posição identifica cada uma
            if (linha.tipo === 'pergunta') {
              // oxlint-disable-next-line react/no-array-index-key
              return <Pergunta key={indice} linha={linha} />
            }
            return (
              <li
                // oxlint-disable-next-line react/no-array-index-key
                key={indice}
                className={`relative pl-7 font-hand text-[23px] leading-[28px] text-ink ${indice === ultima && trabalhando ? 'motion-safe:animate-surgir' : ''}`}
              >
                <span aria-hidden="true" className="absolute left-0 w-5 text-right font-sans text-[13px] text-grafite">
                  {linha.numero}.
                </span>
                <span className="sr-only">Passo {linha.numero}: </span>
                {linha.texto}
              </li>
            )
          })}
        </ol>
      )}
      {trabalhando && (
        <p aria-hidden="true" className="pl-7 font-hand text-[23px] leading-[28px] text-ink/50 motion-safe:animate-piscar motion-safe:[animation-iteration-count:infinite]">
          ...
        </p>
      )}
    </article>
  )
}

export default FolhaPassos
