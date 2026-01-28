"""Privacy utilities for masking sensitive data in traces"""

import re
from typing import Any, Dict


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mask sensitive information in hook data

    This creates a deep copy and masks fields that might contain sensitive user data.
    """
    import copy

    masked = copy.deepcopy(data)

    # Fields to mask completely
    sensitive_fields = [
        "prompt",
        "user_message",
        "agent_message",
        "tool_input",
        "tool_output",
        "mcp_input",
        "command",
        "file_path",
        "edits",
        "transcript_path",
    ]

    for field in sensitive_fields:
        if field in masked:
            if isinstance(masked[field], str):
                masked[field] = "[MASKED]"
            elif isinstance(masked[field], (list, dict)):
                masked[field] = "[MASKED]"

    # Mask email addresses
    if "user_email" in masked and isinstance(masked["user_email"], str):
        masked["user_email"] = mask_email(masked["user_email"])

    # Mask workspace roots (may contain usernames)
    if "workspace_roots" in masked and isinstance(masked["workspace_roots"], list):
        masked["workspace_roots"] = [mask_path(p) for p in masked["workspace_roots"]]

    return masked


def mask_email(email: str) -> str:
    """
    Mask email address while preserving domain

    Example: user@example.com -> u***@example.com
    """
    if "@" not in email:
        return "[MASKED]"

    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"

    return f"{local[0]}***@{domain}"


def mask_path(path: str) -> str:
    """
    Mask potentially sensitive parts of file paths

    Masks username-like components while preserving structure
    """
    # Replace common home directory patterns
    patterns = [
        (r"/home/[^/]+", "/home/[USER]"),
        (r"/Users/[^/]+", "/Users/[USER]"),
        (r"C:\\Users\\[^\\]+", "C:\\Users\\[USER]"),
        (r"/root", "/[USER]"),
    ]

    masked = path
    for pattern, replacement in patterns:
        masked = re.sub(pattern, replacement, masked)

    return masked


def should_mask_field(field_name: str, value: Any) -> bool:
    """
    Determine if a field should be masked based on its name and value

    Returns True if the field likely contains sensitive data
    """
    sensitive_keywords = [
        "prompt",
        "password",
        "secret",
        "token",
        "key",
        "auth",
        "credential",
        "private",
    ]

    field_lower = field_name.lower()

    # Check if field name contains sensitive keywords
    for keyword in sensitive_keywords:
        if keyword in field_lower:
            return True

    # Check if value looks like a token or key (long alphanumeric strings)
    if isinstance(value, str) and len(value) > 32:
        # Check if it's mostly alphanumeric with few spaces
        alphanum_ratio = sum(c.isalnum() for c in value) / len(value)
        if alphanum_ratio > 0.9:
            return True

    return False
