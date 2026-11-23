import Fita from '../landing/mesa/Fita.jsx'

// A política em uma página de caderno: o que o Ditto anota e o que ele nunca toca, riscado à caneta.
// A altura da linha (28px) é a da pauta, para o texto assentar nas linhas.

const ANOTA = [
  'Os sites e os cliques das suas gravações',
  'O texto que você digita em campos comuns',
  'Os dados da tela que você pede para guardar',
  'As planilhas que você envia para repetir uma tarefa',
  'Os acessos que você salva, sempre criptografados',
]

const NUNCA_TOCA = [
  'Senhas digitadas nos sites',
  'Números de cartão e códigos de verificação',
  'As abas que o Ditto não abriu',
  'O seu histórico de navegação',
  'Anúncios, rastreadores e venda de dados',
]

function Coluna({ id, titulo, itens, riscado }) {
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className="font-hand text-[27px] leading-[28px] font-bold text-ink">
        {titulo}
      </h2>
      <ul className="mt-[28px] text-[15.5px] leading-[28px] text-navy">
        {itens.map((item) => (
          <li key={item} className="flex gap-2.5">
            {/* O "×" da Caveat é bem menor que o "✓": o tamanho compensa para as duas marcas parecerem iguais */}
            <span
              aria-hidden="true"
              className={`w-4 shrink-0 text-center font-hand ${riscado ? 'text-[27px] text-rec' : 'text-[20px] text-ink'}`}
            >
              {riscado ? '×' : '✓'}
            </span>
            {/* Riscado de caneta: grosso, vermelho e sem pular as letras */}
            <span
              className={
                riscado
                  ? 'text-grafite line-through decoration-rec/85 decoration-[2.5px] [text-decoration-skip-ink:none]'
                  : undefined
              }
            >
              {item}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function RegistroDoDitto() {
  return (
    <div className="folha folha-pautada relative mt-10 px-5 pt-[28px] pb-[28px] pl-[44px] sm:pr-8">
      <Fita className="-top-2.5 left-10 -rotate-3" />
      <div className="grid gap-x-10 gap-y-[28px] md:grid-cols-2">
        <Coluna id="registro-anota" titulo="O Ditto anota" itens={ANOTA} />
        <Coluna id="registro-nunca" titulo="O Ditto nunca toca" itens={NUNCA_TOCA} riscado />
      </div>
    </div>
  )
}

export default RegistroDoDitto
