import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
TIMEOUT_MS = int(os.getenv("TIMEOUT_MS", "15000"))
