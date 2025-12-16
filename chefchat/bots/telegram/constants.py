from __future__ import annotations

from pathlib import Path

# Telegram bot working directory
TELEGRAM_WORKDIR = Path.home() / "chefchat_output_"

# Message and API limits
TELEGRAM_MESSAGE_TRUNCATE_LIMIT = 4000
MAX_TELEGRAM_API_RETRIES = 3
TELEGRAM_API_RETRY_DELAY_S = 1.0

# Command argument defaults
MIN_COMMAND_ARGS_MINIAPP = 2
MIN_COMMAND_ARGS_SWITCH = 3
MIN_COMMAND_ARGS_MODEL_SELECT = 2

# Output and menu defaults
GIT_OUTPUT_MAX_LEN = 3000
MODEL_MENU_BUTTONS_PER_ROW = 2
CHEAP_MODEL_PRICE_THRESHOLD = 0.5

# Idle and session controls
SESSION_IDLE_WARNING_S = 45 * 60
SESSION_IDLE_TTL_S = 60 * 60

# Approval defaults
APPROVAL_TTL_S = 10.0 * 60.0  # 10 minutes
