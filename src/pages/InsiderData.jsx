import { useRef, useState } from 'react'

const NO_CRITERIA_ENTERED_MESSAGE = 'No Search Criteria Entered'
const NO_RESULTS_MESSAGE = 'No matching insider filings found.'
const REQUEST_FAILED_MESSAGE = 'No Insider Data Found: Real Stock?'

function buildQuery({ symbol, name, dateFrom, dateTo }) {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (name) params.set('name', name)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return params.toString()
}

function InsiderData() {
  const symbolRef = useRef(null)
  const nameRef = useRef(null)
  const dateFromRef = useRef(null)
  const dateToRef = useRef(null)

  const [message, setMessage] = useState('')
  const [results, setResults] = useState([])

  async function handleSearch() {
    const symbol = symbolRef.current.value.trim()
    const name = nameRef.current.value.trim()
    const dateFrom = dateFromRef.current.value
    const dateTo = dateToRef.current.value

    if (!symbol && !name && !dateFrom && !dateTo) {
      setResults([])
      setMessage(NO_CRITERIA_ENTERED_MESSAGE)
      return
    }

    try {
      const query = buildQuery({ symbol, name, dateFrom, dateTo })
      const response = await fetch(`${import.meta.env.BASE_URL}api/insider-data?${query}`)
      const data = await response.json()

      if (data.error) {
        setResults([])
        setMessage(data.error)
        return
      }

      const found = data.results ?? []
      setResults(found)
      setMessage(found.length ? '' : NO_RESULTS_MESSAGE)
    } catch {
      setResults([])
      setMessage(REQUEST_FAILED_MESSAGE)
    }
  }

  return (
    <div id="insider-data" className="stock-card">
      <span className="stock-card-tag">Insider Activity</span>
      <h1>Insider Data</h1>
      <p className="stock-card-sub">
        Search SEC Form 4 insider trading filings by stock symbol, insider or company name, and filing date range.
      </p>
      <div className="insider-form">
        <input
          type="text"
          id="txtInsiderSymbol"
          name="txtInsiderSymbol"
          placeholder="Stock symbol, e.g. AAPL"
          ref={symbolRef}
          className="stock-input"
        />
        <input
          type="text"
          id="txtInsiderName"
          name="txtInsiderName"
          placeholder="Insider or company name"
          ref={nameRef}
          className="stock-input"
        />
        <div className="insider-date-row">
          <input
            type="date"
            id="txtInsiderDateFrom"
            name="txtInsiderDateFrom"
            aria-label="Filing date from"
            ref={dateFromRef}
            className="stock-input"
          />
          <input
            type="date"
            id="txtInsiderDateTo"
            name="txtInsiderDateTo"
            aria-label="Filing date to"
            ref={dateToRef}
            className="stock-input"
          />
        </div>
        <button
          type="button"
          id="btnSearchInsider"
          name="btnSearchInsider"
          onClick={handleSearch}
          className="stock-btn"
        >
          Search
        </button>
      </div>
      <label id="lblInsiderMessage" name="lblInsiderMessage" className="stock-result">
        {message}
      </label>
      {results.length > 0 && (
        <ul id="insiderResults" className="insider-results">
          {results.map((result, index) => (
            <li key={index} data-testid="insider-result-row" className="insider-result-item">
              <strong>{result.insider_name}</strong> · {(result.net_change ?? 0).toLocaleString()} shares ·{' '}
              {result.issuer} · {result.filing_date}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default InsiderData
