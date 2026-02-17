from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_user
from core.models import UserRole
from config import settings
import stripe
import logging

logger = logging.getLogger(__name__)

# Initialize Stripe with error handling
try:
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        logger.info(f"Stripe initialized with key: {settings.STRIPE_SECRET_KEY[:7]}...")
    else:
        logger.error("STRIPE_SECRET_KEY not found in settings")
except Exception as e:
    logger.error(f"Failed to initialize Stripe: {e}")

router = APIRouter(prefix="/stripe", tags=["Stripe Payments"])

@router.post("/create-subscription-session/")
async def create_subscription_session(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create Stripe checkout session for technician subscription"""
    logger.info(f"🔔 Subscription request from user: {current_user.email} (role: {current_user.role})")
    
    if current_user.role != UserRole.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Only technicians can subscribe")
    
    try:
        logger.info(f"✅ Creating Stripe session for user {current_user.id} ({current_user.email})")
        logger.info(f"✅ Using Stripe key: {settings.STRIPE_SECRET_KEY[:7]}...")
        logger.info(f"✅ Payment methods: ['card']")
        
        # Mock Stripe session for testing without real account setup
        if settings.STRIPE_SECRET_KEY == "sk_test_51234567890abcdefghijklmnopqrstuvwxyz":
            logger.info("Using mock Stripe session for testing")
            mock_session_id = f"cs_test_{current_user.id[:8]}"
            return {
                'checkout_url': f'http://localhost:8080/mock_payment.html?session_id={mock_session_id}&user={current_user.email}',
                'session_id': mock_session_id
            }
        
        # Real Stripe integration (requires account setup)
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'gbp',
                    'product_data': {
                        'name': 'Technician Monthly Subscription',
                        'description': 'Access to road assistance jobs'
                    },
                    'unit_amount': 2999,  # £29.99
                    'recurring': {
                        'interval': 'month'
                    }
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url='http://localhost:8080/stripe_success.html?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='http://localhost:8080/stripe_cancel.html',
            customer_email=current_user.email,
            metadata={
                'user_id': str(current_user.id),
                'user_role': current_user.role
            }
        )
        
        logger.info(f"✅ Stripe session created successfully: {checkout_session.id}")
        logger.info(f"✅ Checkout URL: {checkout_session.url}")
        
        return {
            'checkout_url': checkout_session.url,
            'session_id': checkout_session.id
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe API Error: {e}")
        logger.error(f"❌ Error Type: {type(e).__name__}")
        logger.error(f"❌ Error Code: {getattr(e, 'code', 'N/A')}")
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        logger.error(f"❌ General Error: {e}")
        logger.error(f"❌ Error Type: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Payment session creation failed: {str(e)}")

@router.post("/webhook/")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        
        # Update user subscription status
        # Add subscription logic here
        logger.info(f"Subscription activated for user {user_id}")
    
    return {"status": "success"}

@router.get("/subscription-status/")
async def get_subscription_status(current_user = Depends(get_current_user)):
    """Get current user's subscription status"""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "subscription_active": True,  # Add real subscription check
        "next_billing_date": "2025-01-26"  # Add real billing date
    }
