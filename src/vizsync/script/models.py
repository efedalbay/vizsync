"""Plain data for a parsed script."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TextMode(StrEnum):
    """Which text of a paragraph is aligned against the audio."""

    QUOTE = "quote"
    INLINE = "inline"


class ChartTag(BaseModel):
    """A ``<!-- chart: ID -->`` tag under a paragraph: the vizreel chart this paragraph is part of.

    ``sequence`` is True for ``<!-- chart: ID, sequence -->``. ``line`` is where the tag is.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    sequence: bool = False
    line: int


class Paragraph(BaseModel):
    """One numbered paragraph. ``text`` is the cleaned text used for alignment.

    ``pause_after`` is the seconds of silence a ``<!-- pause: SECONDS -->`` tag asks for after this
    paragraph when the paragraph files are joined, or None.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    number: int
    line: int
    text: str
    charts: list[ChartTag] = []
    pause_after: float | None = None


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
