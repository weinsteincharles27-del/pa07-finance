#!/usr/bin/env python3
"""Put a free-text FEC description into a standard category.

The FEC's own disbursement_purpose_category files 55 to 69 percent of these
two campaigns' spending as OTHER, because it only recognises a handful of
words. Campaigns describe their spending clearly enough ("TELEVISION
ADVERTISING", "FUNDRAISING COMMISSION", "YARD SIGNS") that ordered keyword
rules sort almost everything. Order matters: "DIGITAL FUNDRAISING CONSULTING"
is fundraising, not digital advertising, and "FIELD CONSULTING" is field, not
consulting, so the more specific rule comes first.

Every rule was written against the real descriptions in sources/ and is pinned
by tests/test_classify.py. A description that matches nothing is "Other".
"""

# ------------------------------------------------ campaign spending (Schedule B)

SPENDING = [
    ("Refunds",                    ("REFUND",)),
    ("Fundraising",                ("FUNDRAIS", "FUNDRIAISNG", "PROCESSING FEE", "CREDIT CARD", "DONOR",
                                    "SUPPORTER APPRECIATION", "APPRECIATION GIFT", "LIST ACQUISITION",
                                    "RAFFLE")),
    ("Television advertising",     ("TELEVISION", "TV AD", "TV BUY")),
    ("Digital advertising",        ("DIGITAL", "ONLINE AD", "TEXT MESSAGE ADVERTISING", "WEB AD")),
    ("Media production",           ("MEDIA PRODUCTION", "VIDEO", "PHOTO", "AD PRODUCTION")),
    ("Polling and research",       ("RESEARCH", "POLL", "VOTER DATA", "VOTER FILE", "SURVEY")),
    ("Staff and payroll",          ("PAYROLL", "SALARY", "STIPEND", "INCOME TAX", "HEALTH INSURANCE")),
    ("Field, phones and texting",  ("FIELD", "CANVASS", "PETITION", "PHONE BANK", "TEXT BANK",
                                    "TEXT MESSAGING", "TEXTING", "TEXT MESSAGES", "SMS")),
    # Email tooling is office spend, and "EMAIL" contains "MAIL", so it goes first.
    ("Office and administrative",  ("E-MAIL", "EMAIL")),
    ("Print and mail",             ("DIRECT MAIL", "LITERATURE", "PRINT AD", "PRINTING", "POSTAGE",
                                    "INVITATION", "ENVELOPE", "SHIPPING", "MAIL", "CHRISTMAS CARD")),
    ("Consulting",                 ("CONSULTING", "STRATEGY", "STRATEGIC")),
    ("Signs and merchandise",      ("SIGN", "STICKER", "SHIRT", "JACKET", "MAGNET", "APPAREL", "FLAG",
                                    "BANNER", "LOGO", "MERCHANDISE")),
    ("Travel",                     ("TRAVEL", "LODGING", "TRANSPORTATION", "MILEAGE", "AIRFARE",
                                    "FLIGHT", "FUEL", "HOTEL")),
    ("Events and meals",           ("EVENT", "FOOD", "CATERING", "BEVERAGE", "PARADE", "CANDY",
                                    "CONFERENCE", "TICKET", "SPONSORSHIP", "REGISTRATION", "PARTY",
                                    "GIFT", "MEAL")),
    ("Contributions and donations", ("CONTRIBUTION", "CONTRIBTUION", "DONATION")),
    ("Office and administrative",  ("RENT", "OFFICE", "SUPPLIES", "SOFTWARE", "DATABASE", "COMPLIANCE",
                                    "ACCOUNTING", "LEGAL", "BANK", "SUBSCRIPTION", "WEBSITE",
                                    "TELECOM", "INTERNET", "EQUIPMENT", "TECHNOLOGY", "PHONE",
                                    "ZOOM", "FIXTURE", "INSURANCE", "SECURITY")),
]

# ------------------------------------------------ outside spending (Schedule E)

OUTSIDE = [
    ("Digital advertising",        ("DIGITAL", "ONLINE", "STREAMING", "YOUTUBE", "FACEBOOK", "META ")),
    ("Radio",                      ("RADIO",)),
    ("Texting and phone calls",    ("TEXT", "SMS", "PHONE CALL", "PHONE BANK", "ROBOCALL")),
    ("Email",                      ("EMAIL", "E-MAIL")),
    ("Mail and print",             ("MAIL", "PRINTING", "POSTAGE", "LITERATURE", "FLYER")),
    ("Canvassing and field",       ("CANVASS", "STAFF TIME", "VOTER COMMUNICATION", "DOOR", "FIELD")),
    ("Television and media buys",  ("AD BUY", "MEDIA PLACEMENT", "MEDIA BUY", "TELEVISION", "TV ",
                                    "BROADCAST", "CABLE", "AD SERVICING")),
    ("Production",                 ("PRODUCTION",)),
    ("Data",                       ("DATA",)),
]


def _match(text, rules):
    t = (text or "").upper()
    for label, needles in rules:
        for n in needles:
            if n in t:
                return label
    return "Other"


def spending(description):
    """Category for one Schedule B disbursement description."""
    return _match(description, SPENDING)


def outside(description):
    """Category for one Schedule E expenditure description."""
    return _match(description, OUTSIDE)


def _order(rules):
    out = []
    for label, _ in rules:
        if label not in out:
            out.append(label)
    return out + ["Other"]


SPENDING_ORDER = _order(SPENDING)
OUTSIDE_ORDER = _order(OUTSIDE)
