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


def get_settings() -> Settings:
    return Settings()
