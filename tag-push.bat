@echo off
SET REGISTRY=your-registry-url
SET IMAGE=breakdown-technician-backend:vk141

docker tag %IMAGE% %REGISTRY%/%IMAGE%
docker push %REGISTRY%/%IMAGE%
