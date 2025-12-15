"""ChefChat Easter Eggs & Fun Commands 🍳
======================================

Fun interactive commands for ChefChat users inspired by Chef Ramsay's
legendary style mixed with coding wisdom.

Commands:
    /chef - Kitchen status with mode info
    /wisdom - Random cooking/coding wisdom
    /roast - Get roasted by Chef Ramsay
    /modes - Display all modes with descriptions
"""

from __future__ import annotations

from datetime import datetime, timezone
UTC = timezone.utc
import random
from typing import TYPE_CHECKING

# For Python < 3.11 compatibility


if TYPE_CHECKING:
    from chefchat.cli.mode_manager import ModeManager

# Time boundaries for greetings (24-hour format)
_MORNING_START = 5
_AFTERNOON_START = 12
_EVENING_START = 17
_NIGHT_START = 21


# =============================================================================
# CHEF WISDOM - Programming quotes with culinary flair
# =============================================================================

CHEF_WISDOM: tuple[str, ...] = (
    # Classic wisdom
    "🍳 **Mise en place!** Get your code organized before you start cooking features.",
    "🔪 **A sharp knife is safer** — keep your tools updated and your dependencies clean.",
    "🧈 **Low and slow wins the race** — don't rush that refactor, let it simmer.",
    "🍝 **Taste as you go** — test early, test often, test with passion!",
    "🥘 **The secret ingredient is love** — and maybe a few unit tests.",
    # Ramsay-style burns with wisdom
    "🔥 **This spaghetti code is RAWWW!** Time to refactor, you donut!",
    "⚡ **Simple recipes, executed perfectly** — that's what great code looks like.",
    "🍲 **A watched pot never boils** — but an unwatched deployment always fails.",
    "🧅 **Coding is like an onion** — it has layers, and sometimes it makes you cry.",
    "🥄 **Too many cooks spoil the broth** — keep your functions small and focused.",
    # Deep wisdom
    "🌟 **The best dish is the one that gets eaten** — ship it, then iterate!",
    "🍷 **Code drunk, debug sober** — wait, that's not quite right...",
    "🧊 **Cool heads make hot code** — stay calm in production fires.",
    "🍰 **Have your cake and eat it too** — but not your state and mutate it too.",
    "🎂 **Life's too short for bad coffee** and untyped code.",
    # Mode-specific wisdom
    "📋 **PLAN MODE**: Measure twice, `git push` once.",
    "⚡ **AUTO MODE**: Trust yourself, but commit often.",
    "🚀 **YOLO MODE**: Fortune favors the bold... and those with good backups.",
    "🏛️ **ARCHITECT MODE**: Great buildings start with great blueprints.",
    "✋ **NORMAL MODE**: The safe path is sometimes the right path.",
    # Funny ones
    "🍕 **There's no 'I' in 'team'** but there is one in 'spaghetti code'.",
    "🌮 **Tuesday is for tacos** and `git push --force` regrets.",
    "🍔 **Stack overflow answers** are like fast food — convenient but questionable.",
    "🥗 **Eat your vegetables** — and comment your regex.",
    "🍣 **Fresh is best** — rebase early, rebase often.",
)


# =============================================================================
# CHEF ROASTS - Gordon Ramsay style burns for developers
# =============================================================================

CHEF_ROASTS: tuple[str, ...] = (
    # Classic Ramsay
    "🔥 **LOOK AT THIS CODE!** It's so raw, a good compiler would refuse to touch it!",
    "😤 **This function is so long**, it needs its own postal code!",
    "🤦 **You call this error handling?** My nan could catch exceptions better, AND SHE'S DEAD!",
    "💀 **These variable names...** Did you let your cat walk on the keyboard?!",
    "🍝 **This is SPAGHETTI!** And not the good kind from my restaurant!",
    # Technical burns
    "📦 **Your dependencies are older than my mum's recipe book!** UPDATE THEM!",
    "🐛 **This bug has been here so long**, it's basically a feature now!",
    "⏰ **Your code is slower than a snail dipped in molasses!** Profile it, you muppet!",
    "💾 **You call this 'clean code'?** It's dirtier than my kitchen after a dinner rush!",
    "🔄 **DRY! DRY! DRY!** How many times do I have to say it?! DON'T REPEAT YOURSELF!",
    # Encouraging burns
    "🌟 **Okay, that PR wasn't completely terrible.** Maybe there's hope for you yet!",
    "💪 **You're getting better!** Like, statistically, you'd have to be!",
    "🎯 **That was almost competent!** I'm genuinely slightly impressed!",
    "🚀 **FINALLY! Someone who tests their code!** I could kiss you! I won't, but I could!",
    "✨ **Beautiful!** Now do it again, but this time without the memory leak!",
    # Self-aware burns
    "🤖 **I'm an AI pretending to be Gordon Ramsay** — what's YOUR excuse for this code?!",
    "📚 **Have you considered reading the documentation?** It's free! F-R-E-E!",
    "☕ **Step away from the keyboard**, get some coffee, and THINK!",
    "🎪 **This codebase is a circus** — and you're the clown!",
    "🏆 **Congratulations!** You've found a bug. Now find the other 47!",
)


# =============================================================================
# KITCHEN STATUS - Mode-aware status messages
# =============================================================================


def get_kitchen_status(mode_manager: ModeManager | None) -> str:
    """Generate a fun kitchen status report.

    Args:
        mode_manager: Current mode manager for status info, or None.

    Returns:
        Formatted kitchen status with mode info, stats, and chef wisdom.
    """
    now = datetime.now(UTC)
    hour = now.hour

    # Time-based greeting
    if _MORNING_START <= hour < _AFTERNOON_START:
        time_greeting = "☀️ **Morning service!** Fresh coffee, fresh code."
    elif _AFTERNOON_START <= hour < _EVENING_START:
        time_greeting = "🌤️ **Lunch rush!** Keep those commits coming!"
    elif _EVENING_START <= hour < _NIGHT_START:
        time_greeting = "🌅 **Dinner service!** Prime time for shipping."
    else:
        time_greeting = "🌙 **Late night coding!** The kitchen never sleeps."

    # Mode status
    if mode_manager is not None:
        mode = mode_manager.current_mode
        indicator = mode_manager.get_mode_indicator()
        mode_desc = mode_manager.get_mode_description()

        # Mode-specific kitchen metaphors
        mode_metaphors = {
            "plan": "📋 Reviewing the menu, planning the courses...",
            "normal": "✋ Cooking with care, tasting along the way...",
            "auto": "⚡ Full steam ahead! Orders flying out!",
            "yolo": "🚀 **GORDON MODE ACTIVATED!** NO TIME FOR TASTE TESTING!",
            "architect": "🏛️ Designing the perfect kitchen layout...",
        }
        kitchen_mode = mode_metaphors.get(
            mode.value, "🍳 Cooking up something special..."
        )

        # Session stats
        history_len = len(mode_manager.state.mode_history)
        # Calculate time in mode - handle timezone-naive started_at
        started = mode_manager.state.started_at
        if started.tzinfo is None:
            # Naive datetime - compare with naive now
            time_in_mode = (datetime.now() - started).total_seconds()
        else:
            time_in_mode = (now - started).total_seconds()
        mins_in_mode = max(0, int(time_in_mode // 60))  # Ensure non-negative

        mode_section = f"""
### 📊 Current Station

| Setting | Value |
|---------|-------|
| Mode | {indicator} |
| Description | {mode_desc} |
| Time in Mode | {mins_in_mode}m |
| Mode Changes | {history_len - 1} |

{kitchen_mode}
"""
    else:
        mode_section = "\\n*Mode system not initialized*\\n"

    # Random chef quote
    quote = random.choice(CHEF_WISDOM)

    return f"""## 🍳 Chef's Kitchen Status

{time_greeting}

{mode_section}

### 💡 Chef's Wisdom

{quote}

---
*Press `Shift+Tab` to change modes • Type `/modes` for mode details*
"""


def get_modes_display(mode_manager: ModeManager | None) -> str:
    """Display all modes with fun descriptions."""
    from chefchat.cli.mode_manager import MODE_CONFIGS, VibeMode

    current = mode_manager.current_mode if mode_manager else None

    lines = [
        "## 🔄 ChefChat Modes",
        "",
        "Press **Shift+Tab** to cycle through modes:",
        "",
        "```",
        "NORMAL → AUTO → PLAN → YOLO → ARCHITECT → NORMAL ...",
        "```",
        "",
    ]

    # Mode details table
    for mode in VibeMode:
        config = MODE_CONFIGS[mode]
        is_current = mode == current
        marker = "▶️" if is_current else "  "

        # Fun descriptions
        fun_desc = {
            VibeMode.PLAN: '📋 *"Measure twice, cut once"* — Research & planning mode',
            VibeMode.NORMAL: '✋ *"Safe and steady"* — Asks before each tool',
            VibeMode.AUTO: '⚡ *"Trust and execute"* — Auto-approves everything',
            VibeMode.YOLO: '🚀 *"JUST DO IT!"* — Maximum speed, no mercy',
            VibeMode.ARCHITECT: '🏛️ *"Design the cathedral"* — Strategic thinking only',
        }

        # Permissions
        perms = []
        if config.read_only:
            perms.append("🔒 Read-only")
        if config.auto_approve:
            perms.append("🤖 Auto-approve")
        if not config.read_only and not config.auto_approve:
            perms.append("✋ Confirm each")

        perm_str = " • ".join(perms)

        lines.append(f"### {marker} {config.emoji} {mode.value.upper()}")
        lines.append(f"{fun_desc[mode]}")
        lines.append(f"*{perm_str}*")
        lines.append("")

    lines.extend([
        "---",
        "💡 **Tips:**",
        "- Use **PLAN** mode when exploring a new codebase",
        "- Use **AUTO** mode when you trust your changes",
        "- Use **YOLO** mode when shipping under deadline pressure",
        "- Use **ARCHITECT** mode for design discussions",
    ])

    return "\\n".join(lines)


def get_random_roast() -> str:
    """Get a random Chef Ramsay style roast."""
    roast = random.choice(CHEF_ROASTS)

    return f"""## 🔥 Chef's Feedback

{roast}

---
*Don't take it personally! The chef believes in tough love.* 💪
*Now get back in that kitchen and write some beautiful code!*
"""


def get_random_wisdom() -> str:
    """Get random cooking/coding wisdom."""
    wisdom = random.choice(CHEF_WISDOM)

    return f"""## 💡 Chef's Wisdom

{wisdom}

---
*Type `/roast` if you need some aggressive motivation.*
"""


# =============================================================================
# DEVELOPER FORTUNES - Tech mysticism and buggy prophecies
# =============================================================================

DEVELOPER_FORTUNES: tuple[str, ...] = (
    "🥠 **Your next pull request will be merged without comments.**\\n"
    "   Lucky numbers: 42, 404, 200",
    "🥠 **A bug you thought was fixed will return... in production.**\\n"
    "   Lucky numbers: 500, 503, NaN",
    "🥠 **You will solve that tricky bug at 3 AM in the shower.**\\n"
    "   Lucky numbers: 127, 255, 0",
    "🥠 **The rubber duck on your desk holds the answer you seek.**\\n"
    "   Lucky numbers: π, e, ∞",
    "🥠 **YOLO mode will be your downfall... or your triumph.**\\n"
    "   Lucky numbers: 🎲 YOLO, 🚀 SHIP IT",
    "🥠 **Your code will compile on the first try. Be suspicious.**\\n"
    "   Lucky numbers: 1, 0, -1",
    "🥠 **A merge conflict is in your future. Resolve it with patience.**\\n"
    "   Lucky numbers: <<<<<<<, =======, >>>>>>>",
    "🥠 **Someone will star your repo today.**\\n   Lucky numbers: ⭐, 🌟, ✨",
    "🥠 **You will discover a new library that solves all your problems.**\\n"
    "   Lucky numbers: npm, pip, cargo",
    "🥠 **The missing semicolon is on line 42.**\\n   Lucky numbers: ;",
)


def get_dev_fortune() -> str:
    """Get a random developer fortune cookie."""
    fortune = random.choice(DEVELOPER_FORTUNES)
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")

    return f"""## 🥠 Developer Fortune Cookie

{fortune}

---
*Fortune generated on {timestamp}*
*Your lucky bug: Off-by-one error*
"""
