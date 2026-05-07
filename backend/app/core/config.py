from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str = "change-me-in-production"
    frontend_origin: str = "http://localhost:3000"
    jobs_db_path: str = "jobs.db"
    jobs_retention_hours: int = 24

    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    notion_token: str = ""
    notion_payments_db_id: str = ""
    notion_profs_hors_tb_db_id: str = ""
    notion_teachers_pages_parent_id: str = ""
    gmail_user: str = ""
    gmail_app_password: str = ""
    tutorbird_api_key: str = ""
    google_drive_root_folder_id: str = ""
    google_service_account_json: str = ""
    google_oauth_refresh_token: str = ""
    frankfurter_api_url: str = "https://api.frankfurter.app"
    openai_api_key: str = ""


settings = Settings()
