import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # OpenAI Settings
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Microservice Endpoints & Ports
    triage_port: int = 8001
    triage_url: str = "http://localhost:8001"

    resolution_port: int = 8002
    resolution_url: str = "http://localhost:8002"

    saboteur_port: int = 8003
    saboteur_url: str = "http://localhost:8003"

    # Chaos Configuration
    chaos_enabled: bool = True
    chaos_seed: int = 12345
    chaos_prompt_injection_rate: float = 0.20
    chaos_packet_drop_rate: float = 0.15
    chaos_tool_503_rate: float = 0.15

    # Evaluation Harness
    run_count: int = 100
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
