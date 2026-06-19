"""NSE scan universe — ~200 liquid Indian equities.

Hardcoded list covering Nifty 50, Nifty Next 50, and the most liquid
Nifty Midcap 100 names.  Every ticker uses the .NS suffix that
yfinance expects.  Sector mapping is included for rotation analysis
and sector-relative scoring.

Usage:
    from src.universe import get_scan_universe, get_universe_tickers
    stocks = get_scan_universe()          # list[dict]
    tickers = get_universe_tickers()      # list[str]
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Data structure: list of dicts
#   ticker  – yfinance symbol (.NS suffix)
#   name    – human-readable company name
#   sector  – broad sector classification
#   index   – NIFTY50 / NIFTYNEXT50 / MIDCAP100
# ---------------------------------------------------------------------------

SCAN_UNIVERSE: list[dict] = [
    # ======================================================================
    # NIFTY 50  (50 stocks)
    # ======================================================================
    {"ticker": "RELIANCE.NS",    "name": "Reliance Industries",           "sector": "Energy",          "index": "NIFTY50"},
    {"ticker": "TCS.NS",         "name": "Tata Consultancy Services",     "sector": "IT",              "index": "NIFTY50"},
    {"ticker": "HDFCBANK.NS",    "name": "HDFC Bank",                     "sector": "Banking",         "index": "NIFTY50"},
    {"ticker": "INFY.NS",        "name": "Infosys",                       "sector": "IT",              "index": "NIFTY50"},
    {"ticker": "ICICIBANK.NS",   "name": "ICICI Bank",                    "sector": "Banking",         "index": "NIFTY50"},
    {"ticker": "BHARTIARTL.NS",  "name": "Bharti Airtel",                 "sector": "Telecom",         "index": "NIFTY50"},
    {"ticker": "SBIN.NS",        "name": "State Bank of India",           "sector": "Banking",         "index": "NIFTY50"},
    {"ticker": "ITC.NS",         "name": "ITC",                           "sector": "FMCG",            "index": "NIFTY50"},
    {"ticker": "HINDUNILVR.NS",  "name": "Hindustan Unilever",            "sector": "FMCG",            "index": "NIFTY50"},
    {"ticker": "LT.NS",          "name": "Larsen and Toubro",             "sector": "Capital Goods",   "index": "NIFTY50"},
    {"ticker": "BAJFINANCE.NS",  "name": "Bajaj Finance",                 "sector": "Financials",      "index": "NIFTY50"},
    {"ticker": "KOTAKBANK.NS",   "name": "Kotak Mahindra Bank",           "sector": "Banking",         "index": "NIFTY50"},
    {"ticker": "MARUTI.NS",      "name": "Maruti Suzuki",                 "sector": "Auto",            "index": "NIFTY50"},
    {"ticker": "HCLTECH.NS",     "name": "HCL Technologies",             "sector": "IT",              "index": "NIFTY50"},
    {"ticker": "SUNPHARMA.NS",   "name": "Sun Pharma",                    "sector": "Pharma",          "index": "NIFTY50"},
    {"ticker": "TITAN.NS",       "name": "Titan Company",                 "sector": "Consumer",        "index": "NIFTY50"},
    {"ticker": "AXISBANK.NS",    "name": "Axis Bank",                     "sector": "Banking",         "index": "NIFTY50"},
    {"ticker": "ADANIENT.NS",    "name": "Adani Enterprises",             "sector": "Conglomerate",    "index": "NIFTY50"},
    {"ticker": "NTPC.NS",        "name": "NTPC",                          "sector": "Power",           "index": "NIFTY50"},
    {"ticker": "ONGC.NS",        "name": "ONGC",                          "sector": "Energy",          "index": "NIFTY50"},
    {"ticker": "TATAMOTORS.NS",  "name": "Tata Motors",                   "sector": "Auto",            "index": "NIFTY50"},
    {"ticker": "ULTRACEMCO.NS",  "name": "UltraTech Cement",              "sector": "Cement",          "index": "NIFTY50"},
    {"ticker": "ASIANPAINT.NS",  "name": "Asian Paints",                  "sector": "Consumer",        "index": "NIFTY50"},
    {"ticker": "COALINDIA.NS",   "name": "Coal India",                    "sector": "Metals",          "index": "NIFTY50"},
    {"ticker": "BAJAJFINSV.NS",  "name": "Bajaj Finserv",                 "sector": "Financials",      "index": "NIFTY50"},
    {"ticker": "M&M.NS",         "name": "Mahindra and Mahindra",         "sector": "Auto",            "index": "NIFTY50"},
    {"ticker": "WIPRO.NS",       "name": "Wipro",                         "sector": "IT",              "index": "NIFTY50"},
    {"ticker": "POWERGRID.NS",   "name": "Power Grid Corporation",        "sector": "Power",           "index": "NIFTY50"},
    {"ticker": "NESTLEIND.NS",   "name": "Nestle India",                  "sector": "FMCG",            "index": "NIFTY50"},
    {"ticker": "HINDALCO.NS",    "name": "Hindalco Industries",           "sector": "Metals",          "index": "NIFTY50"},
    {"ticker": "JSWSTEEL.NS",    "name": "JSW Steel",                     "sector": "Metals",          "index": "NIFTY50"},
    {"ticker": "TATASTEEL.NS",   "name": "Tata Steel",                    "sector": "Metals",          "index": "NIFTY50"},
    {"ticker": "TECHM.NS",       "name": "Tech Mahindra",                 "sector": "IT",              "index": "NIFTY50"},
    {"ticker": "ADANIPORTS.NS",  "name": "Adani Ports",                   "sector": "Infrastructure",  "index": "NIFTY50"},
    {"ticker": "INDUSINDBK.NS",  "name": "IndusInd Bank",                 "sector": "Banking",         "index": "NIFTY50"},
    {"ticker": "CIPLA.NS",       "name": "Cipla",                         "sector": "Pharma",          "index": "NIFTY50"},
    {"ticker": "GRASIM.NS",      "name": "Grasim Industries",             "sector": "Cement",          "index": "NIFTY50"},
    {"ticker": "DRREDDY.NS",     "name": "Dr. Reddy's Laboratories",     "sector": "Pharma",          "index": "NIFTY50"},
    {"ticker": "SBILIFE.NS",     "name": "SBI Life Insurance",            "sector": "Insurance",       "index": "NIFTY50"},
    {"ticker": "HDFCLIFE.NS",    "name": "HDFC Life Insurance",           "sector": "Insurance",       "index": "NIFTY50"},
    {"ticker": "TATACONSUM.NS",  "name": "Tata Consumer Products",        "sector": "FMCG",            "index": "NIFTY50"},
    {"ticker": "BPCL.NS",        "name": "Bharat Petroleum",              "sector": "Energy",          "index": "NIFTY50"},
    {"ticker": "APOLLOHOSP.NS",  "name": "Apollo Hospitals",              "sector": "Healthcare",      "index": "NIFTY50"},
    {"ticker": "EICHERMOT.NS",   "name": "Eicher Motors",                 "sector": "Auto",            "index": "NIFTY50"},
    {"ticker": "SHRIRAMFIN.NS",  "name": "Shriram Finance",               "sector": "Financials",      "index": "NIFTY50"},
    {"ticker": "DIVISLAB.NS",    "name": "Divi's Laboratories",           "sector": "Pharma",          "index": "NIFTY50"},
    {"ticker": "BRITANNIA.NS",   "name": "Britannia Industries",          "sector": "FMCG",            "index": "NIFTY50"},
    {"ticker": "BAJAJ-AUTO.NS",  "name": "Bajaj Auto",                    "sector": "Auto",            "index": "NIFTY50"},
    {"ticker": "HEROMOTOCO.NS",  "name": "Hero MotoCorp",                 "sector": "Auto",            "index": "NIFTY50"},
    {"ticker": "ETERNAL.NS",     "name": "Zomato (Eternal)",              "sector": "Consumer Tech",   "index": "NIFTY50"},

    # ======================================================================
    # NIFTY NEXT 50  (50 stocks)
    # ======================================================================
    {"ticker": "ADANIGREEN.NS",  "name": "Adani Green Energy",            "sector": "Power",           "index": "NIFTYNEXT50"},
    {"ticker": "ADANIPOWER.NS",  "name": "Adani Power",                   "sector": "Power",           "index": "NIFTYNEXT50"},
    {"ticker": "AMBUJACEM.NS",   "name": "Ambuja Cements",                "sector": "Cement",          "index": "NIFTYNEXT50"},
    {"ticker": "BANKBARODA.NS",  "name": "Bank of Baroda",                "sector": "Banking",         "index": "NIFTYNEXT50"},
    {"ticker": "BERGEPAINT.NS",  "name": "Berger Paints",                 "sector": "Consumer",        "index": "NIFTYNEXT50"},
    {"ticker": "BOSCHLTD.NS",    "name": "Bosch",                         "sector": "Auto Components", "index": "NIFTYNEXT50"},
    {"ticker": "CANBK.NS",       "name": "Canara Bank",                   "sector": "Banking",         "index": "NIFTYNEXT50"},
    {"ticker": "CHOLAFIN.NS",    "name": "Cholamandalam Investment",       "sector": "Financials",      "index": "NIFTYNEXT50"},
    {"ticker": "COLPAL.NS",      "name": "Colgate-Palmolive India",       "sector": "FMCG",            "index": "NIFTYNEXT50"},
    {"ticker": "DLF.NS",         "name": "DLF",                           "sector": "Real Estate",     "index": "NIFTYNEXT50"},
    {"ticker": "DABUR.NS",       "name": "Dabur India",                   "sector": "FMCG",            "index": "NIFTYNEXT50"},
    {"ticker": "GODREJCP.NS",    "name": "Godrej Consumer Products",      "sector": "FMCG",            "index": "NIFTYNEXT50"},
    {"ticker": "HAVELLS.NS",     "name": "Havells India",                  "sector": "Consumer Durables", "index": "NIFTYNEXT50"},
    {"ticker": "HAL.NS",         "name": "Hindustan Aeronautics",         "sector": "Defence",         "index": "NIFTYNEXT50"},
    {"ticker": "ICICIPRULI.NS",  "name": "ICICI Prudential Life",         "sector": "Insurance",       "index": "NIFTYNEXT50"},
    {"ticker": "ICICIGI.NS",     "name": "ICICI Lombard General Ins",     "sector": "Insurance",       "index": "NIFTYNEXT50"},
    {"ticker": "IOC.NS",         "name": "Indian Oil Corporation",        "sector": "Energy",          "index": "NIFTYNEXT50"},
    {"ticker": "INDUSTOWER.NS",  "name": "Indus Towers",                  "sector": "Telecom",         "index": "NIFTYNEXT50"},
    {"ticker": "INDIGO.NS",      "name": "InterGlobe Aviation (IndiGo)",  "sector": "Aviation",        "index": "NIFTYNEXT50"},
    {"ticker": "IRFC.NS",        "name": "Indian Railway Finance Corp",   "sector": "Financials",      "index": "NIFTYNEXT50"},
    {"ticker": "JIOFIN.NS",      "name": "Jio Financial Services",        "sector": "Financials",      "index": "NIFTYNEXT50"},
    {"ticker": "JINDALSTEL.NS",  "name": "Jindal Steel and Power",        "sector": "Metals",          "index": "NIFTYNEXT50"},
    {"ticker": "LICI.NS",        "name": "Life Insurance Corporation",    "sector": "Insurance",       "index": "NIFTYNEXT50"},
    {"ticker": "LUPIN.NS",       "name": "Lupin",                         "sector": "Pharma",          "index": "NIFTYNEXT50"},
    {"ticker": "MARICO.NS",      "name": "Marico",                        "sector": "FMCG",            "index": "NIFTYNEXT50"},
    {"ticker": "MOTHERSON.NS",   "name": "Samvardhana Motherson",         "sector": "Auto Components", "index": "NIFTYNEXT50"},
    {"ticker": "NAUKRI.NS",      "name": "Info Edge (Naukri)",             "sector": "Consumer Tech",   "index": "NIFTYNEXT50"},
    {"ticker": "NHPC.NS",        "name": "NHPC",                          "sector": "Power",           "index": "NIFTYNEXT50"},
    {"ticker": "PFC.NS",         "name": "Power Finance Corporation",     "sector": "Financials",      "index": "NIFTYNEXT50"},
    {"ticker": "PIDILITIND.NS",  "name": "Pidilite Industries",           "sector": "Chemicals",       "index": "NIFTYNEXT50"},
    {"ticker": "PNB.NS",         "name": "Punjab National Bank",          "sector": "Banking",         "index": "NIFTYNEXT50"},
    {"ticker": "RECLTD.NS",      "name": "REC Limited",                   "sector": "Financials",      "index": "NIFTYNEXT50"},
    {"ticker": "SIEMENS.NS",     "name": "Siemens",                       "sector": "Capital Goods",   "index": "NIFTYNEXT50"},
    {"ticker": "SRF.NS",         "name": "SRF",                           "sector": "Chemicals",       "index": "NIFTYNEXT50"},
    {"ticker": "SHREECEM.NS",    "name": "Shree Cement",                  "sector": "Cement",          "index": "NIFTYNEXT50"},
    {"ticker": "TATAPOWER.NS",   "name": "Tata Power",                    "sector": "Power",           "index": "NIFTYNEXT50"},
    {"ticker": "TORNTPHARM.NS",  "name": "Torrent Pharmaceuticals",       "sector": "Pharma",          "index": "NIFTYNEXT50"},
    {"ticker": "TVSMOTOR.NS",    "name": "TVS Motor Company",             "sector": "Auto",            "index": "NIFTYNEXT50"},
    {"ticker": "UNIONBANK.NS",   "name": "Union Bank of India",           "sector": "Banking",         "index": "NIFTYNEXT50"},
    {"ticker": "UNITDSPR.NS",    "name": "United Spirits",                "sector": "Consumer",        "index": "NIFTYNEXT50"},
    {"ticker": "VEDL.NS",        "name": "Vedanta",                       "sector": "Metals",          "index": "NIFTYNEXT50"},
    {"ticker": "IDEA.NS",        "name": "Vodafone Idea",                 "sector": "Telecom",         "index": "NIFTYNEXT50"},
    {"ticker": "YESBANK.NS",     "name": "Yes Bank",                      "sector": "Banking",         "index": "NIFTYNEXT50"},
    {"ticker": "ABB.NS",         "name": "ABB India",                     "sector": "Capital Goods",   "index": "NIFTYNEXT50"},
    {"ticker": "GAIL.NS",        "name": "GAIL (India)",                  "sector": "Energy",          "index": "NIFTYNEXT50"},
    {"ticker": "TRENT.NS",       "name": "Trent",                         "sector": "Consumer",        "index": "NIFTYNEXT50"},
    {"ticker": "MAXHEALTH.NS",   "name": "Max Healthcare Institute",      "sector": "Healthcare",      "index": "NIFTYNEXT50"},
    {"ticker": "LODHA.NS",       "name": "Macrotech Developers (Lodha)",  "sector": "Real Estate",     "index": "NIFTYNEXT50"},
    {"ticker": "POLICYBZR.NS",   "name": "PB Fintech (PolicyBazaar)",     "sector": "Consumer Tech",   "index": "NIFTYNEXT50"},
    {"ticker": "JSWENERGY.NS",   "name": "JSW Energy",                    "sector": "Power",           "index": "NIFTYNEXT50"},

    # ======================================================================
    # NIFTY MIDCAP 100 — most liquid ~100 names
    # ======================================================================
    {"ticker": "AUROPHARMA.NS",  "name": "Aurobindo Pharma",              "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "ASTRAL.NS",      "name": "Astral",                        "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "BALKRISIND.NS",  "name": "Balkrishna Industries",         "sector": "Auto Components", "index": "MIDCAP100"},
    {"ticker": "BANDHANBNK.NS",  "name": "Bandhan Bank",                  "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "BEL.NS",         "name": "Bharat Electronics",            "sector": "Defence",         "index": "MIDCAP100"},
    {"ticker": "BHEL.NS",        "name": "Bharat Heavy Electricals",      "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "BIOCON.NS",      "name": "Biocon",                        "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "CANFINHOME.NS",  "name": "Can Fin Homes",                 "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "CESC.NS",        "name": "CESC",                          "sector": "Power",           "index": "MIDCAP100"},
    {"ticker": "COFORGE.NS",     "name": "Coforge",                       "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "CONCOR.NS",      "name": "Container Corporation",         "sector": "Infrastructure",  "index": "MIDCAP100"},
    {"ticker": "CROMPTON.NS",    "name": "Crompton Greaves Consumer",     "sector": "Consumer Durables", "index": "MIDCAP100"},
    {"ticker": "CUB.NS",         "name": "City Union Bank",               "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "CUMMINSIND.NS",  "name": "Cummins India",                 "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "DEEPAKNTR.NS",   "name": "Deepak Nitrite",                "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "DELHIVERY.NS",   "name": "Delhivery",                     "sector": "Logistics",       "index": "MIDCAP100"},
    {"ticker": "DIXON.NS",       "name": "Dixon Technologies",            "sector": "Consumer Durables", "index": "MIDCAP100"},
    {"ticker": "ESCORTS.NS",     "name": "Escorts Kubota",                "sector": "Auto",            "index": "MIDCAP100"},
    {"ticker": "EXIDEIND.NS",    "name": "Exide Industries",              "sector": "Auto Components", "index": "MIDCAP100"},
    {"ticker": "FEDERALBNK.NS",  "name": "Federal Bank",                  "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "FORTIS.NS",      "name": "Fortis Healthcare",             "sector": "Healthcare",      "index": "MIDCAP100"},
    {"ticker": "GLENMARK.NS",    "name": "Glenmark Pharmaceuticals",      "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "GMRINFRA.NS",    "name": "GMR Airports Infrastructure",   "sector": "Infrastructure",  "index": "MIDCAP100"},
    {"ticker": "GNFC.NS",        "name": "Gujarat Narmada Valley Fert",   "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "GODREJPROP.NS",  "name": "Godrej Properties",             "sector": "Real Estate",     "index": "MIDCAP100"},
    {"ticker": "GSPL.NS",        "name": "Gujarat State Petronet",        "sector": "Energy",          "index": "MIDCAP100"},
    {"ticker": "GUJGASLTD.NS",   "name": "Gujarat Gas",                   "sector": "Energy",          "index": "MIDCAP100"},
    {"ticker": "HINDPETRO.NS",   "name": "Hindustan Petroleum",           "sector": "Energy",          "index": "MIDCAP100"},
    {"ticker": "IDFCFIRSTB.NS",  "name": "IDFC First Bank",               "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "IEX.NS",         "name": "Indian Energy Exchange",        "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "INDIANB.NS",     "name": "Indian Bank",                   "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "IRCTC.NS",       "name": "Indian Railway Catering",       "sector": "Consumer Tech",   "index": "MIDCAP100"},
    {"ticker": "IPCALAB.NS",     "name": "Ipca Laboratories",             "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "JUBLFOOD.NS",    "name": "Jubilant Foodworks",            "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "KALYANKJIL.NS",  "name": "Kalyan Jewellers",              "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "KPITTECH.NS",    "name": "KPIT Technologies",             "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "L&TFH.NS",       "name": "L&T Finance",                   "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "LALPATHLAB.NS",  "name": "Dr Lal PathLabs",               "sector": "Healthcare",      "index": "MIDCAP100"},
    {"ticker": "LAURUSLABS.NS",  "name": "Laurus Labs",                   "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "LICHSGFIN.NS",   "name": "LIC Housing Finance",           "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "LTTS.NS",        "name": "L&T Technology Services",       "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "MANAPPURAM.NS",  "name": "Manappuram Finance",            "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "MFSL.NS",        "name": "Max Financial Services",        "sector": "Insurance",       "index": "MIDCAP100"},
    {"ticker": "MGL.NS",         "name": "Mahanagar Gas",                 "sector": "Energy",          "index": "MIDCAP100"},
    {"ticker": "MPHASIS.NS",     "name": "Mphasis",                       "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "MUTHOOTFIN.NS",  "name": "Muthoot Finance",               "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "NATIONALUM.NS",  "name": "National Aluminium",            "sector": "Metals",          "index": "MIDCAP100"},
    {"ticker": "NAVINFLUOR.NS",  "name": "Navin Fluorine",                "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "NMDC.NS",        "name": "NMDC",                          "sector": "Metals",          "index": "MIDCAP100"},
    {"ticker": "OBEROIRLTY.NS",  "name": "Oberoi Realty",                 "sector": "Real Estate",     "index": "MIDCAP100"},
    {"ticker": "OFSS.NS",        "name": "Oracle Financial Services",     "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "PAGEIND.NS",     "name": "Page Industries",               "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "PATANJALI.NS",   "name": "Patanjali Foods",               "sector": "FMCG",            "index": "MIDCAP100"},
    {"ticker": "PERSISTENT.NS",  "name": "Persistent Systems",            "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "PETRONET.NS",    "name": "Petronet LNG",                  "sector": "Energy",          "index": "MIDCAP100"},
    {"ticker": "PIIND.NS",       "name": "PI Industries",                 "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "POLYCAB.NS",     "name": "Polycab India",                 "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "PRESTIGE.NS",    "name": "Prestige Estates Projects",     "sector": "Real Estate",     "index": "MIDCAP100"},
    {"ticker": "PVRINOX.NS",     "name": "PVR INOX",                      "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "RAMCOCEM.NS",    "name": "Ramco Cements",                 "sector": "Cement",          "index": "MIDCAP100"},
    {"ticker": "RATNAMANI.NS",   "name": "Ratnamani Metals and Tubes",    "sector": "Metals",          "index": "MIDCAP100"},
    {"ticker": "SAIL.NS",        "name": "Steel Authority of India",      "sector": "Metals",          "index": "MIDCAP100"},
    {"ticker": "SBICARD.NS",     "name": "SBI Cards and Payment",         "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "SCHAEFFLER.NS",  "name": "Schaeffler India",              "sector": "Auto Components", "index": "MIDCAP100"},
    {"ticker": "SONACOMS.NS",    "name": "Sona BLW Precision Forgings",   "sector": "Auto Components", "index": "MIDCAP100"},
    {"ticker": "SUNDARMFIN.NS",  "name": "Sundaram Finance",              "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "SUNDRMFAST.NS",  "name": "Sundram Fasteners",             "sector": "Auto Components", "index": "MIDCAP100"},
    {"ticker": "SUNTV.NS",       "name": "Sun TV Network",                "sector": "Media",           "index": "MIDCAP100"},
    {"ticker": "SUPREMEIND.NS",  "name": "Supreme Industries",            "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "SYNGENE.NS",     "name": "Syngene International",         "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "TATACHEM.NS",    "name": "Tata Chemicals",                "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "TATACOMM.NS",    "name": "Tata Communications",           "sector": "Telecom",         "index": "MIDCAP100"},
    {"ticker": "TATAELXSI.NS",   "name": "Tata Elxsi",                    "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "TATAMTRDVR.NS",  "name": "Tata Motors DVR",               "sector": "Auto",            "index": "MIDCAP100"},
    {"ticker": "THERMAX.NS",     "name": "Thermax",                       "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "TIINDIA.NS",     "name": "Tube Investments of India",     "sector": "Auto Components", "index": "MIDCAP100"},
    {"ticker": "TORNTPOWER.NS",  "name": "Torrent Power",                 "sector": "Power",           "index": "MIDCAP100"},
    {"ticker": "UBL.NS",         "name": "United Breweries",              "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "UPL.NS",         "name": "UPL",                           "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "VOLTAS.NS",      "name": "Voltas",                        "sector": "Consumer Durables", "index": "MIDCAP100"},
    {"ticker": "WHIRLPOOL.NS",   "name": "Whirlpool of India",            "sector": "Consumer Durables", "index": "MIDCAP100"},
    {"ticker": "ZEEL.NS",        "name": "Zee Entertainment",             "sector": "Media",           "index": "MIDCAP100"},
    {"ticker": "ZYDUSLIFE.NS",   "name": "Zydus Lifesciences",            "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "ABCAPITAL.NS",   "name": "Aditya Birla Capital",          "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "ACC.NS",         "name": "ACC",                           "sector": "Cement",          "index": "MIDCAP100"},
    {"ticker": "ALOKINDS.NS",    "name": "Alok Industries",               "sector": "Textiles",        "index": "MIDCAP100"},
    {"ticker": "APLLTD.NS",      "name": "Alembic Pharmaceuticals",       "sector": "Pharma",          "index": "MIDCAP100"},
    {"ticker": "ATUL.NS",        "name": "Atul",                          "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "BATAINDIA.NS",   "name": "Bata India",                    "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "BDL.NS",         "name": "Bharat Dynamics",               "sector": "Defence",         "index": "MIDCAP100"},
    {"ticker": "CENTRALBK.NS",   "name": "Central Bank of India",         "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "COCHINSHIP.NS",  "name": "Cochin Shipyard",               "sector": "Defence",         "index": "MIDCAP100"},
    {"ticker": "CYIENT.NS",      "name": "Cyient",                        "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "EMAMILTD.NS",    "name": "Emami",                         "sector": "FMCG",            "index": "MIDCAP100"},
    {"ticker": "ENGINERSIN.NS",  "name": "Engineers India",               "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "FACT.NS",        "name": "Fertilisers and Chemicals",     "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "HDFCAMC.NS",     "name": "HDFC Asset Management",         "sector": "Financials",      "index": "MIDCAP100"},
    {"ticker": "HONAUT.NS",      "name": "Honeywell Automation",          "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "IDBI.NS",        "name": "IDBI Bank",                     "sector": "Banking",         "index": "MIDCAP100"},
    {"ticker": "INDHOTEL.NS",    "name": "Indian Hotels Company",         "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "JSL.NS",         "name": "Jindal Stainless",              "sector": "Metals",          "index": "MIDCAP100"},
    {"ticker": "KAYNES.NS",      "name": "Kaynes Technology",             "sector": "IT",              "index": "MIDCAP100"},
    {"ticker": "KEI.NS",         "name": "KEI Industries",                "sector": "Capital Goods",   "index": "MIDCAP100"},
    {"ticker": "MAZAGON.NS",     "name": "Mazagon Dock Shipbuilders",     "sector": "Defence",         "index": "MIDCAP100"},
    {"ticker": "PHOENIXLTD.NS",  "name": "Phoenix Mills",                 "sector": "Real Estate",     "index": "MIDCAP100"},
    {"ticker": "RAJESHEXPO.NS",  "name": "Rajesh Exports",                "sector": "Consumer",        "index": "MIDCAP100"},
    {"ticker": "SOLARINDS.NS",   "name": "Solar Industries India",        "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "SUMICHEM.NS",    "name": "Sumitomo Chemical India",        "sector": "Chemicals",       "index": "MIDCAP100"},
    {"ticker": "ZOMATO.NS",      "name": "Zomato (Alternate Ticker)",     "sector": "Consumer Tech",   "index": "MIDCAP100"},
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

# Ticker -> dict, built once at import time
_TICKER_MAP: dict[str, dict] = {s["ticker"].upper(): s for s in SCAN_UNIVERSE}

# Unique sectors
SECTORS: list[str] = sorted({s["sector"] for s in SCAN_UNIVERSE})


def get_scan_universe() -> List[dict]:
    """Return the full scan universe as a list of dicts."""
    return list(SCAN_UNIVERSE)


def get_universe_tickers() -> List[str]:
    """Return just the ticker strings."""
    return [s["ticker"] for s in SCAN_UNIVERSE]


def get_nifty50_tickers() -> List[str]:
    """Return only Nifty 50 tickers."""
    return [s["ticker"] for s in SCAN_UNIVERSE if s["index"] == "NIFTY50"]


def get_niftynext50_tickers() -> List[str]:
    """Return only Nifty Next 50 tickers."""
    return [s["ticker"] for s in SCAN_UNIVERSE if s["index"] == "NIFTYNEXT50"]


def get_midcap100_tickers() -> List[str]:
    """Return only Midcap 100 tickers."""
    return [s["ticker"] for s in SCAN_UNIVERSE if s["index"] == "MIDCAP100"]


def get_by_sector(sector: str) -> List[dict]:
    """Return stocks belonging to a given sector (case-insensitive)."""
    sector_lower = sector.lower()
    return [s for s in SCAN_UNIVERSE if s["sector"].lower() == sector_lower]


def get_stock_info(ticker: str) -> dict | None:
    """Lookup a single stock by ticker. Returns None if not found."""
    return _TICKER_MAP.get(ticker.upper())


def get_sectors() -> List[str]:
    """Return all unique sector names, sorted."""
    return list(SECTORS)


def universe_summary() -> dict:
    """Quick stats about the universe."""
    n50 = sum(1 for s in SCAN_UNIVERSE if s["index"] == "NIFTY50")
    nn50 = sum(1 for s in SCAN_UNIVERSE if s["index"] == "NIFTYNEXT50")
    mid = sum(1 for s in SCAN_UNIVERSE if s["index"] == "MIDCAP100")
    return {
        "total_stocks": len(SCAN_UNIVERSE),
        "nifty50": n50,
        "niftynext50": nn50,
        "midcap100": mid,
        "sectors": len(SECTORS),
        "sector_list": SECTORS,
    }
