function mesmoDia(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function ehHoje(data) {
  return mesmoDia(new Date(data), new Date())
}

function formatarHora(data) {
  return new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(data)
}

// "quarta-feira, 4 de novembro"
export function formatarDiaPorExtenso(valor = new Date()) {
  return new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(valor))
}

// "04/11"
export function formatarDiaCurto(valor) {
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit' }).format(new Date(valor))
}

function diaVizinho(deslocamento) {
  const data = new Date()
  data.setDate(data.getDate() + deslocamento)
  return data
}

// "hoje, 07:10", "ontem, 07:10", "amanhã, 07:10" ou "05/10, 07:10"
export function formatarQuando(valor) {
  const data = new Date(valor)

  if (ehHoje(data)) return `hoje, ${formatarHora(data)}`
  if (mesmoDia(data, diaVizinho(-1))) return `ontem, ${formatarHora(data)}`
  if (mesmoDia(data, diaVizinho(1))) return `amanhã, ${formatarHora(data)}`
  return `${formatarDiaCurto(data)}, ${formatarHora(data)}`
}

// "38 s", "4 min 38 s", "35 min" ou "3 h". Quanto maior o tempo, menos precisão é útil.
export function formatarDuracao(segundos) {
  const total = Math.max(0, Math.round(segundos))
  if (total < 60) return `${total} s`

  const horas = Math.floor(total / 3600)
  const minutos = Math.floor((total % 3600) / 60)
  const resto = total % 60
  if (horas > 0) return minutos ? `${horas} h ${minutos} min` : `${horas} h`
  if (minutos >= 10 || resto === 0) return `${minutos} min`
  return `${minutos} min ${resto} s`
}
