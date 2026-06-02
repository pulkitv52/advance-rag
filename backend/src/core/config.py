from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Application ---
    APP_NAME: str = "Advance-Rag"
    LOG_LEVEL: str = "INFO"
    BACKEND_PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"

    # --- PostgreSQL ---
    POSTGRES_USER: str = "app_user"
    POSTGRES_PASSWORD: str = "change-me"
    POSTGRES_DB: str = "app_db"
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Registry Source PostgreSQL ---
    REGISTRY_POSTGRES_USER: Optional[str] = None
    REGISTRY_POSTGRES_PASSWORD: Optional[str] = None
    REGISTRY_POSTGRES_DB: Optional[str] = None
    REGISTRY_POSTGRES_HOST: Optional[str] = None
    REGISTRY_POSTGRES_PORT: Optional[int] = None
    REGISTRY_SCHEMA: str = "srsadmin"
    REGISTRY_BENEFICIARY_TABLE: str = "swasthya_sathi_beneficiary"
    REGISTRY_TRANSACTION_TABLE: str = "swasthya_sathi_transaction_2526"

    @property
    def registry_postgres_user(self) -> str:
        return self.REGISTRY_POSTGRES_USER or self.POSTGRES_USER

    @property
    def registry_postgres_password(self) -> str:
        return self.REGISTRY_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD

    @property
    def registry_postgres_db(self) -> str:
        return self.REGISTRY_POSTGRES_DB or self.POSTGRES_DB

    @property
    def registry_postgres_host(self) -> str:
        return self.REGISTRY_POSTGRES_HOST or self.POSTGRES_HOST

    @property
    def registry_postgres_port(self) -> int:
        return self.REGISTRY_POSTGRES_PORT or self.POSTGRES_PORT

    # --- Qdrant ---
    QDRANT_HOST: str = "127.0.0.1"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_COLLECTION: str = "documents"
    QDRANT_VECTOR_SIZE: int = 1024  # nv-embedqa-e5-v5 dimension

    # --- Neo4j ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "change-me"

    # --- Minio ---
    MINIO_ENDPOINT: str = "127.0.0.1:9000"
    MINIO_ROOT_USER: str = "minio_user"
    MINIO_ROOT_PASSWORD: str = "change-me"
    MINIO_BUCKET: str = "project-docs"
    MINIO_USE_SSL: bool = False

    # --- Redis ---
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # --- NVIDIA NIM ---
    NVIDIA_API_KEY: str = ""
    NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NIM_LLM_MODEL: str = "meta/llama-3.1-70b-instruct"
    NIM_EMBEDDING_MODEL: str = "nvidia/nv-embedqa-e5-v5"
    NIM_PARSE_MODEL: str = "nvidia/neva-22b"
    NIM_RERANK_MODEL: str = "nv-rerank-qa-mistral-4b:1"
    NIM_RERANK_URL: str = "https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking"

    # --- Sarvam Voice ---
    SARVAM_API_KEY: str = ""
    SARVAM_TTS_STREAM_URL: str = "https://api.sarvam.ai/text-to-speech/stream"
    SARVAM_STT_URL: str = "https://api.sarvam.ai/speech-to-text"

    model_config = SettingsConfigDict(
        # Search in current and parent directory (from project root)
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
