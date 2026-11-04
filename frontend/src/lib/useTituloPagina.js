import { useEffect } from 'react'

export function useTituloPagina(titulo) {
  useEffect(() => {
    if (titulo) document.title = `${titulo} | Ditto`
  }, [titulo])
}
