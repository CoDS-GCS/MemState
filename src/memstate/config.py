from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMSTATE_", env_file=".env", extra="ignore")

    # Embedded Kuzu database file (created automatically; parent dirs are mkdir'd).
    kuzu_path: str = "memstate.kuzu"
    api_key: str | None = None
    # HTTP bind for memstate-api / CLI; override with MEMSTATE_API_PORT (e.g. 8080).
    api_host: str = "0.0.0.0"
    api_port: int = 8765
    # Ollama for /api/llm/chat (tool-capable models: e.g. llama3.2, qwen2.5, mistral).
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:latest"
    # If true, allow client-supplied Ollama URLs to any host (SSRF risk — use only in trusted setups).
    ollama_allow_remote: bool = False
    # Groq (https://console.groq.com) — also load GROQ_API_KEY from .env / process env (no MEMSTATE_ prefix).
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"

    @model_validator(mode="after")
    def _load_groq_api_key_from_env_file(self) -> Self:
        if self.groq_api_key:
            return self
        import os

        key = os.environ.get("GROQ_API_KEY")
        if not key:
            p = Path(".env")
            if p.is_file():
                for raw in p.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("GROQ_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if key:
            return self.model_copy(update={"groq_api_key": key})
        return self


def get_settings() -> Settings:
    return Settings()
