from enum import StrEnum


class Permission(StrEnum):
    ADMIN_ACCOUNTS_CREATE = "statement.admin.accounts.create"
    ADMIN_ACCOUNTS_UPDATE = "statement.admin.accounts.update"
    ADMIN_ACCOUNTS_GET = "statement.admin.accounts.get"
    ADMIN_ACCOUNTS_DELETE = "statement.admin.accounts.delete"
    ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET = (
        "statement.admin.accounts.ledger.discrepancy.get"
    )
    ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE = (
        "statement.admin.accounts.ledger.discrepancy.resolve"
    )
