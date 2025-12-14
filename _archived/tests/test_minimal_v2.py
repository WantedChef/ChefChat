from textual.app import App, ComposeResult
from textual.widgets import Label
import sys

class MinimalApp(App):
    def compose(self) -> ComposeResult:
        print("DEBUG: MinimalApp.compose", file=sys.stderr)
        yield Label("Hello")

    def on_mount(self) -> None:
        print("DEBUG: MinimalApp.on_mount", file=sys.stderr)
        self.exit()

if __name__ == "__main__":
    print("DEBUG: Starting run", file=sys.stderr)
    MinimalApp().run()
    print("DEBUG: Finished run", file=sys.stderr)
