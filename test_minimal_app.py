
import sys
from textual.app import App, ComposeResult
from textual.widgets import Label, Button

class MinimalApp(App):
    def compose(self) -> ComposeResult:
        print("DEBUG: MinimalApp.compose", flush=True)
        yield Label("Hello World")
        yield Button("Quit", id="quit")

    def on_mount(self) -> None:
        print("DEBUG: MinimalApp.on_mount", flush=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.exit()

if __name__ == "__main__":
    print("Starting MinimalApp...", flush=True)
    print(f"DEBUG: isatty: {sys.stdout.isatty()}", flush=True)
    try:
        app = MinimalApp()
        app.run()
        print("MinimalApp finished.", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)
