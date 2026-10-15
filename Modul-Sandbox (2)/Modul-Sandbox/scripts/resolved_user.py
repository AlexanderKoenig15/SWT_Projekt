from __future__ import annotations

import json
import os
from base64 import b64encode
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from responsibility import GITHUB_PROJECT_BASE_URL

_USERS_BY_EMAIL = {}


@dataclass(frozen=True)
class ResolvedUser:
    """A person attributed in content, resolved to a directory identity where possible.

    The optional members mirror the GitHub "Get a user" payload. Only ``name``,
    ``email`` and ``html_url`` are populated by the Azure DevOps fallback.
    """

    name: str

    # Identity.
    login: str | None = None
    id: int | None = None
    node_id: str | None = None
    type: str | None = None
    user_view_type: str | None = None
    site_admin: bool | None = None
    ldap_dn: str | None = None

    # Profile.
    email: str | None = None
    company: str | None = None
    blog: str | None = None
    location: str | None = None
    bio: str | None = None
    hireable: bool | None = None
    twitter_username: str | None = None
    notification_email: str | None = None

    # Links.
    html_url: str | None = None
    url: str | None = None
    avatar_url: str | None = None
    gravatar_id: str | None = None
    followers_url: str | None = None
    following_url: str | None = None
    gists_url: str | None = None
    starred_url: str | None = None
    subscriptions_url: str | None = None
    organizations_url: str | None = None
    repos_url: str | None = None
    events_url: str | None = None
    received_events_url: str | None = None

    # Counters.
    public_repos: int | None = None
    public_gists: int | None = None
    followers: int | None = None
    following: int | None = None

    created_at: str | None = None
    updated_at: str | None = None
    suspended_at: str | None = None

    # Only returned when the token may see the account's private details.
    private_gists: int | None = None
    total_private_repos: int | None = None
    owned_private_repos: int | None = None
    disk_usage: int | None = None
    collaborators: int | None = None
    two_factor_authentication: bool | None = None
    business_plus: bool | None = None
    plan: dict | None = None

    @property
    def markdown_link(self) -> str:
        return f"[{self.name}]({self.html_url})" if self.html_url else self.name

    @classmethod
    def from_github_api(cls, user: Mapping[str, Any], email: str) -> ResolvedUser:
        """Build from a "Get a user" payload, dropping members this type does not declare."""
        declared = {member.name for member in fields(cls)}
        values = {key: value for key, value in user.items() if key in declared}
        # GitHub reports a private address as null rather than omitting the key.
        values["email"] = values.get("email") or email
        return cls(**values)

    @classmethod
    def resolve(cls, value: str) -> ResolvedUser:
        """Resolve a user from an email address.

        An unresolved user carries the raw attribution as its name, without an email or link."""
        login = value.split("(")[0].strip('" \t\v\r\n').lower()
        if "@" in login:
            return _resolve_by_email(login)
        return cls(name=value)


def _azure_api_request(email: str) -> list[ResolvedUser]:
    """Fallback level 1: Query the Azure DevOps directory for a user by email."""
    query = {
        "api-version": "6.0",
        "searchFilter": "MailAddress",
        "queryMembership": "None",
        "filterValue": email,
    }

    token = os.environ.get("MODUL_DASHBOARD_AZURE_IDENTITY_TOKEN")
    url = f"https://jupiter.tfs.siemens.net/tfs/IPS/_apis/identities?{urlencode(query)}"

    headers = {
        "Accept": "application/json",
        "Authorization": "Basic " + b64encode(f":{token}".encode()).decode(),
    }

    try:
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            data = json.load(response)

    # Not an Azure DevOps user -> Generate a "mailto:" fallback.
    except HTTPError:
        return []

    return [
        ResolvedUser(
            name=user["providerDisplayName"],
            email=address,
            html_url=f"https://teams.microsoft.com/l/chat/0/0?users={quote(address)}",
        )
        for user in data["value"]
        if (address := user["properties"].get("Mail", {}).get("$value") or email)
    ]


def _github_api_request(email: str) -> list[ResolvedUser]:
    """Query GitHub for a user by username, deduced from their email address."""
    token = os.environ.get("MODUL_DASHBOARD_GITHUB_IDENTITY_TOKEN")
    login = quote(email[: email.index("@")].replace(".", "-"))
    url = f"{GITHUB_PROJECT_BASE_URL}/api/v3/users/{login}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }

    try:
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            user = json.load(response)

    # Not a GitHub Enterprise user -> fall back to the Azure DevOps directory.
    except HTTPError:
        return _azure_api_request(email)

    return [ResolvedUser.from_github_api(user, email)]


def _user_from_email(email: str) -> ResolvedUser:
    """Build a mailto-only user, rendering ``given.family@host`` as ``Family, Given``."""
    parts = email[: email.index("@")].split(".")
    if len(parts) > 1 and parts[-1] == "ext":  # Contractor marker, not a name.
        parts.pop()
    parts = [part.title() for part in parts]
    name = f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else parts[0]
    return ResolvedUser(name=name, email=email, html_url=f"mailto:{email}")


def _resolve_by_email(email: str) -> ResolvedUser:
    """Resolve a user by email address. Results are cached in _USERS_BY_EMAIL."""
    try:
        return _USERS_BY_EMAIL[email]
    except KeyError:
        users = _github_api_request(email)

    user = users[0] if users else _user_from_email(email)
    _USERS_BY_EMAIL[email] = user
    return user
