import { pedir, pedirArquivo } from '../../lib/http.js'

export function salvarConta({ nome, alertas }) {
  return pedir('/account', {
    metodo: 'PATCH',
    corpo: {
      ...(nome !== undefined ? { name: nome } : {}),
      ...(alertas !== undefined ? { email_alerts: alertas } : {}),
    },
  })
}

export function enviarFoto(arquivo) {
  const formulario = new FormData()
  formulario.append('file', arquivo)
  return pedir('/account/avatar', { metodo: 'PUT', formulario })
}

export function removerFoto() {
  return pedir('/account/avatar', { metodo: 'DELETE' })
}

export function buscarFoto() {
  return pedirArquivo('/account/avatar')
}

export function trocarSenha({ atual, nova }) {
  return pedir('/account/password', {
    metodo: 'POST',
    corpo: { current_password: atual || null, new_password: nova },
  })
}

export function excluirConta({ confirmacao, senha }) {
  return pedir('/account', {
    metodo: 'DELETE',
    corpo: { confirmation: confirmacao, password: senha || null },
  })
}

export function listarAcessos() {
  return pedir('/credentials')
}

export function apagarAcesso(id) {
  return pedir(`/credentials/${id}`, { metodo: 'DELETE' })
}
