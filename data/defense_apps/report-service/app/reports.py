"""Monthly report generation."""

from datetime import datetime, timezone

from .models import CategoryTotal, MonthComparison, MonthlyReport, Transaction
from .warehouse import MONTHS, WarehouseClient


class UnknownMonth(Exception):
    pass


class ReportService:
    def __init__(self, warehouse: WarehouseClient) -> None:
        self.warehouse = warehouse

    def available_months(self) -> list[str]:
        return list(MONTHS)

    async def monthly_report(self, month: str) -> MonthlyReport:
        if month not in MONTHS:
            raise UnknownMonth(month)
        rows = self.warehouse.fetch_transactions(month)
        return self._summarize(month, rows)

    @staticmethod
    def _summarize(month: str, rows: list[Transaction]) -> MonthlyReport:
        totals: dict[str, CategoryTotal] = {}
        for row in rows:
            entry = totals.setdefault(
                row.category, CategoryTotal(category=row.category, count=0, total_cents=0)
            )
            entry.count += 1
            entry.total_cents += row.amount_cents
        by_category = sorted(totals.values(), key=lambda c: c.total_cents, reverse=True)
        return MonthlyReport(
            month=month,
            transactions=len(rows),
            total_cents=sum(r.amount_cents for r in rows),
            by_category=by_category,
            largest_cents=max((r.amount_cents for r in rows), default=0),
            generated_at=datetime.now(timezone.utc),
        )

    async def compare(self, month: str, previous: str) -> MonthComparison:
        current = await self.monthly_report(month)
        before = await self.monthly_report(previous)
        before_by_cat = {c.category: c.total_cents for c in before.by_category}
        up, down = [], []
        for cat in current.by_category:
            prior = before_by_cat.get(cat.category, 0)
            if cat.total_cents > prior:
                up.append(cat.category)
            elif cat.total_cents < prior:
                down.append(cat.category)
        change = None
        if before.total_cents:
            change = round(100 * (current.total_cents - before.total_cents) / before.total_cents, 1)
        return MonthComparison(
            month=month,
            previous=previous,
            total_cents=current.total_cents,
            previous_total_cents=before.total_cents,
            change_pct=change,
            categories_up=up,
            categories_down=down,
        )

    async def export_csv(self, month: str) -> str:
        report = await self.monthly_report(month)
        lines = ["category,count,total_dollars"]
        for cat in report.by_category:
            lines.append(f"{cat.category},{cat.count},{cat.total_cents / 100:.2f}")
        return "\n".join(lines) + "\n"
