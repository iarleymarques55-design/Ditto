const COR_DA_LINHA = {
  ok: 'text-ok-texto',
  falha: 'text-rec-texto',
  busca: 'text-ink',
  info: 'text-grafite',
}

const LINHAS_VISIVEIS = 7

// Recibo impresso pela máquina
function LogExecucao({ linhas }) {
  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Registro da execução"
      className="min-h-[150px] border-t border-dashed border-tinta-media pt-3 font-mono text-[12.5px] leading-[20px]"
    >
      {linhas.slice(-LINHAS_VISIVEIS).map((linha) => (
        <p key={linha.id} className={`break-words whitespace-pre-wrap ${COR_DA_LINHA[linha.tipo] ?? 'text-grafite'}`}>
          {linha.texto}
        </p>
      ))}
    </div>
  )
}

export default LogExecucao
