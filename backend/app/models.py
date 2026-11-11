from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)
class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    currency: Mapped[str] = mapped_column(String, default="INR")
    email: Mapped[str | None] = mapped_column(String, nullable=True)
class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    number: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    currency: Mapped[str] = mapped_column(String, default="INR")
    total_amount: Mapped[float] = mapped_column(Float)
    previously_invoiced: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String, default="OPEN")
class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    file_hash: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    method: Mapped[str] = mapped_column(String, default="text")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String, default="PENDING", index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    human_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (Index("ix_vendor_invoice", "id"),)
class Review(Base):
    __tablename__ = "manual_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Setting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
