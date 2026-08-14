import os
import json
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from core.config import Config

Base = declarative_base()

class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)  # 'facebook', 'linkedin', 'twitter'
    name = Column(String(100), nullable=False)
    credentials = Column(JSON, default=dict)
    settings = Column(JSON, default=dict)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    posts = relationship("Post", back_populates="account", cascade="all, delete-orphan")

class AccessLink(Base):
    __tablename__ = 'access_links'

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(100), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    code = Column(String(20), nullable=False)
    account_ids = Column(Text, nullable=False, default="[]")
    platforms = Column(Text, default="[]")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Post(Base):
    __tablename__ = 'posts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    
    folder_name = Column(String(200), unique=True, nullable=False)
    persona = Column(String(100))
    topic = Column(Text)
    content_text = Column(Text)
    
    status = Column(String(50), default="pending")  # pending, approved, published, corrupted
    published = Column(Boolean, default=False)
    scheduled_time = Column(String(50))
    
    has_image = Column(Boolean, default=False)
    image_filename = Column(String(200))
    image_failed = Column(Boolean, default=False)
    
    has_reel = Column(Boolean, default=False)
    reel_filename = Column(String(200))
    
    llm_provider = Column(String(100))
    llm_model = Column(String(100))
    error_msg = Column(Text)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    account = relationship("Account", back_populates="posts")

class FBAppInvitation(Base):
    __tablename__ = 'fb_app_invitations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)  # ID de l'utilisateur invité (de la table users)
    user_name = Column(String(100), nullable=False)  # Nom de l'utilisateur
    user_code = Column(String(20), nullable=False)  # Code de l'utilisateur
    invited_by = Column(Integer, nullable=False)  # ID de l'admin qui a invité
    status = Column(String(20), default="pending")  # pending, accepted, expired, revoked
    facebook_user_id = Column(String(100))  # Facebook ID (rempli après acceptation)
    notes = Column(Text)  # Notes optionnelles
    invited_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    accepted_at = Column(DateTime)
    expires_at = Column(DateTime)  # Expiration (30 jours par défaut)
    
def is_expired(self):
        """VǸrifie si l'invitation a expirǸ."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

class Client(Base):
    __tablename__ = 'clients'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    email = Column(String(150), default="")
    plan = Column(String(50), default="starter")  # starter, pro, agence
    active = Column(Boolean, default=True)
    # account_ids : liste JSON des comptes rattachés au client (toutes plateformes)
    account_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Database setup
DB_PATH = Config.DATA_DIR / "leads_station.db"
# Ensure data dir exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
