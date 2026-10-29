import { BrowserRouter, Route, Routes } from 'react-router'
import Home from './pages/Home.jsx'
import Painel from './pages/Painel.jsx'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/painel" element={<Painel />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
