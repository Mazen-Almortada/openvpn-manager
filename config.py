import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration with default settings"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookies
    SESSION_COOKIE_SECURE = True    # Only send cookies over HTTPS in production
    REMEMBER_COOKIE_HTTPONLY = True  # Protect remember cookies from JavaScript access
    REMEMBER_COOKIE_SECURE = True    # Only send remember cookies over HTTPS

class ProductionConfig(Config):
    """Production-specific configuration"""
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    DEBUG = False

class DevelopmentConfig(Config):
    """Development-specific configuration"""
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    DEBUG = True


# Map environments to configurations
config = {
    'production': ProductionConfig,
    'development': DevelopmentConfig,
}
