"""
Stripe Connect Service - Enhanced version (2025-11-17.preview compatible)

Features:
- create_custom_account(...) -> creates Stripe Custom Connect account, returns full account dict
- attach_bank_account(...) -> attaches external bank account (SEPA/IBAN assumed for EUR)
- create_account_link(...) -> generates onboarding/update Account Link (uses /v1/account_links)
- get_account_status(...) -> retrieves full status
- create_transfer(...) -> creates a Transfer (platform -> connected account)
- create_payout(...) -> creates a payout from connected account to its bank
- get_balance(...) -> retrieve connected account balance
- Raises clear exceptions with Stripe messages; logs tracebacks
"""

import stripe
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from config import settings
from core.models import Driver, DriverBankDetail, DriverDocument
from core.utils.field_encryption import decrypt_email, decrypt_phone, decrypt_field

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeConnectService:
    """Service for Stripe Connect operations"""

    # -----------------------------
    # Helper to normalize Stripe errors
    # -----------------------------
    @staticmethod
    def _format_stripe_error(err: Exception) -> str:
        # prefer Stripe's user_message if present
        try:
            return getattr(err, "user_message", None) or getattr(err, "stripe_message", None) or str(err)
        except Exception:
            return str(err)

    # -----------------------------
    # Create Account Link (onboarding / update)
    # -----------------------------
    @staticmethod
    def create_account_link(
        stripe_account_id: str,
        refresh_url: str,
        return_url: str,
        type: str = "account_onboarding"
    ) -> Dict[str, Any]:
        """
        Creates an account link for onboarding or updating a connected account.
        Returns the account_link object (url, expires_at, etc).
        """
        try:
            link = stripe.AccountLink.create(
                account=stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type=type
            )
            return link
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception("Failed to create account link")
            raise Exception(f"Failed to create account link: {msg}")

    # -----------------------------
    # Create Custom Account
    # -----------------------------
    @staticmethod
    def create_custom_account(
        driver: Driver,
        bank_detail: Optional[DriverBankDetail] = None,
        document: Optional[DriverDocument] = None,
        country: str = "IE",
        ip_address: str = "127.0.0.1",
        raise_on_error: bool = True
    ) -> Dict[str, Any]:
        """
        Create a Stripe Custom Connected Account.

        Params:
        - driver: Driver model instance
        - bank_detail: optional bank details (attach after account creation)
        - document: optional driver document
        - country: country code (default IE)
        - ip_address: ip for tos acceptance
        - raise_on_error: if True, raise exceptions on Stripe errors (recommended for dev).
                          if False, returns {"error": "..."} on failure.

        Returns:
        - On success: dict representation of the Stripe Account object (selected fields included).
        - On failure and raise_on_error=False: {"error": "message"}
        """
        try:
            logger.info(f"[Stripe] Creating connected account for driver {driver.id}")

            # Decrypt encrypted fields for Stripe
            email = decrypt_email(driver.email) if driver.email else ""
            phone = decrypt_phone(driver.phone_number) if driver.phone_number else ""
            full_name = decrypt_field(driver.full_name) if driver.full_name else ""
            address = decrypt_field(driver.address) if driver.address else ""

            # prepare dob
            dob = None
            if getattr(driver, "dob", None):
                dob = {
                    "day": driver.dob.day,
                    "month": driver.dob.month,
                    "year": driver.dob.year
                }

            # split name
            parts = full_name.split(" ", 1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else first_name

            # required capabilities: request both card_payments and transfers
            account = stripe.Account.create(
                type="custom",
                country=country,
                email=email,
                business_type="individual",
                individual={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "phone": phone,
                    "dob": dob,
                    "address": {
                        "line1": address[:200] if address else "",
                        "country": country
                    }
                },
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True}
                },
                tos_acceptance={
                    "date": int(datetime.now().timestamp()),
                    "ip": ip_address
                },
                metadata={
                    "driver_id": str(driver.id),
                    "platform": "road_assistance"
                }
            )

            logger.info(f"[Stripe] Created account {account.id} (payouts_enabled={account.payouts_enabled})")

            # Attach bank account AFTER account creation (if provided)
            attach_result = None
            if bank_detail and getattr(bank_detail, "bank_account_number", None):
                try:
                    attach_result = StripeConnectService.attach_bank_account(
                        stripe_account_id=account.id,
                        bank_detail=bank_detail,
                        account_holder_name=full_name,
                        country=country
                    )
                except Exception as e_attach:
                    # Bank attach can fail while account creation succeeded.
                    # Logger will record it, and decision whether to raise is controlled by raise_on_error.
                    attach_msg = StripeConnectService._format_stripe_error(e_attach)
                    logger.exception(f"[Stripe] Bank attach failed for account {account.id}: {attach_msg}")
                    if raise_on_error:
                        raise Exception(f"Bank attach failed: {attach_msg}")
                    # else continue and return partial info
            # Build response with important fields (and raw object for inspection)
            resp = {
                "stripe_account_id": account.id,
                "payouts_enabled": getattr(account, "payouts_enabled", False),
                "charges_enabled": getattr(account, "charges_enabled", False),
                "details_submitted": getattr(account, "details_submitted", False),
                "requirements": account.requirements.to_dict() if getattr(account, "requirements", None) else {},
                "raw": account,
                "bank_attach": attach_result
            }
            return resp

        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] create_custom_account failed: {msg}")
            if raise_on_error:
                raise Exception(msg)
            return {"error": msg}

    # -----------------------------
    # Create Express Account (with Dashboard Access)
    # -----------------------------
    @staticmethod
    def create_express_account(
        driver: Driver,
        country: str = "IE",
        raise_on_error: bool = True
    ) -> Dict[str, Any]:
        """
        Create a Stripe Express Connected Account.
        
        Express accounts have:
        - Full Stripe Dashboard access (via login links)
        - Stripe handles all compliance/verification UI
        - Simpler integration but less control
        
        Returns account details including stripe_account_id
        """
        try:
            logger.info(f"[Stripe] Creating Express account for driver {driver.id}")
            
            # Decrypt email for Stripe
            email = decrypt_email(driver.email) if driver.email else ""
            
            account = stripe.Account.create(
                type="express",
                country=country,
                email=email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True}
                },
                business_type="individual",
                metadata={
                    "driver_id": str(driver.id),
                    "platform": "road_assistance"
                }
            )
            
            logger.info(f"[Stripe] Created Express account {account.id}")
            
            return {
                "stripe_account_id": account.id,
                "payouts_enabled": getattr(account, "payouts_enabled", False),
                "charges_enabled": getattr(account, "charges_enabled", False),
                "details_submitted": getattr(account, "details_submitted", False),
                "requirements": account.requirements.to_dict() if getattr(account, "requirements", None) else {},
                "raw": account
            }
            
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] create_express_account failed: {msg}")
            if raise_on_error:
                raise Exception(msg)
            return {"error": msg}

    # -----------------------------
    # Attach bank account
    # -----------------------------
    @staticmethod
    def attach_bank_account(
        stripe_account_id: str,
        bank_detail: DriverBankDetail,
        account_holder_name: str,
        country: str = "IE"
    ) -> Dict[str, Any]:
        """
        Attach an external bank account to a connected account.
        For EUR/SEPA countries, bank_detail.bank_account_number is expected as IBAN.
        """
        try:
            logger.info(f"[Stripe] Attaching bank to {stripe_account_id}")

            # Decrypt bank account number
            account_number = decrypt_field(bank_detail.bank_account_number) if bank_detail.bank_account_number else ""

            external_account = stripe.Account.create_external_account(
                stripe_account_id,
                external_account={
                    "object": "bank_account",
                    "country": country,
                    "currency": "eur",
                    "account_holder_name": account_holder_name,
                    "account_holder_type": "individual",
                    "account_number": account_number
                }
            )

            # return some info
            out = {
                "bank_account_id": external_account.id,
                "last4": getattr(external_account, "last4", None),
                "status": getattr(external_account, "status", None)
            }
            logger.info(f"[Stripe] Bank attached: {out}")
            return out

        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] attach_bank_account failed: {msg}")
            raise Exception(msg)

    # -----------------------------
    # Get account status
    # -----------------------------
    @staticmethod
    def get_account_status(stripe_account_id: str) -> Dict[str, Any]:
        try:
            acc = stripe.Account.retrieve(stripe_account_id)
            return {
                "stripe_account_id": stripe_account_id,
                "payouts_enabled": getattr(acc, "payouts_enabled", False),
                "charges_enabled": getattr(acc, "charges_enabled", False),
                "details_submitted": getattr(acc, "details_submitted", False),
                "requirements": acc.requirements.to_dict() if getattr(acc, "requirements", None) else {}
            }
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] get_account_status failed: {msg}")
            raise Exception(msg)

    # -----------------------------
    # Transfer from platform to connected account
    # -----------------------------
    @staticmethod
    def create_transfer(
        stripe_account_id: str,
        amount_in_cents: int,
        currency: str = "eur",
        description: str = "Driver payout",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        try:
            transfer = stripe.Transfer.create(
                amount=amount_in_cents,
                currency=currency,
                destination=stripe_account_id,
                description=description,
                metadata=metadata or {}
            )
            return {
                "transfer_id": transfer.id,
                "amount": transfer.amount,
                "destination": transfer.destination,
                "raw": transfer
            }
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] create_transfer failed: {msg}")
            raise Exception(msg)

    # -----------------------------
    # Create payout from connected account to bank
    # -----------------------------
    @staticmethod
    def create_payout(
        stripe_account_id: str,
        amount_in_cents: int,
        currency: str = "eur",
        description: str = "Bank payout"
    ) -> Dict[str, Any]:
        try:
            payout = stripe.Payout.create(
                amount=amount_in_cents,
                currency=currency,
                description=description,
                stripe_account=stripe_account_id
            )
            return {"payout_id": payout.id, "status": payout.status, "raw": payout}
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] create_payout failed: {msg}")
            raise Exception(msg)

    # -----------------------------
    # Get connected account balance
    # -----------------------------
    @staticmethod
    def get_balance(self_or_stripe_account_id) -> Dict[str, Any]:
        """
        Accepts either stripe_account_id (str) or ignores param and returns platform balance.
        If a stripe_account_id is provided, call stripe.Balance.retrieve(stripe_account=...)
        """
        try:
            if isinstance(self_or_stripe_account_id, str):
                bal = stripe.Balance.retrieve(stripe_account=self_or_stripe_account_id)
            else:
                bal = stripe.Balance.retrieve()
            # aggregate EUR amounts
            available = 0
            pending = 0
            for item in getattr(bal, "available", []):
                if item.currency == "eur":
                    available = item.amount
            for item in getattr(bal, "pending", []):
                if item.currency == "eur":
                    pending = item.amount
            return {"available": available, "pending": pending, "currency": "eur"}
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] get_balance failed: {msg}")
            raise Exception(msg)

    # -----------------------------
    # Create Login Link (for Express/Custom dashboard)
    # -----------------------------
    @staticmethod
    def create_login_link(stripe_account_id: str) -> Dict[str, Any]:
        """
        Creates a single-use login link for the Express Dashboard.
        """
        try:
            link = stripe.Account.create_login_link(stripe_account_id)
            return {
                "url": link.url,
                "created": link.created,
                "raw": link
            }
        except Exception as e:
            msg = StripeConnectService._format_stripe_error(e)
            logger.exception(f"[Stripe] create_login_link failed: {msg}")
            raise Exception(msg)


# singleton
stripe_connect_service = StripeConnectService()
