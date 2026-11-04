import { useEffect, useState } from 'react'
import { buscarFoto } from '../api.js'

function iniciais(nome = '') {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : ''
  return `${partes[0][0]}${ultima}`.toUpperCase()
}

// A foto exige login, então vem pelo fetch. Sem foto, ou se ela falhar, ficam as iniciais do nome.
function Avatar({ usuario, className = '', classeIniciais = 'text-[12px]' }) {
  const [foto, setFoto] = useState(null)
  const idDaFoto = usuario.avatar_id

  useEffect(() => {
    if (!idDaFoto) return undefined

    let ativo = true
    let criada
    buscarFoto()
      .then((arquivo) => {
        if (!ativo) return
        criada = URL.createObjectURL(arquivo)
        setFoto({ id: idDaFoto, url: criada })
      })
      .catch(() => {
        if (ativo) setFoto(null)
      })

    return () => {
      ativo = false
      if (criada) URL.revokeObjectURL(criada)
    }
  }, [idDaFoto])

  // A foto antiga nunca aparece depois de trocada ou removida
  if (foto && foto.id === idDaFoto) {
    return <img src={foto.url} alt="" className={`block object-cover ${className}`} />
  }

  return (
    <span aria-hidden="true" className={`flex items-center justify-center bg-post-it font-display font-bold text-ink ${classeIniciais} ${className}`}>
      {iniciais(usuario.name)}
    </span>
  )
}

export default Avatar
