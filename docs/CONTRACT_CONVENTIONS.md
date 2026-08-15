# ChangeMesh Contract Conventions Reference

> **Status:** `P-05.06 — IMPLEMENTED & FROZEN`
> **Authority:** `domain/contracts/conventions.py`
> **Date:** 2026-08-15

This document establishes the canonical naming, enum, timestamp, hashing, serialization, and redaction conventions for all ChangeMesh provider-neutral domain contracts.

---

## 1. Naming Conventions

### 1.1 Class and Type Names
- **Rule:** `PascalCase` strictly for all Pydantic models, custom types, and Enum classes (e.g., `ChangeRequest`, `EvidenceRecord`, `EventEnvelope`, `HashAlgorithm`, `UtcDateTime`).
- **Forbidden:** snake_case or camelCase class names.

### 1.2 Field and Function Names
- **Rule:** `snake_case` strictly for all schema fields, model attributes, module-level helper functions, and validator methods (e.g., `schema_version`, `requested_at`, `normalize_utc_datetime`, `sha256_hex`).
- **Exact Schema Version Field:** Always spelled `schema_version` (`str`). Synonyms such as `schemaVersion`, `schema_ver`, `version`, or `version_schema` are rejected.

### 1.3 Enum Member Names and Values
- **Member Identifiers:** `UPPER_SNAKE_CASE` (e.g., `HashAlgorithm.SHA256`, `EvidenceState.PASS`, `AutonomyClass.HUMAN_AUTHORITY_REQUIRED`).
- **Member Values:** Machine-readable, locale-neutral strings.

### 1.4 Identity and Reference Field Distinctions
ChangeMesh enforces clear, intentional distinctions between different identifier scopes:
- `request_id`: Primary identity of an incoming `ChangeRequest` (intent contract).
- `change_request_id`: Reference linking downstream contracts (`EvidenceRecord`, `RehearsalScenario`, `RehearsalResult`, `AutonomyDecision`, `ApprovalCompressionCard`) to an originating `ChangeRequest`.
- `change_id`: Durable saga/event-stream identity spanning the entire lifecycle of a change across distributed boundaries.
- `event_id`: Identity of a single discrete domain event envelope (`EventEnvelope`).
- `memory_id`, `passport_id`, `scenario_id`, `result_id`, `decision_id`, `card_id`, `evidence_id`: Dedicated stable identities for respective contract entities.

---

## 2. Enum Conventions

- **Locale-Neutral:** All enum values are ASCII machine tokens (e.g., `"PASS"`, `"FAIL"`, `"SIMULATION"`, `"sha256"`), never localized strings.
- **Frozen Vocabularies:** Enum members are closed sets. Synonyms or aliases within a single semantic enum are rejected (e.g., `HashAlgorithm` accepts only `"sha256"`, rejecting `"SHA256"`, `"SHA-256"`, `"sha-256"`).
- **Cross-Enum Token Independence:** Distinct semantic enums may legitimately share token strings when semantically appropriate (e.g., `EvidenceState.SIMULATED` vs `ExecutionEvidenceMode.SIMULATION`, `EvidenceState.BLOCKED` vs `AutonomyClass.BLOCKED`).
- **Inheritance:** String-backed enums inherit from `(str, Enum)` for consistent JSON and Pydantic serialization.

---

## 3. Timestamp Conventions

### 3.1 Strict Timezone-Aware UTC Normalization
- **Contract Type:** `UtcDateTime` (defined in `domain/contracts/conventions.py` as `Annotated[datetime, AfterValidator(normalize_utc_datetime)]`).
- **Naive Datetime Rejection:** Timezone-naive datetimes (`tzinfo is None` or `tzinfo.utcoffset() is None`) are rejected with `ValueError` / `ValidationError` across all domain contracts.
- **Offset Normalization:** Aware datetimes with non-UTC offsets (e.g., `2026-08-13T15:00:00-05:00`) are normalized to equivalent UTC instants (`2026-08-13T20:00:00+00:00`) with `tzinfo == timezone.utc`.
- **System-Local Timezone Prohibition:** Normalization never consults or applies the local system clock's timezone offset.

### 3.2 Canonical Wire Format
- **Wire Representation:** RFC 3339 / ISO-8601 UTC string with fixed 6-digit microsecond precision and uppercase `'Z'` suffix:
  ```text
  YYYY-MM-DDTHH:MM:SS.ffffffZ
  ```
  Example: `2026-08-13T20:08:25.000000Z`
- **Helpers:**
  - `normalize_utc_datetime(value: datetime) -> datetime`
  - `format_utc_timestamp(value: datetime) -> str`
  - `parse_utc_timestamp(value: str) -> datetime` (rejects non-canonical or locale formats).

### 3.3 Non-Causal Timestamp Boundary
- Wall-clock timestamps in `EventEnvelope` and execution records are informational metadata for audit and observability.
- Wall-clock timestamps **never** serve as causal ordering authority. Distributed causal ordering is determined strictly by explicit causality chains (`causation_id`, `correlation_id`, and `classify_event_delivery`).

---

## 4. Hashing Conventions

### 4.1 Canonical Hash Algorithm
- **Algorithm:** SHA-256 exclusively.
- **Machine Token:** `"sha256"` (via `HashAlgorithm.SHA256`).
- **Digest Format:** Exactly 64 lowercase hexadecimal characters matching regex `^[0-9a-f]{64}$`.

### 4.2 ArtifactHash Contract
- `ArtifactHash` requires `algorithm: HashAlgorithm` and `digest: str` (validated to 64 lowercase hex characters).
- Frozen and immutable (`extra="forbid", frozen=True`).

### 4.3 Deterministic Model Hashing
- `canonical_model_sha256(model: BaseModel) -> str` computes SHA-256 over `canonical_json_bytes(model)`.
- Models representing the same semantic state produce identical digests regardless of field construction dictionary order or timezone offset representations.

---

## 5. Serialization Conventions

### 5.1 Canonical JSON Format
Deterministic canonical JSON bytes are generated via `canonical_json_bytes(value: Any) -> bytes` according to the following strict rules:
1. **Encoding:** UTF-8 bytes without BOM.
2. **Key Ordering:** Lexicographical sort (`sort_keys=True`).
3. **Separators:** Compact delimiters without whitespace (`separators=(',', ':')`).
4. **Enums:** Serialized to their machine string `.value`.
5. **Datetimes:** Serialized to canonical wire format (`YYYY-MM-DDTHH:MM:SS.ffffffZ`).
6. **Sequences:** Python `list` and `tuple` serialize to JSON arrays `[...]`.
7. **Nulls:** `None` serializes to JSON `null`.
8. **Floating-Point Limits:** `float` `NaN`, `Infinity`, and `-Infinity` are rejected (fail closed).
9. **Unsupported Types:** Unsupported types (e.g. `bytes`, arbitrary objects) fail closed with `TypeError`.
10. **ASCII Independence:** `ensure_ascii=False` to preserve valid UTF-8 characters without escapes.

---

## 6. Redaction Conventions

### 6.1 Sentinel
- `REDACTION_SENTINEL = "[REDACTED]"`

### 6.2 Structural Redaction Helper
- `redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]`
- Case-insensitive key matching against `SECRET_KEY_PATTERNS` (`token`, `access_token`, `refresh_token`, `api_key`, `secret`, `password`, `private_key`, `credential`, `credentials`, `service_account`).
- **Purity:** Pure function that does not mutate input mappings; returns a newly constructed sanitized structure.
- **Recursive:** Recursively traverses nested mappings and sequences.

### 6.3 Security and Boundary Invariants
- **Defense in Depth:** Structural field redaction is a local sanitization helper for logs and displays; it is NOT universal DLP or unstructured text PII detection.
- **Credential Storage Prohibition:** Redaction helpers do NOT authorize storing or passing secret credentials in domain models. ChangeMesh domain contracts strictly forbid credential fields.
- **Hashing vs Redaction:** Hashing a secret value is not redaction. Redaction replaces secret fields with `"[REDACTED]"`.

---

## 7. Provider-Neutrality & Runtime Boundaries

- All convention code lives in `domain/contracts/conventions.py` and depends only on Python standard library (`datetime`, `hashlib`, `json`, `re`, `enum`, `typing`) and `pydantic`.
- Zero dependencies on cloud vendor SDKs (Google Cloud, Pub/Sub, Firestore, Vertex AI, ADK, GitHub, OpenTelemetry).
- P-05.06 provides domain contract conventions; transport, storage, and cloud runtime adapters are implemented in later phases (P-07+).
