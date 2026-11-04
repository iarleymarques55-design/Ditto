import { useState } from 'react'
import { Link } from 'react-router'
import { POLITICA_PRIVACIDADE_URL } from '../../../components/landing/navLinks.js'
import { criarConta, entrarComGoogle } from '../api.js'
import { useEnvioAuth } from '../hooks/useEnvioAuth.js'
import { BotaoEnviar, Campo, CampoSenha, MensagemErro } from './CamposAuth.jsx'
import EntrarComGoogle from './EntrarComGoogle.jsx'

function FormCadastro() {
  const { erro, ocupado, enviar, mostrarErro } = useEnvioAuth()
  const [form, setForm] = useState({ nome: '', email: '', senha: '', confirmacao: '' })

  const alterar = (chave) => (evento) => setForm({ ...form, [chave]: evento.target.value })

  return (
    <>
      <EntrarComGoogle
        cadastro
        aoReceberCredencial={(credencial) => enviar(() => entrarComGoogle(credencial))}
        aoFalhar={mostrarErro}
      />

      <form
        className="flex flex-col gap-4"
        onSubmit={(evento) => {
          evento.preventDefault()
          if (form.senha !== form.confirmacao) {
            mostrarErro('As senhas não são iguais. Digite a mesma senha nos dois campos.')
            return
          }
          enviar(() => criarConta({ nome: form.nome, email: form.email, senha: form.senha }))
        }}
      >
        <Campo
          rotulo="Nome completo"
          placeholder="Como você quer ser chamado"
          autoComplete="name"
          value={form.nome}
          onChange={alterar('nome')}
          data-foco-inicial
        />
        <Campo
          rotulo="E-mail"
          type="email"
          placeholder="seu.email@empresa.com.br"
          autoComplete="email"
          value={form.email}
          onChange={alterar('email')}
        />
        <CampoSenha
          rotulo="Senha (mínimo 8 caracteres)"
          placeholder="Crie uma senha"
          autoComplete="new-password"
          minLength={8}
          value={form.senha}
          onChange={alterar('senha')}
        />
        <CampoSenha
          rotulo="Confirmar senha"
          placeholder="Repita a senha"
          autoComplete="new-password"
          minLength={8}
          value={form.confirmacao}
          onChange={alterar('confirmacao')}
        />
        <MensagemErro>{erro}</MensagemErro>
        <BotaoEnviar ocupado={ocupado}>Criar conta</BotaoEnviar>

        {/* Sem a página da política, o aviso não aparece: não se concorda com um texto que não existe */}
        {POLITICA_PRIVACIDADE_URL && (
          <p className="text-center text-[13px] leading-normal text-body">
            Ao criar a conta, você concorda com a{' '}
            <Link to={POLITICA_PRIVACIDADE_URL} className="font-medium text-ink underline-offset-2 hover:underline">
              Política de privacidade
            </Link>
            .
          </p>
        )}
      </form>
    </>
  )
}

export default FormCadastro
