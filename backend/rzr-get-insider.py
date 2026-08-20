from datetime import date

from edgar import get_filings, set_identity
from edgar import Company

# Use your name and email (required by SEC)
set_identity("enochmgmt.com enzork@gmail.com")

# To process MULTIPLE filings, loop over filings:
# dateYesterday = date.today().replace(day=date.today().day - 1)
# for filing in company.get_filings(form="4", filing_date=dateYesterday).head(20):
#     summary = filing.obj().get_ownership_summary()
#     print(f"{summary.insider_name}: {summary.primary_activity}")

# filings = get_filings(form=4)
# for f in filings[:20]:
#     form4 = f.obj()
#     if form4:
#         summary = form4.get_ownership_summary()
#         if summary.net_change > 10000:
#             # Get all filings for this company and print the insider's name, the number of shares bought, and the company name
#             stock = Company(summary.issuer[-5:-1])
#             form4single = stock.get_filings(form="4")

#             print(
#                 f"{summary.insider_name} bought {summary.net_change:,} shares of {summary.issuer}")
#             # print(stocksymbol)
#             print(f"Total FORM4 filings found: {len(form4single)}")


# BKKT
company = Company("BKKT")
filings = company.get_filings(form=4)
for f in filings[:20]:
    form4 = f.obj()
    if form4:
        summary = form4.get_ownership_summary()
        print(
            f"{summary.insider_name} bought {summary.net_change:,} shares of {summary.issuer}")

# print(form4s)
