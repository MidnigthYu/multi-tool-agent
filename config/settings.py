"""pydantic-settings 配置类，自动从 .env 加载全部环境变量。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    LLM_DEEPSEEK_API_KEY: str = ""
    LLM_DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_DOUBAO_API_KEY: str = ""
    LLM_DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    LLM_DOUBAO_MODEL: str = "doubao-pro-128k"
    TAVILY_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = ""
    CHROMA_PERSIST_DIR: str = "data/chroma_data"
    SQLITE_DB_PATH: str = "data/sessions.db"
    UPLOAD_DIR: str = "data/uploads"
    MODEL_REQUEST_TIMEOUT_S: int = 60
    MODEL_FALLBACK_COOLDOWN_S: int = 300
    FALLBACK_MAX_RETRIES: int = 2
    TOKEN_MAX_PER_SESSION: int = 50000
    TOKEN_COMPRESS_THRESHOLD: int = 30000
    MAX_REFLECTION_ROUNDS: int = 2
    SEARCH_TIMEOUT_S: int = 15
    SEARCH_RETRY_MAX: int = 2
    SEARCH_RETRY_BASE_DELAY_S: int = 1
    SEARCH_RESULT_MAX_LENGTH: int = 5000
    DOC_MAX_FILE_SIZE_MB: int = 50
    DOC_CHUNK_SIZE: int = 1000
    DOC_CHUNK_OVERLAP: int = 200
    DOC_SUPPORTED_FORMATS: str = ".pdf,.docx,.xlsx"
    CHROMA_HEARTBEAT_INTERVAL_S: int = 30
    CHROMA_DEGRADED_THRESHOLD: int = 3
    CHROMA_COLLECTION_DOCS: str = "user_docs"
    CHROMA_COLLECTION_MEMORY: str = "user_memories"
    SQLITE_BUSY_TIMEOUT_S: int = 5
    SESSION_EXPIRE_HOURS: int = 24
    MID_TERM_SUMMARY_THRESHOLD: int = 20
    CODE_SANDBOX_TIMEOUT_S: int = 30
    CODE_SANDBOX_MEMORY_LIMIT_MB: int = 512
    CODE_SANDBOX_MAX_OUTPUT_CHARS: int = 10000
    SHORT_TERM_MAX_MESSAGES: int = 5
    SESSION_MAX_ROUNDS: int = 20
    LONG_TERM_MEMORY_TOP_K: int = 5
    LONG_TERM_MEMORY_SIMILARITY_THRESHOLD: float = 0.7
    SUMMARY_PROMPT_TEMPLATE: str = (
        "请为以下对话生成结构化摘要。返回 JSON 格式："
        '{"intent":"对话核心意图","conclusion":"主要结论",'
        '"todos":["待办1","待办2"],"preferences":["偏好1"]}'
    )
    EMBEDDING_MODEL: str = "text-embedding-ada-002"
    EMBEDDING_DIMENSION: int = 1536
    WS_HEARTBEAT_INTERVAL_S: int = 30
    WS_MAX_CONNECTIONS: int = 100
    CORS_ORIGINS: str = "*"
    CORS_METHODS: str = "GET,POST,PUT,DELETE"
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_S: int = 60
    RETRY_BASE_DELAY_S: int = 1
    RETRY_MAX_DELAY_S: int = 60
    RETRY_JITTER: float = 0.1
    HEALTH_CHECK_INTERVAL_S: int = 60
    HEALTH_CHECK_TIMEOUT_S: int = 10

    @property
    def log_file_path(self) -> Path | None:
        return Path(self.LOG_FILE) if self.LOG_FILE else None

    @property
    def chroma_persist_path(self) -> Path:
        return Path(self.CHROMA_PERSIST_DIR)

    @property
    def sqlite_db_path(self) -> Path:
        return Path(self.SQLITE_DB_PATH)

    @property
    def upload_dir_path(self) -> Path:
        return Path(self.UPLOAD_DIR)

    @property
    def supported_format_list(self) -> list[str]:
        return [f.strip().lower() for f in self.DOC_SUPPORTED_FORMATS.split(",") if f.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
