import hashlib
import re
import sys
from typing import Any, Dict, List, Set

import yaml

MANIFEST_PATH = "docs/DONOR_REUSE_MANIFEST.md"

VALID_REUSE_METHODS: Set[str] = {
    "COPIED",
    "ADAPTED",
    "CLEAN_ROOM_REIMPLEMENTED",
    "IDEA_ONLY",
    "REFERENCE_ONLY",
}
VALID_STATUSES: Set[str] = {
    "DISCOVERED",
    "PIN_REQUIRED",
    "UNDER_REVIEW",
    "BLOCKED",
    "APPROVED_FOR_IMPLEMENTATION",
    "IMPLEMENTED_PENDING_PARITY",
    "VERIFIED",
    "EXCLUDED",
    "SUPERSEDED",
}


def lint_manifest() -> None:
    with open(MANIFEST_PATH, "rb") as f:
        raw_text = f.read()

    sha256 = hashlib.sha256(raw_text).hexdigest()
    text = raw_text.decode("utf-8")

    blocks = re.findall(r"```yaml(.*?)```", text, re.MULTILINE | re.DOTALL)
    components: List[Dict[str, Any]] = []

    for b in blocks:
        try:
            d = yaml.safe_load(b)
            if not isinstance(d, dict):
                print("ERROR: Malformed YAML block found (not a dict).")
                sys.exit(1)
        except yaml.YAMLError as e:
            print(f"ERROR: Malformed YAML block found: {e}")
            sys.exit(1)

        if "component_id" not in d:
            print("ERROR: Missing component_id in YAML block.")
            sys.exit(1)

        comp_id = d["component_id"]

        # Ignore exact schema example
        if comp_id == "DONOR-COMPONENT-NNN":
            continue

        if not comp_id:
            print("ERROR: component_id is empty.")
            sys.exit(1)

        # Validate required fields
        required_fields = [
            "status",
            "donor_id",
            "repository",
            "source_commit",
            "source_paths",
            "license_state",
            "source_behavior",
            "reuse_method",
            "target_paths_or_contracts",
            "required_transformations",
            "forbidden_carry_over",
            "required_tests",
            "competition_introduction_commit",
            "evidence",
            "reviewer",
            "last_reviewed",
        ]
        for field in required_fields:
            if field not in d or not d[field]:
                print(f"ERROR: Component {comp_id} is missing required field '{field}'.")
                sys.exit(1)

        status = d["status"]
        if status not in VALID_STATUSES:
            print(f"ERROR: Component {comp_id} has invalid status '{status}'.")
            sys.exit(1)

        reuse_method = d["reuse_method"]
        if reuse_method not in VALID_REUSE_METHODS:
            print(
                f"ERROR: Component {comp_id} has invalid reuse_method '{reuse_method}'."
                " Must be a single allowed enum value."
            )
            sys.exit(1)

        # Check source commit SHA format
        commit = str(d["source_commit"])
        if not re.match(r"^[0-9a-f]{40}$", commit):
            print(
                f"ERROR: Component {comp_id} has invalid source_commit '{commit}'."
                " Must be a 40-character SHA."
            )
            sys.exit(1)

        # Check competition introduction commit format if VERIFIED
        intro_commit = str(d.get("competition_introduction_commit", "")).strip()
        if status == "VERIFIED":
            if intro_commit == "PENDING" or not re.match(r"^[0-9a-f]{40}$", intro_commit):
                print(
                    f"ERROR: Component {comp_id} is status VERIFIED but "
                    f"competition_introduction_commit is '{intro_commit}'. "
                    "Must be a 40-character commit SHA."
                )
                sys.exit(1)

        components.append(d)

    print(f"SHASUM: {sha256}")
    print(f"Components: {len(components)}")
    print("Manifest linting passed successfully.")


if __name__ == "__main__":
    lint_manifest()
