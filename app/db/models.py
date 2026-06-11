"""ORM models that mirror the Prisma schema in the dashboard.

Source of truth: bella-casa-dashboard/prisma/schema.prisma. Keep these in sync.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Enums devem usar create_type=False — o Prisma já cria os tipos.
_routing_type = ENUM('matriz', 'remoto', name='RoutingType', create_type=False)
_purchase_purpose = ENUM(
    'reforma', 'casa_nova', 'troca', name='PurchasePurpose', create_type=False
)
_purchase_timeline = ENUM(
    'imediato', '30_dias', 'pesquisando', name='PurchaseTimeline', create_type=False
)
_lead_status = ENUM(
    'novo',
    'em_atendimento',
    'agendado',
    'convertido',
    'frio',
    name='LeadStatus',
    create_type=False,
)
_language = ENUM('pt', 'en', 'es', name='Language', create_type=False)
_conversation_stage = ENUM(
    'qualificacao',
    'handoff',
    'encerrado',
    name='ConversationStage',
    create_type=False,
)


class Seller(Base):
    __tablename__ = 'sellers'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    whatsapp_number: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    total_leads_assigned: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    leads: Mapped[list[Lead]] = relationship(back_populates='assigned_seller')


class Lead(Base):
    __tablename__ = 'leads'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    routing_type: Mapped[str] = mapped_column(_routing_type, nullable=False)
    product: Mapped[str] = mapped_column(String, nullable=False)
    purchase_purpose: Mapped[str] = mapped_column(_purchase_purpose, nullable=False)
    purchase_timeline: Mapped[str] = mapped_column(_purchase_timeline, nullable=False)
    ambient_size: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_seller_id: Mapped[str | None] = mapped_column(
        String, ForeignKey('sellers.id'), nullable=True
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    status: Mapped[str] = mapped_column(_lead_status, default='novo', server_default='novo')
    visit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visit_reminder_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default='false'
    )
    language: Mapped[str] = mapped_column(_language, default='pt', server_default='pt')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assigned_seller: Mapped[Seller | None] = relationship(back_populates='leads')
    conversation: Mapped[Conversation | None] = relationship(
        back_populates='lead', uselist=False, cascade='all, delete-orphan'
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates='lead', cascade='all, delete-orphan'
    )

    __table_args__ = (
        Index('leads_assigned_seller_id_created_at_idx', 'assigned_seller_id', 'created_at'),
        Index('leads_created_at_idx', 'created_at'),
        Index('leads_visit_date_idx', 'visit_date'),
    )


class Conversation(Base):
    __tablename__ = 'conversations'

    lead_id: Mapped[str] = mapped_column(
        String, ForeignKey('leads.id', ondelete='CASCADE'), primary_key=True
    )
    phone: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(
        _conversation_stage, default='qualificacao', server_default='qualificacao'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lead: Mapped[Lead] = relationship(back_populates='conversation')
    messages: Mapped[list[Message]] = relationship(
        back_populates='conversation', cascade='all, delete-orphan'
    )

    __table_args__ = (Index('conversations_phone_idx', 'phone'),)


class Message(Base):
    __tablename__ = 'messages'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(
        String, ForeignKey('conversations.lead_id', ondelete='CASCADE'), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates='messages')

    __table_args__ = (Index('messages_lead_id_timestamp_idx', 'lead_id', 'timestamp'),)


class Reminder(Base):
    __tablename__ = 'reminders'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        String, ForeignKey('leads.id', ondelete='CASCADE'), nullable=False
    )
    phone: Mapped[str] = mapped_column(String, nullable=False)
    lead_name: Mapped[str] = mapped_column(String, nullable=False)
    visit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reminder_scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    lead: Mapped[Lead] = relationship(back_populates='reminders')

    __table_args__ = (
        Index('reminders_sent_reminder_scheduled_for_idx', 'sent', 'reminder_scheduled_for'),
    )


class RoundRobinControl(Base):
    __tablename__ = 'round_robin_control'

    id: Mapped[str] = mapped_column(String, primary_key=True, default='control')
    next_seller_idx: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    seller_order: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default='{}'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Config(Base):
    __tablename__ = 'config'

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
