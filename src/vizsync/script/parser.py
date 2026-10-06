"""Markdown script parser. Collects every problem before it fails."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from vizsync.errors import ScriptError, ScriptParseError, ScriptProblem
from vizsync.script.models import Chapter, Paragraph, Script, TextMode

_IDENTIFIER = r"(?:(?P<mark>\*\*|__|\*)[Pp](?P<marked>\d+)(?P=mark)|[Pp](?P<plain>\d+))"
_PARAGRAPH_LINE = re.compile(rf"^{_IDENTIFIER}[ \t]*[—–\-:.][ \t]*(?P<text>.*)$")
_MISSING_SEPARATOR = re.compile(rf"^{_IDENTIFIER}(?:\s|$)")
_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_QUOTE_LINE = re.compile(r"^>[ \t]?(.*)$")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_LEADING_NUMBER = re.compile(r"^\d+\.(?:\s+|$)")
_TITLE_SEPARATOR = " / "
_INTRO_TITLE = "Intro"

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CITATION = re.compile(r"\[\d+\]")
_EMPHASIS = re.compile(r"[*_`]")


def clean_text(text: str) -> str:
    """Remove HTML comments, citation markers and emphasis characters, then collapse whitespace."""
    text = _HTML_COMMENT.sub("", text)
    text = _CITATION.sub("", text)
    text = _EMPHASIS.sub("", text)
    return " ".join(text.split())


def parse_script(text: str, mode: TextMode = TextMode.QUOTE, *, path: Path | None = None) -> Script:
    """Parse script text into chapters and paragraphs.

    Args:
        text: The whole script.
        mode: Which text of each paragraph is aligned.
        path: The script file, used only to name it in error messages.

    Raises:
        ScriptParseError: If the script has any problem. All problems are reported together.
    """
    parser = _Parser(mode)
    lines = _LINE_BREAK.split(text.removeprefix("﻿"))
    for number, line in enumerate(lines, start=1):
        parser.feed(number, line)
    return parser.finish(path)


def load_script(path: Path, mode: TextMode = TextMode.QUOTE) -> Script:
    """Read a UTF-8 script file (a byte order mark is accepted) and parse it.

    Raises:
        ScriptError: If the file cannot be read.
        ScriptParseError: If the script has any problem.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ScriptError(f"Script file not found: {path}") from None
    except UnicodeDecodeError:
        raise ScriptError("Script file is not valid UTF-8", path=path) from None
    except OSError as error:
        raise ScriptError(f"Cannot read script file: {error.strerror}", path=path) from None
    return parse_script(text, mode, path=path)


def _number_of(match: re.Match[str]) -> int:
    return int(match.group("marked") or match.group("plain"))


def _chapter_title(heading: str, mode: TextMode) -> str:
    heading = heading.strip()
    if _TITLE_SEPARATOR in heading:
        if mode is TextMode.QUOTE:
            heading = heading.rsplit(_TITLE_SEPARATOR, 1)[1]
        else:
            heading = heading.split(_TITLE_SEPARATOR, 1)[0]
    return _LEADING_NUMBER.sub("", heading.strip())


@dataclass
class _ChapterDraft:
    title: str
    paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass
class _Draft:
    number: int
    line: int
    chapter: _ChapterDraft
    inline_lines: list[str]
    quote_lines: list[str] = field(default_factory=list)
    collecting_inline: bool = True

    @property
    def id(self) -> str:
        return f"P{self.number}"


class _Parser:
    def __init__(self, mode: TextMode) -> None:
        self._mode = mode
        self._problems: list[ScriptProblem] = []
        self._chapters: list[_ChapterDraft] = []
        self._chapter: _ChapterDraft | None = None
        self._draft: _Draft | None = None
        self._first_line_of: dict[int, int] = {}
        self._last_number: int | None = None

    def feed(self, line_number: int, line: str) -> None:
        if match := _PARAGRAPH_LINE.match(line):
            self._start_paragraph(line_number, _number_of(match), match.group("text"))
        elif match := _MISSING_SEPARATOR.match(line):
            self._report_missing_separator(line_number, _number_of(match))
        elif match := _HEADING.match(line):
            self._start_heading(line_number, len(match.group(1)), match.group(2) or "")
        elif match := _QUOTE_LINE.match(line):
            self._add_quote(match.group(1))
        elif not line.strip():
            self._end_inline_text()
        else:
            self._add_text(line)

    def finish(self, path: Path | None) -> Script:
        self._finish_paragraph()
        if not self._first_line_of:
            self._problem(None, "no paragraphs found")
        if self._problems:
            raise ScriptParseError(self._problems, path=path)
        chapters = [Chapter(title=c.title, paragraphs=c.paragraphs) for c in self._chapters]
        return Script(chapters=[chapter for chapter in chapters if chapter.paragraphs])

    def _problem(self, line: int | None, message: str) -> None:
        self._problems.append(ScriptProblem(line, message))

    def _start_paragraph(self, line_number: int, number: int, first_text: str) -> None:
        self._finish_paragraph()
        self._check_number(line_number, number)
        if self._chapter is None:
            self._chapter = self._new_chapter(_INTRO_TITLE)
        self._draft = _Draft(number, line_number, self._chapter, [first_text])

    def _check_number(self, line_number: int, number: int) -> None:
        if number in self._first_line_of:
            first = self._first_line_of[number]
            self._problem(line_number, f"P{number} is repeated (first at line {first})")
        else:
            self._first_line_of[number] = line_number
            if self._last_number is not None and number < self._last_number:
                self._problem(
                    line_number,
                    f"P{number} comes after P{self._last_number} but numbers must increase",
                )
        self._last_number = number

    def _report_missing_separator(self, line_number: int, number: int) -> None:
        self._finish_paragraph()
        self._problem(
            line_number,
            f"P{number} is missing a separator after the identifier "
            "(use '-', ':', '.', an en dash or an em dash)",
        )

    def _start_heading(self, line_number: int, level: int, heading: str) -> None:
        self._finish_paragraph()
        if level not in (2, 3):
            return
        title = _chapter_title(heading, self._mode)
        if not title:
            self._problem(line_number, "chapter heading has no title")
        self._chapter = self._new_chapter(title)

    def _new_chapter(self, title: str) -> _ChapterDraft:
        chapter = _ChapterDraft(title)
        self._chapters.append(chapter)
        return chapter

    def _add_quote(self, text: str) -> None:
        if self._draft is not None:
            self._draft.quote_lines.append(text)
            self._draft.collecting_inline = False

    def _end_inline_text(self) -> None:
        if self._draft is not None:
            self._draft.collecting_inline = False

    def _add_text(self, line: str) -> None:
        if self._draft is not None and self._draft.collecting_inline:
            self._draft.inline_lines.append(line)

    def _finish_paragraph(self) -> None:
        draft, self._draft = self._draft, None
        if draft is None:
            return
        if self._mode is TextMode.QUOTE:
            if not draft.quote_lines:
                self._problem(draft.line, f"{draft.id} has no blockquote (use --text inline?)")
                return
            raw = " ".join(draft.quote_lines)
        else:
            raw = " ".join(draft.inline_lines)
        text = clean_text(raw)
        if not text:
            self._problem(draft.line, f"{draft.id} has no text to align (empty after cleaning)")
            return
        paragraph = Paragraph(id=draft.id, number=draft.number, line=draft.line, text=text)
        draft.chapter.paragraphs.append(paragraph)
