from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.database import get_db
from core.models import Category
from core.schemas import CategoryResponse

router = APIRouter(prefix="/categories", tags=["Categories"])

@router.get("/", response_model=List[CategoryResponse])
async def get_categories(db: AsyncSession = Depends(get_db)):
    '''Get all active categories'''
    result = await db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.name)
    )
    categories = result.scalars().all()
    return categories

@router.get("/{category_id}/", response_model=CategoryResponse)
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    '''Get a specific category'''
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.is_active == True
        )
    )
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return category



