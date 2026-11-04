import Badge from '../../../components/ui/Badge.jsx'
import { SITUACOES_EXECUCAO } from '../situacoes.js'

function StatusExecucao({ situacao, carimbo = false }) {
  const { rotulo, tom, Icone } = SITUACOES_EXECUCAO[situacao]
  // A chave faz o carimbo bater de novo quando a situação muda
  return (
    <Badge key={situacao} tom={tom} Icone={Icone} carimbo={carimbo}>
      {rotulo}
    </Badge>
  )
}

export default StatusExecucao
