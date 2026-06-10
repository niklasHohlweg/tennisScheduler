"""Configuration for Tennis Scheduler Flask Application"""
import os
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'tennis_scheduler')
    DB_USER = os.getenv('DB_USER', 'tennis_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'tennis_password')

    # Authentik / OIDC
    AUTHENTIK_ISSUER = os.getenv('AUTHENTIK_ISSUER', '')
    AUTHENTIK_CLIENT_ID = os.getenv('AUTHENTIK_CLIENT_ID', '')
    AUTHENTIK_CLIENT_SECRET = os.getenv('AUTHENTIK_CLIENT_SECRET', '')
    AUTHENTIK_REDIRECT_URI = os.getenv('AUTHENTIK_REDIRECT_URI', '')
    
    # Session
    SESSION_COOKIE_NAME = 'tennis_session'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    
    # Application
    ITEMS_PER_PAGE = 20
    MAX_TEAMS = 50
    MAX_COURTS = 20
    
    @property
    def DATABASE_URL(self):
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
