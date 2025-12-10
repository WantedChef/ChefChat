"""🍽️ ChefChat Plating System
==========================

The "Plating" feature presents your coding work like a chef plates a dish.
A beautiful, stylized summary of what was accomplished.

Features:
- /plate - Present the current work beautifully
- /recipe - Show the "recipe" (ingredients + steps) for a coding task
- /taste - Quick code taste test (review)

Each presentation is mode-aware and themed to the current cooking style!
"""

from __future__ import annotations

from datetime import UTC, datetime
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibe.cli.mode_manager import ModeManager
    from vibe.core.agent import AgentStats

# Difficulty thresholds for recipe complexity
_EASY_STEPS_MAX = 3
_MEDIUM_STEPS_MAX = 6


# =============================================================================
# PLATING PRESENTATIONS - Present work like a finished dish
# =============================================================================

PRESENTATION_STYLES: dict[str, dict[str, str]] = {
    "plan": {
        "plate": "📋 THE BLUEPRINT",
        "garnish": "📐 architectural detail",
        "style": "Methodical presentation with clear structure",
        "chef_note": "As they say in the kitchen: *mise en place!*",
    },
    "normal": {
        "plate": "🍽️ HOME COOKING",
        "garnish": "🌿 fresh and reliable",
        "style": "Clean presentation, honest flavors",
        "chef_note": "Comfort food for the codebase.",
    },
    "auto": {
        "plate": "⚡ RAPID SERVICE",
        "garnish": "🔥 efficiency dots",
        "style": "Quick plating, maximum throughput",
        "chef_note": "Hot and fast! Just how we like it.",
    },
    "yolo": {
        "plate": "🚀 CHEF'S SPECIAL",
        "garnish": "💥 EXPLOSIVE flavor",
        "style": "Bold presentation, no holds barred",
        "chef_note": "Send it! *chef's kiss*",
    },
    "architect": {
        "plate": "🏛️ TASTING MENU",
        "garnish": "🎨 artistic swirls",
        "style": "Elevated presentation, multi-course vision",
        "chef_note": "A symphony of design decisions.",
    },
}


def generate_plating(
    mode_manager: ModeManager | None,
    stats: AgentStats | None = None,
    work_summary: str | None = None,
) -> str:
    """Generate a beautiful plating presentation of the work done.

    Args:
        mode_manager: Current mode for themed presentation
        stats: Agent stats for the metrics
        work_summary: Optional summary of what was accomplished

    Returns:
        Beautifully formatted presentation string
    """
    # Get mode-specific styling
    mode_name = mode_manager.current_mode.value if mode_manager else "normal"
    style = PRESENTATION_STYLES.get(mode_name, PRESENTATION_STYLES["normal"])

    # Current time for presentation
    now = datetime.now(UTC)
    time_str = now.strftime("%H:%M")

    # Get stats if available
    if stats:
        steps = stats.steps
        tokens = stats.session_total_llm_tokens
        cost = stats.session_cost
        tool_calls = stats.tool_calls_succeeded
    else:
        steps = "—"
        tokens = "—"
        cost = "—"
        tool_calls = "—"

    # Random plating flourish
    flourishes = [
        "✨ *Drizzled with elegant abstractions*",
        "🌟 *Topped with a reduction of best practices*",
        "💫 *Garnished with type safety*",
        "⭐ *Finished with a sprinkle of documentation*",
        "🎯 *Precision-placed with surgical accuracy*",
        "🔮 *Crystallized with pure logic*",
    ]
    flourish = random.choice(flourishes)

    # Build the presentation
    presentation = f"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║                       {style["plate"]:^40}                       ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🕐 Served at: {time_str:^8}                                      ║
║  🍽️ Presentation: {style["style"]:<40} ║
║  🌿 Garnish: {style["garnish"]:<45} ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  📊 KITCHEN METRICS                                              ║
║  ────────────────────────────────────────────                    ║
║  • Preparations (steps): {steps!s:>10}                         ║
║  • Ingredients used (tokens): {tokens!s:>10}                   ║
║  • Kitchen cost: ${str(cost)[:6]:>10}                             ║
║  • Tools employed: {tool_calls!s:>10}                          ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  {flourish:<60} ║
║                                                                  ║
║  👨‍🍳 Chef's Note: {style["chef_note"]:<43} ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if work_summary:
        presentation += f"""
### 📝 What We Prepared

{work_summary}
"""

    return presentation


# =============================================================================
# RECIPE GENERATOR - Show the "recipe" for a coding task
# =============================================================================


def generate_recipe(
    task_name: str,
    ingredients: list[str],
    steps: list[str],
    mode_manager: ModeManager | None = None,
    prep_time: str = "10 min",
    cook_time: str = "varies",
    serves: str = "the whole team",
) -> str:
    """Generate a recipe-style breakdown of a coding task.

    Args:
        task_name: Name of the feature/fix
        ingredients: List of files/dependencies needed
        steps: Implementation steps
        mode_manager: For mode-aware styling
        prep_time: Planning time estimate
        cook_time: Implementation time estimate
        serves: Who benefits from this

    Returns:
        Recipe-formatted task description
    """
    mode_name = mode_manager.current_mode.value if mode_manager else "normal"

    # Difficulty based on steps
    if len(steps) <= _EASY_STEPS_MAX:
        difficulty = "🟢 Easy"
    elif len(steps) <= _MEDIUM_STEPS_MAX:
        difficulty = "🟡 Medium"
    else:
        difficulty = "🔴 Advanced"

    # Format ingredients
    ingredients_list = "\n".join(f"  • {ing}" for ing in ingredients)

    # Format steps with numbers
    steps_list = "\n".join(f"  **{i + 1}.** {step}" for i, step in enumerate(steps))

    # Random chef tip
    tips = [
        "Always taste your tests before serving to production!",
        "Let your code rest before the final review - fresh eyes catch bugs!",
        "A watched CI/CD pipeline never finishes... but refresh anyway.",
        "When in doubt, add more types. Butter? Also types.",
        "The secret ingredient is always error handling.",
        "Mise en place: organize your imports before cooking!",
    ]
    tip = random.choice(tips)

    return f"""## 📖 RECIPE: {task_name}

╭───────────────────────────────────────────╮
│  ⏱️ Prep Time: {prep_time:<10}  🍳 Cook Time: {cook_time:<10} │
│  🍽️ Serves: {serves:<15}  📊 Difficulty: {difficulty:<10} │
╰───────────────────────────────────────────╯

### 🥗 Ingredients

{ingredients_list}

### 👨‍🍳 Method

{steps_list}

### 💡 Chef's Tip

*{tip}*

---
*Recipe from the ChefChat Kitchen • Mode: {mode_name.upper()}*
"""


# =============================================================================
# TASTE TEST - Quick code review
# =============================================================================

TASTE_VERDICTS = [
    ("🌟🌟🌟🌟🌟", "EXCEPTIONAL", "This code is *chef's kiss*! Michelin-worthy."),
    ("🌟🌟🌟🌟", "EXCELLENT", "Almost perfect! Just needs a pinch more seasoning."),
    ("🌟🌟🌟", "GOOD", "Solid home cooking. Gets the job done well."),
    ("🌟🌟", "NEEDS WORK", "The ingredients are there, but needs refinement."),
    ("🌟", "BACK TO BASICS", "Let's revisit the recipe from scratch."),
]

TASTE_ASPECTS = {
    "readability": [
        "Clear as a consommé 🍜",
        "Easy to follow like a well-written recipe 📖",
        "Could use some clarifying comments 💭",
        "A bit like reading hieroglyphics 🤔",
        "My eyes are watering like cutting onions 🧅",
    ],
    "structure": [
        "Perfectly layered like a mille-feuille 🥐",
        "Well-organized mise en place 📋",
        "Some ingredients out of place 🥄",
        "Like a kitchen after dinner rush 🌪️",
        "Needs a complete reorganization 📦",
    ],
    "efficiency": [
        "Runs like a well-oiled wok 🥘",
        "Efficient as a professional kitchen ⚡",
        "Some slow spots in the service 🐢",
        "Could use some optimization herbs 🌿",
        "Burning through resources like gas 🔥",
    ],
    "maintainability": [
        "A recipe anyone could follow 👨‍🍳👩‍🍳",
        "Well-documented like a cookbook 📚",
        "Some secret ingredients undocumented 🤫",
        "Inherited family recipe, unclear origins 👴",
        "Only the original chef understands this 🧙",
    ],
}


def generate_taste_test(
    code_snippet: str | None = None,
    file_path: str | None = None,
    mode_manager: ModeManager | None = None,
    severity: int | None = None,  # 1-5, None for random
) -> str:
    """Generate a fun taste test (code review) report.

    Args:
        code_snippet: Code being reviewed (optional)
        file_path: File being reviewed (optional)
        mode_manager: For mode-aware commentary
        severity: Override the review severity (1-5)

    Returns:
        Taste test report
    """
    # Random severity if not specified
    if severity is None:
        # Weight towards positive reviews (we're encouraging!)
        severity = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 30, 35, 20])[0]

    stars, verdict, description = TASTE_VERDICTS[5 - severity]

    # Random aspects
    aspects = {
        aspect: random.choice(comments) for aspect, comments in TASTE_ASPECTS.items()
    }

    # Mode-specific commentary
    mode_name = mode_manager.current_mode.value if mode_manager else "normal"
    mode_notes = {
        "plan": "📋 *In planning mode, we're being thorough with the review.*",
        "normal": "✋ *Standard taste test - checking all the bases.*",
        "auto": "⚡ *Quick taste - looks good, let's move!*",
        "yolo": "🚀 *LGTM ship it! ...but maybe run the tests first.*",
        "architect": "🏛️ *Looking at the high-level flavor profile.*",
    }
    mode_note = mode_notes.get(mode_name, "")

    # Build report header
    if file_path:
        header = f"Tasting: `{file_path}`"
    elif code_snippet:
        preview = code_snippet[:50].replace("\n", " ") + "..."
        header = f"Tasting: `{preview}`"
    else:
        header = "General Kitchen Inspection"

    return f"""## 🍽️ TASTE TEST RESULTS

**{header}**

### Overall Rating

{stars} **{verdict}**

*{description}*

### Flavor Profile

| Aspect | Notes |
|--------|-------|
| 📖 **Readability** | {aspects["readability"]} |
| 🏗️ **Structure** | {aspects["structure"]} |
| ⚡ **Efficiency** | {aspects["efficiency"]} |
| 🔧 **Maintainability** | {aspects["maintainability"]} |

{mode_note}

---
*Taste test by Chef's AI • Not a substitute for real code review!*
"""


# =============================================================================
# KITCHEN TIMER - Time estimates
# =============================================================================


def estimate_cooking_time(task_description: str) -> dict[str, Any]:
    """Estimate time for a coding task in cooking terms.

    Args:
        task_description: Description of the task

    Returns:
        Dict with time estimates and cooking metaphor
    """
    desc_lower = task_description.lower()

    # Simple heuristics for demo
    if any(w in desc_lower for w in ["bug", "fix", "typo", "small"]):
        return {
            "prep_time": "5 min",
            "cook_time": "10-15 min",
            "total": "15-20 min",
            "metaphor": "🥪 Quick sandwich",
            "tip": "This is a quick fix - but don't rush the testing!",
        }
    elif any(w in desc_lower for w in ["feature", "add", "new", "implement"]):
        return {
            "prep_time": "15-30 min",
            "cook_time": "1-2 hours",
            "total": "1.5-2.5 hours",
            "metaphor": "🍝 Full pasta dinner",
            "tip": "Take time to plan the architecture before diving in.",
        }
    elif any(w in desc_lower for w in ["refactor", "rewrite", "migrate", "upgrade"]):
        return {
            "prep_time": "30-60 min",
            "cook_time": "2-4 hours",
            "total": "2.5-5 hours",
            "metaphor": "🦃 Holiday feast",
            "tip": "This is a big one - break it into smaller courses!",
        }
    elif any(w in desc_lower for w in ["design", "architect", "plan", "research"]):
        return {
            "prep_time": "1-2 hours",
            "cook_time": "depends",
            "total": "ongoing",
            "metaphor": "📖 Writing the cookbook",
            "tip": "Good planning saves cooking time later!",
        }
    else:
        return {
            "prep_time": "15 min",
            "cook_time": "30-60 min",
            "total": "45 min - 1.5 hours",
            "metaphor": "🍲 Hearty stew",
            "tip": "Taste as you go - incremental progress is key!",
        }


def format_kitchen_timer(task_description: str) -> str:
    """Format a kitchen timer display for a task.

    Args:
        task_description: What needs to be done

    Returns:
        Formatted timer display
    """
    est = estimate_cooking_time(task_description)

    return f"""## ⏱️ KITCHEN TIMER

**Task:** {task_description}

╭────────────────────────────────────────╮
│  📐 Prep Time:     {est["prep_time"]:<15}     │
│  🍳 Cook Time:     {est["cook_time"]:<15}     │
│  ⏱️ Total Time:    {est["total"]:<15}     │
│                                        │
│  🍽️ Dish Type:     {est["metaphor"]:<15}     │
╰────────────────────────────────────────╯

### 💡 Chef's Tip

{est["tip"]}

---
*Estimates based on complexity heuristics. Actual time may vary!*
*Remember: good code takes time to simmer.* 🍲
"""


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "PRESENTATION_STYLES",
    "estimate_cooking_time",
    "format_kitchen_timer",
    "generate_plating",
    "generate_recipe",
    "generate_taste_test",
]
