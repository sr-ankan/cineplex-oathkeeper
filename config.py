import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!").strip() or "!"
POLL_INTERVAL = max(15, int(os.getenv("POLL_INTERVAL", "30")))
DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "").strip()

CINEPLEX_API_BASE = os.getenv("CINEPLEX_API_BASE", "https://api.kichole.com").rstrip("/")
CINEPLEX_SITE_URL = os.getenv("CINEPLEX_SITE_URL", "https://starcineplex.com").rstrip("/")
CINEPLEX_ORG_ID = os.getenv(
    "CINEPLEX_ORG_ID", "0ab00001-0000-0000-0000-000000000001"
).strip()
