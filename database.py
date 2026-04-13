from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from config import settings

# SQLite for local dev, Postgres for Railway
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True)
    github_id    = Column(Integer, unique=True, nullable=False)
    username     = Column(String(100), nullable=False)
    avatar_url   = Column(String(500))
    access_token = Column(String(500))
    created_at   = Column(DateTime, default=datetime.utcnow)

    repositories = relationship("Repository", back_populates="owner", cascade="all, delete")


class Repository(Base):
    __tablename__ = "repositories"
    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    github_id    = Column(Integer, unique=True, nullable=False)
    full_name    = Column(String(200), nullable=False)   # owner/repo
    name         = Column(String(100), nullable=False)
    description  = Column(Text)
    private      = Column(Boolean, default=False)
    webhook_id   = Column(Integer)
    active       = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    owner   = relationship("User", back_populates="repositories")
    reviews = relationship("Review", back_populates="repository", cascade="all, delete")


class Review(Base):
    __tablename__ = "reviews"
    id           = Column(Integer, primary_key=True)
    repo_id      = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    pr_number    = Column(Integer, nullable=False)
    pr_title     = Column(String(300))
    pr_url       = Column(String(500))
    pr_author    = Column(String(100))
    status       = Column(String(20), default="pending")  # pending | processing | done | error
    summary      = Column(Text)
    api_changes  = Column(Text)
    breaking     = Column(Boolean, default=False)
    security_issues = Column(Boolean, default=False)
    raw_review   = Column(Text)
    diff_size    = Column(Integer, default=0)
    doc_committed = Column(Boolean, default=False)
    doc_branch   = Column(String(100))
    meta         = Column(JSON, default=dict)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    repository = relationship("Repository", back_populates="reviews")


def init_db():
    Base.metadata.create_all(bind=engine)
