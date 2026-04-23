"""런타임 설정 — 환경변수/`.env` 파일에서 읽음.

Railway 는 프로젝트에 Postgres 플러그인을 붙이면 자동으로 ``DATABASE_URL``
환경변수를 주입한다. 형식은 ``postgresql://...`` 이지만 SQLAlchemy async 로
쓰려면 ``postgresql+asyncpg://...`` 가 필요하므로 `async_database_url` 에서
자동 변환한다.

로컬 개발은 기본값 SQLite 폴백으로 충분 — `alembic upgrade head` 가 동일한
스키마로 돌아간다.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 배포 환경 식별
    OHDO_ENV: str = "development"

    # Railway 가 주입하거나 .env 로 설정. 기본은 로컬 SQLite.
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # Device Flow 의 verification_uri 에 쓰는 공개 URL (예:
    # ``https://ohdo-production.up.railway.app``). 설정되지 않으면 요청
    # ``base_url`` 로부터 유도 — 로컬 개발에서는 자연스럽지만 프록시 뒤에서는
    # 누락/오표기 위험이 있으므로 Railway Variables 로 명시 권장.
    PUBLIC_BASE_URL: str | None = None

    # Device Flow TTL — 기본 15 분.
    DEVICE_CODE_TTL_SECONDS: int = 900
    # Agent 권장 폴링 간격.
    DEVICE_CODE_INTERVAL_SECONDS: int = 5

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async 엔진이 바로 쓸 수 있는 형식으로 정규화."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
