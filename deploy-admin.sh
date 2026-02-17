#!/bin/bash
# Admin/Technician Backend Deployment Script
# NOTE: Replace all placeholder values with actual secrets from .env file

docker run -d --name admin-backend \
  -e DATABASE_URL="<your_database_url>" \
  -e SECRET_KEY="<your_secret_key>" \
  -e ALGORITHM="HS256" \
  -e ACCESS_TOKEN_EXPIRE_MINUTES="1440" \
  -e REDIS_URL="<your_redis_url>" \
  -e STRIPE_PUBLISHABLE_KEY="<your_stripe_publishable_key>" \
  -e STRIPE_SECRET_KEY="<your_stripe_secret_key>" \
  -e STRIPE_WEBHOOK_SECRET="<your_stripe_webhook_secret>" \
  -e EMAIL_ADDRESS="<your_email>" \
  -e EMAIL_PASSWORD="<your_email_password>" \
  -e SMTP_SERVER="smtp.gmail.com" \
  -e SMTP_PORT="587" \
  -e MAPBOX_TOKEN="<your_mapbox_token>" \
  -e TWILIO_ACCOUNT_SID="<your_twilio_account_sid>" \
  -e TWILIO_AUTH_TOKEN="<your_twilio_auth_token>" \
  -e TWILIO_VERIFY_SERVICE_SID="<your_twilio_verify_service_sid>" \
  -e GOOGLE_CLIENT_ID="<your_google_client_id>" \
  -e GOOGLE_CLIENT_SECRET="<your_google_client_secret>" \
  -e GOOGLE_REDIRECT_URI="http://127.0.0.1:8001/api/auth/google/callback" \
  -p 8001:8002 \
  --restart unless-stopped \
  admin-backend:v1.0.0

echo "Admin/Technician backend deployed on port 8001"
