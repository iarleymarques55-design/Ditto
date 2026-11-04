import { useCallback, useEffect, useRef, useState } from 'react'

const CARREGANDO = { dados: null, erro: null, carregando: true }

// Busca dados e, se `intervalo(dados)` devolver milissegundos, consulta de novo depois desse tempo.
export function useConsulta(buscar, dependencias = [], { intervalo } = {}) {
  const chave = JSON.stringify(dependencias)
  const [resultado, setResultado] = useState({ chave, ...CARREGANDO })
  const [versao, setVersao] = useState(0)
  const refBuscar = useRef(buscar)
  const refIntervalo = useRef(intervalo)

  useEffect(() => {
    refBuscar.current = buscar
    refIntervalo.current = intervalo
  })

  useEffect(() => {
    let ativo = true
    let temporizador

    async function consultar() {
      try {
        const dados = await refBuscar.current()
        if (!ativo) return
        setResultado({ chave, dados, erro: null, carregando: false })
        const espera = refIntervalo.current?.(dados)
        if (espera) temporizador = setTimeout(consultar, espera)
      } catch (erro) {
        if (!ativo) return
        // Uma falha passageira não apaga o que já está na tela: tenta de novo na próxima volta
        setResultado((atual) => {
          if (atual.chave === chave && atual.dados) return atual
          return { chave, dados: null, erro, carregando: false }
        })
        const espera = refIntervalo.current?.(null)
        if (espera) temporizador = setTimeout(consultar, espera)
      }
    }

    consultar()
    return () => {
      ativo = false
      clearTimeout(temporizador)
    }
  }, [chave, versao])

  const recarregar = useCallback(() => setVersao((atual) => atual + 1), [])

  // Resultado de outro recurso (id diferente) nunca aparece enquanto o novo carrega
  const { chave: chaveDoResultado, ...estado } = resultado
  return { ...(chaveDoResultado === chave ? estado : CARREGANDO), recarregar }
}
