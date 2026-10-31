from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    extractor_model: str = Field(default="", alias="EXTRACTOR_MODEL")
    classifier_model: str = Field(default="", alias="CLASSIFIER_MODEL")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_timeout: float = Field(default=120.0, alias="LLM_TIMEOUT")

    taxonomy_db: Path = Field(default=BASE_DIR / "data" / "taxonomy.sqlite")
    cache_db: Path = Field(default=BASE_DIR / "data" / "cache.sqlite")
    upload_dir: Path = Field(default=BASE_DIR / "storage" / "uploads")
    generated_dir: Path = Field(default=BASE_DIR / "storage" / "generated")
    template_path: Path = Field(
        default=BASE_DIR / "app" / "assets" / "发票开具项目信息导入模板.xlsx"
    )

    top_k: int = Field(default=20, alias="TOP_K")
    classify_batch_size: int = Field(default=50, alias="CLASSIFY_BATCH_SIZE")
    extract_chunk_rows: int = Field(default=200, alias="EXTRACT_CHUNK_ROWS")
    fixed_tax_rate: float = Field(default=0.13, alias="FIXED_TAX_RATE")
    amount_tolerance: float = Field(default=0.02, alias="AMOUNT_TOLERANCE")
    max_upload_mb: int = Field(default=20, alias="MAX_UPLOAD_MB")

    @property
    def extractor_model_name(self) -> str:
        return self.extractor_model or self.llm_model

    @property
    def classifier_model_name(self) -> str:
        return self.classifier_model or self.llm_model

    def ensure_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.taxonomy_db.parent.mkdir(parents=True, exist_ok=True)
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
