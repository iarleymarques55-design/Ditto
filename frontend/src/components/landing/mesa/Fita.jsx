// Pedaço de fita adesiva lavanda, com as pontas rasgadas. Posição e giro vêm do className.
function Fita({ className = '' }) {
  return (
    <span
      aria-hidden="true"
      className={`absolute z-10 h-[22px] w-[92px] bg-fita [clip-path:polygon(3%_0,97%_4%,100%_30%,96%_55%,100%_82%,97%_100%,2%_96%,0_70%,4%_45%,0_18%)] ${className}`}
    />
  )
}

export default Fita
