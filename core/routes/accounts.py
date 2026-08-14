from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from core.db import get_db, Account, Post

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])

@router.get("/", response_model=List[Dict[str, Any]])
async def get_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).all()
    return [
        {
            "id": acc.id,
            "platform": acc.platform,
            "name": acc.name,
            "status": acc.status,
            "created_at": acc.created_at.isoformat() if acc.created_at else None
        }
        for acc in accounts
    ]

@router.post("/", response_model=Dict[str, Any])
async def create_account(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    platform = body.get("platform")
    name = body.get("name")
    credentials = body.get("credentials", {})
    
    if not platform or not name:
        raise HTTPException(status_code=400, detail="Platform and name are required")
        
    account = Account(platform=platform, name=name, credentials=credentials)
    db.add(account)
    db.commit()
    db.refresh(account)
    
    return {
        "id": account.id,
        "platform": account.platform,
        "name": account.name,
        "status": account.status
    }

@router.get("/{account_id}/posts")
async def get_account_posts(account_id: int, limit: int = 50, offset: int = 0, status: str = "", db: Session = Depends(get_db)):
    query = db.query(Post).filter(Post.account_id == account_id)
    
    if status:
        if status == "published":
            query = query.filter(Post.published == True)
        else:
            query = query.filter(Post.status == status)
            
    total = query.count()
    posts = query.order_by(Post.created_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for p in posts:
        import json
        topic = p.topic
        try:
            if topic and topic.startswith("{"):
                topic = json.loads(topic).get("sujet", topic)
        except:
            pass
            
        result.append({
            "id": p.id,
            "folder": p.folder_name,
            "persona": p.persona,
            "topic": topic,
            "status": p.status,
            "published": p.published,
            "preview": p.content_text[:200] if p.content_text else "",
            "has_image": p.has_image,
            "image_filename": p.image_filename,
            "image_failed": p.image_failed,
            "has_reel": p.has_reel,
            "llm_provider": p.llm_provider,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })
        
    return {
        "posts": result,
        "total": total,
        "has_more": offset + limit < total
    }
