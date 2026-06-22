DETECT_LANGUAGE = """\
Identify the language of the following text.
Reply with ONLY the BCP-47 language code from this list: {codes}.
If the text is a mix of languages (code-switching), return the dominant one.
If you cannot determine the language, return "hi" as the default.

Text:
{text}
"""

TRANSLATE_TO_ENGLISH = """\
Translate the following message to English.
Preserve the exact meaning, especially financial figures, amounts, and terms.
Do not add explanations. Return only the translated text.

Original ({lang_name}):
{text}
"""

TRANSLATE_TO_USER_LANG = """\
Translate the following message to {lang_name}.
The audience is a regular person who uses WhatsApp.
Keep the tone warm, simple, and conversational.
Preserve all currency amounts and numbers exactly.
Do not add explanations. Return only the translated text.

English message:
{text}
"""
