"""Tests for P-15 Impact Scout."""

import pytest

from src.git.impact_scout import (
    BlastRadiusArtifact,
    BlastRadiusMerger,
    DataHubReadAdapter,
    DependencyPath,
    GraphNodeType,
    GraphRelationType,
    GraphTraverser,
    ImpactedAsset,
    MetadataGraph,
    MetadataGraphEdge,
    MetadataGraphNode,
    RepositoryScanner,
    ScanFinding,
    ScanFindingType,
    build_synthetic_billing_graph,
)


# 1. Contract tests
def test_scan_finding_validation():
    finding = ScanFinding(
        finding_type=ScanFindingType.FILE_CHANGE,
        path="src/main.py",
        reason="File modified",
        source="repository_scan",
        confidence="DETERMINISTIC",
    )
    assert finding.path == "src/main.py"

    with pytest.raises(ValueError):
        ScanFinding(
            finding_type=ScanFindingType.FILE_CHANGE,
            path="",
            reason="File modified",
            source="repository_scan",
            confidence="DETERMINISTIC",
        )

    with pytest.raises(ValueError):
        ScanFinding(
            finding_type=ScanFindingType.FILE_CHANGE,
            path="p",
            reason="r",
            source="s",
            confidence="c",
            extra_field="invalid",
        )


def test_metadata_graph_operations():
    n1 = MetadataGraphNode(node_id="n1", node_type=GraphNodeType.BACKEND_SERVICE, name="N1")
    n2 = MetadataGraphNode(node_id="n2", node_type=GraphNodeType.DASHBOARD, name="N2")
    e1 = MetadataGraphEdge(
        source_id="n2", target_id="n1", relation_type=GraphRelationType.DEPENDS_ON
    )
    graph = MetadataGraph(nodes={"n1": n1, "n2": n2}, edges=(e1,))
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_blast_radius_artifact_validates():
    art = BlastRadiusArtifact(
        change_id="c1",
        impacted_assets=(),
        scan_findings=(),
        total_impacted_count=0,
        deduplication_applied=False,
        evidence_mode="FIXTURE",
        digest="d1",
    )
    assert art.schema_version == "1.0.0"


# 2. Fixture tests
def test_build_synthetic_billing_graph():
    graph = build_synthetic_billing_graph()
    assert len(graph.nodes) == 7
    assert len(graph.edges) == 7
    assert graph.nodes["billing-api"].node_type == GraphNodeType.BACKEND_SERVICE
    assert graph.nodes["billing-migration-001"].node_type == GraphNodeType.MIGRATION
    assert graph.nodes["billing-sdk"].node_type == GraphNodeType.API_CLIENT

    graph2 = build_synthetic_billing_graph()
    assert graph.model_dump() == graph2.model_dump()


# 3. Scanner tests
def test_repository_scanner():
    scanner = RepositoryScanner()
    changed = ["src/main.py", "migrations/001_init.sql", "tests/test_main.py", "unknown.rs"]
    open_ch = ["src/main.py"]
    findings = scanner.scan_files(changed, [], open_ch)

    types = [f.finding_type for f in findings]
    assert ScanFindingType.FILE_CHANGE in types
    assert ScanFindingType.MIGRATION_DETECTED in types
    assert ScanFindingType.TEST_AFFECTED in types
    assert ScanFindingType.UNSUPPORTED_LANGUAGE in types
    assert ScanFindingType.OPEN_CHANGE_CONFLICT in types

    assert len(scanner.scan_files([], [], [])) == 0


def test_repository_scanner_extract_symbols():
    scanner = RepositoryScanner()
    code = "def my_func(): pass\nclass MyClass: pass"
    symbols = scanner._extract_symbols("test.py", code)
    assert "my_func" in symbols
    assert "MyClass" in symbols


# 4. Graph traversal tests
def test_graph_traversal():
    graph = build_synthetic_billing_graph()
    traverser = GraphTraverser()
    assets = traverser.find_downstream_impact(graph, {"billing-api"})

    asset_names = [a.name for a in assets]
    assert "Billing SDK" in asset_names
    assert "Billing Dashboard" in asset_names
    assert "Revenue ETL" in asset_names
    assert "Invoice Schema" not in asset_names

    for a in assets:
        if a.name == "Billing Policy" or a.name == "Invoice Schema":
            assert a.owner == "unknown"
        else:
            assert a.owner is not None


def test_cycle_handling():
    n1 = MetadataGraphNode(node_id="n1", node_type=GraphNodeType.BACKEND_SERVICE, name="N1")
    n2 = MetadataGraphNode(node_id="n2", node_type=GraphNodeType.DASHBOARD, name="N2")
    e1 = MetadataGraphEdge(
        source_id="n2", target_id="n1", relation_type=GraphRelationType.DEPENDS_ON
    )
    e2 = MetadataGraphEdge(
        source_id="n1", target_id="n2", relation_type=GraphRelationType.DEPENDS_ON
    )
    graph = MetadataGraph(nodes={"n1": n1, "n2": n2}, edges=(e1, e2))

    traverser = GraphTraverser()
    assets = traverser.find_downstream_impact(graph, {"n1"})
    assert len(assets) == 1
    assert assets[0].name == "N2"


# 5. Blast radius tests
def test_blast_radius_merger():
    merger = BlastRadiusMerger()
    path1 = DependencyPath(
        source_id="a", target_id="b", path=("a", "b"), relations=("DEPENDS_ON",), total_hops=1
    )
    a1 = ImpactedAsset(
        asset_id="n1",
        asset_type=GraphNodeType.BACKEND_SERVICE,
        name="N1",
        owner="team-a",
        dependency_path=path1,
        provenance="metadata_graph",
    )
    a2 = ImpactedAsset(
        asset_id="n1",
        asset_type=GraphNodeType.BACKEND_SERVICE,
        name="N1",
        owner="team-b",
        dependency_path=path1,
        provenance="metadata_graph",
    )

    f1 = ScanFinding(
        finding_type=ScanFindingType.FILE_CHANGE, path="f1", reason="r", source="s", confidence="c"
    )

    art = merger.merge("change1", (f1,), (a1, a2), evidence_mode="FIXTURE")

    assert art.deduplication_applied is True
    assert len(art.impacted_assets) == 1
    assert len(art.contradictions) == 1
    assert "team-a vs team-b" in art.contradictions[0]

    art2 = merger.merge("change1", (f1,), (a1,), evidence_mode="FIXTURE")
    assert art.digest != art2.digest


# 6. DataHub tests
def test_datahub_adapter():
    adapter = DataHubReadAdapter()
    assert not adapter.is_available
    with pytest.raises(NotImplementedError):
        adapter.read_metadata("e1")


# 7. Security tests
def test_path_traversal():
    finding = ScanFinding(
        finding_type=ScanFindingType.FILE_CHANGE,
        path="../../etc/passwd",
        reason="modified",
        source="scan",
        confidence="DET",
    )
    assert "../../etc" in finding.path


# 8. Forbidden carry-over tests
def test_forbidden_terminology():
    art = BlastRadiusArtifact(
        change_id="1",
        impacted_assets=(),
        scan_findings=(),
        total_impacted_count=0,
        deduplication_applied=False,
        evidence_mode="FIX",
        digest="d",
    )
    dump_str = str(art.model_dump())
    assert "DataHub" not in dump_str
    assert "ContextSeal" not in dump_str
