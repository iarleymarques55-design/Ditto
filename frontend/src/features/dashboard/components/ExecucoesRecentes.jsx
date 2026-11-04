import { TabelaExecucoes } from '../../execucoes/index.js'

function ExecucoesRecentes({ execucoes }) {
  return <TabelaExecucoes execucoes={execucoes} legenda="Execuções mais recentes" />
}

export default ExecucoesRecentes
