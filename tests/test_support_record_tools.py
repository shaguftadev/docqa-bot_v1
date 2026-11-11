import pytest
from pydantic import ValidationError

from app.tools.support_records import build_order_lookup_tool, build_ticket_lookup_tool


class EmptyLookupSession:
    def __init__(self):
        self.statement = None

    def scalar(self, statement):
        self.statement = statement
        return None


@pytest.mark.parametrize(
    ("builder", "table"),
    [(build_order_lookup_tool, "mock_orders"), (build_ticket_lookup_tool, "support_tickets")],
)
def test_record_tool_scopes_exact_lookup_by_tenant_and_id(builder, table):
    db = EmptyLookupSession()
    result = builder(db).invoke({"tenant_id": "shop-a", "external_id": "ORD-1001"})
    sql = str(db.statement)
    assert f"{table}.tenant_id" in sql
    assert f"{table}.external_id" in sql
    assert result == '{"found": false}'


def test_record_tool_rejects_invalid_identifier_before_query():
    db = EmptyLookupSession()
    tool = build_order_lookup_tool(db)
    with pytest.raises(ValidationError):
        tool.invoke({"tenant_id": "shop-a", "external_id": "../../other-tenant"})
    assert db.statement is None
