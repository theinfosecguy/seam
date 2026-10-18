"""Detect credentials in memory without verification, configuration, or findings."""

import ast
import json
from collections.abc import Iterator

from detect_secrets.filters.heuristic import is_indirect_reference
from detect_secrets.plugins import (
    artifactory,
    aws,
    azure_storage_key,
    basic_auth,
    cloudant,
    discord,
    github_token,
    gitlab_token,
    ibm_cloud_iam,
    ibm_cos_hmac,
    jwt,
    keyword,
    mailchimp,
    npm,
    openai,
    private_key,
    pypi_token,
    sendgrid,
    slack,
    softlayer,
    square_oauth,
    stripe,
    telegram_token,
    twilio,
)

from seam.constants.security import CREDENTIAL_FIELD_NAMES, MAX_SECRET_PARSE_BYTES

# Use only trusted built-ins; analyze_line/scan_file can verify over the network,
# load configurable filters, and log findings containing raw credentials.
_DETECTORS = (
    artifactory.ArtifactoryDetector(),
    aws.AWSKeyDetector(),
    azure_storage_key.AzureStorageKeyDetector(),
    basic_auth.BasicAuthDetector(),
    cloudant.CloudantDetector(),
    discord.DiscordBotTokenDetector(),
    github_token.GitHubTokenDetector(),
    gitlab_token.GitLabTokenDetector(),
    ibm_cloud_iam.IbmCloudIamDetector(),
    ibm_cos_hmac.IbmCosHmacDetector(),
    jwt.JwtTokenDetector(),
    mailchimp.MailchimpDetector(),
    npm.NpmDetector(),
    openai.OpenAIDetector(),
    private_key.PrivateKeyDetector(),
    pypi_token.PypiTokenDetector(),
    sendgrid.SendGridDetector(),
    slack.SlackDetector(),
    softlayer.SoftlayerDetector(),
    square_oauth.SquareOAuthDetector(),
    stripe.StripeDetector(),
    telegram_token.TelegramBotTokenDetector(),
    twilio.TwilioKeyDetector(),
)
_KEYWORD_DETECTOR = keyword.KeywordDetector()


def _target_name(target: ast.expr) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if (
        isinstance(target, ast.Subscript)
        and isinstance(target.slice, ast.Constant)
        and isinstance(target.slice.value, str)
    ):
        return target.slice.value
    return None


def _credential_field(name: str) -> bool:
    normalized = name.strip()
    if ("." in normalized or "[" in normalized) and len(
        normalized.encode("utf-8")
    ) <= MAX_SECRET_PARSE_BYTES:
        try:
            target = ast.parse(normalized, mode="eval").body
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            normalized = _target_name(target) or normalized
    normalized = normalized.strip("\"'[]").lower().replace("-", "_")
    return normalized in CREDENTIAL_FIELD_NAMES or any(
        normalized.endswith("_" + field) for field in CREDENTIAL_FIELD_NAMES
    )


def _keyword_value(value: str) -> bool:
    assignment = "secret = " + value
    if is_indirect_reference(assignment):
        return False
    reference = value.strip()
    if reference.isidentifier() and reference.isupper():
        return False
    if len(value.encode("utf-8")) <= MAX_SECRET_PARSE_BYTES:
        try:
            literal = ast.literal_eval(value.strip())
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            return isinstance(literal, str) and bool(literal)
    return (
        next(
            _KEYWORD_DETECTOR.analyze_string(
                assignment,
                denylist_regex_to_group=keyword.CONFIG_DENYLIST_REGEX_TO_GROUP,
            ),
            None,
        )
        is not None
    )


def _has_match(text: str) -> bool:
    armored = text.strip()
    if armored[:1] in {"+", "-"} and armored[1:].startswith("-----BEGIN "):
        armored = armored[1:]
    if armored.startswith("-----BEGIN ") and armored.endswith(" PRIVATE KEY-----"):
        return True
    if any(
        next(detector.analyze_string(text), None) is not None for detector in _DETECTORS
    ):
        return True
    if (
        ":" in text.partition("=")[0]
        and len(text.encode("utf-8")) <= MAX_SECRET_PARSE_BYTES
    ):
        try:
            statements = ast.parse(text.lstrip("+- ").rstrip(",")).body
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            if len(statements) == 1 and isinstance(statements[0], ast.AnnAssign):
                annotation = statements[0]
                if annotation.value is not None:
                    text = (
                        f"{ast.unparse(annotation.target)} = "
                        f"{ast.unparse(annotation.value)}"
                    )
                else:
                    names = {
                        node.id
                        for node in ast.walk(annotation.annotation)
                        if isinstance(node, ast.Name)
                    }
                    if names and names <= {"str", "bytes"}:
                        return False
    for delimiter in ("=", ":"):
        name, separator, value = (
            text.lstrip("+- ").removeprefix("export ").partition(delimiter)
        )
        if separator and _credential_field(name) and _keyword_value(value):
            return True
    return False


def _python_literals(text: str) -> Iterator[str]:
    """Normalize literal assignments, including triple quotes and parentheses."""
    # shortcut: literal syntax only; add language parsing for computed secrets.
    if len(text.encode("utf-8")) > MAX_SECRET_PARSE_BYTES:
        return
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, item in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _credential_field(key.value)
                    and isinstance(item, ast.Constant)
                    and isinstance(item.value, str)
                ):
                    yield f"secret = {json.dumps(item.value)}"
            continue
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                name = _target_name(target)
                if name is not None and _credential_field(name):
                    yield f"secret = {json.dumps(value.value)}"


def contains_secret(text: str) -> bool:
    """Return only a verdict; never verify, log, or return credential material.

    Structured credentials and hardcoded keyword assignments are heuristic
    signals. Detection cannot establish absence of secrets.
    """
    pending: list[object] = [text]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    isinstance(key, str)
                    and isinstance(item, str)
                    and _credential_field(key)
                    and _keyword_value(json.dumps(item))
                ):
                    return True
                pending.append(item)
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str):
            # Include adjacent lines for values assigned on the next line.
            previous = ""
            for line in value.splitlines():
                if _has_match(line) or (
                    previous.rstrip().endswith(("=", ":"))
                    and _has_match(previous + "\n" + line)
                ):
                    return True
                previous = line
            if any(_has_match(item) for item in _python_literals(value)):
                return True
            if len(value.encode("utf-8")) > MAX_SECRET_PARSE_BYTES:
                continue
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                continue
            if decoded != value:
                pending.append(decoded)
    return False
