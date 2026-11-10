import { useEffect, useState } from 'react'
import { buscarImagem } from '../api.js'

// A imagem exige login, então vem pelo fetch em vez de um <img src> direto.
function ScreenshotPasso({ telaId, descricao }) {
  const [url, setUrl] = useState(null)

  useEffect(() => {
    let ativo = true
    let criada

    buscarImagem(telaId)
      .then((arquivo) => {
        if (!ativo) return
        criada = URL.createObjectURL(arquivo)
        setUrl(criada)
      })
      .catch(() => {
        // Sem a imagem, os passos ainda contam o que aconteceu
        if (ativo) setUrl(null)
      })

    return () => {
      ativo = false
      if (criada) URL.revokeObjectURL(criada)
    }
  }, [telaId])

  if (!url) return null

  return (
    <figure className="max-w-[520px]">
      <img src={url} alt={descricao} className="block w-full rounded-[2px] border border-line shadow-papel" />
      <figcaption className="mt-2 text-[13px]">Como a tela estava quando o problema aconteceu.</figcaption>
    </figure>
  )
}

export default ScreenshotPasso
