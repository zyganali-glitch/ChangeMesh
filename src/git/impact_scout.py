"""
Impact Scout business logic module.
"""

import ast
import os
from collections import deque
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import canonical_json_bytes, sha256_hex


class ScanFindingType(str, Enum):
    FILE_CHANGE = "FILE_CHANGE"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    TEST_AFFECTED = "TEST_AFFECTED"
    MIGRATION_DETECTED = "MIGRATION_DETECTED"
    OPEN_CHANGE_CONFLICT = "OPEN_CHANGE_CONFLICT"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    UNAVAILABLE_INTEGRATION = "UNAVAILABLE_INTEGRATION"


class ScanFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    finding_type: ScanFindingType
    path: str
    reason: str
    source: str
    confidence: str
    related_paths: tuple[str, ...] = ()

    @field_validator("path", "reason", "source", "confidence")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must not be blank")
        return v


class GraphNodeType(str, Enum):
    BACKEND_SERVICE = "BACKEND_SERVICE"
    MIGRATION = "MIGRATION"
    API_CLIENT = "API_CLIENT"
    DASHBOARD = "DASHBOARD"
    DATA_JOB = "DATA_JOB"
    POLICY = "POLICY"
    SCHEMA = "SCHEMA"
    UNKNOWN = "UNKNOWN"


class GraphRelationType(str, Enum):
    DEPENDS_ON = "DEPENDS_ON"
    PRODUCES_DATA_FOR = "PRODUCES_DATA_FOR"
    CONSUMES_DATA_FROM = "CONSUMES_DATA_FROM"
    MIGRATES = "MIGRATES"
    OWNED_BY = "OWNED_BY"
    TESTED_BY = "TESTED_BY"
    GOVERNED_BY = "GOVERNED_BY"


class MetadataGraphNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    node_id: str
    node_type: GraphNodeType
    name: str
    owner: str | None = None
    metadata: dict[str, str] = {}

    @field_validator("node_id", "name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must not be blank")
        return v


class MetadataGraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    target_id: str
    relation_type: GraphRelationType
    metadata: dict[str, str] = {}

    @field_validator("source_id", "target_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must not be blank")
        return v


class MetadataGraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    nodes: dict[str, MetadataGraphNode]
    edges: tuple[MetadataGraphEdge, ...]


class DependencyPath(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    target_id: str
    path: tuple[str, ...]
    relations: tuple[str, ...]
    total_hops: int


class ImpactedAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_id: str
    asset_type: GraphNodeType
    name: str
    owner: str | None
    dependency_path: DependencyPath
    scan_findings: tuple[ScanFinding, ...] = ()
    provenance: str


class BlastRadiusArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: str = "1.0.0"
    change_id: str
    impacted_assets: tuple[ImpactedAsset, ...]
    scan_findings: tuple[ScanFinding, ...]
    contradictions: tuple[str, ...] = ()
    total_impacted_count: int
    deduplication_applied: bool
    evidence_mode: str
    digest: str

    @field_validator("change_id", "evidence_mode", "digest")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must not be blank")
        return v


def build_synthetic_billing_graph() -> MetadataGraph:
    nodes = {
        "billing-api": MetadataGraphNode(
            node_id="billing-api",
            node_type=GraphNodeType.BACKEND_SERVICE,
            name="Billing API",
            owner="team-billing",
        ),
        "billing-migration-001": MetadataGraphNode(
            node_id="billing-migration-001",
            node_type=GraphNodeType.MIGRATION,
            name="Billing Migration 001",
            owner="team-billing",
        ),
        "billing-sdk": MetadataGraphNode(
            node_id="billing-sdk",
            node_type=GraphNodeType.API_CLIENT,
            name="Billing SDK",
            owner="team-platform",
        ),
        "billing-dashboard": MetadataGraphNode(
            node_id="billing-dashboard",
            node_type=GraphNodeType.DASHBOARD,
            name="Billing Dashboard",
            owner="team-analytics",
        ),
        "revenue-etl": MetadataGraphNode(
            node_id="revenue-etl",
            node_type=GraphNodeType.DATA_JOB,
            name="Revenue ETL",
            owner="team-analytics",
        ),
        "billing-policy": MetadataGraphNode(
            node_id="billing-policy",
            node_type=GraphNodeType.POLICY,
            name="Billing Policy",
            owner=None,
        ),
        "invoice-schema": MetadataGraphNode(
            node_id="invoice-schema",
            node_type=GraphNodeType.SCHEMA,
            name="Invoice Schema",
            owner=None,
        ),
    }

    edges = (
        MetadataGraphEdge(
            source_id="billing-migration-001",
            target_id="billing-api",
            relation_type=GraphRelationType.DEPENDS_ON,
        ),
        MetadataGraphEdge(
            source_id="billing-sdk",
            target_id="billing-api",
            relation_type=GraphRelationType.DEPENDS_ON,
        ),
        MetadataGraphEdge(
            source_id="billing-dashboard",
            target_id="billing-api",
            relation_type=GraphRelationType.DEPENDS_ON,
        ),
        MetadataGraphEdge(
            source_id="billing-dashboard",
            target_id="billing-sdk",
            relation_type=GraphRelationType.CONSUMES_DATA_FROM,
        ),
        MetadataGraphEdge(
            source_id="revenue-etl",
            target_id="billing-api",
            relation_type=GraphRelationType.CONSUMES_DATA_FROM,
        ),
        MetadataGraphEdge(
            source_id="billing-policy",
            target_id="billing-api",
            relation_type=GraphRelationType.GOVERNED_BY,
        ),
        MetadataGraphEdge(
            source_id="billing-migration-001",
            target_id="invoice-schema",
            relation_type=GraphRelationType.MIGRATES,
        ),
    )

    return MetadataGraph(nodes=nodes, edges=edges)


class RepositoryScanner:
    SUPPORTED_LANGUAGES: ClassVar[frozenset[str]] = frozenset(
        {".py", ".sql", ".yaml", ".yml", ".json", ".md", ".toml"}
    )

    def scan_files(
        self,
        changed_files: list[str],
        all_files: list[str],
        open_change_files: list[str] | None = None,
    ) -> tuple[ScanFinding, ...]:
        findings = []

        for file in changed_files:
            ext = os.path.splitext(file)[1]
            if ext and ext not in self.SUPPORTED_LANGUAGES:
                findings.append(
                    ScanFinding(
                        finding_type=ScanFindingType.UNSUPPORTED_LANGUAGE,
                        path=file,
                        reason=f"Unsupported language: {ext}",
                        source="repository_scan",
                        confidence="DETERMINISTIC",
                    )
                )
                continue

            findings.append(
                ScanFinding(
                    finding_type=ScanFindingType.FILE_CHANGE,
                    path=file,
                    reason="File changed",
                    source="repository_scan",
                    confidence="DETERMINISTIC",
                )
            )

            if self._detect_migrations(file):
                findings.append(
                    ScanFinding(
                        finding_type=ScanFindingType.MIGRATION_DETECTED,
                        path=file,
                        reason="Migration file detected",
                        source="repository_scan",
                        confidence="DETERMINISTIC",
                    )
                )

            if self._detect_tests(file):
                findings.append(
                    ScanFinding(
                        finding_type=ScanFindingType.TEST_AFFECTED,
                        path=file,
                        reason="Test file affected",
                        source="repository_scan",
                        confidence="DETERMINISTIC",
                    )
                )

        if open_change_files:
            findings.extend(self._check_conflicts(changed_files, open_change_files))

        return tuple(findings)

    def _extract_symbols(self, file_path: str, content: str) -> list[str]:
        if not file_path.endswith(".py"):
            return []
        try:
            tree = ast.parse(content)
            symbols = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(node.name)
            return symbols
        except SyntaxError:
            return []

    def _detect_migrations(self, file_path: str) -> bool:
        path = file_path.lower()
        return "migration" in path or "alembic" in path or "versions" in path

    def _detect_tests(self, file_path: str) -> bool:
        path = file_path.lower()
        name = os.path.basename(path)
        return name.startswith("test_") or name.endswith("_test.py") or "tests/" in path

    def _check_conflicts(
        self, changed_files: list[str], open_change_files: list[str]
    ) -> list[ScanFinding]:
        findings = []
        changed_set = set(changed_files)
        open_set = set(open_change_files)
        overlap = changed_set.intersection(open_set)
        for file in overlap:
            findings.append(
                ScanFinding(
                    finding_type=ScanFindingType.OPEN_CHANGE_CONFLICT,
                    path=file,
                    reason="Conflict with open change",
                    source="conflict_check",
                    confidence="DETERMINISTIC",
                )
            )
        return findings


class GraphTraverser:
    def find_downstream_impact(
        self, graph: MetadataGraph, changed_node_ids: set[str]
    ) -> list[ImpactedAsset]:
        assets = []
        paths = self._bfs_paths(graph, changed_node_ids)
        for p in paths:
            target_node = graph.nodes.get(p.target_id)
            if not target_node:
                continue
            assets.append(
                ImpactedAsset(
                    asset_id=target_node.node_id,
                    asset_type=target_node.node_type,
                    name=target_node.name,
                    owner=target_node.owner if target_node.owner else "unknown",
                    dependency_path=p,
                    provenance="metadata_graph",
                )
            )
        return assets

    def _bfs_paths(self, graph: MetadataGraph, start_ids: set[str]) -> list[DependencyPath]:
        downstream: dict[str, list[tuple[str, GraphRelationType]]] = {}
        for edge in graph.edges:
            if edge.target_id not in downstream:
                downstream[edge.target_id] = []
            downstream[edge.target_id].append((edge.source_id, edge.relation_type))

        all_paths = []
        for start_id in start_ids:
            if start_id not in graph.nodes:
                continue
            queue: deque[tuple[str, list[str], list[str]]] = deque(
                [(start_id, [start_id], [])]
            )
            visited = {start_id}

            while queue:
                curr_id, path_nodes, path_rels = queue.popleft()
                if curr_id in downstream:
                    for next_id, rel in downstream[curr_id]:
                        if next_id not in visited:
                            visited.add(next_id)
                            new_path_nodes = path_nodes + [next_id]
                            new_path_rels = path_rels + [rel.value]
                            all_paths.append(
                                DependencyPath(
                                    source_id=start_id,
                                    target_id=next_id,
                                    path=tuple(new_path_nodes),
                                    relations=tuple(new_path_rels),
                                    total_hops=len(new_path_rels),
                                )
                            )
                            queue.append((next_id, new_path_nodes, new_path_rels))
        return all_paths


class BlastRadiusMerger:
    def merge(
        self,
        change_id: str,
        scan_findings: tuple[ScanFinding, ...],
        impacted_assets: tuple[ImpactedAsset, ...],
        evidence_mode: str = "FIXTURE",
    ) -> BlastRadiusArtifact:

        asset_map: dict[str, ImpactedAsset] = {}
        contradictions: list[str] = []
        deduplication_applied = False

        for asset in impacted_assets:
            if asset.asset_id in asset_map:
                deduplication_applied = True
                existing = asset_map[asset.asset_id]
                if existing.owner != asset.owner:
                    contradictions.append(
                        f"Owner contradiction for {asset.asset_id}: "
                        f"{existing.owner} vs {asset.owner}"
                    )
            else:
                asset_map[asset.asset_id] = asset

        merged_assets = tuple(asset_map.values())

        data_to_hash = {
            "change_id": change_id,
            "impacted_assets": [a.model_dump() for a in merged_assets],
            "scan_findings": [f.model_dump() for f in scan_findings],
            "contradictions": list(contradictions),
            "deduplication_applied": deduplication_applied,
            "evidence_mode": evidence_mode,
        }
        digest = sha256_hex(canonical_json_bytes(data_to_hash))

        return BlastRadiusArtifact(
            change_id=change_id,
            impacted_assets=merged_assets,
            scan_findings=scan_findings,
            contradictions=tuple(contradictions),
            total_impacted_count=len(merged_assets),
            deduplication_applied=deduplication_applied,
            evidence_mode=evidence_mode,
            digest=digest,
        )


class DataHubReadAdapter:
    def __init__(self):
        self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def read_metadata(self, entity_id: str) -> None:
        raise NotImplementedError("DataHub read adapter is NOT_RUN: no access available")
