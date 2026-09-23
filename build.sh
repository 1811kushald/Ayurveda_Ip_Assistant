#!/usr/bin/env bash
# Render build script for IP-SAKTI Sahayak

set -o errexit  # Exit on error

# 1. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 2. Collect static files
python manage.py collectstatic --no-input

# 3. Run database migrations
python manage.py migrate
