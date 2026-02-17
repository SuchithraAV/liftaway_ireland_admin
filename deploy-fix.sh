#!/bin/bash

# Deployment Script for OTP Fix
# This script rebuilds and redeploys the backend with proper environment configuration

echo "🚀 Starting deployment with OTP fix..."

# Step 1: Stop existing containers
echo "📦 Stopping existing containers..."
docker-compose down

# Step 2: Rebuild image with no cache
echo "🔨 Rebuilding Docker image (no cache)..."
docker-compose build --no-cache

# Step 3: Start containers
echo "▶️  Starting containers..."
docker-compose up -d

# Step 4: Wait for container to be healthy
echo "⏳ Waiting for container to be healthy..."
sleep 10

# Step 5: Verify environment variables
echo "🔍 Verifying Twilio credentials..."
docker exec admin-backend env | grep TWILIO

# Step 6: Check logs
echo "📋 Checking application logs..."
docker logs admin-backend --tail 50

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Test driver registration: POST /api/auth/register/driver"
echo "2. Test admin registration: POST /api/auth/register/admin"
echo "3. Verify OTP SMS is received"
echo ""
echo "Monitor logs with: docker logs admin-backend -f"
