// Folha de caderno em que a IA anota cada passo, à mão, no ritmo em que faz.
// A altura da linha (28px) é a mesma da pauta, para a letra assentar nas linhas.
function FolhaPassos({ pedido, trabalhando }) {
  return (
    <article className="folha folha-pautada relative min-h-[420px] pt-[28px] pr-5 pb-[56px] pl-[44px]">
      <h2 className="font-display text-[15px] leading-[28px] font-bold text-navy">O pedido</h2>
      <p className="max-w-[62ch] text-[15px] leading-[28px] text-navy">“{pedido.texto}”</p>

      <h2 className="mt-[28px] font-display text-[15px] leading-[28px] font-bold text-navy">Passos anotados</h2>
      {pedido.passos.length === 0 ? (
        <p className="font-hand text-[23px] leading-[28px] text-grafite">{trabalhando ? 'Abrindo o site...' : 'Nenhum passo.'}</p>
      ) : (
        <ol className="list-decimal pl-6 font-hand text-[23px] leading-[28px] text-ink marker:font-sans marker:text-[13px] marker:text-grafite">
          {pedido.passos.map((passo, indice) => (
            <li
              // Os passos só crescem no fim: a posição identifica cada um
              // oxlint-disable-next-line react/no-array-index-key
              key={indice}
              className={indice === pedido.passos.length - 1 && trabalhando ? 'motion-safe:animate-surgir' : undefined}
            >
              {passo}
            </li>
          ))}
        </ol>
      )}
      {trabalhando && (
        <p aria-hidden="true" className="pl-6 font-hand text-[23px] leading-[28px] text-ink/50 motion-safe:animate-piscar motion-safe:[animation-iteration-count:infinite]">
          ...
        </p>
      )}
    </article>
  )
}

export default FolhaPassos
