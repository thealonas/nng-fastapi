"""
Report service module - provides report generation functionality.
"""

import datetime
import json
from typing import List, Dict, Any, Optional
from enum import Enum

from pydantic import BaseModel
from nng_sdk.postgres.nng_postgres import NngPostgres


class ReportType(str, Enum):
    USER_ACTIVITY = "user_activity"
    GROUP_STATUS = "group_status"
    VIOLATIONS = "violations"
    TICKETS = "tickets"
    REQUESTS = "requests"
    SYSTEM_OVERVIEW = "system_overview"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    JSON = "json"
    HTML = "html"
    TEXT = "text"


class ReportPeriod(str, Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ALL_TIME = "all_time"
    CUSTOM = "custom"


class ReportConfig(BaseModel):
    report_type: ReportType
    period: ReportPeriod = ReportPeriod.MONTH
    format: ReportFormat = ReportFormat.JSON
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    filters: Dict[str, Any] = {}
    include_details: bool = True


class ReportSection(BaseModel):
    title: str
    data: Dict[str, Any]
    summary: Optional[str] = None


class Report(BaseModel):
    report_id: str
    report_type: ReportType
    title: str
    generated_at: datetime.datetime
    period_start: Optional[datetime.date] = None
    period_end: Optional[datetime.date] = None
    sections: List[ReportSection]
    summary: Dict[str, Any]
    metadata: Dict[str, Any] = {}


class ReportService:
    def __init__(self, postgres: NngPostgres):
        self.postgres = postgres
        self._report_counter = 0

    def _generate_report_id(self) -> str:
        self._report_counter += 1
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        return f"RPT-{timestamp}-{self._report_counter:04d}"

    def _get_period_dates(
        self,
        period: ReportPeriod,
        start_date: datetime.date = None,
        end_date: datetime.date = None
    ) -> tuple:
        today = datetime.date.today()
        
        if period == ReportPeriod.TODAY:
            return today, today
        elif period == ReportPeriod.WEEK:
            start = today - datetime.timedelta(days=7)
            return start, today
        elif period == ReportPeriod.MONTH:
            start = today - datetime.timedelta(days=30)
            return start, today
        elif period == ReportPeriod.QUARTER:
            start = today - datetime.timedelta(days=90)
            return start, today
        elif period == ReportPeriod.YEAR:
            start = today - datetime.timedelta(days=365)
            return start, today
        elif period == ReportPeriod.CUSTOM:
            return start_date or today, end_date or today
        else:
            return None, None

    async def generate_report(self, config: ReportConfig) -> Report:
        period_start, period_end = self._get_period_dates(
            config.period,
            config.start_date,
            config.end_date
        )
        
        if config.report_type == ReportType.USER_ACTIVITY:
            return await self._generate_user_activity_report(config, period_start, period_end)
        elif config.report_type == ReportType.GROUP_STATUS:
            return await self._generate_group_status_report(config, period_start, period_end)
        elif config.report_type == ReportType.VIOLATIONS:
            return await self._generate_violations_report(config, period_start, period_end)
        elif config.report_type == ReportType.TICKETS:
            return await self._generate_tickets_report(config, period_start, period_end)
        elif config.report_type == ReportType.REQUESTS:
            return await self._generate_requests_report(config, period_start, period_end)
        elif config.report_type == ReportType.SYSTEM_OVERVIEW:
            return await self._generate_system_overview_report(config, period_start, period_end)
        else:
            return await self._generate_custom_report(config, period_start, period_end)

    async def _generate_user_activity_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        all_users = self.postgres.users.get_all_users()
        
        active_users = [u for u in all_users if not u.has_active_violation()]
        banned_users = [u for u in all_users if u.has_active_violation()]
        admin_users = [u for u in all_users if u.admin]
        
        sections = [
            ReportSection(
                title="User Overview",
                data={
                    "total_users": len(all_users),
                    "active_users": len(active_users),
                    "banned_users": len(banned_users),
                    "admin_users": len(admin_users)
                },
                summary=f"Total of {len(all_users)} users registered"
            ),
            ReportSection(
                title="User Distribution",
                data={
                    "with_groups": len([u for u in all_users if u.groups and len(u.groups) > 0]),
                    "without_groups": len([u for u in all_users if not u.groups or len(u.groups) == 0]),
                    "with_violations": len([u for u in all_users if u.violations and len(u.violations) > 0])
                }
            )
        ]
        
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.USER_ACTIVITY,
            title="User Activity Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            summary={
                "total_users": len(all_users),
                "active_rate": round(len(active_users) / len(all_users) * 100, 2) if all_users else 0
            }
        )

    async def _generate_group_status_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        all_groups = self.postgres.groups.get_all_groups()
        
        sections = [
            ReportSection(
                title="Group Overview",
                data={
                    "total_groups": len(all_groups)
                },
                summary=f"Total of {len(all_groups)} groups"
            )
        ]
        
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.GROUP_STATUS,
            title="Group Status Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            summary={"total_groups": len(all_groups)}
        )

    async def _generate_violations_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        banned_users = self.postgres.users.get_banned_users()
        
        violations_by_priority = {}
        for user in banned_users:
            for violation in user.violations:
                if violation.active and violation.priority:
                    priority = violation.priority.value
                    violations_by_priority[priority] = violations_by_priority.get(priority, 0) + 1
        
        sections = [
            ReportSection(
                title="Violations Overview",
                data={
                    "total_banned_users": len(banned_users),
                    "by_priority": violations_by_priority
                },
                summary=f"{len(banned_users)} users with active violations"
            )
        ]
        
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.VIOLATIONS,
            title="Violations Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            summary={"total_violations": len(banned_users)}
        )

    async def _generate_tickets_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        open_tickets = self.postgres.tickets.get_opened_tickets()
        
        by_status = {}
        for ticket in open_tickets:
            status = ticket.status.value if hasattr(ticket.status, 'value') else str(ticket.status)
            by_status[status] = by_status.get(status, 0) + 1
        
        sections = [
            ReportSection(
                title="Tickets Overview",
                data={
                    "total_open": len(open_tickets),
                    "by_status": by_status
                },
                summary=f"{len(open_tickets)} tickets currently open"
            )
        ]
        
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.TICKETS,
            title="Tickets Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            summary={"open_tickets": len(open_tickets)}
        )

    async def _generate_requests_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        pending_requests = self.postgres.requests.get_all_unanswered_requests()
        
        by_type = {}
        for request in pending_requests:
            req_type = request.request_type.value if hasattr(request.request_type, 'value') else str(request.request_type)
            by_type[req_type] = by_type.get(req_type, 0) + 1
        
        sections = [
            ReportSection(
                title="Requests Overview",
                data={
                    "total_pending": len(pending_requests),
                    "by_type": by_type
                },
                summary=f"{len(pending_requests)} requests pending review"
            )
        ]
        
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.REQUESTS,
            title="Requests Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            summary={"pending_requests": len(pending_requests)}
        )

    async def _generate_system_overview_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        all_users = self.postgres.users.get_all_users()
        all_groups = self.postgres.groups.get_all_groups()
        open_tickets = self.postgres.tickets.get_opened_tickets()
        pending_requests = self.postgres.requests.get_all_unanswered_requests()
        unreviewed_logs = self.postgres.watchdog.get_all_unreviewed_logs()
        
        sections = [
            ReportSection(
                title="System Overview",
                data={
                    "users": {
                        "total": len(all_users),
                        "active": len([u for u in all_users if not u.has_active_violation()])
                    },
                    "groups": {
                        "total": len(all_groups)
                    },
                    "tickets": {
                        "open": len(open_tickets)
                    },
                    "requests": {
                        "pending": len(pending_requests)
                    },
                    "watchdog": {
                        "unreviewed": len(unreviewed_logs)
                    }
                },
                summary="System overview generated successfully"
            )
        ]
        
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.SYSTEM_OVERVIEW,
            title="System Overview Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=sections,
            summary={
                "total_users": len(all_users),
                "total_groups": len(all_groups),
                "open_tickets": len(open_tickets),
                "pending_requests": len(pending_requests)
            }
        )

    async def _generate_custom_report(
        self,
        config: ReportConfig,
        period_start: datetime.date,
        period_end: datetime.date
    ) -> Report:
        return Report(
            report_id=self._generate_report_id(),
            report_type=ReportType.CUSTOM,
            title="Custom Report",
            generated_at=datetime.datetime.now(),
            period_start=period_start,
            period_end=period_end,
            sections=[],
            summary={"message": "Custom report template"}
        )

    def format_report(self, report: Report, format: ReportFormat) -> str:
        if format == ReportFormat.JSON:
            return report.model_dump_json(indent=2)
        elif format == ReportFormat.TEXT:
            return self._format_as_text(report)
        elif format == ReportFormat.HTML:
            return self._format_as_html(report)
        return report.model_dump_json()

    def _format_as_text(self, report: Report) -> str:
        lines = [
            f"{'=' * 60}",
            f"REPORT: {report.title}",
            f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'=' * 60}",
            ""
        ]
        
        for section in report.sections:
            lines.append(f"--- {section.title} ---")
            for key, value in section.data.items():
                lines.append(f"  {key}: {value}")
            if section.summary:
                lines.append(f"  Summary: {section.summary}")
            lines.append("")
        
        lines.append(f"{'=' * 60}")
        lines.append("SUMMARY:")
        for key, value in report.summary.items():
            lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)

    def _format_as_html(self, report: Report) -> str:
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{report.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f5f5f5; }}
        .section h2 {{ margin-top: 0; }}
        table {{ border-collapse: collapse; width: 100%; }}
        td, th {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    </style>
</head>
<body>
    <h1>{report.title}</h1>
    <p>Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
"""
        
        for section in report.sections:
            html += f'<div class="section"><h2>{section.title}</h2>'
            html += "<table>"
            for key, value in section.data.items():
                html += f"<tr><td>{key}</td><td>{value}</td></tr>"
            html += "</table></div>"
        
        html += "</body></html>"
        return html
