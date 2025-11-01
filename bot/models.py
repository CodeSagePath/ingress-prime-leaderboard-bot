from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class VerificationStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Faction(str, Enum):
    enl = "ENL"
    res = "RES"


class GroupPrivacyMode(str, Enum):
    strict = "strict"
    soft = "soft"
    public = "public"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    codename: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    faction: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    submissions: Mapped[list["Submission"]] = relationship(back_populates="agent", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("faction IN ('ENL','RES')", name="agents_faction_check"),
        # Add composite index for better performance on old Android devices
        Index('idx_agent_faction_codename', 'faction', 'codename'),
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    ap: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    time_span: Mapped[str] = mapped_column(String(32), nullable=False, default="ALL TIME")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    agent: Mapped[Agent] = relationship(back_populates="submissions")
    verification: Mapped["Verification"] = relationship(back_populates="submission", uselist=False, cascade="all, delete-orphan")
    
    # Add composite indexes for better performance on old Android devices
    __table_args__ = (
        Index('idx_submission_agent_chat', 'agent_id', 'chat_id'),
        Index('idx_submission_chat_ap', 'chat_id', 'ap'),
        Index('idx_submission_agent_timespan', 'agent_id', 'time_span'),
        CheckConstraint("time_span IN ('ALL TIME', 'LAST 7 DAYS', 'LAST 30 DAYS', 'PAST 7 DAYS', 'PAST 30 DAYS', 'THIS WEEK', 'THIS MONTH', 'LAST WEEK', 'LAST MONTH', 'WEEKLY', 'MONTHLY', 'DAILY')", name="submission_timespan_check"),
    )


class WeeklyStat(Base):
    __tablename__ = "weekly_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    faction: Mapped[str] = mapped_column(String(8), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("faction IN ('ENL','RES')", name="weekly_stats_faction_check"),
        # Add composite indexes for better performance on old Android devices
        Index('idx_weekly_stat_week_faction', 'week_start', 'week_end', 'faction'),
        Index('idx_weekly_stat_agent_category', 'agent_id', 'category'),
    )


class GroupMessage(Base):
    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="group_messages_chat_message_uc"),
        # Add composite index for better performance on old Android devices
        Index('idx_group_message_chat_received', 'chat_id', 'received_at'),
    )


class GroupSetting(Base):
    __tablename__ = "group_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    privacy_mode: Mapped[str] = mapped_column(String(16), nullable=False, default=GroupPrivacyMode.public.value)
    retention_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("privacy_mode IN ('strict','soft','public')", name="group_settings_privacy_mode_check"),
        CheckConstraint("retention_minutes >= 0", name="group_settings_retention_check"),
    )


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Add composite index for better performance on old Android devices
    __table_args__ = (
        Index('idx_pending_action_chat_executed', 'chat_id', 'executed'),
    )


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    screenshot_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=VerificationStatus.pending.value)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    submission: Mapped["Submission"] = relationship(back_populates="verification")

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="verification_status_check"),
        # Add composite indexes for better performance on old Android devices
        Index('idx_verification_status_created', 'status', 'created_at'),
        Index('idx_verification_submission', 'submission_id'),
    )
