"""Plain data for a parsed script."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TextMode(StrEnum):
    """Which text of a paragraph is aligned against the audio."""

    QUOTE = "quote"
    INLINE = "inline"


class Paragraph(BaseModel):
    """One numbered paragraph. ``text`` is the cleaned text used for alignment."""

    model_config = ConfigDict(frozen=True)

    id: str
    number: int
    line: int
    text: str


class Chapter(BaseModel):
    """A chapter and the paragraphs under its heading, in script order."""

    model_config = ConfigDict(frozen=True)

    title: str
    paragraphs: list[Paragraph]


class Script(BaseModel):
    """A parsed script: chapters in order, each with at least one paragraph."""

    model_config = ConfigDict(frozen=True)

    chapters: list[Chapter]

    @property
    def paragraphs(self) -> list[Paragraph]:
        """All paragraphs in script order."""
        return [paragraph for chapter in self.chapters for paragraph in chapter.paragraphs]
