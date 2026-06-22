DETECT_AND_TRANSLATE = """\
Detect the language of the following text and translate it to English in one step.

Supported language codes: {codes}

Rules:
- language_code: BCP-47 code from the supported list above; if mixed languages use the dominant one
- english_text: translate to English preserving all financial figures, amounts, and numbers exactly;
  if the text is already in English return it unchanged

Text: "{text}"

Return ONLY the JSON object.
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
