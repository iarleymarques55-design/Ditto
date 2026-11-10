import { useContext } from 'react'
import { AuthContext } from '../context/AuthProvider.jsx'

export function useAuth() {
  return useContext(AuthContext)
}
