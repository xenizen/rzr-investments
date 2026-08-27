const DISCLAIMER =
  'Not investment advice. Signals are derived from public SEC Form 4 filings and market data, for informational use only.'

function InsiderScreener() {
  return (
    <div id="insider-screener" className="stock-card">
      <span className="stock-card-tag">Insider Signals</span>
      <h1>Insider Screener</h1>
      <p className="stock-card-sub">
        Screen recent SEC Form 4 insider transactions and surface buy/sell ideas, filtered by insider activity and price
        relative to the 52-week high.
      </p>
      {/* Parameter dropdowns are added in SCRUM-37. */}
      <div id="screenerForm" className="screener-form" />
      {/* Results table and pagination are added in SCRUM-38 / SCRUM-39. */}
      <div id="screenerResults" className="screener-results" />
      <p id="lblScreenerDisclaimer" className="screener-disclaimer" role="note">
        {DISCLAIMER}
      </p>
    </div>
  )
}

export default InsiderScreener
