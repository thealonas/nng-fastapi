"""
Export router module - provides data export endpoints.
"""

import datetime
from typing import Optional, Annotated, List

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dependencies import get_db
from auth.actions import ensure_authorization
from nng_sdk.postgres.nng_postgres import NngPostgres
from services.export_service import ExportService, ExportConfig, ExportFormat


class ExportRequest(BaseModel):
    format: str = "json"
    pretty_print: bool = False
    fields: Optional[List[str]] = None


router = APIRouter()


@router.get("/export/users", tags=["export"])
async def export_users(
    format: str = "json",
    pretty: bool = False,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db)
):
    service = ExportService(postgres)
    
    export_format = ExportFormat(format) if format in [f.value for f in ExportFormat] else ExportFormat.JSON
    
    config = ExportConfig(
        format=export_format,
        pretty_print=pretty
    )
    
    result = await service.export_users(config)
    
    content_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.CSV: "text/csv",
        ExportFormat.XML: "application/xml"
    }
    
    return Response(
        content=result.content,
        media_type=content_types[export_format],
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        }
    )


@router.get("/export/groups", tags=["export"])
async def export_groups(
    format: str = "json",
    pretty: bool = False,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db)
):
    service = ExportService(postgres)
    
    export_format = ExportFormat(format) if format in [f.value for f in ExportFormat] else ExportFormat.JSON
    
    config = ExportConfig(
        format=export_format,
        pretty_print=pretty
    )
    
    result = await service.export_groups(config)
    
    content_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.CSV: "text/csv",
        ExportFormat.XML: "application/xml"
    }
    
    return Response(
        content=result.content,
        media_type=content_types[export_format],
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        }
    )


@router.get("/export/tickets", tags=["export"])
async def export_tickets(
    format: str = "json",
    pretty: bool = False,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db)
):
    service = ExportService(postgres)
    
    export_format = ExportFormat(format) if format in [f.value for f in ExportFormat] else ExportFormat.JSON
    
    config = ExportConfig(
        format=export_format,
        pretty_print=pretty
    )
    
    result = await service.export_tickets(config)
    
    content_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.CSV: "text/csv",
        ExportFormat.XML: "application/xml"
    }
    
    return Response(
        content=result.content,
        media_type=content_types[export_format],
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        }
    )


@router.get("/export/requests", tags=["export"])
async def export_requests(
    format: str = "json",
    pretty: bool = False,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db)
):
    service = ExportService(postgres)
    
    export_format = ExportFormat(format) if format in [f.value for f in ExportFormat] else ExportFormat.JSON
    
    config = ExportConfig(
        format=export_format,
        pretty_print=pretty
    )
    
    result = await service.export_requests(config)
    
    content_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.CSV: "text/csv",
        ExportFormat.XML: "application/xml"
    }
    
    return Response(
        content=result.content,
        media_type=content_types[export_format],
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        }
    )


@router.get("/export/user/{user_id}", tags=["export"])
async def export_user_data(
    user_id: int,
    format: str = "json",
    pretty: bool = False,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db)
):
    service = ExportService(postgres)
    
    export_format = ExportFormat(format) if format in [f.value for f in ExportFormat] else ExportFormat.JSON
    
    config = ExportConfig(
        format=export_format,
        pretty_print=pretty
    )
    
    result = await service.export_user_data(user_id, config)
    
    content_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.CSV: "text/csv",
        ExportFormat.XML: "application/xml"
    }
    
    return Response(
        content=result.content,
        media_type=content_types[export_format],
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        }
    )
