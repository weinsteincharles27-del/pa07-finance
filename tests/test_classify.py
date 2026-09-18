"""classify.py against the real descriptions these committees filed."""
import support

C = support.load("classify")

SPENDING_CASES = {
    "TELEVISION ADVERTISING": "Television advertising",
    "DIGITAL ADVERTISING": "Digital advertising",
    "DIGITAL CONSULTING SERVICES": "Digital advertising",
    "TEXT MESSAGE ADVERTISING": "Digital advertising",
    "DIGITAL FUNDRAISING CONSULTING": "Fundraising",   # fundraising beats digital
    "FUNDRAISING COMMISSION": "Fundraising",
    "FUNDRIAISNG CONSULTING/COMMISSION": "Fundraising",   # as filed, typo and all
    "DIRECT MAIL FUNDRAISING": "Fundraising",
    "DIRECT MAIL FUNDRAISING POSTAGE": "Fundraising",
    "LIST ACQUISITION": "Fundraising",
    "FUNDRAISING EVENT- FOOD AND BEVERAGE": "Fundraising",
    "FUNDRAISING COMMISSION AND FUNDRAISING EVENT": "Fundraising",   # commission first
    "FUNDRAISING COMMISSION/FUNDRAISING EVENTS/REIMBURSEMENT": "Fundraising",
    "FUNDRAISER EVENT INVITES AND POSTAGE": "Fundraising",
    "CREDIT CARD PROCESSING FEES": "Fundraising",
    "PROCESSING FEE": "Fundraising",
    "SUPPORTER APPRECIATION GIFTS": "Fundraising",
    "FUNDRAISING CONSULTING": "Fundraising",
    "FUNDRAISING EXPENSE": "Fundraising",
    "DIRECT MAIL": "Mail and printing",
    "PRINT ADVERTISEMENT": "Print and radio advertising",
    "CAMPAIGN LITERATURE": "Mail and printing",
    "PRINTING": "Mail and printing",
    "INVITATIONS AND POSTAGE": "Mail and printing",
    "PAYROLL": "Staff and payroll",
    "PAYROLL TAX": "Staff and payroll",
    "RESEARCH": "Polling and research",
    "RESEARCH SERVICES": "Polling and research",
    "VOTER FILE": "Polling and research",
    "VOTER DATA SOFTWARE": "Polling and research",
    "FIELD CONSULTING SERVICES": "Field, phones and texting",   # field beats consulting
    "FIELD SERVICES": "Field, phones and texting",
    "TEXT MESSAGING SERVICES": "Field, phones and texting",
    "PETITIONING SERVICES": "Field, phones and texting",
    "GENERAL CAMPAIGN CONSULTING": "Consulting",
    "MANAGEMENT CONSULTING": "Consulting",
    "STRATEGIC CONSULTING SERVICES": "Consulting",
    "COMMUNICATIONS CONSULTING": "Consulting",
    "MEDIA PRODUCTION": "Media production",
    "VIDEO PRODUCTION": "Media production",
    "PHOTOSHOOT": "Media production",
    "YARD SIGNS": "Signs and merchandise",
    "CAMPAIGN LOGO T-SHIRTS": "Signs and merchandise",
    "CAMPAIGN STICKERS": "Signs and merchandise",
    "TRAVEL-FLIGHT": "Travel",
    "LODGING": "Travel",
    "MILEAGE REIMBURSEMENT": "Travel",
    "CAMPAIGN EVENT- FOOD AND BEVERAGE": "Events and meals",
    "PARADE CANDY": "Events and meals",
    "ELECTION NIGHT EVENT": "Events and meals",
    "CONFERENCE FEES": "Events and meals",
    "NON-FEDERAL CONTRIBUTION": "Contributions and donations",
    "DONATION": "Contributions and donations",
    "REFUND": "Refunds",
    "REFUND: REFUND OF EXCESS CONTRIBUTION": "Refunds",       # refund beats contribution
    "OFFICE RENT": "Office and administrative",
    "CAMPAIGN OFFICE TV SUBSCRIPTION": "Office and administrative",   # not television advertising
    "COMPLIANCE SERVICES": "Office and administrative",
    "ACCOUNTING AND COMPLIANCE SERVICE": "Office and administrative",
    "DATABASE SERVICES": "Office and administrative",
    "IN KIND : TECHNOLOGY SERVICES": "Office and administrative",
    "BANK FEES": "Office and administrative",
    "WEBSITE HOSTING SERVICE": "Office and administrative",
    "E-MAIL SERVICE": "Office and administrative",                # not mail
    "LEGAL SERVICES": "Office and administrative",
    "REIMBURSEMENT - SEE BELOW": "Other",
    "": "Other",
    None: "Other",
}

OUTSIDE_CASES = {
    "AD BUY": "Television and media buys",
    "AD BUY (ESTIMATE)": "Television and media buys",
    "MEDIA PLACEMENT / MEDIA PRODUCTION": "Television and media buys",
    "MEDIA PLACEMENT": "Television and media buys",
    "MEDIA BUY AND AD SERVICING": "Television and media buys",
    "AD BUY & AD PRODUCTION": "Television and media buys",
    "DIGITAL BUY": "Digital advertising",
    "DIGITAL AD BUY - ESTIMATE": "Digital advertising",
    "DIGITAL ADVERTISING - NON-CONTRIBUTION ACCOUNT": "Digital advertising",
    "DIGITAL AD PRODUCTION - ACTUAL AMOUNT OF ESTIMATE PREVIOUSLY REPORTED": "Digital advertising",
    "STREAMING AND YOUTUBE": "Digital advertising",
    "PRINTING  / POSTAGE": "Mail and print",
    "VOTER MAIL CONTACT": "Mail and print",
    "DIRECT MAIL PRODUCTION - NON-CONTRIBUTION ACCOUNT": "Mail and print",   # mail beats production
    "TEXTING": "Texting and phone calls",
    "TEXT MESSAGES": "Texting and phone calls",
    "SMS TEXTING": "Texting and phone calls",
    "MESSAGE PHONE CALLS": "Texting and phone calls",
    "CANVASSING SERVICES  (CORRESPONDING MEMO ON 24/48 CAN NOT BE DELETED I": "Canvassing and field",
    "STAFF TIME FOR VOTER COMMUNICATIONS": "Canvassing and field",
    "DOOR LITERATURE": "Mail and print",                       # literature is mail, checked first
    "AD PRODUCTION": "Production",
    "MEDIA PRODUCTION - NON-CONTRIBUTION ACCOUNT": "Production",
    "RADIO AD": "Radio",
    "VOTER DATA": "Data",
    "EMAIL MESSAGING": "Email",
    "FOOD FOR CANVASSERS": "Canvassing and field",
}


def test_spending_descriptions_as_filed():
    bad = {d: (C.spending(d), want) for d, want in SPENDING_CASES.items() if C.spending(d) != want}
    assert not bad, bad


def test_outside_descriptions_as_filed():
    bad = {d: (C.outside(d), want) for d, want in OUTSIDE_CASES.items() if C.outside(d) != want}
    assert not bad, bad


def test_every_rule_label_is_in_the_display_order():
    assert set(l for l, _ in C.SPENDING) | {"Other"} == set(C.SPENDING_ORDER)
    assert set(l for l, _ in C.OUTSIDE) | {"Other"} == set(C.OUTSIDE_ORDER)


def test_other_is_small_on_the_real_data():
    """If the rules ever drift, this is the alarm: Other must stay a sliver."""
    fec = support.fixture("fec_detail.json") if support.has_fixture("fec_detail.json") else None
    if not fec:
        return
    for cid, c in fec["committees"].items():
        cats = {r["category"]: r["amount"] for r in c["spending"]["by_category"]}
        total = sum(cats.values())
        assert cats.get("Other", 0) / total < 0.02, (cid, cats.get("Other"), total)
