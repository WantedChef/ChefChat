from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Label


class MinimalApp(App):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("If you can see this, Textual works!", id="lbl")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Label).update("Environment confirmed valid.")


if __name__ == "__main__":
    app = MinimalApp()
    app.run()
