"""
Smart Academic Assessment System - Centralized Configuration Module
"""

from typing import List, Optional, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, field_validator


class Settings(BaseSettings):
    # Global Identity & Metadata
    PROJECT_NAME: str = "SynGrad"
    COMPANY_NAME: str = "Academic Advising"
    PROJECT_DOMAIN: str = "localhost"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    PORT: int = 8000

    # Supabase Credentials
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Resend Notification Settings
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM: Optional[str] = None

    # Micro-LLM Fallback & Vision Model (Groq / OpenRouter / OpenAI SDK compatible)
    GROQ_API_KEY: Optional[str] = ""
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "llama-3.1-8b-instant"
    LLM_VISION_MODEL: Optional[str] = None

    # Staging Slip Lab Settings
    LAB_ALLOWED_EMAILS: str = ""

    # Frontend URL & CORS
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        # Production custom domains
        "https://syngrad.my",
        "https://www.syngrad.my",
        # Known production deployments
        "https://syngrad.vercel.app",
        "https://syngrad.onrender.com",
        "https://luma-two-theta.vercel.app",
        "https://luma-xswf.onrender.com",
        # Local development & loopback
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ]
    # Regex for wildcard-style origins (Starlette requires a real regex; glob patterns
    # like "https://*.vercel.app" are NOT supported in allow_origins).
    # For staging set: BACKEND_CORS_ORIGIN_REGEX=^https://syngrad-git-dev-[a-z0-9-]+\.vercel\.app$
    # Or add the exact staging URL to BACKEND_CORS_ORIGINS instead.
    BACKEND_CORS_ORIGIN_REGEX: Optional[str] = None
    CORS_ORIGINS: Optional[Union[List[str], str]] = None

    @field_validator("BACKEND_CORS_ORIGINS", "CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str], None]) -> Union[List[str], None]:
        if isinstance(v, str) and not v.strip().startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @model_validator(mode="after")
    def populate_fallback_keys(self) -> "Settings":
        if not self.LLM_API_KEY and self.GROQ_API_KEY:
            self.LLM_API_KEY = self.GROQ_API_KEY
        if self.CORS_ORIGINS is not None:
            self.BACKEND_CORS_ORIGINS = self.CORS_ORIGINS
        else:
            self.CORS_ORIGINS = self.BACKEND_CORS_ORIGINS
        return self

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
