import { useRef, useState } from 'react'

const NO_CRITERIA_ENTERED_MESSAGE = 'No Search Criteria Entered'
const NO_RESULTS_MESSAGE = 'No matching insider filings found.'
const REQUEST_FAILED_MESSAGE = 'No Insider Data Found: Real Stock?'
const SEARCHING_MESSAGE = 'Searching…'

function buildQuery({ symbol, name, dateFrom, dateTo, page }) {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (name) params.set('name', name)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (page && page !== 1) params.set('page', String(page))
  return params.toString()
}

function InsiderData() {
  const symbolRef = useRef(null)
  const nameRef = useRef(null)
  const dateFromRef = useRef(null)
  const dateToRef = useRef(null)

  // The criteria the current result set was fetched with -- kept separate
  // from the input refs so paging uses what was actually searched, even if
  // the user has since edited the fields without clicking Search again.
  const [criteria, setCriteria] = useState(null)
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [results, setResults] = useState([])

  async function runSearch(searchCriteria, targetPage) {
    setLoading(true)
    try {
      const query = buildQuery({ ...searchCriteria, page: targetPage })
      const response = await fetch(`${import.meta.env.BASE_URL}api/insider-data?${query}`)
      const data = await response.json()

      if (data.error) {
        setResults([])
        setMessage(data.error)
        setHasNext(false)
        setTotalCount(0)
        return
      }

      const found = data.results ?? []
      setResults(found)
      setMessage(found.length ? '' : NO_RESULTS_MESSAGE)
      setPage(data.page ?? targetPage)
      setTotalCount(data.total_count ?? 0)
      setHasNext(Boolean(data.has_next))
    } catch {
      setResults([])
      setMessage(REQUEST_FAILED_MESSAGE)
      setHasNext(false)
      setTotalCount(0)
    } finally {
      setLoading(false)
    }
  }

  function handleSearch() {
    const symbol = symbolRef.current.value.trim()
    const name = nameRef.current.value.trim()
    const dateFrom = dateFromRef.current.value
    const dateTo = dateToRef.current.value

    if (!symbol && !name && !dateFrom && !dateTo) {
      setCriteria(null)
      setResults([])
      setMessage(NO_CRITERIA_ENTERED_MESSAGE)
      setHasNext(false)
      setTotalCount(0)
      setPage(1)
      return
    }

    const newCriteria = { symbol, name, dateFrom, dateTo }
    setCriteria(newCriteria)
    runSearch(newCriteria, 1)
  }

  function handlePrevPage() {
    if (!criteria || loading || page <= 1) return
    runSearch(criteria, page - 1)
  }

  function handleNextPage() {
    if (!criteria || loading || !hasNext) return
    runSearch(criteria, page + 1)
  }

  const rangeStart = results.length ? (page - 1) * 10 + 1 : 0
  const rangeEnd = rangeStart ? rangeStart + results.length - 1 : 0

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
          disabled={loading}
          className="stock-btn"
        >
          Search
        </button>
      </div>
      <label id="lblInsiderMessage" name="lblInsiderMessage" className="stock-result">
        {loading ? SEARCHING_MESSAGE : message}
      </label>
      {results.length > 0 && (
        <>
          <div className="insider-table-wrap">
            <table id="insiderResultsTable" className="insider-table">
              <thead>
                <tr>
                  <th scope="col">Insider</th>
                  <th scope="col">Shares</th>
                  <th scope="col">Issuer</th>
                  <th scope="col">Filing Date</th>
                </tr>
              </thead>
              <tbody>
                {results.map((result, index) => (
                  <tr key={index} data-testid="insider-result-row">
                    <td>{result.insider_name}</td>
                    <td>{(result.net_change ?? 0).toLocaleString()}</td>
                    <td>{result.issuer}</td>
                    <td>{result.filing_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div id="insiderPagination" className="insider-pagination">
            <button
              type="button"
              id="btnPrevPage"
              onClick={handlePrevPage}
              disabled={loading || page <= 1}
              className="insider-page-btn"
            >
              Previous
            </button>
            <span id="lblInsiderPageInfo" className="insider-page-info">
              Showing {rangeStart}–{rangeEnd} of {totalCount}
            </span>
            <button
              type="button"
              id="btnNextPage"
              onClick={handleNextPage}
              disabled={loading || !hasNext}
              className="insider-page-btn"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export default InsiderData
