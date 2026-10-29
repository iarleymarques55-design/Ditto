// Ícone de "gravar": círculo branco com um ponto vermelho no centro.
function RecordIcon({ className = 'size-4' }) {
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center rounded-full bg-white ${className}`}>
      <span className="size-[40%] rounded-full bg-rec" />
    </span>
  )
}

export default RecordIcon
