from __future__ import annotations

import pytest

from chefchat.kitchen.validation import InputValidationError, InputValidator


class TestMarkdownValidationFix:
    """Test that markdown content passes validation while dangerous content is blocked."""

    def test_legitimate_markdown_passes(self):
        """Test that legitimate markdown content with quotes, colons, etc passes validation."""
        markdown_content = """
📋 **Plan for Ticket #228cb8b2**:

**Analysis:**
The user greeted us, likely expecting a professional response or initiating a request for assistance.

**Step-by-Step Plan:**
1. **Clarify the Request:** Politely ask for specifics about the project.
2. **Gather Requirements:** Analyze the scope (e.g., system design, code refactor).
3. **Files to Create/Modify:**
   - `api/routes/user_routes.py` (new)
   - `models/user_model.py` (new)

**Potential Challenges:**
1. **Ambiguity:** Lack of clear requirements may lead to misaligned solutions.
2. **Scope Creep:** User may underestimate complexity.

**Next Step:**
"Hello! How can I assist you today?"
"""

        payload = {
            "content": markdown_content,
            "task": "analysis task",
            "metadata": {
                "description": "Plan with 'quotes' and \"double quotes\"",
                "status": "in-progress",
            },
        }

        # Should not raise an exception
        result = InputValidator.validate_message_payload(payload)
        assert result == payload

    def test_still_blocks_dangerous_content(self):
        """Test that truly dangerous content is still blocked."""
        dangerous_content = "Hello\x00world"  # Contains null byte

        payload = {"content": dangerous_content}

        with pytest.raises(InputValidationError, match="Dangerous characters detected"):
            InputValidator.validate_message_payload(payload)

    def test_command_context_is_more_restrictive(self):
        """Test that command contexts use stricter validation."""
        command_payload = {
            "command": "run <script>",  # Contains < and > which should be blocked in commands
            "task": "execute",
        }

        with pytest.raises(InputValidationError, match="Dangerous characters detected"):
            InputValidator.validate_message_payload(command_payload)

    def test_backticks_allowed_in_content(self):
        """Test that backticks are allowed in regular content (common in markdown)."""
        backtick_payload = {
            "content": "Code with `backticks` here",
            "description": "Regular content",
        }

        # Should not raise an exception - backticks are allowed in markdown content
        result = InputValidator.validate_message_payload(backtick_payload)
        assert result == backtick_payload

    def test_backticks_blocked_in_actions(self):
        """Test that backticks are blocked in action names."""
        # This would be caught by the action format regex, not dangerous chars
        with pytest.raises(InputValidationError, match="Invalid action format"):
            InputValidator.validate_action("bad`action")

    def test_control_chars_blocked(self):
        """Test that control characters are still blocked."""
        control_chars_payload = {
            "content": "Text with control \x1b[31mred\x1b[0m colors"
        }

        with pytest.raises(InputValidationError, match="Dangerous characters detected"):
            InputValidator.validate_message_payload(control_chars_payload)

    def test_regular_content_works(self):
        """Test that regular non-markdown content still works."""
        normal_payload = {
            "message": "Hello world",
            "user": "test_user",
            "action": "greet",
        }

        # Should not raise an exception
        result = InputValidator.validate_message_payload(normal_payload)
        assert result == normal_payload
