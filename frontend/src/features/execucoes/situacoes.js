import { CircleAlert, CircleCheck, CircleSlash, CircleX, Clock, LoaderCircle, TriangleAlert } from 'lucide-react'

export const SITUACOES_EXECUCAO = {
  fila: { rotulo: 'Na fila', tom: 'neutro', Icone: Clock },
  rodando: { rotulo: 'Rodando', tom: 'tinta', Icone: LoaderCircle },
  espera: { rotulo: 'Espera você', tom: 'perigo', Icone: CircleAlert },
  concluida: { rotulo: 'Concluída', tom: 'ok', Icone: CircleCheck },
  parcial: { rotulo: 'Com falhas', tom: 'perigo', Icone: TriangleAlert },
  falhou: { rotulo: 'Falhou', tom: 'perigo', Icone: CircleX },
  cancelada: { rotulo: 'Cancelada', tom: 'neutro', Icone: CircleSlash },
}

export const SITUACOES_ITEM = {
  ok: 'Concluída',
  reparado: 'Concluída com reparo',
  rodando: 'Saindo agora',
  espera: 'Espera você',
  falhou: 'Falhou',
  pulado: 'Pulada',
  pendente: 'Na fila',
}

// Enquanto a execução pode mudar sozinha, a tela continua consultando
export const emAndamento = (situacao) => situacao === 'rodando' || situacao === 'fila' || situacao === 'espera'
