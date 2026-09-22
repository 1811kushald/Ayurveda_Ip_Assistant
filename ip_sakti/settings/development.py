"""
Development settings for IP-SAKTI Sahayak.
Uses Supabase PostgreSQL when DATABASE_URL is set,
falls back to SQLite for initial project structure testing.
"""
import os
from dotenv import load_dotenv
import dj_database_url
from .base import *  # noqa: F401, F403

# Load .env file for development
load_dotenv(BASE_DIR / '.env')

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Database — Supabase PostgreSQL (primary) or SQLite (fallback for initial testing)
# Set DATABASE_URL in your .env file to use Supabase
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Fallback to SQLite for initial project structure testing
    # NOTE: pgvector features (VectorField, CosineDistance) will NOT work with SQLite.
    # Switch to Supabase PostgreSQL before Sprint 4 (document processing).
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Session cookie — not secure in dev (no HTTPS)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
