"""Migration state tracking for secret migration workflows."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Default state file location
STATE_FILE = Path.home() / ".claude-vault" / "migration-state.json"


def load_migration_state() -> Dict:
    """
    Load migration state from disk.

    Returns:
        Dict of service migration states
    """
    if not STATE_FILE.exists():
        return {}

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If file is corrupted or unreadable, return empty state
        return {}


def save_migration_state(state: Dict) -> None:
    """
    Save migration state to disk.

    Args:
        state: Migration state dict to save
    """
    # Ensure directory exists
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write state file
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def mark_scanned(service: str, file_paths: List[str], secret_count: int) -> None:
    """
    Mark service as scanned.

    Args:
        service: Service name
        file_paths: List of file paths scanned
        secret_count: Number of secrets detected
    """
    state = load_migration_state()

    # Initialize service state if needed
    if service not in state:
        state[service] = {}

    # Update scan info
    state[service].update(
        {
            "scanned_at": datetime.utcnow().isoformat() + "Z",
            "scanned_files": file_paths,
            "secrets_detected": secret_count,
        }
    )

    save_migration_state(state)


def mark_migrated(service: str, keys: List[str], vault_version: int) -> None:
    """
    Mark service secrets as migrated to Vault.

    Args:
        service: Service name
        keys: List of secret keys migrated
        vault_version: Vault secret version number
    """
    state = load_migration_state()

    # Initialize service state if needed
    if service not in state:
        state[service] = {}

    # Update migration info
    state[service].update(
        {
            "migrated_at": datetime.utcnow().isoformat() + "Z",
            "migrated_keys": keys,
            "vault_version": vault_version,
        }
    )

    save_migration_state(state)


def mark_replaced(service: str, backup_path: str) -> None:
    """
    Mark service files as replaced with tokens.

    Args:
        service: Service name
        backup_path: Path to backup file created
    """
    state = load_migration_state()

    # Initialize service state if needed
    if service not in state:
        state[service] = {}

    # Get existing backup files list
    backup_files = state[service].get("backup_files", [])
    backup_files.append(backup_path)

    # Update replacement info
    state[service].update(
        {
            "replaced_at": datetime.utcnow().isoformat() + "Z",
            "backup_files": backup_files,
        }
    )

    save_migration_state(state)


def get_service_state(service: str) -> Optional[Dict]:
    """
    Get migration state for a specific service.

    Args:
        service: Service name

    Returns:
        Service state dict or None if not found
    """
    state = load_migration_state()
    return state.get(service)


def is_service_scanned(service: str) -> bool:
    """
    Check if service has been scanned.

    Args:
        service: Service name

    Returns:
        True if service has been scanned
    """
    service_state = get_service_state(service)
    return service_state is not None and "scanned_at" in service_state


def is_service_migrated(service: str) -> bool:
    """
    Check if service secrets have been migrated to Vault.

    Args:
        service: Service name

    Returns:
        True if service has been migrated
    """
    service_state = get_service_state(service)
    return service_state is not None and "migrated_at" in service_state


def is_service_replaced(service: str) -> bool:
    """
    Check if service files have been replaced with tokens.

    Args:
        service: Service name

    Returns:
        True if service files have been replaced
    """
    service_state = get_service_state(service)
    return service_state is not None and "replaced_at" in service_state


def get_migration_summary() -> Dict:
    """
    Get summary of all migration states.

    Returns:
        Dict with counts of services in each state
    """
    state = load_migration_state()

    summary = {
        "total_services": len(state),
        "scanned": 0,
        "migrated": 0,
        "replaced": 0,
        "services": list(state.keys()),
    }

    for service in state:
        if is_service_scanned(service):
            summary["scanned"] += 1
        if is_service_migrated(service):
            summary["migrated"] += 1
        if is_service_replaced(service):
            summary["replaced"] += 1

    return summary


def clear_service_state(service: str) -> None:
    """
    Clear migration state for a specific service.

    Args:
        service: Service name
    """
    state = load_migration_state()

    if service in state:
        del state[service]
        save_migration_state(state)


def clear_all_state() -> None:
    """Clear all migration state."""
    save_migration_state({})
