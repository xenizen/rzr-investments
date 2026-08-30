import { useState } from 'react'

const DIRECTIONS = ['Purchase', 'Sold']
const SHARE_SIZES = [5000, 10000, 15000, 20000]
const MONTHS = [1, 2, 3, 4, 5, 6]
const PCT_BELOW_HIGH = [50, 60, 70, 80, 90, 100]

const DEFAULT_PARAMS = { direction: 'Purchase', shares: 10000, months: 1, pct_below_high: 70 }

const DISCLAIMER =
  'Not investment advice. Signals are derived from public SEC Form 4 filings and market data, for informational use only.'
const SCREENING_MESSAGE = 'Screening…'
const NO_MATCHES_MESSAGE = 'No matches for these parameters. Try a wider window or a smaller trade size.'
const REQUEST_FAILED_MESSAGE = 'Something went wrong running the screen. Please try again.'

function buildQuery({ direction, shares, months, pct_below_high }) {
  return new URLSearchParams({
    direction,
    shares: String(shares),
    months: String(months),
    pct_below_high: String(pct_below_high),
  }).toString()
}

function formatShares(value) {
  return Math.round(value).toLocaleString()
}

function formatPrice(value) {
  return value == null ? '—' : `$${value.toFixed(2)}`
}

function ScreenerRow({ row, expanded, onToggle }) {
  return (
    <>
      <tr data-testid="screener-result-row">
        <td>
          <button type="button" className="screener-ticker-btn" onClick={onToggle} aria-expanded={expanded}>
            <span className="screener-ticker">{row.ticker}</span>
            {row.multiple_insiders && (
              <span className="screener-badge" title="More than one distinct insider">
                multi-insider
              </span>
            )}
          </button>
          <span className="screener-company">{row.company}</span>
        </td>
        <td>{row.side}</td>
        <td>{row.insider_count}</td>
        <td>{formatShares(row.total_insider_shares)}</td>
        <td>{formatPrice(row.current_price)}</td>
        <td>{formatPrice(row.fifty_two_week_high)}</td>
        <td>{row.discount_pct}%</td>
        <td>{formatShares(row.suggested_quantity)}</td>
      </tr>
      {expanded && (
        <tr className="screener-filings-row" data-testid="screener-filings">
          <td colSpan={8}>
            <ul className="screener-filings">
              {row.filings.map((filing) => (
                <li key={filing.accession_no}>
                  <span>{filing.transaction_date}</span>
                  <span>{filing.insider_name}</span>
                  <span>{formatShares(filing.shares)} sh</span>
                  <span>{formatPrice(filing.price)}</span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  )
}

function InsiderScreener() {
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [expanded, setExpanded] = useState(null)

  function updateParam(key, value) {
    setParams((prev) => ({ ...prev, [key]: value }))
  }

  async function handleRunScreen() {
    setLoading(true)
    setError('')
    setResult(null)
    setExpanded(null)
    try {
      const response = await fetch(
        `${import.meta.env.BASE_URL}api/insider-screener?${buildQuery(params)}`,
      )
      const data = await response.json()
      if (data.error) {
        setError(data.error)
        return
      }
      setResult(data)
    } catch {
      setError(REQUEST_FAILED_MESSAGE)
    } finally {
      setLoading(false)
    }
  }

  const rows = result?.results ?? []

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

      <div id="screenerResults" className="screener-results">
        {loading && <p className="screener-status">{SCREENING_MESSAGE}</p>}

        {!loading && error && (
          <p id="lblScreenerError" className="screener-status screener-error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && result && rows.length === 0 && (
          <p id="lblScreenerEmpty" className="screener-status screener-empty">
            {NO_MATCHES_MESSAGE}
          </p>
        )}

        {!loading && !error && rows.length > 0 && (
          <>
            <p className="screener-count">
              {result.total_count} {result.total_count === 1 ? 'match' : 'matches'}
            </p>
            <div className="insider-table-wrap">
              <table id="screenerResultsTable" className="insider-table">
                <thead>
                  <tr>
                    <th scope="col">Stock</th>
                    <th scope="col">Side</th>
                    <th scope="col">Insiders</th>
                    <th scope="col">Insider shares</th>
                    <th scope="col">Price</th>
                    <th scope="col">52-wk high</th>
                    <th scope="col">% below</th>
                    <th scope="col">Suggested qty</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <ScreenerRow
                      key={row.ticker}
                      row={row}
                      expanded={expanded === row.ticker}
                      onToggle={() => setExpanded((current) => (current === row.ticker ? null : row.ticker))}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      <p id="lblScreenerDisclaimer" className="screener-disclaimer" role="note">
        {DISCLAIMER}
      </p>
    </div>
  )
}

export default InsiderScreener
