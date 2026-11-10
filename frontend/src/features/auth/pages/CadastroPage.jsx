import FormCadastro from '../components/FormCadastro.jsx'
import ModalAuth from '../components/ModalAuth.jsx'

function CadastroPage() {
  return (
    <ModalAuth
      titulo="Criar sua conta"
      subtitulo="Grave uma tarefa uma vez e deixe o Ditto repetir."
      pergunta="Já tem conta?"
      trocarPara="/entrar"
      trocarTexto="Entrar"
    >
      <FormCadastro />
    </ModalAuth>
  )
}

export default CadastroPage
