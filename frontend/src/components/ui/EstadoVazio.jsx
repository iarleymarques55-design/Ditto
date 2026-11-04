// Recado escrito à mão na folha: diz o que aconteceu e, com `acao`, o que fazer agora.
// `comoTitulo` faz do recado o título da página, quando ele é tudo o que há nela.
function EstadoVazio({ titulo, comoTitulo = false, children, acao }) {
  const Titulo = comoTitulo ? 'h1' : 'p'

  return (
    <div className="py-8">
      <Titulo className="font-hand text-[28px] leading-tight font-bold text-ink">{titulo}</Titulo>
      {children && <p className="mt-2 max-w-[56ch] text-[15px] leading-relaxed">{children}</p>}
      {acao && <div className="mt-4">{acao}</div>}
    </div>
  )
}

export default EstadoVazio
