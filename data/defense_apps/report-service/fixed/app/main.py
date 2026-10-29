"""Tallyboard: monthly spending reports."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from .models import MonthComparison, MonthlyReport
from .reports import ReportService, UnknownMonth
from .warehouse import WarehouseClient

app = FastAPI(title="Tallyboard", version="2.3.1")

service = ReportService(WarehouseClient())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/reports")
async def list_reports() -> dict:
    return {"months": service.available_months()}


@app.get("/reports/{month}", response_model=MonthlyReport)
async def monthly_report(month: str) -> MonthlyReport:
    try:
        return await service.monthly_report(month)
    except UnknownMonth:
        raise HTTPException(status_code=404, detail=f"No data for {month}")


@app.get("/reports/{month}/compare/{previous}", response_model=MonthComparison)
async def compare_months(month: str, previous: str) -> MonthComparison:
    try:
        return await service.compare(month, previous)
    except UnknownMonth as exc:
        raise HTTPException(status_code=404, detail=f"No data for {exc}")


@app.get("/reports/{month}/export.csv", response_class=PlainTextResponse)
async def export_csv(month: str) -> str:
    try:
        return await service.export_csv(month)
    except UnknownMonth:
        raise HTTPException(status_code=404, detail=f"No data for {month}")
