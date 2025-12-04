"""
Reports router module - provides report generation endpoints.
"""

import datetime
from typing import Optional, Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from dependencies import get_db
from auth.actions import ensure_authorization
from nng_sdk.postgres.nng_postgres import NngPostgres
from services.report_service import (
    ReportService,
    ReportConfig,
    ReportType,
    ReportPeriod,
    ReportFormat,
)


class ReportRequest(BaseModel):
    report_type: str
    period: str = "month"
    format: str = "json"
    include_details: bool = True


router = APIRouter()


def parse_report_type(value: str) -> ReportType:
    mapping = {
        "user_activity": ReportType.USER_ACTIVITY,
        "group_status": ReportType.GROUP_STATUS,
        "violations": ReportType.VIOLATIONS,
        "tickets": ReportType.TICKETS,
        "requests": ReportType.REQUESTS,
        "system_overview": ReportType.SYSTEM_OVERVIEW,
    }
    return mapping.get(value, ReportType.SYSTEM_OVERVIEW)


def parse_period(value: str) -> ReportPeriod:
    mapping = {
        "today": ReportPeriod.TODAY,
        "week": ReportPeriod.WEEK,
        "month": ReportPeriod.MONTH,
        "quarter": ReportPeriod.QUARTER,
        "year": ReportPeriod.YEAR,
        "all_time": ReportPeriod.ALL_TIME,
    }
    return mapping.get(value, ReportPeriod.MONTH)


def parse_format(value: str) -> ReportFormat:
    mapping = {
        "json": ReportFormat.JSON,
        "html": ReportFormat.HTML,
        "text": ReportFormat.TEXT,
    }
    return mapping.get(value, ReportFormat.JSON)


@router.post("/reports/generate", tags=["reports"])
async def generate_report(
    request: ReportRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = ReportService(postgres)

    config = ReportConfig(
        report_type=parse_report_type(request.report_type),
        period=parse_period(request.period),
        format=parse_format(request.format),
        include_details=request.include_details,
    )

    report = await service.generate_report(config)
    formatted = service.format_report(report, config.format)

    content_types = {
        ReportFormat.JSON: "application/json",
        ReportFormat.HTML: "text/html",
        ReportFormat.TEXT: "text/plain",
    }

    return Response(content=formatted, media_type=content_types[config.format])


@router.get("/reports/users", tags=["reports"])
async def get_user_report(
    period: str = "month",
    format: str = "json",
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db),
):
    service = ReportService(postgres)

    config = ReportConfig(
        report_type=ReportType.USER_ACTIVITY,
        period=parse_period(period),
        format=parse_format(format),
    )

    report = await service.generate_report(config)
    formatted = service.format_report(report, config.format)

    content_types = {
        ReportFormat.JSON: "application/json",
        ReportFormat.HTML: "text/html",
        ReportFormat.TEXT: "text/plain",
    }

    return Response(content=formatted, media_type=content_types[config.format])


@router.get("/reports/violations", tags=["reports"])
async def get_violations_report(
    period: str = "month",
    format: str = "json",
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db),
):
    service = ReportService(postgres)

    config = ReportConfig(
        report_type=ReportType.VIOLATIONS,
        period=parse_period(period),
        format=parse_format(format),
    )

    report = await service.generate_report(config)
    formatted = service.format_report(report, config.format)

    content_types = {
        ReportFormat.JSON: "application/json",
        ReportFormat.HTML: "text/html",
        ReportFormat.TEXT: "text/plain",
    }

    return Response(content=formatted, media_type=content_types[config.format])


@router.get("/reports/tickets", tags=["reports"])
async def get_tickets_report(
    period: str = "month",
    format: str = "json",
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db),
):
    service = ReportService(postgres)

    config = ReportConfig(
        report_type=ReportType.TICKETS,
        period=parse_period(period),
        format=parse_format(format),
    )

    report = await service.generate_report(config)
    formatted = service.format_report(report, config.format)

    content_types = {
        ReportFormat.JSON: "application/json",
        ReportFormat.HTML: "text/html",
        ReportFormat.TEXT: "text/plain",
    }

    return Response(content=formatted, media_type=content_types[config.format])


@router.get("/reports/system", tags=["reports"])
async def get_system_report(
    period: str = "month",
    format: str = "json",
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db),
):
    service = ReportService(postgres)

    config = ReportConfig(
        report_type=ReportType.SYSTEM_OVERVIEW,
        period=parse_period(period),
        format=parse_format(format),
    )

    report = await service.generate_report(config)
    formatted = service.format_report(report, config.format)

    content_types = {
        ReportFormat.JSON: "application/json",
        ReportFormat.HTML: "text/html",
        ReportFormat.TEXT: "text/plain",
    }

    return Response(content=formatted, media_type=content_types[config.format])
