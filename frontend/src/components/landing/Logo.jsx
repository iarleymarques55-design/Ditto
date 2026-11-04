import { Link } from 'react-router'
import marca from '../../assets/ditto-marca.png'
import nome from '../../assets/ditto-nome.png'

// Marca "D" + nome "ditto", recortados de img/Logo ditto com ícone de conversa.png
const TAMANHOS = {
  normal: { link: 'gap-2', marca: 'h-[34px]', nome: 'mt-1 h-[22px]' },
  grande: { link: 'gap-2.5', marca: 'h-10', nome: 'mt-1 h-[26px]' },
  navbar: { link: 'gap-2 lg:gap-2.5', marca: 'h-8 lg:h-10', nome: 'mt-1 h-[21px] lg:h-[26px]' },
}

function Logo({ tamanho = 'normal' }) {
  const classes = TAMANHOS[tamanho]

  return (
    <Link to="/" className={`inline-flex min-h-11 items-center ${classes.link}`}>
      <img src={marca} alt="" width={126} height={120} className={`${classes.marca} w-auto`} />
      <img src={nome} alt="Ditto" width={240} height={84} className={`${classes.nome} w-auto`} />
    </Link>
  )
}

export default Logo
