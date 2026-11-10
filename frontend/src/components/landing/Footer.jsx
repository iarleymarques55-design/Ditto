import { ChevronRight, Mail } from 'lucide-react'
import marca from '../../assets/ditto-marca.png'
import { IconeGithub, IconeLinkedin, IconeYoutube } from './IconesSociais.jsx'
import Logo from './Logo.jsx'
import { EMAIL_CONTATO, GITHUB_URL, LINKEDIN_URL, YOUTUBE_URL, navLinks, propsDoLink } from './navLinks.js'

const linksRodape = [
  ...navLinks,
  { label: 'GitHub', href: GITHUB_URL, externo: true },
  { label: 'LinkedIn', href: LINKEDIN_URL, externo: true },
]

const ANO_ATUAL = new Date().getFullYear()

// Rede sem endereço não aparece.
const redesSociais = [
  { label: 'GitHub de Iarley Marques', href: GITHUB_URL, externo: true, Icone: IconeGithub },
  { label: 'LinkedIn de Iarley Marques', href: LINKEDIN_URL, externo: true, Icone: IconeLinkedin },
  { label: 'Canal no YouTube', href: YOUTUBE_URL, externo: true, Icone: IconeYoutube },
].filter((rede) => rede.href)

function TituloColuna({ children }) {
  return (
    <>
      <h2 className="text-[18px] leading-tight font-bold text-navy">{children}</h2>
      <span aria-hidden="true" className="mt-2 block h-[3px] w-11 rounded-full bg-ink" />
    </>
  )
}

// Alvos de 44px no toque; com mouse as linhas ficam mais baixas e o rodapé mais compacto.
function Footer() {
  return (
    <footer id="informacoes" className="relative overflow-hidden border-t border-line bg-card-soft">
      <img
        src={marca}
        alt=""
        aria-hidden="true"
        width={126}
        height={120}
        className="pointer-events-none absolute -right-16 -bottom-8 hidden h-[200px] w-auto opacity-[0.06] md:block"
      />

      <div className="shell relative">
        <div className="grid gap-8 pt-8 pb-7 md:grid-cols-2 lg:grid-cols-[1.1fr_1.18fr_1fr] lg:gap-0 lg:pt-10">
          <div className="md:col-span-2 lg:col-span-1 lg:border-r lg:border-line lg:pr-4">
            <Logo tamanho="grande" />
            <p className="mt-2.5 max-w-[340px] text-[15px] leading-normal text-body">
              Grave uma tarefa do navegador uma vez. O&nbsp;Ditto repete, e se adapta quando o site muda.
            </p>
            <ul className="mt-3.5 flex gap-2.5">
              {redesSociais.map(({ Icone, ...rede }) => (
                <li key={rede.label}>
                  <a
                    href={rede.href}
                    {...propsDoLink(rede)}
                    aria-label={rede.label}
                    className="flex size-11 items-center justify-center rounded-full bg-tinta-clara text-navy hover:bg-tinta-media motion-safe:transition-colors pointer-fine:size-10"
                  >
                    <Icone className="size-5" />
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="lg:pl-14">
            <TituloColuna>Links rápidos</TituloColuna>
            <nav aria-label="Rodapé" className="mt-2">
              <ul>
                {linksRodape.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      {...propsDoLink(link)}
                      className="group inline-flex min-h-11 items-center gap-2.5 text-[15px] text-navy hover:text-ink motion-safe:transition-colors pointer-fine:min-h-[30px]"
                    >
                      {link.label}
                      <ChevronRight
                        aria-hidden="true"
                        className="size-3.5 text-navy group-hover:translate-x-0.5 motion-safe:transition-transform"
                      />
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </div>

          <div>
            <TituloColuna>Contato</TituloColuna>
            <a
              href={`mailto:${EMAIL_CONTATO}`}
              className="group mt-2 flex min-h-11 items-center gap-2.5 text-[15px] text-navy pointer-fine:min-h-[30px]"
            >
              {/* O rect do lucide cobre a aba se for preenchido: o envelope cheio vem do fundo recortado */}
              <Mail
                aria-hidden="true"
                className="size-5 shrink-0 bg-ink text-card-soft [clip-path:inset(12.5%_4.2%_round_3px)] [&_rect]:stroke-transparent"
              />
              <span className="min-w-0 break-all group-hover:underline">{EMAIL_CONTATO}</span>
            </a>
          </div>
        </div>

        <div className="flex flex-col gap-1 border-t border-line py-3 text-[13px] leading-5 text-body md:flex-row md:items-center md:justify-between">
          <p>
            © {ANO_ATUAL} <span className="font-medium text-ink">Ditto</span>. Todos os direitos reservados.
          </p>
          <p className="italic">
            Projeto de código aberto, feito por{' '}
            <a
              href={LINKEDIN_URL}
              {...propsDoLink({ externo: true })}
              className="-my-3 inline-flex min-h-11 items-center text-navy hover:text-ink motion-safe:transition-colors"
            >
              Iarley Marques
            </a>
          </p>
        </div>
      </div>
    </footer>
  )
}

export default Footer
