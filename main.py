from fastapi import FastAPI, Request, Depends
from apscheduler.schedulers.background import BackgroundScheduler
from faker import Faker
import starkbank
from datetime import datetime, timedelta
import logging
import random
import json
import uuid
import uvicorn

from database import SessionLocal, Invoice
from config import get_starkbank_user


# ------------- Definições Iniciais ----------------


app = FastAPI()
logger = logging.getLogger("uvicorn.logger")
starkbank_user = get_starkbank_user()

# Configura o scheduler
scheduler = BackgroundScheduler()

# Gerador de dados fake
fake = Faker('pt_BR')

# Autenticação do SDK da Stark Bank
starkbank.user = starkbank_user

# Arquivo de log para requisições recebidas
WEBHOOK_LOG_FILE = "webhook_requests.log"


# ------------- Helper functions -------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_invoices(db=Depends(get_db)):
    logger.info("Gerando invoices...")
    try:
        num_invoices = 8 + random.randint(0, 4)
        invoices = []
        for _ in range(num_invoices):
            invoice = starkbank.Invoice(
                amount=random.randint(50, 100)*100,
                tax_id=fake.cpf(),
                name=fake.name(),
                due=datetime.now() + timedelta(days=1)
            )
            invoices.append(invoice)

        created_invoices = starkbank.invoice.create(invoices)

        for invoice in created_invoices:
            db_invoice = Invoice(invoice_id=invoice.id, invoice_status="requested",
            internal_transfer_id="", transfer_status="unrequested")
            db.add(db_invoice)
        db.commit()
        logger.info(f"Criados {len(created_invoices)} invoices")
    except Exception as e:
        logger.error(f"Erro ao gerar invoices: {e}")
    finally:
        db.close()


def save_request_to_file(request_data: dict):
    """Salva a requisição no arquivo de log"""
    try:
        with open(WEBHOOK_LOG_FILE, "a", encoding="utf-8") as f:
            json.dump(request_data, f, ensure_ascii=False)
            f.write("\n")  # Adiciona uma nova linha para separar logs
    except Exception as e:
        logger.error(f"Erro ao salvar requisição no arquivo: {e}")


# ------------- Rotas ------------------------------

@app.get("/health-check")
async def health_check():
    return {"status": "ok"}


@app.post("/callback")
async def handle_callback(request: Request, db=Depends(get_db)):
    """
    Webhook para receber callbacks.
    Quatro possíveis eventos foram mapeados:
    
    - invoice.created: Quando uma invoice é criada
    - invoice.credited: Quando uma invoice tem seu valor creditado (pago)
    - transfer.created: Quando uma transferência é criada
    - transfer.success: Quando uma transferência é completada com sucesso

    Cada um desses eventos atualiza o status da invoice (invoice_status ou transfer_status) no banco de dados.
    """
    
    try:
        body = await request.json()
        headers = dict(request.headers)

        # Salva a requisição no arquivo
        request_log = {
            "timestamp": datetime.now().isoformat(),
            "headers": headers,
            "body": body
        }
        save_request_to_file(request_log)
        
        # Captura os dados do evento
        invoice_id = body.get("event", {}).get("log", {}).get("invoice", {}).get("id")
        transfer_id = body.get("event", {}).get("log", {}).get("transfer", {}).get("id")
        status = body.get("event", {}).get("log", {}).get("type")
        subscription = body.get("event", {}).get("subscription")
        invoice_amount = body.get("event", {}).get("log", {}).get("invoice", {}).get("amount")
        invoice_fee = body.get("event", {}).get("log", {}).get("invoice", {}).get("fee")

        logger.info(f"Callback recebido: {subscription} - {status} - {invoice_id} - {transfer_id}")

        if 'invoice' in subscription and status == 'created':
            db_invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
            if db_invoice:
                db_invoice.invoice_status = "created"
                db.commit()
                logger.info(f"Invoice {invoice_id} criada")

        if 'invoice' in subscription and status == "credited":
            db_invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
            if db_invoice:
                db_invoice.invoice_status = "paid"
                db.commit()
                logger.info(f"Invoice {invoice_id} marcada como paga")

                # Solicita a transferência
                transfer = starkbank.Transfer(
                    amount=invoice_amount-invoice_fee,
                    bank_code="20018183",
                    branch_code="0001",
                    account_number="6341320293482496",
                    name="Stark Bank S.A.",
                    tax_id="20.018.183/0001-80",
                    account_type="payment",
                    external_id=str(uuid.uuid4())
                )
                transfer_ = starkbank.transfer.create([transfer])

                db_invoice.transfer_status = "requested"
                db_invoice.transfer_id = transfer_[0].id
                db_invoice.internal_transfer_id = transfer_[0].external_id
                db.commit()
                logger.info(f"Transferência {transfer_id} solicitada para invoice {invoice_id}")
        
        if 'transfer' in subscription and status == "created":
            db_invoice = db.query(Invoice).filter(Invoice.transfer_id == transfer_id).first()
            if db_invoice:
                db_invoice.transfer_status = "created"
                db.commit()
                logger.info(f"Transferência {transfer_id} criada")
        
        if 'transfer' in subscription and status == "success":
            db_invoice = db.query(Invoice).filter(Invoice.transfer_id == transfer_id).first()
            if db_invoice:
                db_invoice.transfer_status = "completed"
                db.commit()
                logger.info(f"Transferência {transfer_id} completada")

        if 'transfer' in subscription and status == "failed":
            db_invoice = db.query(Invoice).filter(Invoice.transfer_id == transfer_id).first()
            if db_invoice:
                db_invoice.transfer_status = "failed"
                db.commit()
                logger.error(f"Transferência {transfer_id} falhou")

        db.close()
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return {"status": "error", "message": str(e)}, 500


# ------------- Main -------------------------------

if __name__ == "__main__":

    # Configura os agendamentos
    scheduler.add_job(generate_invoices, 'interval', hours=3, next_run_time=(datetime.now() + timedelta(seconds=30)))
    scheduler.start()

    uvicorn.run(app, host="0.0.0.0", port=5000)
