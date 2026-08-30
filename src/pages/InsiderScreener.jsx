import { useState } from 'react'

const DIRECTIONS = ['Purchase', 'Sold']
const SHARE_SIZES = [5000, 10000, 15000, 20000]
const MONTHS = [1, 2, 3, 4, 5, 6]
const PCT_BELOW_HIGH = [50, 60, 70, 80, 90, 100]

const DEFAULT_PARAMS = { direction: 'Purchase', shares: 10000, months: 1, pct_below_high: 70 }

const DISCLAIMER =
  'Not investment advice. Signals are derived from public SEC Form 4 filings and market data, for informational use only.'
const SCREENING_MESSAGE = 'Screening…'
const NO_MATCHES_MESSAGE = 'No matches for these parameters.'
const REQUEST_FAILED_MESSAGE = 'Something went wrong running the screen.'

function buildQuery({ direction, shares, months, pct_below_high }) {
  return new URLSearchParams({
    direction,
    shares: String(shares),
    months: String(months),
    pct_below_high: String(pct_below_high),
  }).toString()
}

function InsiderScreener() {
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  // The whole response body. SCRUM-38 renders it as a table with the
  // multi-insider badge; SCRUM-39 adds pagination controls.
  const [result, setResult] = useState(null)

  function updateParam(key, value) {
    setParams((prev) => ({ ...prev, [key]: value }))
  }

  async function handleRunScreen() {
    setLoading(true)
    setResult(null)
    setMessage('')
    try {
      const response = await fetch(
        `${import.meta.env.BASE_URL}api/insider-screener?${buildQuery(params)}`,
      )
      const data = await response.json()
      if (data.error) {
        setMessage(data.error)
        return
      }
      setResult(data)
      setMessage(data.total_count === 0 ? NO_MATCHES_MESSAGE : `${data.total_count} matches`)
    } catch {
      setMessage(REQUEST_FAILED_MESSAGE)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div id="insider-screener" className="stock-card">
      <span className="stock-card-tag">Insider Signals</span>
      <h1>Insider Screener</h1>
      <p className="stock-card-sub">
        Screen SEC Form 4 insider transactions and surface buy/sell ideas, filtered by insider activity and price
        relative to the 52-week high.
      </p>

      <div id="screenerForm" className="screener-form">
        <label className="screener-field">
          <span>Direction</span>
          <select
            id="selScreenerDirection"
            className="screener-select"
            value={params.direction}
            onChange={(event) => updateParam('direction', event.target.value)}
          >
            {DIRECTIONS.map((direction) => (
              <option key={direction} value={direction}>
                {direction}
              </option>
            ))}
          </select>
        </label>

        <label className="screener-field">
          <span>Insider trade size</span>
          <select
            id="selScreenerShares"
            className="screener-select"
            value={params.shares}
            onChange={(event) => updateParam('shares', Number(event.target.value))}
          >
            {SHARE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size.toLocaleString()}+ shares
              </option>
            ))}
          </select>
        </label>

        <label className="screener-field">
          <span>Months to review</span>
          <select
            id="selScreenerMonths"
            className="screener-select"
            value={params.months}
            onChange={(event) => updateParam('months', Number(event.target.value))}
          >
            {MONTHS.map((month) => (
              <option key={month} value={month}>
                {month === 1 ? '1 month' : `${month} months`}
              </option>
            ))}
          </select>
        </label>

        <label className="screener-field">
          <span>% below 52-week high</span>
          <select
            id="selScreenerPct"
            className="screener-select"
            value={params.pct_below_high}
            onChange={(event) => updateParam('pct_below_high', Number(event.target.value))}
          >
            {PCT_BELOW_HIGH.map((pct) => (
              <option key={pct} value={pct}>
                {pct}%
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          id="btnRunScreen"
          className="stock-btn"
          onClick={handleRunScreen}
          disabled={loading}
        >
          Run screen
        </button>

        <p className="screener-hint">
          Insider trade size is a signal threshold on the Form 4 transaction, not a trade quantity. “% below 52-week
          high” is how far under its high a stock must trade to qualify.
        </p>
      </div>

      <label id="lblScreenerMessage" className="stock-result">
        {loading ? SCREENING_MESSAGE : message}
      </label>

      {/* SCRUM-38: results table + multi-insider badge + empty/error states.
          SCRUM-39: pagination controls + loading/error refinement. */}
      <div id="screenerResults" className="screener-results">
        {result?.results.map((row) => (
          <div key={row.ticker} className="screener-row-stub" data-testid="screener-result-row">
            <strong>{row.ticker}</strong> · {row.side} · {row.discount_pct}% below high
            {row.multiple_insiders ? ' · multiple insiders' : ''}
          </div>
        ))}
      </div>

      <p id="lblScreenerDisclaimer" className="screener-disclaimer" role="note">
        {DISCLAIMER}
      </p>
    </div>
  )
}

export default InsiderScreener
