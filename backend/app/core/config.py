from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://pensionz:pensionz_dev_password@db:5432/pensionz"

    minio_endpoint: str = "http://minio:9000"
    minio_public_endpoint: str = "http://localhost:9002"
    minio_root_user: str = "pensionz"
    minio_root_password: str = "pensionz_dev_password"
    minio_bucket: str = "pensionz-documents"

    jwt_secret_key: str = "dev-only-change-me-do-not-use-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Sign-in lockout: this many wrong passwords in a row locks the account
    # for lockout_minutes (FR-SEC-004).
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # One-time codes (FR-PRT-006, FR-SEC-004): portal users enter one at every
    # sign-in, and later before money-affecting actions. Sent by email until an
    # SMS gateway is chosen (decided 2026-11-02).
    otp_minutes: int = 10
    otp_max_attempts: int = 5
    otp_max_sends_per_15_minutes: int = 5

    # Product branding for emails and messages (mirror of frontend/src/brand.ts).
    brand_name: str = "Pensionz"
    brand_color: str = "#0b5c6b"
    brand_administrator: str = "your pension administrator"

    backend_cors_origins: str = "http://localhost:5178"

    log_level: str = "INFO"

    # Background worker (app/worker.py). Business dates for scheduled jobs
    # are taken in this timezone, not the container's UTC clock.
    business_timezone: str = "Africa/Blantyre"
    worker_poll_seconds: int = 60
    outbox_poll_seconds: int = 5
    job_catchup_days: int = 7

    # Email is queued in notification_outbox and sent by the worker. Empty
    # smtp_host = not configured: the worker logs and marks messages skipped.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "no-reply@pensionz.dev"
    smtp_from_name: str = "Pensionz"
    smtp_use_tls: bool = True
    app_base_url: str = "http://localhost:5178"


settings = Settings()
