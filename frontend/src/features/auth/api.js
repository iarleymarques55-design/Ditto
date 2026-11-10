import { pedir } from '../../lib/http.js'

export function entrar({ email, senha }) {
  return pedir('/auth/login', { metodo: 'POST', corpo: { email, password: senha } })
}

export function criarConta({ nome, email, senha }) {
  return pedir('/auth/register', { metodo: 'POST', corpo: { name: nome, email, password: senha } })
}

export function entrarComGoogle(credencial) {
  return pedir('/auth/google', { metodo: 'POST', corpo: { credential: credencial } })
}

export function buscarContaLogada() {
  return pedir('/auth/me')
}
