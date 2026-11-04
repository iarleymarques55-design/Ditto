// Converte entre o horário em palavras, mostrado na tela, e o formato cron, guardado na API.

const DIAS_DA_SEMANA = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']

export const OPCOES_DIA_DA_SEMANA = DIAS_DA_SEMANA.map((rotulo, valor) => ({ rotulo, valor }))

const doisDigitos = (valor) => String(valor).padStart(2, '0')

export function descreverCron(cron) {
  const [minuto, hora, diaDoMes, mes, diaDaSemana] = cron.split(' ')
  const horario = `${doisDigitos(hora)}:${doisDigitos(minuto)}`

  if (mes !== '*') return cron
  if (diaDoMes !== '*') return `Todo dia ${diaDoMes}, às ${horario}`
  if (diaDaSemana !== '*') {
    const nome = DIAS_DA_SEMANA[Number(diaDaSemana)]
    if (!nome) return cron
    return `${['sábado', 'domingo'].includes(nome) ? 'Todo' : 'Toda'} ${nome}, às ${horario}`
  }
  return `Todo dia, às ${horario}`
}

// horario no formato "07:10", como vem do <input type="time">
export function montarCron({ frequencia, horario, diaDoMes, diaDaSemana }) {
  const [hora, minuto] = horario.split(':').map(Number)
  if (frequencia === 'mensal') return `${minuto} ${hora} ${diaDoMes} * *`
  if (frequencia === 'semanal') return `${minuto} ${hora} * * ${diaDaSemana}`
  return `${minuto} ${hora} * * *`
}
