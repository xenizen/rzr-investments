import { useState } from 'react'
import Stocks from './pages/Stocks'
import InsiderData from './pages/InsiderData'
import InsiderScreener from './pages/InsiderScreener'

const PAGES = {
  stocks: { label: 'Stock Price', Component: Stocks },
  insider: { label: 'Insider Data', Component: InsiderData },
  screener: { label: 'Screener', Component: InsiderScreener },
}

function App() {
  const [page, setPage] = useState('stocks')
  const { Component } = PAGES[page]

  return (
    <div id="rzr-invest" className="app-shell">
      <div className="app-content">
        <nav className="app-nav">
          {Object.entries(PAGES).map(([key, { label }]) => (
            <button
              key={key}
              type="button"
              className={`app-nav-btn${key === page ? ' app-nav-btn-active' : ''}`}
              onClick={() => setPage(key)}
            >
              {label}
            </button>
          ))}
        </nav>
        <Component />
      </div>
    </div>
  )
}

export default App
