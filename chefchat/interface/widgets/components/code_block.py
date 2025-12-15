"""CodeBlock Widget - Syntax-highlighted code display component.

Extracted from ThePlate for reusability across the TUI.
"""

from __future__ import annotations

from rich.console import RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from textual.widgets import Static


class CodeBlock(Static):
    """A syntax-highlighted code block widget.

    Displays source code with syntax highlighting, optional line numbers,
    and an optional title. Can be used standalone or within containers.

    Usage:
        ```python
        block = CodeBlock(
            code="def hello(): pass",
            language="python",
            title="hello.py"
        )
        ```
    """

    DEFAULT_CSS = """
    CodeBlock {
        padding: 0;
        margin: 0;
    }
    """

    def __init__(
        self,
        code: str,
        language: str = "python",
        title: str | None = None,
        theme: str = "github-dark",
        line_numbers: bool = True,
        word_wrap: bool = True,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize a code block.

        Args:
            code: The source code to display
            language: Programming language for syntax highlighting
            title: Optional title for the code block
            theme: Syntax theme (default: github-dark)
            line_numbers: Show line numbers (default: True)
            word_wrap: Wrap long lines (default: True)
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self._code = code
        self._language = language
        self._title = title
        self._theme = theme
        self._line_numbers = line_numbers
        self._word_wrap = word_wrap

    @property
    def code(self) -> str:
        """Get the current code content."""
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        """Set the code content and refresh display."""
        self._code = value
        self.refresh()

    @property
    def language(self) -> str:
        """Get the current language."""
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        """Set the language and refresh display."""
        self._language = value
        self.refresh()

    @property
    def title(self) -> str | None:
        """Get the title."""
        return self._title

    @title.setter
    def title(self, value: str | None) -> None:
        """Set the title and refresh display."""
        self._title = value
        self.refresh()

    def render(self) -> RenderableType:
        """Render the syntax-highlighted code."""
        syntax = Syntax(
            self._code,
            self._language,
            theme=self._theme,
            line_numbers=self._line_numbers,
            word_wrap=self._word_wrap,
            background_color="#0d1117",
        )

        if self._title:
            return Panel(
                syntax, title=self._title, title_align="left", border_style="dim"
            )
        return syntax

    def update_code(self, code: str, language: str | None = None) -> None:
        """Update the code content and optionally the language.

        Args:
            code: New code content
            language: Optional new language
        """
        self._code = code
        if language:
            self._language = language
        self.refresh()
