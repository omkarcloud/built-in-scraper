"""ISO 3166-1 alpha-2 -> alpha-3: the board's `country=` takes alpha-3
(USA, GBR, DEU); the API takes alpha-2 (US, GB, DE)."""

ALPHA2_TO_ALPHA3 = {
    "AD": "AND", "AE": "ARE", "AG": "ATG", "AI": "AIA", "AL": "ALB", "AM": "ARM", "AO": "AGO", "AR": "ARG",
    "AT": "AUT", "AU": "AUS", "AZ": "AZE", "BA": "BIH", "BB": "BRB", "BE": "BEL", "BF": "BFA", "BG": "BGR",
    "BH": "BHR", "BM": "BMU", "BN": "BRN", "BO": "BOL", "BR": "BRA", "BS": "BHS", "BW": "BWA", "BY": "BLR",
    "BZ": "BLZ", "CA": "CAN", "CD": "COD", "CH": "CHE", "CI": "CIV", "CL": "CHL", "CM": "CMR", "CN": "CHN",
    "CO": "COL", "CR": "CRI", "CU": "CUB", "CV": "CPV", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
    "DM": "DMA", "DO": "DOM", "DZ": "DZA", "EC": "ECU", "EE": "EST", "EG": "EGY", "ES": "ESP", "FI": "FIN",
    "FJ": "FJI", "FM": "FSM", "FR": "FRA", "GB": "GBR", "GD": "GRD", "GF": "GUF", "GG": "GGY", "GH": "GHA",
    "GI": "GIB", "GM": "GMB", "GQ": "GNQ", "GR": "GRC", "GT": "GTM", "GW": "GNB", "GY": "GUY", "HK": "HKG",
    "HN": "HND", "HR": "HRV", "HU": "HUN", "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IQ": "IRQ",
    "IS": "ISL", "IT": "ITA", "JM": "JAM", "JO": "JOR", "JP": "JPN", "KE": "KEN", "KG": "KGZ", "KH": "KHM",
    "KN": "KNA", "KR": "KOR", "KW": "KWT", "KY": "CYM", "KZ": "KAZ", "LA": "LAO", "LB": "LBN", "LC": "LCA",
    "LI": "LIE", "LK": "LKA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "LY": "LBY", "MA": "MAR", "MC": "MCO",
    "MD": "MDA", "ME": "MNE", "MG": "MDG", "MK": "MKD", "ML": "MLI", "MN": "MNG", "MO": "MAC", "MT": "MLT",
    "MU": "MUS", "MW": "MWI", "MX": "MEX", "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NE": "NER", "NG": "NGA",
    "NI": "NIC", "NL": "NLD", "NO": "NOR", "NP": "NPL", "NZ": "NZL", "OM": "OMN", "PA": "PAN", "PE": "PER",
    "PF": "PYF", "PG": "PNG", "PH": "PHL", "PK": "PAK", "PL": "POL", "PS": "PSE", "PT": "PRT", "PY": "PRY",
    "QA": "QAT", "RO": "ROU", "RS": "SRB", "RU": "RUS", "SA": "SAU", "SC": "SYC", "SE": "SWE", "SG": "SGP",
    "SI": "SVN", "SK": "SVK", "SM": "SMR", "SN": "SEN", "SV": "SLV", "SZ": "SWZ", "TC": "TCA", "TD": "TCD",
    "TH": "THA", "TJ": "TJK", "TM": "TKM", "TN": "TUN", "TR": "TUR", "TT": "TTO", "TW": "TWN", "TZ": "TZA",
    "UA": "UKR", "UG": "UGA", "US": "USA", "UY": "URY", "UZ": "UZB", "VA": "VAT", "VE": "VEN", "VG": "VGB",
    "VN": "VNM", "YE": "YEM", "ZA": "ZAF", "ZM": "ZMB", "ZW": "ZWE",
}
