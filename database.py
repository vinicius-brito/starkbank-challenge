from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./invoices.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id = Column(String, primary_key=True)
    invoice_status = Column(String, default="unrequested")
    transfer_id = Column(String, default="")
    internal_transfer_id = Column(String, default="")
    transfer_status = Column(String, default="unrequested")

# Cria as tabelas
Base.metadata.create_all(bind=engine)