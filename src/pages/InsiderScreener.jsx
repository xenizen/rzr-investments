import { useState } from 'react'

const DIRECTIONS = ['Purchase', 'Sold']
const SHARE_SIZES = [5000, 10000, 15000, 20000]
const MONTHS = [1, 2, 3, 4, 5, 6]
const PCT_BELOW_HIGH = [50, 60, 70, 80, 90, 100]

const DEFAULT_PARAMS = { direction: 'Purchase', shares: 10000, months: 1, pct_below_high: 70 }

const DISCLAIMER =
  'Not investment advice. Signals are derived from public SEC Form 4 filings and market data, for informational use only.'
const FRESHNESS_NOTE =
  'Insider history comes from SEC’s quarterly bulk Form 4 data, topped up nightly from EDGAR — the most recent day or two of filings may not be included yet.'
const SCREENING_MESSAGE = 'Screening…'
const NO_MATCHES_MESSAGE = 'No matches for these parameters. Try a wider window or a smaller trade size.'
const REQUEST_FAILED_MESSAGE = 'Something went wrong running the screen. Please try again.'

function reviewWindowLabel(months) {
  return months === 1 ? 'the last month' : `the last ${months} months`
}

function formatThroughDate(iso) {
  const parsed = new Date(`${iso}T00:00:00`)
  return Number.isNaN(parsed.getTime())
    ? null
    : parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function buildQuery({ direction, shares, months, pct_below_high }, page) {
  const query = new URLSearchParams({
    direction,
    shares: String(shares),
    months: String(months),
    pct_below_high: String(pct_below_high),
  })
  if (page && page > 1) query.set('page', String(page))
  return query.toString()
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
  // The params the visible results were fetched with -- kept separate from
  // the dropdowns so paging uses what was actually screened, even if the
  // user has since changed a dropdown without clicking Run screen again.
  const [activeParams, setActiveParams] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [expanded, setExpanded] = useState(null)

  function updateParam(key, value) {
    setParams((prev) => ({ ...prev, [key]: value }))
  }

  async function runScreen(searchParams, targetPage) {
    setLoading(true)
    setError('')
    setExpanded(null)
    try {
      const response = await fetch(
        `${import.meta.env.BASE_URL}api/insider-screener?${buildQuery(searchParams, targetPage)}`,
      )
      const data = await response.json()
      if (data.error) {
        setError(data.error)
        setResult(null)
        return
      }
      setResult(data)
      setActiveParams(searchParams)
      setPage(data.page ?? targetPage)
    } catch {
      setError(REQUEST_FAILED_MESSAGE)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  function handleRunScreen() {
    // Any Run screen click starts a fresh screen at page 1.
    runScreen(params, 1)
  }

  function handlePrevPage() {
    if (loading || !activeParams || page <= 1) return
    runScreen(activeParams, page - 1)
  }

  function handleNextPage() {
    if (loading || !activeParams || !result?.has_next) return
    runScreen(activeParams, page + 1)
  }

  const rows = result?.results ?? []
  const showTable = Boolean(result && result.total_count > 0)
  const rangeStart = showTable ? (page - 1) * result.page_size + 1 : 0
  const rangeEnd = rangeStart ? rangeStart + rows.length - 1 : 0

  const dataThrough = result?.data_through ? formatThroughDate(result.data_through) : null
  const freshnessText = dataThrough
    ? `Insider data current through ${dataThrough}. New filings can take a day or two to appear.`
    : FRESHNESS_NOTE

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
          Insider trade size is a signal threshold on the Form 4 transaction, not a trade quantity. “Months to review”
          sets how far back Form 4 filings count toward the signal. “% below 52-week high” is how far under its high a
          stock must trade to qualify.
        </p>
      </div>

      <div id="screenerResults" className="screener-results">
        {activeParams && (
          <p id="lblScreenerWindow" className="screener-window">
            Reviewing insider filings from {reviewWindowLabel(activeParams.months)}.
          </p>
        )}

        {!loading && error && (
          <p id="lblScreenerError" className="screener-status screener-error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && result && result.total_count === 0 && (
          <p id="lblScreenerEmpty" className="screener-status screener-empty">
            {NO_MATCHES_MESSAGE}
          </p>
        )}

        {loading && !showTable && <p className="screener-status">{SCREENING_MESSAGE}</p>}

        {showTable && (
          <>
            <p className="screener-count" id="lblScreenerRange">
              {loading ? SCREENING_MESSAGE : `Showing ${rangeStart}–${rangeEnd} of ${result.total_count}`}
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
            <div id="screenerPagination" className="insider-pagination">
              <button
                type="button"
                id="btnScreenerPrev"
                className="insider-page-btn"
                onClick={handlePrevPage}
                disabled={loading || page <= 1}
              >
                Previous
              </button>
              <span className="insider-page-info">
                Page {page} of {result.total_pages}
              </span>
              <button
                type="button"
                id="btnScreenerNext"
                className="insider-page-btn"
                onClick={handleNextPage}
                disabled={loading || !result.has_next}
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>

      <p id="lblScreenerFreshness" className="screener-freshness" role="note">
        {freshnessText}
      </p>

      <p id="lblScreenerDisclaimer" className="screener-disclaimer" role="note">
        {DISCLAIMER}
      </p>
    </div>
  )
}

export default InsiderScreener
