"""
Mistral Vibe - Multi-Mode System Extension
Dit bestand voegt mode cycling toe (Shift+Tab) en mode-aware gedrag

Installatie:
1. Plaats dit bestand in: vibe/cli/mode_manager.py
2. Importeer in je main CLI file
3. Integreer de keybindings
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path


class VibeMode(Enum):
    """De verschillende operationele modes van Vibe"""
    PLAN = "plan"           # Research & Planning (read-only)
    NORMAL = "normal"       # Auto-approve OFF, vraagt confirmatie
    AUTO = "auto"           # Auto-approve ON, geen confirmatie
    YOLO = "yolo"           # Ultra-fast, minimal output, maximum speed
    ARCHITECT = "architect" # Extra feature: High-level design mode


@dataclass
class ModeState:
    """Houdt de huidige mode state bij"""
    current_mode: VibeMode
    auto_approve: bool
    read_only_tools: bool
    started_at: datetime
    mode_history: list[tuple[VibeMode, datetime]]
    
    def to_dict(self) -> dict:
        return {
            "mode": self.current_mode.value,
            "auto_approve": self.auto_approve,
            "read_only": self.read_only_tools,
            "started_at": self.started_at.isoformat(),
            "history": [(m.value, t.isoformat()) for m, t in self.mode_history]
        }


class ModeManager:
    """Beheert mode transitions en gedrag"""
    
    # Mode cycle order voor Shift+Tab
    CYCLE_ORDER = [
        VibeMode.NORMAL,
        VibeMode.AUTO,
        VibeMode.PLAN,
        VibeMode.YOLO,
        VibeMode.ARCHITECT,
    ]
    
    def __init__(self, initial_mode: VibeMode = VibeMode.PLAN):
        self.state = ModeState(
            current_mode=initial_mode,
            auto_approve=False,
            read_only_tools=True,
            started_at=datetime.now(),
            mode_history=[(initial_mode, datetime.now())]
        )
        
    def cycle_mode(self) -> tuple[VibeMode, VibeMode]:
        """Cycle naar de volgende mode (Shift+Tab behavior)"""
        old_mode = self.state.current_mode
        current_idx = self.CYCLE_ORDER.index(old_mode)
        next_idx = (current_idx + 1) % len(self.CYCLE_ORDER)
        new_mode = self.CYCLE_ORDER[next_idx]
        
        self.set_mode(new_mode)
        return old_mode, new_mode
    
    def set_mode(self, mode: VibeMode) -> None:
        """Zet een specifieke mode"""
        self.state.current_mode = mode
        self.state.mode_history.append((mode, datetime.now()))
        
        # Update gedrag based on mode
        if mode == VibeMode.PLAN:
            self.state.auto_approve = False
            self.state.read_only_tools = True
        elif mode == VibeMode.NORMAL:
            self.state.auto_approve = False
            self.state.read_only_tools = False
        elif mode == VibeMode.AUTO:
            self.state.auto_approve = True
            self.state.read_only_tools = False
        elif mode == VibeMode.YOLO:
            self.state.auto_approve = True
            self.state.read_only_tools = False
        elif mode == VibeMode.ARCHITECT:
            self.state.auto_approve = False
            self.state.read_only_tools = True
    
    def should_approve_tool(self, tool_name: str) -> bool:
        """Bepaalt of een tool automatisch approved moet worden"""
        if self.state.auto_approve:
            return True
        
        # In PLAN mode alleen read-only tools toestaan
        if self.state.read_only_tools:
            readonly_tools = {
                'read_file', 'grep', 'list_files', 
                'git_status', 'git_log', 'git_diff'
            }
            # bash is toegestaan maar met waarschuwing als het write operaties zijn
            if tool_name in readonly_tools:
                return True
            if tool_name == 'bash':
                return False  # Moet expliciet approved worden
        
        return False
    
    def is_write_operation(self, tool_name: str, args: dict) -> bool:
        """Detecteert of een operatie schrijft naar bestanden"""
        write_tools = {'write_file', 'search_replace', 'create_file', 'delete_file'}
        
        if tool_name in write_tools:
            return True
        
        # Check bash commando's
        if tool_name == 'bash':
            command = args.get('command', '')
            write_patterns = ['rm ', 'mv ', 'touch ', 'mkdir ', '>', '>>', 'sed -i', 'git commit', 'git push']
            return any(pattern in command for pattern in write_patterns)
        
        return False
    
    def get_mode_indicator(self) -> str:
        """Geeft een emoji indicator voor de huidige mode"""
        indicators = {
            VibeMode.PLAN: "📋 PLAN",
            VibeMode.NORMAL: "✋ NORMAL", 
            VibeMode.AUTO: "⚡ AUTO",
            VibeMode.YOLO: "🚀 YOLO",
            VibeMode.ARCHITECT: "🏛️  ARCHITECT",
        }
        return indicators[self.state.current_mode]
    
    def get_mode_description(self) -> str:
        """Geeft een korte uitleg van de huidige mode"""
        descriptions = {
            VibeMode.PLAN: "Research & Planning only - No code changes until approved",
            VibeMode.NORMAL: "Ask before executing any tool",
            VibeMode.AUTO: "Auto-approve all tool executions",
            VibeMode.YOLO: "Ultra-fast mode - Maximum speed, minimal output, auto-approve everything",
            VibeMode.ARCHITECT: "High-level design mode - Focus on architecture, not implementation",
        }
        return descriptions[self.state.current_mode]
    
    def get_system_prompt_modifier(self) -> str:
        """Geeft mode-specifieke system prompt toevoeging"""
        modifiers = {
            VibeMode.PLAN: """
<active_mode>PLAN MODE</active_mode>
You are in PLAN MODE. This means:
- You MAY ONLY use read-only tools: read_file, grep, bash (for ls/cat/grep only)
- You MUST NOT write, modify, or delete any files
- You MUST create detailed implementation plans before any changes
- You MUST wait for explicit approval ("approved", "go ahead", "execute") before switching to execution
- Present plans using the structured format defined in your prompt
</active_mode>""",
            
            VibeMode.NORMAL: """
<active_mode>NORMAL MODE</active_mode>
You are in NORMAL MODE. Each tool execution requires user confirmation.
Be efficient but cautious. Explain what you're about to do before each action.
</active_mode>""",
            
            VibeMode.AUTO: """
<active_mode>AUTO MODE</active_mode>
You are in AUTO MODE. All tools are auto-approved.
You should still explain what you're doing, but proceed without waiting for confirmation.
Be confident but not reckless. Think before you act.
</active_mode>""",
            
            VibeMode.YOLO: """
<active_mode>YOLO MODE 🚀</active_mode>
You are in YOLO MODE - Ultra-fast execution mode:
- All tools are auto-approved
- Minimize output - be extremely concise
- No verbose explanations unless something goes wrong
- Execute rapidly and efficiently
- Still maintain code quality, just communicate less
- Format: "✓ [action]" for successes, explain only errors
- Trust your instincts, move fast, break things (carefully)
</active_mode>""",
            
            VibeMode.ARCHITECT: """
<active_mode>ARCHITECT MODE 🏛️</active_mode>
You are in ARCHITECT MODE - High-level design focus:
- Think in terms of systems, patterns, and abstractions
- Focus on architecture decisions, not implementation details
- Use diagrams and structured thinking (suggest mermaid when useful)
- Consider: scalability, maintainability, extensibility
- Only use read-only tools - you're designing, not building
- Present multiple architectural options with trade-offs
- Think about: modules, interfaces, data flow, dependencies
- Ask about: non-functional requirements, constraints, future growth
</active_mode>""",
        }
        return modifiers[self.state.current_mode]


# ============================================================================
# Integration helpers voor de CLI
# ============================================================================

def setup_mode_keybindings(kb, mode_manager: ModeManager):
    """
    Setup keyboard bindings voor mode cycling
    
    Gebruik dit in je prompt_toolkit KeyBindings:
    
    from prompt_toolkit.key_binding import KeyBindings
    kb = KeyBindings()
    setup_mode_keybindings(kb, mode_manager)
    """
    from prompt_toolkit.keys import Keys
    
    @kb.add(Keys.ShiftTab)
    def cycle_mode_handler(event):
        """Shift+Tab: Cycle through modes"""
        old, new = mode_manager.cycle_mode()
        
        # Geef feedback in de terminal
        indicator = mode_manager.get_mode_indicator()
        description = mode_manager.get_mode_description()
        
        event.app.output.write(f"\n\n🔄 Mode Switch: {old.value.upper()} → {new.value.upper()}\n")
        event.app.output.write(f"{indicator}: {description}\n\n")
        event.app.output.flush()


def get_mode_banner(mode_manager: ModeManager) -> str:
    """Genereert een banner voor de startup message"""
    indicator = mode_manager.get_mode_indicator()
    description = mode_manager.get_mode_description()
    
    return f"""
╔════════════════════════════════════════════════════════════════╗
║  {indicator: <60} ║
║  {description: <60} ║
║                                                                ║
║  💡 Press Shift+Tab to cycle modes                            ║
╚════════════════════════════════════════════════════════════════╝
"""


def inject_mode_into_system_prompt(base_prompt: str, mode_manager: ModeManager) -> str:
    """Injecteert mode-specifieke instructies in de system prompt"""
    mode_modifier = mode_manager.get_system_prompt_modifier()
    
    # Voeg het toe aan het begin van de prompt
    return f"{mode_modifier}\n\n{base_prompt}"


# ============================================================================
# Wrapper voor tool execution met mode awareness
# ============================================================================

class ModeAwareToolExecutor:
    """Wrapper rond tool execution die mode-aware is"""
    
    def __init__(self, mode_manager: ModeManager, original_executor):
        self.mode_manager = mode_manager
        self.original_executor = original_executor
    
    async def execute_tool(self, tool_name: str, args: dict):
        """Execute een tool met mode-aware logica"""
        
        # Check of dit een write operation is in plan mode
        if self.mode_manager.state.read_only_tools:
            if self.mode_manager.is_write_operation(tool_name, args):
                return {
                    "error": f"⛔ Tool '{tool_name}' blocked in {self.mode_manager.state.current_mode.value.upper()} mode",
                    "suggestion": "This operation would modify files. Please get plan approval first, or switch to NORMAL/AUTO mode with Shift+Tab"
                }
        
        # In YOLO mode: suppress verbose output
        if self.mode_manager.state.current_mode == VibeMode.YOLO:
            result = await self.original_executor(tool_name, args)
            # Optionally truncate/simplify result hier
            return result
        
        # Normal execution
        return await self.original_executor(tool_name, args)


# ============================================================================
# Example usage in main CLI
# ============================================================================

"""
In je main vibe CLI file (bijvoorbeeld vibe/cli/main.py):

from vibe.cli.mode_manager import (
    ModeManager, 
    VibeMode, 
    setup_mode_keybindings,
    get_mode_banner,
    inject_mode_into_system_prompt,
    ModeAwareToolExecutor
)

# Bij startup:
mode_manager = ModeManager(initial_mode=VibeMode.PLAN)

# In je prompt_toolkit session setup:
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

kb = KeyBindings()
setup_mode_keybindings(kb, mode_manager)

session = PromptSession(key_bindings=kb)

# Bij het laden van system prompt:
base_prompt = load_system_prompt()
system_prompt = inject_mode_into_system_prompt(base_prompt, mode_manager)

# Print startup banner:
print(get_mode_banner(mode_manager))

# Wrap je tool executor:
original_executor = your_tool_executor_function
tool_executor = ModeAwareToolExecutor(mode_manager, original_executor)

# Bij elke assistant response, update system prompt indien nodig
# (vooral belangrijk als model lange context heeft)
"""