#!/bin/bash

IMAGE_NAME="breakdown-technician-backend"
TAG="vk141"
REGISTRY="your-registry-url"
VERSION="latest"

echo "Building Docker image..."
docker build -t ${IMAGE_NAME}:${TAG} .

echo "Tagging image with version..."
docker tag ${IMAGE_NAME}:${TAG} ${IMAGE_NAME}:${TAG}-${VERSION}

echo "Tagging for registry..."
docker tag ${IMAGE_NAME}:${TAG} ${REGISTRY}/${IMAGE_NAME}:${TAG}
docker tag ${IMAGE_NAME}:${TAG} ${REGISTRY}/${IMAGE_NAME}:${TAG}-${VERSION}

echo "Pushing to registry..."
docker push ${REGISTRY}/${IMAGE_NAME}:${TAG}
docker push ${REGISTRY}/${IMAGE_NAME}:${TAG}-${VERSION}

echo "Done!"
