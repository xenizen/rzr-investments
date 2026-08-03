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
    <div id="stocks">
      <input type="text" id="txtStockSymbol" name="txtStockSymbol" ref={symbolRef} />
      <button type="button" id="btnGetPrice" name="btnGetPrice" onClick={handleGetPrice}>
        Get Price
      </button>
      <label id="lblFoundPrice" name="lblFoundPrice">
        {priceLabel}
      </label>
    </div>
  )
}

export default Stocks
