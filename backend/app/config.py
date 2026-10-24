import os
from pathlib import Path
from dotenv import load_dotenv


# Local development reads the user's Ollama connection without affecting Docker.
load_dotenv(Path(__file__).resolve().parents[2] / ".env.local", override=False)


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/ai03.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "30")) * 1024 * 1024
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "change-this-password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "neo4j")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
TRANSLATION_DATA_DIR = Path(os.getenv("TRANSLATION_DATA_DIR", "data/translation"))
# Argos otherwise creates model, cache and config directories in the user's home.
os.environ.setdefault("XDG_DATA_HOME", str(TRANSLATION_DATA_DIR / "share"))
os.environ.setdefault("XDG_CONFIG_HOME", str(TRANSLATION_DATA_DIR / "config"))
os.environ.setdefault("XDG_CACHE_HOME", str(TRANSLATION_DATA_DIR / "cache"))
os.environ.setdefault("ARGOS_PACKAGES_DIR", str(TRANSLATION_DATA_DIR / "packages"))


def llm_configured() -> bool:
    return bool(LLM_BASE_URL and LLM_MODEL and LLM_API_KEY)
