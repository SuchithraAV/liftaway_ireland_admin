from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.database import get_db

from core.schemas import PricingRuleCreate, PricingRuleResponse
from sqlalchemy.orm import selectinload
from core.dependencies import get_current_admin

router = APIRouter(prefix="/pricing", tags=["Pricing"])

@router.get("/{sub_service_id}/", response_model=dict)
async def get_sub_service_pricing(
    sub_service_id: int,
    db: AsyncSession = Depends(get_db)
):
    '''Get pricing for a sub-service'''
    result = await db.execute(
        select(SubService)
        .options(selectinload(SubService.service_type))
        .where(
            SubService.id == sub_service_id,
            SubService.is_active == True
        )
    )
    sub_service = result.scalar_one_or_none()
    
    if not sub_service:
        raise HTTPException(status_code=404, detail="Sub-service not found")
    
    return {
        "sub_service_id": sub_service.id,
        "sub_service_name": sub_service.name,
        "service_type_id": sub_service.service_type_id,
        "service_type_name": sub_service.service_type.name,
        "base_price": sub_service.base_price,
        "currency": "GBP"
    }

@router.post("/", response_model=PricingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_pricing_rule(
    pricing_data: PricingRuleCreate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Create new pricing rule (admin only)'''
    new_pricing = PricingRule(**pricing_data.model_dump())
    db.add(new_pricing)
    await db.commit()
    await db.refresh(new_pricing)
    return new_pricing

@router.patch("/{pricing_id}/", response_model=PricingRuleResponse)
async def update_pricing_rule(
    pricing_id: int,
    base_price: float = None,
    price_per_km: float = None,
    is_active: bool = None,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    '''Update pricing rule (admin only)'''
    result = await db.execute(select(PricingRule).where(PricingRule.id == pricing_id))
    pricing = result.scalar_one_or_none()
    
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    
    if base_price is not None:
        pricing.base_price = base_price
    if price_per_km is not None:
        pricing.price_per_km = price_per_km
    if is_active is not None:
        pricing.is_active = is_active
    
    await db.commit()
    await db.refresh(pricing)
    return pricing
