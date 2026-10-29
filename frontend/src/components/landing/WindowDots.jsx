// Os três pontinhos de janela (vermelho, amarelo, verde).
function WindowDots() {
  return (
    <div aria-hidden="true" className="flex gap-1.5">
      <span className="size-[7px] rounded-full bg-rec" />
      <span className="size-[7px] rounded-full bg-sinal" />
      <span className="size-[7px] rounded-full bg-ok" />
    </div>
  )
}

export default WindowDots
