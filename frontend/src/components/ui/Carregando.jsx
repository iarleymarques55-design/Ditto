function Carregando({ texto = 'Carregando...' }) {
  return (
    <p role="status" className="py-10 font-hand text-[26px] font-bold text-ink">
      {texto}
    </p>
  )
}

export default Carregando
