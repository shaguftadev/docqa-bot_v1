"""Insert the portfolio's synthetic order and ticket examples idempotently."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import MockOrder, SupportTicket
from app.db.session import SessionLocal


def seed() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        orders = [
            MockOrder(
                tenant_id="demo", external_id="ORD-1001", status="shipped",
                tracking_number="TRK-9001", estimated_delivery=now + timedelta(days=2),
                items_json=[{"name": "Desk lamp", "quantity": 1}],
            ),
            MockOrder(
                tenant_id="demo", external_id="ORD-1002", status="processing",
                tracking_number=None, estimated_delivery=None,
                items_json=[{"name": "Notebook", "quantity": 2}],
            ),
        ]
        tickets = [
            SupportTicket(
                tenant_id="demo", external_id="TKT-2001", status="open", category="returns",
                priority="normal", subject="Damaged item report",
                details="Synthetic example ticket awaiting support review.",
            ),
            SupportTicket(
                tenant_id="demo", external_id="TKT-2002", status="in_progress", category="billing",
                priority="high", subject="Invoice question",
                details="Synthetic example ticket assigned to the billing team.",
            ),
        ]
        for model, records in ((MockOrder, orders), (SupportTicket, tickets)):
            for record in records:
                exists = db.scalar(select(model.id).where(
                    model.tenant_id == record.tenant_id,
                    model.external_id == record.external_id,
                ))
                if exists is None:
                    db.add(record)
    print("Synthetic demo records are ready: ORD-1001, ORD-1002, TKT-2001, TKT-2002")


if __name__ == "__main__":
    seed()
