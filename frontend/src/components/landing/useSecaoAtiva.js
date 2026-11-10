import { useEffect, useState } from 'react'

// Ativa é a seção que cruza uma faixa fina no meio da tela. Fora de todas, vale a última.
// O rodapé (idRodape) é baixo demais para chegar a essa faixa: ele ganha quando metade dele está à vista.
// `ids` precisa ser estável: passe uma constante, não um array criado na renderização.
export function useSecaoAtiva(ids, idRodape) {
  const [secaoNoMeio, setSecaoNoMeio] = useState(ids[0])
  const [rodapeVisivel, setRodapeVisivel] = useState(false)

  useEffect(() => {
    const observadorSecoes = new IntersectionObserver(
      (entradas) => {
        const entrou = entradas.find((entrada) => entrada.isIntersecting)
        if (entrou) setSecaoNoMeio(entrou.target.id)
      },
      { rootMargin: '-45% 0px -50% 0px' },
    )
    const observadorRodape = new IntersectionObserver(
      ([entrada]) => setRodapeVisivel(entrada.isIntersecting),
      { threshold: 0.5 },
    )

    ids.forEach((id) => {
      const secao = document.getElementById(id)
      if (secao) observadorSecoes.observe(secao)
    })
    const rodape = document.getElementById(idRodape)
    if (rodape) observadorRodape.observe(rodape)

    return () => {
      observadorSecoes.disconnect()
      observadorRodape.disconnect()
    }
  }, [ids, idRodape])

  return rodapeVisivel ? idRodape : secaoNoMeio
}
