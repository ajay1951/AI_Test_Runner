"""
Configuration Module & Secure Credential Store.
Loads environment variables and sets global defaults for execution, browser, and timeouts.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# AI / LLM Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
PLANNER_MODE = os.getenv("PLANNER_MODE", "hybrid").lower()
PLANNER_STRICT = os.getenv("PLANNER_STRICT", "false").lower() == "true"

# Browser Configuration
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
TIMEOUT_MS = int(os.getenv("TIMEOUT_MS", "15000"))

# Secure Test Credential Vault (Configurable per environment, never hardcoded in scripts)
TEST_CUSTOMER_EMAIL = os.getenv("TEST_CUSTOMER_EMAIL", "user@phptravels.com")
TEST_CUSTOMER_PASSWORD = os.getenv("TEST_CUSTOMER_PASSWORD", "demouser")
TEST_ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@phptravels.com")
TEST_ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "demoadmin")
