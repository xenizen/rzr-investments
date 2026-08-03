import { useRef, useState } from 'react'

const REQUEST_FAILED_MESSAGE = 'No Price Found: Real Stock?'

function Stocks() {
  const symbolRef = useRef(null)
  const [priceLabel, setPriceLabel] = useState('')

  async function handleGetPrice() {
    const symbol = symbolRef.current.value.trimStart()
    try {
      const response = await fetch(`${import.meta.env.BASE_URL}api/stock-price?symbol=${encodeURIComponent(symbol)}`)
      const data = await response.json()
      setPriceLabel(data.error ?? String(data.price))
    } catch {
      setPriceLabel(REQUEST_FAILED_MESSAGE)
    }
  }

  return (
    <div id="stocks" className="stock-card">
      <span className="stock-card-tag">Live Quote</span>
      <h1>RZR Investments</h1>
      <p className="stock-card-sub">Look up the latest price for any stock symbol.</p>
      <div className="stock-form">
        <input
          type="text"
          id="txtStockSymbol"
          name="txtStockSymbol"
          placeholder="e.g. AAPL"
          ref={symbolRef}
          className="stock-input"
        />
        <button type="button" id="btnGetPrice" name="btnGetPrice" onClick={handleGetPrice} className="stock-btn">
          Get Price
        </button>
      </div>
      <label id="lblFoundPrice" name="lblFoundPrice" className="stock-result">
        {priceLabel}
      </label>
    </div>
  )
}

export default Stocks
