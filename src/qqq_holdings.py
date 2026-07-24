"""Shared Invesco QQQ holdings loader.

This module is the single implementation used by both the isolated vintage
archiver and the production L4 full-constituent forward-PE source.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("vintage_archiver")

INVESCO_QQQ_HOLDINGS_URL = (
    "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/"
    "holdings/fund?idType=ticker&interval=monthly&productType=ETF"
)
INVESCO_QQQ_HOLDINGS_PAGE = "https://www.invesco.com/qqq-etf/en/about.html#top-10-holdings"

EQUITY_SECURITY_TYPE_MARKERS = ("common stock", "depository receipt", "depositary receipt")

# Static fallback sourced from the live Invesco endpoint on 2026-07-23;
# holdings effective date reported by the endpoint was 2026-07-22.
_STATIC_FULL_FALLBACK_ROWS = """\
1	NVDA	NVIDIA Corp	8.288274
2	AAPL	Apple Inc	7.730452
3	MU	Micron Technology Inc	4.824474
4	MSFT	Microsoft Corp	4.683078
5	AMZN	Amazon.com Inc	4.253882
6	AMD	Advanced Micro Devices Inc	4.015629
7	GOOGL	Alphabet Inc Class A	3.217750
8	AVGO	Broadcom Inc	3.038568
9	TSLA	Tesla Inc	3.017522
10	GOOG	Alphabet Inc Class C	3.012851
11	META	Meta Platforms Inc	2.999586
12	WMT	Walmart Inc	2.377961
13	INTC	Intel Corp	2.299653
14	CSCO	Cisco Systems Inc	1.971943
15	AMAT	Applied Materials Inc	1.960879
16	COST	Costco Wholesale Corp	1.834309
17	LRCX	Lam Research Corp	1.780332
18	NFLX	Netflix Inc	1.286627
19	PLTR	Palantir Technologies Inc	1.275285
20	KLAC	KLA Corp	1.250409
21	PANW	Palo Alto Networks Inc	1.219858
22	TXN	Texas Instruments Inc	1.193776
23	SNDK	Sandisk Corp	1.055979
24	LIN	Linde PLC	1.048614
25	SPCX	Space Exploration Technologies Corp	0.984991
26	TMUS	T-Mobile US Inc	0.921328
27	STX	Seagate Technology Holdings PLC	0.907878
28	AMGN	Amgen Inc	0.880859
29	WDC	Western Digital Corp	0.855512
30	CRWD	Crowdstrike Holdings Inc	0.855497
31	ADI	Analog Devices Inc	0.839894
32	PEP	PepsiCo Inc	0.826649
33	QCOM	QUALCOMM Inc	0.825366
34	MRVL	Marvell Technology Inc	0.823194
35	ASML	ASML Holding NV	0.736212
36	GILD	Gilead Sciences Inc	0.721532
37	SHOP	Shopify Inc	0.643939
38	BKNG	Booking Holdings Inc	0.614493
39	APP	AppLovin Corp	0.562272
40	ISRG	Intuitive Surgical Inc	0.537985
41	ARM	ARM Holdings PLC	0.535772
42	VRTX	Vertex Pharmaceuticals Inc	0.534783
43	SBUX	Starbucks Corp	0.528380
44	FTNT	Fortinet Inc	0.506498
45	CEG	Constellation Energy Corp	0.442710
46	MAR	Marriott International Inc/MD	0.434774
47	ADP	Automatic Data Processing Inc	0.433306
48	MNST	Monster Beverage Corp	0.417185
49	CDNS	Cadence Design Systems Inc	0.414448
50	CSX	CSX Corp	0.413663
51	MELI	MercadoLibre Inc	0.406505
52	ADBE	Adobe Inc	0.393525
53	CMCSA	Comcast Corp	0.373624
54	DDOG	Datadog Inc	0.362528
55	CTAS	Cintas Corp	0.359203
56	MDLZ	Mondelez International Inc	0.348326
57	INTU	Intuit Inc	0.346948
58	ROST	Ross Stores Inc	0.342154
59	HON	Honeywell International Inc	0.329134
60	DASH	DoorDash Inc	0.325961
61	AEP	American Electric Power Co Inc	0.322826
62	SNPS	Synopsys Inc	0.322384
63	ORLY	O'Reilly Automotive Inc	0.319730
64	NXPI	NXP Semiconductors NV	0.313843
65	PCAR	PACCAR Inc	0.307655
66	MPWR	Monolithic Power Systems Inc	0.306370
67	REGN	Regeneron Pharmaceuticals Inc	0.299120
68	HONA	Honeywell Aerospace Inc	0.293521
69	WBD	Warner Bros Discovery Inc	0.288966
70	LITE	Lumentum Holdings Inc	0.287642
71	ABNB	Airbnb Inc	0.260976
72	TER	Teradyne Inc	0.257679
73	FANG	Diamondback Energy Inc	0.254652
74	ALAB	Astera Labs Inc	0.252881
75	BKR	Baker Hughes Co	0.250361
76	PDD	PDD Holdings Inc	0.248936
77	EA	Electronic Arts Inc	0.233616
78	FAST	Fastenal Co	0.232032
79	XEL	Xcel Energy Inc	0.223203
80	PYPL	PayPal Holdings Inc	0.218107
81	ODFL	Old Dominion Freight Line Inc	0.215676
82	NBIS	Nebius Group NV	0.214192
83	EXC	Exelon Corp	0.212872
84	CCEP	Coca-Cola Europacific Partners PLC	0.210501
85	FER	Ferrovial NV	0.205502
86	MCHP	Microchip Technology Inc	0.205310
87	TTWO	Take-Two Interactive Software Inc	0.193367
88	IDXX	IDEXX Laboratories Inc	0.191690
89	ADSK	Autodesk Inc	0.191450
90	KDP	Keurig Dr Pepper Inc	0.183023
91	RKLB	Rocket Lab Corp	0.179828
92	PAYX	Paychex Inc	0.176723
93	AXON	Axon Enterprise Inc	0.176460
94	CRWV	CoreWeave Inc	0.164730
95	ALNY	Alnylam Pharmaceuticals Inc	0.158939
96	ROP	Roper Technologies Inc	0.151322
97	TRI	Thomson Reuters Corp	0.148204
98	MSTR	Strategy Inc	0.147320
99	KHC	Kraft Heinz Co/The	0.137060
100	GEHC	GE HealthCare Technologies Inc	0.124372
101	DXCM	Dexcom Inc	0.122717
102	WDAY	Workday Inc	0.118495
103	CPRT	Copart Inc	0.111973
"""

STATIC_FULL_FALLBACK = [
    {
        "rank": int(rank),
        "ticker": ticker,
        "issuer_name": issuer_name,
        "weight_pct": float(weight_pct),
    }
    for rank, ticker, issuer_name, weight_pct in (
        line.split("\t") for line in _STATIC_FULL_FALLBACK_ROWS.splitlines() if line
    )
]
STATIC_FULL_FALLBACK_DATED = "2026-07-23 (holdings effective 2026-07-22)"


def _classify_holding(
    ticker: str, weight_pct: Optional[float], security_type: Optional[str]
) -> Optional[str]:
    """Return None for a usable equity holding, otherwise an exclusion reason."""
    if not ticker:
        return "missing_ticker"
    if weight_pct is None:
        return "missing_or_invalid_weight"
    if weight_pct <= 0:
        return "non_positive_weight"
    normalized_type = (security_type or "").strip().lower()
    if any(marker in normalized_type for marker in EQUITY_SECURITY_TYPE_MARKERS):
        return None
    return f"non_equity_security_type:{security_type or 'unknown'}"


def _fetch_qqq_top_holdings(
    top_n: Optional[int] = None, timeout: int = 15
) -> Dict[str, Any]:
    """Fetch all valid official QQQ equity holdings, with a dated static fallback."""
    try:
        response = requests.get(
            INVESCO_QQQ_HOLDINGS_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.invesco.com",
                "Referer": "https://www.invesco.com/qqq-etf/en/about.html",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        holdings_raw = data.get("holdings") if isinstance(data, dict) else None
        if not isinstance(holdings_raw, list) or not holdings_raw:
            raise ValueError("Invesco response missing holdings list")

        normalized = []
        filtered_out = []
        for row in holdings_raw:
            ticker = str(row.get("ticker") or "").strip().upper()
            security_type = row.get("securityTypeName")
            try:
                weight_pct = float(row.get("percentageOfTotalNetAssets"))
            except (TypeError, ValueError):
                weight_pct = None
            reason = _classify_holding(ticker, weight_pct, security_type)
            if reason is not None:
                filtered_out.append(
                    {
                        "ticker": ticker or None,
                        "issuer_name": row.get("issuerName"),
                        "security_type": security_type,
                        "weight_pct": weight_pct,
                        "reason": reason,
                    }
                )
                continue
            normalized.append(
                {
                    "ticker": ticker,
                    "issuer_name": row.get("issuerName"),
                    "weight_pct": round(weight_pct, 6),
                    "security_type": security_type,
                }
            )
        normalized.sort(key=lambda item: item["weight_pct"], reverse=True)
        selected = normalized[:top_n] if top_n else normalized
        for rank, item in enumerate(selected, start=1):
            item["rank"] = rank

        effective_date = data.get("effectiveBusinessDate") or data.get("effectiveDate")
        return {
            "status": "ok",
            "method": "live_invesco_qqq_holdings_api",
            "source_name": "Invesco QQQ official holdings API",
            "source_url": INVESCO_QQQ_HOLDINGS_URL,
            "source_authority": "official_provider",
            "fallback_used": False,
            "effective_date": str(effective_date)[:10] if effective_date else None,
            "total_holdings_reported": data.get("totalNumberOfHoldings"),
            "total_holdings_selected": len(selected),
            "fund_name": data.get("fundName") or data.get("shareClassName"),
            "constituents": selected,
            "weight_pct_sum": (
                round(sum(item["weight_pct"] for item in selected), 6) if selected else 0.0
            ),
            "filtered_out_count": len(filtered_out),
            "filtered_out": filtered_out,
        }
    except Exception as exc:
        logger.warning("Live QQQ holdings fetch failed, using static fallback: %s", exc)
        fallback = [
            dict(item)
            for item in (
                STATIC_FULL_FALLBACK[:top_n] if top_n else STATIC_FULL_FALLBACK
            )
        ]
        return {
            "status": "fallback_used",
            "method": "static_fallback",
            "source_name": "Invesco QQQ official holdings API (static fallback, not live)",
            "source_url": INVESCO_QQQ_HOLDINGS_PAGE,
            "source_authority": "official_provider",
            "fallback_used": True,
            "effective_date": None,
            "fallback_dated": STATIC_FULL_FALLBACK_DATED,
            "fallback_reason": str(exc)[:200],
            "total_holdings_reported": None,
            "total_holdings_selected": len(fallback),
            "fund_name": None,
            "constituents": fallback,
            "weight_pct_sum": (
                round(sum(item["weight_pct"] for item in fallback), 6)
                if fallback
                else 0.0
            ),
            "filtered_out_count": 0,
            "filtered_out": [],
        }
