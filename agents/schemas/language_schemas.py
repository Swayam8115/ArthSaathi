from typing import Literal
from pydantic import BaseModel


class LanguageDetectionResponse(BaseModel):
    language_code: Literal["hi", "mr", "kn", "en", "te", "ta", "bn"]


class LanguageAndTranslationResponse(BaseModel):
    language_code: Literal["hi", "mr", "kn", "en", "te", "ta", "bn"]
    english_text: str
