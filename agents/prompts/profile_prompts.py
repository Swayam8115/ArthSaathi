"""
Prompts for the Profile Agent.
"""

EXTRACT_FINANCIAL_EVENTS = """\
You are a financial data extraction assistant for an Indian personal finance app.

Analyse the user message below and extract all financial events mentioned.
Return a JSON array. Each element must have exactly these fields:

  event_type  : one of "income", "expense", "loan", "savings", "query"
  amount      : number (rupees) or null if no amount mentioned
  description : short English description of the event (max 10 words)

Rules:
- One event per distinct financial action. A single message may have multiple events.
- If the message is a general question about finance (e.g. "What is SIP?"), use event_type "query" with amount null.
- Salary, wages, freelance payment, crop sale, gig earning → "income"
- Any spending, bill, purchase, EMI payment made → "expense"
- Taking a loan, mentioning borrowing → "loan"
- Putting money aside, saving, RD/SIP deposit → "savings"
- Return an empty array [] if no financial event is present.

User message (English):
{message}

Return ONLY the JSON array. No explanation.
"""

INFER_PERSONA = """\
Based on the user message below, infer the user's financial persona.
Return a JSON object with one field:

  persona_type : one of "salaried", "gig", "farmer", "freelancer", or null

Rules:
- "salaried"   : mentions salary, office job, company, payslip
- "gig"        : mentions delivery, ride, Swiggy, Zomato, Ola, Uber, daily wages, thela
- "farmer"     : mentions fasal, crop, khet, kisan, harvest, mandi, PM-KISAN
- "freelancer" : mentions client, project, invoice, freelance, design, coding work
- null         : cannot determine from this message alone

User message (English):
{message}

Return ONLY the JSON object. No explanation.
"""
