#!/usr/bin/env bash
# Render build script for IP-SAKTI Sahayak

set -o errexit  # Exit on error

pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate
