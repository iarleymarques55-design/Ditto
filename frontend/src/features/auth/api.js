import { pedir } from '../../lib/http.js'

export function entrar({ email, senha }) {
  return pedir('/auth/login', { metodo: 'POST', corpo: { email, password: senha } })
}

export function criarConta({ nome, email, senha }) {
  return pedir('/auth/register', { metodo: 'POST', corpo: { name: nome, email, password: senha } })
}

// O cadastro não entrega acesso: ele devolve o e-mail para onde o código foi enviado
export function confirmarEmail({ email, codigo }) {
  return pedir('/auth/verify-email', { metodo: 'POST', corpo: { email, code: codigo } })
}

export function reenviarCodigo(email) {
  return pedir('/auth/resend-code', { metodo: 'POST', corpo: { email } })
}

export function entrarComGoogle(credencial) {
  return pedir('/auth/google', { metodo: 'POST', corpo: { credential: credencial } })
}

export function buscarContaLogada() {
  return pedir('/auth/me')
}
