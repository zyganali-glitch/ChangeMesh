import os
from typing import ClassVar


class WorktreeGuard:
    """Scoped write allowlist for synthetic target repository.

    Confines Migration Engineer writes to approved paths only.
    MUST NOT allow mutation of:
    - ChangeMesh governance repo paths
    - Unrelated fixture paths
    - Arbitrary filesystem paths
    - Protected/live production targets
    """

    GOVERNANCE_PATHS: ClassVar[frozenset[str]] = frozenset(
        {
            "AGENTS.md",
            "CHANGEMESH_RULES.md",
            "README.md",
            "README.tr.md",
            "plans/",
            "docs/",
            ".agents/",
            "domain/",
            "src/",
            "tests/",
            "integrations/",
            "events/",
            "tools/",
            "scripts/",
        }
    )

    def __init__(self, allowed_roots: list[str]):
        """Initialize with list of allowed root directories for writes."""
        self._allowed_roots = tuple(os.path.normpath(os.path.abspath(r)) for r in allowed_roots)

    def validate_write_path(self, target_path: str) -> bool:
        """Return True only if target_path is under an allowed root.

        Path traversal attacks (../) are blocked.
        Symlinks are resolved before checking.
        """
        if not self._allowed_roots:
            return False

        abs_target = os.path.normpath(os.path.abspath(target_path))

        # Check against governance paths
        for gov_path in self.GOVERNANCE_PATHS:
            if gov_path.endswith("/"):
                if gov_path[:-1] in target_path.split(os.sep) or gov_path[:-1] in target_path.split(
                    "/"
                ):
                    return False
            else:
                if (
                    target_path.endswith(gov_path)
                    or gov_path in target_path.split(os.sep)
                    or gov_path in target_path.split("/")
                ):
                    return False

        for root in self._allowed_roots:
            try:
                # commonpath raises ValueError if paths are on different drives
                if os.path.commonpath([root, abs_target]) == root:
                    return True
            except ValueError:
                continue

        return False

    def validate_paths(self, paths: list[str]) -> tuple[str, ...]:
        """Validate multiple paths. Return tuple of violations. Empty = all valid."""
        violations = []
        for p in paths:
            if not self.validate_write_path(p):
                violations.append(p)
        return tuple(violations)
