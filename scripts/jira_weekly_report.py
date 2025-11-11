"""Generate and email Jira weekly report using Jira REST API."""
from __future__ import annotations

import argparse
import datetime as dt
import email.message
import logging
import os
import smtplib
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

@dataclass
class JiraConfig:
    base_url: str
    project_key: str
    auth_email: str
    api_token: str
    verify_ssl: bool = True

    @classmethod
    def from_env(cls) -> "JiraConfig":
        missing = [
            name
            for name in ["JIRA_BASE_URL", "JIRA_PROJECT_KEY", "JIRA_AUTH_EMAIL", "JIRA_API_TOKEN"]
            if not os.getenv(name)
        ]
        if missing:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            base_url=os.environ["JIRA_BASE_URL"].rstrip("/"),
            project_key=os.environ["JIRA_PROJECT_KEY"],
            auth_email=os.environ["JIRA_AUTH_EMAIL"],
            api_token=os.environ["JIRA_API_TOKEN"],
            verify_ssl=os.environ.get("JIRA_VERIFY_SSL", "true").lower() == "true",
        )


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        missing = [
            name
            for name in ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_SENDER", "SMTP_RECIPIENT"]
            if not os.getenv(name)
        ]
        if missing:
            raise EnvironmentError(f"Missing required SMTP environment variables: {', '.join(missing)}")
        return cls(
            host=os.environ["SMTP_HOST"],
            port=int(os.environ["SMTP_PORT"]),
            username=os.environ["SMTP_USERNAME"],
            password=os.environ["SMTP_PASSWORD"],
            sender=os.environ["SMTP_SENDER"],
            recipient=os.environ["SMTP_RECIPIENT"],
            use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
        )


@dataclass
class JiraIssueSummary:
    created_count: int
    resolved_count: int
    open_count: int
    issue_keys: Dict[str, List[str]]


def build_jql(project_key: str, start: dt.datetime, end: dt.datetime, extra_filters: str = "") -> Dict[str, str]:
    date_range = f" >= '{start.strftime('%Y-%m-%d')}' AND created <= '{end.strftime('%Y-%m-%d')}'"
    created_clause = f"project = {project_key} AND created{date_range}"
    resolved_clause = f"project = {project_key} AND resolved >= '{start.strftime('%Y-%m-%d')}' AND resolved <= '{end.strftime('%Y-%m-%d')}'"
    open_clause = f"project = {project_key} AND statusCategory != Done AND updated >= '{start.strftime('%Y-%m-%d')}'"

    if extra_filters:
        created_clause += f" AND {extra_filters}"
        resolved_clause += f" AND {extra_filters}"
        open_clause += f" AND {extra_filters}"

    return {
        "created": created_clause,
        "resolved": resolved_clause,
        "open": open_clause,
    }


def call_jira_api(config: JiraConfig, jql: str) -> Tuple[int, List[str]]:
    url = f"{config.base_url}/rest/api/3/search"
    params = {"jql": jql, "fields": "key", "maxResults": 1000}
    try:
        response = requests.get(
            url,
            params=params,
            auth=(config.auth_email, config.api_token),
            headers={"Accept": "application/json"},
            verify=config.verify_ssl,
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.error("Failed to call Jira API: %s", exc)
        raise

    if response.status_code != 200:
        logger.error("Jira API returned %s: %s", response.status_code, response.text)
        raise RuntimeError(f"Jira API error {response.status_code}")

    data = response.json()
    issue_keys = [issue["key"] for issue in data.get("issues", [])]
    return data.get("total", len(issue_keys)), issue_keys


def summarize_issues(config: JiraConfig, start: dt.datetime, end: dt.datetime, extra_filters: str = "") -> JiraIssueSummary:
    jql_queries = build_jql(config.project_key, start, end, extra_filters)
    counts: Dict[str, int] = {}
    issue_keys: Dict[str, List[str]] = {}

    for label, jql in jql_queries.items():
        total, keys = call_jira_api(config, jql)
        counts[label] = total
        issue_keys[label] = keys
        logger.info("%s issues: %s", label.capitalize(), total)

    return JiraIssueSummary(
        created_count=counts.get("created", 0),
        resolved_count=counts.get("resolved", 0),
        open_count=counts.get("open", 0),
        issue_keys=issue_keys,
    )


def build_email_body(summary: JiraIssueSummary, config: JiraConfig) -> str:
    lines = ["<h2>Weekly Jira Project Summary</h2>"]
    lines.append("<ul>")
    lines.append(f"  <li>Issues created: <strong>{summary.created_count}</strong></li>")
    lines.append(f"  <li>Issues resolved: <strong>{summary.resolved_count}</strong></li>")
    lines.append(f"  <li>Issues currently open: <strong>{summary.open_count}</strong></li>")
    lines.append("</ul>")
    lines.append("<h3>Issue Links</h3>")

    for label, keys in summary.issue_keys.items():
        lines.append(f"<p><strong>{label.title()} issues</strong>:</p>")
        if not keys:
            lines.append("<p>No issues found.</p>")
            continue
        items = "".join(
            f"<li><a href='{config.base_url}/browse/{key}'>{key}</a></li>"
            for key in keys
        )
        lines.append(f"<ul>{items}</ul>")

    return "\n".join(lines)


def send_email(smtp: SmtpConfig, subject: str, body_html: str) -> None:
    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp.sender
    message["To"] = smtp.recipient
    message.set_content("This report requires an HTML capable email client.")
    message.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
            if smtp.use_tls:
                server.starttls()
            server.login(smtp.username, smtp.password)
            server.send_message(message)
            logger.info("Email successfully sent to %s", smtp.recipient)
    except smtplib.SMTPException as exc:
        logger.error("Failed to send email: %s", exc)
        raise


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Jira weekly report")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back for the report")
    parser.add_argument("--filters", type=str, default="", help="Additional JQL filters (e.g. priority = High)")
    parser.add_argument("--dry-run", action="store_true", help="Print the report without sending email")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    end = dt.datetime.utcnow()
    start = end - dt.timedelta(days=args.days)

    try:
        jira_config = JiraConfig.from_env()
        smtp_config = SmtpConfig.from_env()
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    try:
        summary = summarize_issues(jira_config, start, end, args.filters)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to summarize issues")
        return 2

    body = build_email_body(summary, jira_config)
    subject = f"Weekly Jira Report for {jira_config.project_key} ({start.date()} - {end.date()})"
    print(body)

    if args.dry_run:
        logger.info("Dry run enabled; not sending email")
        return 0

    try:
        send_email(smtp_config, subject, body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send email")
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
