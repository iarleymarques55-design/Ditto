import { Outlet } from 'react-router'
import Navbar from '../components/landing/Navbar.jsx'
import Hero from '../components/landing/Hero.jsx'
import HowItWorks from '../components/landing/HowItWorks.jsx'
import RealCase from '../components/landing/RealCase.jsx'
import Footer from '../components/landing/Footer.jsx'

function Home() {
  return (
    <>
      <Navbar />
      <main className="fundo-mesa">
        <Hero />
        <HowItWorks />
        <RealCase />
      </main>
      <Footer />
      {/* Modais de entrar e criar conta */}
      <Outlet />
    </>
  )
}

export default Home
