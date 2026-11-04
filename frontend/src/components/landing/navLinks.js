export const GITHUB_URL = 'https://github.com/iarleymarques55-design'
export const LINKEDIN_URL = 'https://www.linkedin.com/in/iarley-marques23'
// Vazio: o ícone do YouTube não aparece no rodapé.
export const YOUTUBE_URL = ''
export const EMAIL_CONTATO = 'iarleymarques672@gmail.com'
// Vazio: o aviso de concordância não aparece no cadastro.
export const POLITICA_PRIVACIDADE_URL = ''

export const INICIO = { label: 'Início', href: '#demo' }
// Só na navbar: leva ao rodapé, então não entra na lista de links dele.
export const INFORMACOES = { label: 'Informações', href: '#informacoes' }

export const navLinks = [
  { label: 'Como funciona', href: '#como-funciona' },
  { label: 'Exemplo', href: '#exemplo' },
]

// Atributos de um link que abre fora da landing.
export function propsDoLink(link) {
  return link.externo ? { target: '_blank', rel: 'noreferrer' } : {}
}
