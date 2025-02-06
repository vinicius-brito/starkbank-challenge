import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app, get_db
from database import Base, Invoice
import tempfile
import os

# Cria um arquivo temporário para o banco de dados SQLite
@pytest.fixture(scope="session")
def temp_db_file():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        yield tmp.name
    os.unlink(tmp.name)  # Remove o arquivo temporário após os testes

# Configura o banco de dados usando o arquivo temporário
@pytest.fixture
def client(temp_db_file):
    # Configura o banco de dados
    test_engine = create_engine(f"sqlite:///{temp_db_file}")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Substitui a dependência do banco de dados
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)

# Testar callback de criação de invoice
def test_invoice_created(client):
    # Adiciona uma invoice ao banco de dados
    db = next(client.app.dependency_overrides[get_db]())
    invoice = Invoice(invoice_id="123", invoice_status="unrequested")
    db.add(invoice)
    db.commit()

    # Envia a requisição de callback
    response = client.post("/callback", json={
        "event": {"log": {"invoice": {"id": "123"}, "type": "created"}, "subscription": "invoice"}
    })

    assert response.status_code == 200

    # Verifica se o status da invoice foi atualizado
    updated_invoice = db.query(Invoice).filter_by(invoice_id="123").first()
    assert updated_invoice.invoice_status == "created"

    # Fecha a sessão do banco de dados
    db.close()

# Testar callback de invoice paga
def test_invoice_paid(client):
    # Adiciona uma invoice ao banco de dados
    db = next(client.app.dependency_overrides[get_db]())
    invoice = Invoice(invoice_id="456", invoice_status="created")
    db.add(invoice)
    db.commit()

    # Envia a requisição de callback
    response = client.post("/callback", json={
        "event": {"log": {"invoice": {"id": "456", "amount": 1000, "fee": 50}, "type": "credited"}, "subscription": "invoice"}
    })

    assert response.status_code == 200

    # Verifica se o status da invoice foi atualizado
    updated_invoice = db.query(Invoice).filter_by(invoice_id="456").first()
    assert updated_invoice.invoice_status == "paid"

    # Fecha a sessão do banco de dados
    db.close()

# Testar callback de criação de transferência
def test_transfer_created(client):
    # Adiciona uma invoice ao banco de dados
    db = next(client.app.dependency_overrides[get_db]())
    invoice = Invoice(invoice_id="1234", transfer_id="789", invoice_status="paid")
    db.add(invoice)
    db.commit()

    # Envia a requisição de callback
    response = client.post("/callback", json={
        "event": {"log": {"transfer": {"id": "789"}, "type": "created"}, "subscription": "transfer"}
    })

    assert response.status_code == 200

    # Verifica se o status da transferência foi atualizado
    updated_invoice = db.query(Invoice).filter_by(transfer_id="789").first()
    assert updated_invoice.transfer_status == "created"

    # Fecha a sessão do banco de dados
    db.close()

# Testar callback de transferência bem-sucedida
def test_transfer_success(client):
    # Adiciona uma invoice ao banco de dados
    db = next(client.app.dependency_overrides[get_db]())
    invoice = Invoice(invoice_id="101112", transfer_id="12345", invoice_status="paid", transfer_status="created")
    db.add(invoice)
    db.commit()

    # Envia a requisição de callback
    response = client.post("/callback", json={
        "event": {"log": {"transfer": {"id": "12345"}, "type": "success"}, "subscription": "transfer"}
    })

    assert response.status_code == 200

    # Verifica se o status da transferência foi atualizado
    updated_invoice = db.query(Invoice).filter_by(transfer_id="12345").first()
    assert updated_invoice.transfer_status == "completed"

    # Fecha a sessão do banco de dados
    db.close()