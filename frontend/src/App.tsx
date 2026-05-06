import { useEffect } from 'react'
import { logInfo } from './logger'
import { FilingsPage } from './components/FilingsPage'
import './App.css'

function App() {
  useEffect(() => {
    logInfo('React App mounted successfully.')
  }, [])

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>BSE Filings</h1>
        <p className="app-subtitle">Corporate announcements from Bombay Stock Exchange</p>
      </header>
      <main className="app-main">
        <FilingsPage />
      </main>
    </div>
  )
}

export default App
