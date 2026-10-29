import Navbar from '../components/landing/Navbar.jsx'
import Hero from '../components/landing/Hero.jsx'
import HowItWorks from '../components/landing/HowItWorks.jsx'
import RealCase from '../components/landing/RealCase.jsx'
import Security from '../components/landing/Security.jsx'
import Footer from '../components/landing/Footer.jsx'

function Home() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <HowItWorks />
        <RealCase />
        <Security />
      </main>
      <Footer />
    </>
  )
}

export default Home
