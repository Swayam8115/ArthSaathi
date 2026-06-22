"""
Project-wide constants: nudge types, persona types, supported languages.
"""

# Nudge types sent to users
NUDGE_TYPES = [
    "savings_nudge",
    "loan_warning",
    "scheme_alert",
    "investment_nudge",
    "tax_saving_nudge",
]

# Persona types derived from user self-reporting
PERSONA_TYPES = ["salaried", "gig", "farmer", "freelancer"]

# Supported language codes (BCP-47) mapped to display names
SUPPORTED_LANGUAGES: dict[str, str] = {
    "hi": "Hindi",
    "mr": "Marathi",
    "kn": "Kannada",
    "en": "English",
    "te": "Telugu",
    "ta": "Tamil",
    "bn": "Bengali",
}

# Responsible AI disclaimer appended to every nudge
NUDGE_DISCLAIMER = "Yeh sirf jaankari hai, koi financial advice nahi."

# Human escalation message shown on distress-signal detection
ESCALATION_MESSAGE = (
    "Lagta hai aap mushkil mein hain. "
    "Kisi se baat karo — iCall helpline: 9152987821"
)

# Days of inactivity before triggering a no-savings pattern flag
NO_SAVINGS_THRESHOLD_DAYS = 30

# Seekho levels (tracks user's financial micro-learning progress)
MAX_SEEKHO_LEVEL = 10
