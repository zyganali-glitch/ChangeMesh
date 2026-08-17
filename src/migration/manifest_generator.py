import hashlib
import json

from pydantic import BaseModel, ConfigDict


class ChangedFileEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    content_hash: str  # SHA-256
    change_type: str  # 'ADDED', 'MODIFIED', 'DELETED'
    diff_summary: str


class ChangedFileManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: str = "1.0.0"
    change_id: str
    plan_id: str
    entries: tuple[ChangedFileEntry, ...]
    manifest_hash: str  # SHA-256 of the manifest itself
    # NO deployment/execution claim
    deployment_claim: str = "NONE"  # always NONE - no deployment happened
    evidence_mode: str = "FIXTURE"


class ManifestGenerator:
    """Generate changed-file manifest with deterministic hashes.

    Manifest MUST match actual worktree.
    No deployment/execution claim.
    """

    def generate_manifest(
        self, change_id: str, plan_id: str, file_contents: dict[str, str]
    ) -> ChangedFileManifest:
        entries = []
        for path, content in file_contents.items():
            if content is None:
                # Deleted
                entries.append(
                    ChangedFileEntry(
                        path=path,
                        content_hash=hashlib.sha256(b"").hexdigest(),
                        change_type="DELETED",
                        diff_summary="File deleted",
                    )
                )
            else:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                entries.append(
                    ChangedFileEntry(
                        path=path,
                        content_hash=content_hash,
                        change_type="MODIFIED",  # Simplified
                        diff_summary="File modified/added",
                    )
                )

        # Sort for determinism
        entries.sort(key=lambda x: x.path)

        # Calculate manifest hash deterministically
        manifest_data = {
            "change_id": change_id,
            "plan_id": plan_id,
            "entries": [e.model_dump() for e in entries],
        }
        manifest_json = json.dumps(manifest_data, sort_keys=True)
        manifest_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

        return ChangedFileManifest(
            change_id=change_id,
            plan_id=plan_id,
            entries=tuple(entries),
            manifest_hash=manifest_hash,
        )
