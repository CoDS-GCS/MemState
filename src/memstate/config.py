from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMSTATE_", env_file=".env", extra="ignore")

    # Embedded Kuzu database file (created automatically; parent dirs are mkdir'd).
    kuzu_path: str = "memstate.kuzu"
    api_key: str | None = None
    # Optional stronger admin key for protected config updates (e.g. fixed system context).
    admin_key: str | None = None
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
    # Groq Whisper (speech-to-text for UI mic); same GROQ_API_KEY as chat.
    groq_whisper_model: str = "whisper-large-v3-turbo"
    # LLM chat: how many dialogue turns (user + optional assistant each) to send for intent/context.
    chat_intent_turns: int = Field(default=8, ge=1, le=64)
    # Max assistant↔API iterations while the model keeps requesting tool calls (reorganize flows need more).
    chat_max_tool_rounds: int = Field(default=32, ge=1, le=256)
    # Study ingest: when the last user message exceeds this length and intent is ingest/both, run Study (two phases).
    chat_chunk_threshold_chars: int = Field(default=10000, ge=2000, le=500_000)
    # Legacy overlap chunking parameters (unused by default Study pipeline).
    chat_chunk_max_chars: int = Field(default=10000, ge=1000, le=100_000)
    chat_chunk_overlap: int = Field(default=800, ge=0, le=5000)
    # Tool budget for Study phase A (and any legacy per-segment runs).
    chat_chunk_per_segment_tool_rounds: int = Field(default=72, ge=8, le=256)
    # Pause between Study phase A and B (seconds) to reduce Groq TPM bursts; 0 disables.
    study_phase_delay_seconds: float = Field(default=8.0, ge=0.0, le=600.0)
    # Groq: retry after rate_limit_exceeded / HTTP 429 with backoff (caps single sleep).
    groq_rate_limit_max_retries: int = Field(default=20, ge=1, le=100)
    groq_rate_limit_backoff_cap_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    # On query intent: bump field salience when read tools return field data (cap field_salience_max).
    query_field_salience_bump: float = Field(default=0.1, ge=0.0, le=2.0)
    field_salience_max: float = Field(default=10.0, ge=0.1, le=10.0)

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
