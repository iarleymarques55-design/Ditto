import { Box, FileText, Lock, Shield } from 'lucide-react'

const garantias = [
  {
    Icone: Box,
    titulo: 'Não armazena suas senhas',
    descricao: 'O Ditto não salva senhas, nem acessa suas contas. Ele apenas executa o que você gravou.',
  },
  {
    Icone: Lock,
    titulo: 'Não compartilha seus dados',
    descricao: 'Suas gravações ficam no seu dispositivo. O Ditto não vende, não compartilha e não usa seus dados.',
  },
  {
    Icone: Shield,
    titulo: 'Não interage fora do navegador',
    descricao: 'Tudo acontece dentro do Chrome. Sem acessos a arquivos, sem programas externos, sem riscos desnecessários.',
  },
  {
    Icone: FileText,
    titulo: 'Não faz nada sem você',
    descricao:
      'Você decide o que gravar, quando executar e pode editar ou excluir qualquer automação a qualquer momento.',
  },
]

function Security() {
  return (
    <section id="seguranca" aria-labelledby="seguranca-titulo" className="pt-14 pb-20">
      <div className="shell">
        <h2 id="seguranca-titulo" className="font-display text-[28px] leading-[1.15] font-bold text-navy sm:text-[34px]">
          O que o Ditto nunca faz
        </h2>
        <p className="mt-3 max-w-[540px] text-[15.5px] leading-[1.7]">
          Seu ambiente é importante. Por isso, o Ditto foi feito para ser seguro, respeitoso e transparente.
        </p>

        <ul className="relative mt-10 grid gap-y-9 md:grid-cols-2 md:gap-x-14 md:before:absolute md:before:inset-y-0 md:before:left-1/2 md:before:w-px md:before:bg-line">
          {garantias.map(({ Icone, titulo, descricao }) => (
            <li key={titulo} className="flex items-start gap-6 sm:gap-8">
              <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-line text-navy">
                <Icone size={20} strokeWidth={1.6} />
              </span>
              <div className="pt-1">
                <h3 className="text-[15px] font-medium text-navy">{titulo}</h3>
                <p className="mt-1.5 max-w-[340px] text-[13px] leading-[1.7]">{descricao}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

export default Security
