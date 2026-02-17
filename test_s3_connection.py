"""
Test Utho Object Storage Connection
Run this script to verify your Utho Object Storage credentials and bucket access
"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv

load_dotenv()

# UTHO Object Storage Configuration
UTHO_ACCESS_KEY = os.getenv("UTHO_ACCESS_KEY")
UTHO_SECRET_KEY = os.getenv("UTHO_SECRET_KEY")
UTHO_BUCKET = os.getenv("UTHO_BUCKET")
UTHO_ENDPOINT = os.getenv("UTHO_ENDPOINT")
UTHO_BUCKET_URL = os.getenv("UTHO_BUCKET_URL")
UTHO_REGION = os.getenv("UTHO_REGION", "ap-south-1")

def test_object_storage_connection():
    """Test Utho Object Storage connection and bucket access"""
    
    print("=" * 60)
    print("UTHO OBJECT STORAGE CONNECTION TEST")
    print("=" * 60)
    
    # Print configuration
    print("\n📋 Configuration:")
    print(f"   Endpoint: {UTHO_ENDPOINT}")
    print(f"   Bucket: {UTHO_BUCKET}")
    print(f"   Region: {UTHO_REGION}")
    print(f"   Bucket URL: {UTHO_BUCKET_URL}")
    print(f"   Access Key: {UTHO_ACCESS_KEY[:10]}..." if UTHO_ACCESS_KEY else "   Access Key: NOT SET")
    
    if not all([UTHO_ACCESS_KEY, UTHO_SECRET_KEY, UTHO_BUCKET, UTHO_ENDPOINT]):
        print("\n❌ ERROR: Missing required environment variables!")
        print("   Please check your .env file")
        return False
    
    try:
        # Create Object Storage client
        print("\n🔌 Creating Object Storage client...")
        storage_client = boto3.client(
            's3',
            endpoint_url=UTHO_ENDPOINT,
            aws_access_key_id=UTHO_ACCESS_KEY,
            aws_secret_access_key=UTHO_SECRET_KEY,
            region_name=UTHO_REGION,
            config=Config(signature_version='s3v4')
        )
        print("   ✅ Object Storage client created successfully")
        
        # Test bucket access
        print(f"\n🪣 Testing bucket access: {UTHO_BUCKET}")
        response = storage_client.head_bucket(Bucket=UTHO_BUCKET)
        print("   ✅ Bucket is accessible")
        
        # List some objects (if any)
        print(f"\n📂 Listing objects in bucket...")
        response = storage_client.list_objects_v2(Bucket=UTHO_BUCKET, MaxKeys=5)
        
        if 'Contents' in response:
            print(f"   Found {len(response['Contents'])} objects (showing first 5):")
            for obj in response['Contents']:
                print(f"   - {obj['Key']} ({obj['Size']} bytes)")
        else:
            print("   Bucket is empty (no objects found)")
        
        # Test upload (create a test file)
        print(f"\n📤 Testing file upload...")
        test_key = "test/connection_test.txt"
        test_content = "This is a test file to verify Utho Object Storage upload functionality"
        
        storage_client.put_object(
            Bucket=UTHO_BUCKET,
            Key=test_key,
            Body=test_content.encode('utf-8'),
            ContentType='text/plain',
            ACL='public-read'
        )
        print(f"   ✅ Test file uploaded: {test_key}")
        
        # Generate URL
        test_url = f"{UTHO_BUCKET_URL}/{test_key}"
        print(f"   🔗 File URL: {test_url}")
        
        # Test download
        print(f"\n📥 Testing file download...")
        response = storage_client.get_object(Bucket=UTHO_BUCKET, Key=test_key)
        downloaded_content = response['Body'].read().decode('utf-8')
        
        if downloaded_content == test_content:
            print("   ✅ File downloaded and verified successfully")
        else:
            print("   ⚠️ Downloaded content doesn't match uploaded content")
        
        # Clean up test file
        print(f"\n🗑️ Cleaning up test file...")
        storage_client.delete_object(Bucket=UTHO_BUCKET, Key=test_key)
        print("   ✅ Test file deleted")
        
        # Test driver folder structure
        print(f"\n📁 Testing driver folder structure...")
        test_driver_id = "test-driver-123"
        test_driver_key = f"drivers/{test_driver_id}/test_photo.txt"
        
        storage_client.put_object(
            Bucket=UTHO_BUCKET,
            Key=test_driver_key,
            Body=b"Test driver photo",
            ContentType='text/plain',
            ACL='public-read'
        )
        print(f"   ✅ Driver folder created: drivers/{test_driver_id}/")
        
        driver_url = f"{UTHO_BUCKET_URL}/{test_driver_key}"
        print(f"   🔗 Driver file URL: {driver_url}")
        
        # Clean up
        storage_client.delete_object(Bucket=UTHO_BUCKET, Key=test_driver_key)
        print("   ✅ Test driver file deleted")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\n🎉 Your Utho Object Storage configuration is working correctly!")
        print("   You can now use the driver registration endpoint.")
        print("\n📝 Next steps:")
        print("   1. Start the server: uvicorn main:app --reload --port 8001")
        print("   2. Test the endpoint: http://localhost:8001/docs")
        print("   3. Or use the test page: http://localhost:8001/static/driver_registration_upload_test.html")
        
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"\n❌ Object Storage Error ({error_code}): {error_message}")
        
        if error_code == 'NoSuchBucket':
            print(f"\n💡 Bucket '{UTHO_BUCKET}' does not exist.")
            print("   Please create the bucket in Utho dashboard first.")
        elif error_code == 'InvalidAccessKeyId':
            print("\n💡 Invalid access key.")
            print("   Please check UTHO_ACCESS_KEY in .env file")
        elif error_code == 'SignatureDoesNotMatch':
            print("\n💡 Invalid secret key.")
            print("   Please check UTHO_SECRET_KEY in .env file")
        else:
            print(f"\n💡 Please check your Utho Object Storage credentials and bucket configuration")
        
        return False
        
    except Exception as e:
        print(f"\n❌ Unexpected Error: {str(e)}")
        print(f"   Error Type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    test_object_storage_connection()
