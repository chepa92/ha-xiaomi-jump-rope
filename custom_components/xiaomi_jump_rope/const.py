"""Constants for the Xiaomi Jump Rope integration."""

DOMAIN = "xiaomi_jump_rope"

CONF_ADDRESS = "address"
CONF_APP_DEVICE_ID = "app_device_id"
CONF_TOKEN = "token"

# The rope advertises as "Mijia Smart Jump Rope <last 4 hex digits of its MAC>".
DEVICE_NAME_PREFIX = "Mijia Smart Jump Rope"

# While the jump count is changing we re-read often; otherwise about once a minute.
ACTIVE_INTERVAL = 20  # seconds between reads during a workout
IDLE_INTERVAL = 60  # seconds between reads when nothing changes
TICK_INTERVAL = 20  # seconds between "is the rope around?" checks
MAX_BACKOFF = 300  # seconds, cap for retry back-off after failures
