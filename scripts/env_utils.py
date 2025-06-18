from pathlib import Path
from dotenv import dotenv_values, set_key

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
EXAMPLE_PATH = Path(__file__).resolve().parents[1] / ".env.example"


def load_env():
    """Return environment values from the .env file (falls back to example)."""
    path = ENV_PATH if ENV_PATH.exists() else EXAMPLE_PATH
    if not path.exists():
        return {}
    return dict(dotenv_values(path))


def update_env(values: dict):
    """Update the .env file with provided key/value pairs."""
    path = ENV_PATH if ENV_PATH.exists() else EXAMPLE_PATH
    path = str(path)
    for key, val in values.items():
        if val is not None:
            set_key(path, key, str(val))
