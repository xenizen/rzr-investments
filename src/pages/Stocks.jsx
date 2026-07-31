function Stocks() {
  return (
    <div id="stocks">
      <input type="text" id="txtStockSymbol" name="txtStockSymbol" />
      <button type="button" id="btnGetPrice" name="btnGetPrice">
        Get Price
      </button>
      <label id="lblFoundPrice" name="lblFoundPrice" />
    </div>
  )
}

export default Stocks
