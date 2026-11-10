import FormLogin from '../components/FormLogin.jsx'
import ModalAuth from '../components/ModalAuth.jsx'

function LoginPage() {
  return (
    <ModalAuth
      titulo="Entrar na sua conta"
      subtitulo="Suas tarefas gravadas estão te esperando."
      pergunta="Ainda não tem conta?"
      trocarPara="/criar-conta"
      trocarTexto="Criar conta"
    >
      <FormLogin />
    </ModalAuth>
  )
}

export default LoginPage
