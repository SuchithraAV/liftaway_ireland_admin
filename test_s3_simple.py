import boto3
from botocore.config import Config
from dotenv import load_dotenv
import os

load_dotenv()

UTHO_ACCESS_KEY = os.getenv("UTHO_ACCESS_KEY")
UTHO_SECRET_KEY = os.getenv("UTHO_SECRET_KEY")
UTHO_BUCKET = os.getenv("UTHO_BUCKET")
UTHO_ENDPOINT = os.getenv("UTHO_ENDPOINT")
UTHO_REGION = os.getenv("UTHO_REGION", "ap-south-1")

print("Testing UTHO S3 Connection...")
print(f"Endpoint: {UTHO_ENDPOINT}")
print(f"Bucket: {UTHO_BUCKET}")
print(f"Region: {UTHO_REGION}")

try:
    client = boto3.client(
        's3',
        endpoint_url=UTHO_ENDPOINT,
        aws_access_key_id=UTHO_ACCESS_KEY,
        aws_secret_access_key=UTHO_SECRET_KEY,
        region_name=UTHO_REGION,
        config=Config(signature_version='s3v4')
    )
    
    print("\nTesting bucket access...")
    client.head_bucket(Bucket=UTHO_BUCKET)
    print(f"SUCCESS: Bucket '{UTHO_BUCKET}' is accessible")
    
    print("\nTesting upload...")
    client.put_object(
        Bucket=UTHO_BUCKET,
        Key="test/test.txt",
        Body=b"test",
        ACL='public-read'
    )
    print("SUCCESS: File uploaded")
    
    client.delete_object(Bucket=UTHO_BUCKET, Key="test/test.txt")
    print("SUCCESS: Test file deleted")
    
    print("\nAll tests passed!")
    
except Exception as e:
    print(f"\nERROR: {e}")
    print(f"Error type: {type(e).__name__}")
