# Agent.md — ArvanCloud IaaS API Engineering Reference

> **Purpose:** authoritative engineering guide for an AI coding agent working on an ArvanCloud IaaS automation project
> **Reviewed:** 2026-06-29
> **Primary API documentation:** `https://www.arvancloud.ir/api/iaas/3.0.0`
> **IaaS base URL:** `https://napi.arvancloud.ir/ecc/v1`
> **Recommended implementation:** Python 3.12+, `httpx`, `pydantic`, PostgreSQL, Alembic
> **Project phases:** Phase 1 core orchestrator; Phase 2 Telegram interface

---

## 0. Mandatory reading rules for the coding agent

Before changing any code, the agent must read this file completely.

The agent must not guess endpoint paths, HTTP methods, authentication headers, request field names, response structures, server states, report metric names, traffic units, billing-cycle boundaries, write retry safety, or delete/snapshot/power-off/IP-cleanup behavior.

When an item is not completely confirmed, mark it with:

```text
NEEDS_LIVE_VALIDATION
```

and add a contract test or read-only probe before using it in production code.

Use these evidence labels in code comments and design notes:

```text
OFFICIAL_VERIFIED
    Confirmed in current ArvanCloud product/API documentation.

SDK_SNAPSHOT
    Extracted from a generated SDK/OpenAPI snapshot.
    Must be checked against the current official API.

LIVE_VERIFIED
    Confirmed with a sanitized response from an authorized test account.

INFERRED
    Architectural inference. Never treat as an API contract.

UNKNOWN
    Not yet confirmed. Production code must fail closed.
```

Priority of truth:

```text
1. Sanitized live response from the current official endpoint
2. Current official ArvanCloud API documentation
3. Current official ArvanCloud product documentation
4. Generated OpenAPI/SDK snapshot
5. Existing project code
6. Assumption or memory
```

If two sources conflict, do not silently select one. Record the conflict and run controlled validation.

## 1. Scope of this document

This file is primarily an API and implementation reference for the coding agent. It defines authentication, URL construction, required headers, discovery flows, server lifecycle, bootstrap, health verification, traffic accounting, handover, power-off, deletion, idempotency, retries, error handling, persistence, audit logs, contract tests, and Phase 2 Telegram boundaries.

This document is not a substitute for the provider's current API schema. It is designed to prevent undocumented assumptions.

## 2. Product boundary and account authorization

The orchestrator may manage multiple ArvanCloud accounts or workspaces only when the operator is authorized to administer them.

Do not implement automatic account creation, CAPTCHA/KYC/identity/registration bypass, fake-account enrollment, credential harvesting, free-tier farming, or automated behavior intended to evade provider billing or Fair Usage controls.

Multi-account handover must be disabled by default and enabled only for an explicitly authorized account pool:

```yaml
account_pool:
  mode: authorized_multi_tenant
  allow_cross_account_handover: false
```

Enabling it requires a stored approval reference:

```yaml
account_pool:
  allow_cross_account_handover: true
  approval_reference: "ticket-or-contract-reference"
```

## 3. Authentication

### 3.1 Machine User access key

Authentication uses a Machine User access key. Official documentation states the key is used in the `Authorization` request header, acts like a password, must be stored securely, cannot be recovered after the creation dialog is closed, and is displayed similarly to:

```text
apikey XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

Source: `https://docs.arvancloud.ir/fa/developer-tools/api/api-key`

### 3.2 Correct header behavior

Official API usage examples show:

```http
Authorization: <MU-KEY>
Accept: application/json
```

`<MU-KEY>` means the exact Machine User key copied from the panel. Because the generated key is displayed with the `apikey` prefix, store the complete value and send it verbatim.

Recommended configuration:

```yaml
arvan:
  base_url: https://napi.arvancloud.ir/ecc/v1
  authorization_value_env: ARVAN_MU_KEY
```

Correct request construction:

```python
headers = {
    "Authorization": settings.arvan_mu_key,
    "Accept": "application/json",
}
```

Do not automatically prepend `Bearer`, prepend a second `apikey`, or strip the `apikey` prefix unless a live test proves that the stored value excludes it.

### 3.3 Authentication failure

Official documentation gives this example:

```json
{
  "message": "Unauthenticated."
}
```

Treat HTTP 401 and this message as `AUTH_INVALID`. Treat HTTP 403 separately as `AUTH_PERMISSION_DENIED`; a valid key may still lack IaaS permission.

### 3.4 Secret handling rules

Never store the key in Git, put a real key in `.env.example`, print it in logs, include it in exception text, send it through Telegram, save request headers in audit payloads, embed it in a database row as plaintext, or include it in cloud-init.

Store only a secret reference:

```text
vault://arvan/accounts/<account-id>/mu-key
```

At log time, redact `apikey 12345678-1234-1234-1234-123456789012` to `apikey 1234…9012`.

## 4. HTTP client standard

Recommended client: `httpx.AsyncClient`.

Required defaults:

```yaml
http:
  connect_timeout_seconds: 10
  read_timeout_seconds: 30
  write_timeout_seconds: 30
  pool_timeout_seconds: 10
  max_connections: 20
  max_keepalive_connections: 10
```

Required headers:

```http
Authorization: <MU-KEY>
Accept: application/json
```

For JSON writes:

```http
Content-Type: application/json
```

Every request log must contain internal operation ID, account ID, region, method, normalized path without secrets, duration, HTTP status, provider request ID if returned, and retry count. Never log `Authorization`, full secret-bearing bodies, SSH private keys, or cloud-init secrets.

## 5. URL construction

Base:

```text
https://napi.arvancloud.ir/ecc/v1
```

Examples:

```text
GET  /regions/ir-thr-c2/servers
GET  /regions/ir-thr-c2/images
POST /regions/nl-ams-su1/servers
```

Never put literal `:region` in a live URL. Correct: `/regions/{region}/servers`. Incorrect: `/regions/:region/servers`.

Region values must come from configuration or a validated provider response. Known examples in official documentation are `ir-thr-c2` and `nl-ams-su1`; these examples do not guarantee current capacity or availability.

## 6. Source registry

Official sources:

```text
https://www.arvancloud.ir/api/iaas/3.0.0
https://docs.arvancloud.ir/fa/developer-tools/api/api-key
https://docs.arvancloud.ir/fa/developer-tools/api/api-usage
```

Secondary generated API snapshot:

```text
https://github.com/hamidfzm/arvancloud-go/tree/main/iaas
```

Treat all fields found only in this SDK as `SDK_SNAPSHOT` until live-validated.

Archived Terraform provider:

```text
https://github.com/arvancloud/terraform-provider-arvan
```

It may provide historical examples but must not be treated as the current API contract.

## 7. Core project workflow

```text
DISCOVER ACCOUNT -> VALIDATE CREDENTIAL -> DISCOVER CREATION OPTIONS -> CREATE TARGET SERVER -> POLL SERVER STATE -> BOOTSTRAP TARGET -> RUN HEALTH CHECKS -> SWITCH SERVICE ENTRY POINT -> VERIFY TARGET TRAFFIC -> DRAIN SOURCE -> POWER OFF SOURCE -> OPTIONAL RETENTION WINDOW -> DELETE SOURCE -> VERIFY RESOURCE CLEANUP
```

The old server must never be deleted before target creation, bootstrap, health checks, traffic switch, post-switch verification, rollback-window consideration, and dependent disk/IP/snapshot inventory are complete.

## Part A — Endpoint reference

## 8. Server endpoints

Base group: `/regions/{region}/servers`.

| Operation | Method | Path | Evidence |
| --- | --- | --- | --- |
| List servers | GET | `/regions/{region}/servers` | OFFICIAL_VERIFIED |
| Create server | POST | `/regions/{region}/servers` | OFFICIAL_VERIFIED |
| Server details | GET | `/regions/{region}/servers/{id}` | SDK_SNAPSHOT |
| Available actions | GET | `/regions/{region}/servers/{id}/actions` | SDK_SNAPSHOT |
| Creation options | GET | `/regions/{region}/servers/options` | SDK_SNAPSHOT |
| Delete reasons | GET | `/regions/{region}/servers/delete-reasons` | SDK_SNAPSHOT |
| Power on | POST | `/regions/{region}/servers/{id}/power-on` | SDK_SNAPSHOT |
| Power off | POST | `/regions/{region}/servers/{id}/power-off` | SDK_SNAPSHOT |
| Reboot | POST | `/regions/{region}/servers/{id}/reboot` | SDK_SNAPSHOT |
| Hard reboot | POST | `/regions/{region}/servers/{id}/hard-reboot` | SDK_SNAPSHOT |
| Rename | POST | `/regions/{region}/servers/{id}/rename` | SDK_SNAPSHOT |
| Rebuild | POST | `/regions/{region}/servers/{id}/rebuild` | SDK_SNAPSHOT |
| Rescue | POST | `/regions/{region}/servers/{id}/rescue` | SDK_SNAPSHOT |
| Unrescue | POST | `/regions/{region}/servers/{id}/unrescue` | SDK_SNAPSHOT |
| Reset root password | POST | `/regions/{region}/servers/{id}/reset-root-password` | SDK_SNAPSHOT |
| Resize server | POST | `/regions/{region}/servers/{id}/resize` | SDK_SNAPSHOT |
| Resize root volume | PUT | `/regions/{region}/servers/{id}/resizeRoot` | SDK_SNAPSHOT |
| Attach root volume | PUT | `/regions/{region}/servers/{id}/attachRoot` | SDK_SNAPSHOT |
| Detach root volume | PUT | `/regions/{region}/servers/{id}/detachRoot` | SDK_SNAPSHOT |
| Add public IP | POST | `/regions/{region}/servers/{id}/add-public-ip` | SDK_SNAPSHOT |
| Add security group | POST | `/regions/{region}/servers/{id}/add-security-group` | SDK_SNAPSHOT |
| Remove security group | POST | `/regions/{region}/servers/{id}/remove-security-group` | SDK_SNAPSHOT |
| Take snapshot | POST | `/regions/{region}/servers/{id}/snapshot` | SDK_SNAPSHOT |
| VNC | GET | `/regions/{region}/servers/{id}/vnc` | SDK_SNAPSHOT |
| Toggle instance HA | POST | `/regions/{region}/servers/{id}/instance-ha/{action}` | SDK_SNAPSHOT |
| Delete server | DELETE | `/regions/{region}/servers/{id}` | SDK_SNAPSHOT |

### 8.1 List servers

Official example:

```bash
curl --location --request GET \
  'https://napi.arvancloud.ir/ecc/v1/regions/ir-thr-c2/servers' \
  --header 'Accept: application/json' \
  --header 'Authorization: <MU-KEY>'
```

Implementation requirements: support empty lists; do not assume pagination is absent; preserve unknown fields; parse provider IDs as strings; do not identify a managed server by name alone; save raw sanitized response fixtures for contract tests.

Expected internal result:

```python
class ServerSummary(BaseModel):
    id: str
    name: str | None = None
    status: str | None = None
    ipv4: list[str] = []
    ipv6: list[str] = []
    raw: dict[str, Any]
```

Exact response property names: `NEEDS_LIVE_VALIDATION`.

### 8.2 Get server details

`GET /regions/{region}/servers/{id}`. Use after every write to verify final state. Never treat a successful write response as proof of final state.

### 8.3 Creation options

`GET /regions/{region}/servers/options`. Use before server creation when possible. Exact response: `NEEDS_LIVE_VALIDATION`. Do not hardcode IDs copied from another account or region.

### 8.4 Create server

Official request: `POST /regions/{region}/servers` with `Content-Type: application/json` and `Authorization: <MU-KEY>`.

Official example body:

```json
{
  "name": "abrak",
  "network_id": "fe9645fc-2234-4865-895b-e3bb4bb0eb7b",
  "flavor_id": "g1-2-2-75",
  "image_id": "8751dd0c-6529-44a9-afec-2a1b29411116",
  "security_groups": [{"name": "054f34d8-f4c1-45bc-ba4e-bcb8c00f17f6"}],
  "ssh_key": true,
  "key_name": "testkey",
  "count": 1
}
```

Core verified fields: `name`, `network_id`, `flavor_id`, `image_id`, `security_groups`, `security_groups[].name`, `ssh_key`, `key_name`, `count`.

Additional SDK snapshot fields: `backup_id`, `create_type`, `disk_size`, `ha_enabled`, `init_script`, `is_sandbox`, `network_ids`, `os_volume_id`, `server_volumes`. Do not send additional fields until validated.

Recommended request model:

```python
class SecurityGroupRef(BaseModel):
    name: str

class CreateServerRequest(BaseModel):
    name: str
    network_id: str
    flavor_id: str
    image_id: str
    security_groups: list[SecurityGroupRef]
    ssh_key: bool = True
    key_name: str
    count: int = Field(default=1, ge=1, le=1)

    # Send only after live validation:
    disk_size: int | None = None
    init_script: str | None = None
    ha_enabled: bool | None = None
```

For the first production version, force `count = 1`.

### 8.5 Safe create algorithm

Generate an operation ID and deterministic unique server name, persist `CREATE_REQUESTED`, re-check for existing matching managed server, submit POST once, persist provider ID immediately on success, never blindly retry timeouts, reconcile by deterministic name/creation time/expected image/flavor/metadata if supported, retry only when non-creation is proven, then poll details to terminal ready/failure state.

Suggested name: `svc-<service>-<template-version>-<operation-short-id>`.

### 8.6 Power off

`POST /regions/{region}/servers/{id}/power-off`. Verify existence first, record current state, submit once, poll details, accept success only after provider confirms stopped/off, and reconcile on timeout instead of immediate retry. Response body: `NEEDS_LIVE_VALIDATION`.

### 8.7 Power on

`POST /regions/{region}/servers/{id}/power-on`. Use during rollback or recovery and always poll final state.

### 8.8 Delete server

`DELETE /regions/{region}/servers/{id}`. Optional SDK concepts include `force_delete` and `delete_server_reasons`; exact query/body encoding is `NEEDS_LIVE_VALIDATION`.

Before live deletion, run a controlled contract test and save sanitized request/response. Preconditions include healthy target service, moved traffic, drained and powered-off source, completed or bypassed retention, inventoried dependent volumes, known public/floating IP behavior, satisfied snapshot policy, and approval. Verify deletion via `GET /regions/{region}/servers/{id}`; final behavior may be 404 or a deleted state and is `NEEDS_LIVE_VALIDATION`.

## 9. Image endpoints

| Operation | Method | Path |
| --- | --- | --- |
| List images | GET | `/regions/{region}/images` |
| Upload image | POST | `/regions/{region}/images` |
| Append TUS data | PATCH | `/regions/{region}/images/{id}` |
| Import image from URL | POST | `/regions/{region}/images/import` |
| Delete image | DELETE | `/regions/{region}/images/{id}` |

Use image IDs discovered in the same account and region. Never assume an image ID is globally stable across regions.

## 10. Plans / sizes

| Operation | Method | Path |
| --- | --- | --- |
| List plans | GET | `/regions/{region}/sizes` |
| Plan details | GET | `/regions/{region}/sizes/{id}` |

Persist plan ID, display name, CPU, RAM, disk constraints, generation/family, region, retrieval time, and raw response hash. Exact model: `NEEDS_LIVE_VALIDATION`.

## 11. Quota

`GET /regions/{region}/quota`. Always query live quota before provisioning. Do not assume this endpoint reports monthly traffic usage; resource quota and traffic billing are different concepts.

## 12. SSH key endpoints

| Operation | Method | Path |
| --- | --- | --- |
| List keys | GET | `/regions/{region}/ssh-keys` |
| Key details | GET | `/regions/{region}/ssh-keys/{name}` |
| Create key | POST | `/regions/{region}/ssh-keys` |
| Delete key | POST | `/regions/{region}/ssh-keys/{name}` |

The delete operation is POST in the SDK snapshot; do not “correct” it to DELETE without validation. Never transmit SSH private keys if only public keys are required.

## 13. Security group endpoints

| Operation | Method | Path |
| --- | --- | --- |
| List groups | GET | `/regions/{region}/securities` |
| Create group | POST | `/regions/{region}/securities` |
| Get rules | GET | `/regions/{region}/securities/security-rules/{id}` |
| Create rule | POST | `/regions/{region}/securities/securitiy-rules/{id}` |
| Delete rule | DELETE | `/regions/{region}/securities/securitiy-rules/{id}` |
| Delete group | DELETE | `/regions/{region}/securities/{id}` |
| Import CDN group | POST | `/regions/{region}/securities/securitiy-rules/cdn` |

`securitiy-rules` appears misspelled in the generated API snapshot. Do not silently change it; confirm the live official path. Exact request schema: `NEEDS_LIVE_VALIDATION`.

## 14. Network endpoints

Networks: list `GET /regions/{region}/networks`, attach `PATCH /regions/{region}/networks/{id}/attach`, detach `PATCH /regions/{region}/networks/{id}/detach`.

Private networks/subnets: create `POST /regions/{region}/subnets`, get `GET /regions/{region}/subnets/{id}`, update `PATCH /regions/{region}/subnets`, delete `DELETE /regions/{region}/subnets/{id}`.

Network IDs are account- and region-specific. Templates must use logical selectors and resolve them per account.

## 15. Floating IP endpoints

List `GET /regions/{region}/float-ips`, create `POST /regions/{region}/float-ips`, attach `PATCH /regions/{region}/float-ips/{id}/attach`, detach `PATCH /regions/{region}/float-ips/detach`, internal IP info `GET /regions/{region}/float-ips/ips`, delete `DELETE /regions/{region}/float-ips/{id}`.

Do not assume a floating IP can move between accounts. Cross-account floating-IP portability is `UNKNOWN`.

## 16. Volume endpoints

List `GET /regions/{region}/volumes`, list OS volumes `GET /regions/{region}/volumes/os-volumes`, options `GET /regions/{region}/volumes/options`, limits `GET /regions/{region}/volumes/limits`, create `POST /regions/{region}/volumes`, create from snapshot `POST /regions/{region}/volumes/snapshots/{id}/create-volume`, create OS volume from snapshot `POST /regions/{region}/volumes/snapshots/{id}/os-volume`, attach `PATCH /regions/{region}/volumes/attach`, detach `PATCH /regions/{region}/volumes/detach`, update `PATCH /regions/{region}/volumes/{id}`, delete `DELETE /regions/{region}/volumes/{id}`, list snapshots `GET /regions/{region}/volumes/snapshots`, delete snapshot `DELETE /regions/{region}/volumes/{id}/snapshot`, revert snapshot `PUT /regions/{region}/volumes/{id}/snapshot/revert`, update snapshot `PATCH /regions/{region}/volumes/{id}/snapshot`.

Before deleting a server, determine whether root/data volumes are automatically deleted, retained, billed independently, or attached elsewhere. All four are `NEEDS_LIVE_VALIDATION`.

## 17. Snapshot endpoints

List `GET /regions/{region}/snapshots`, server snapshot `POST /regions/{region}/snapshots/servers/{id}`, volume snapshot `POST /regions/{region}/snapshots/volumes/{id}/`, create image `POST /regions/{region}/snapshots/{id}/images/`, create volume `POST /regions/{region}/snapshots/{id}/volumes/`, update `PUT /regions/{region}/snapshots/{id}`, revert `PUT /regions/{region}/snapshots/{id}/revert`, delete `DELETE /regions/{region}/snapshots/{id}`.

Snapshot consistency guarantees are not documented in the extracted material. Do not assume online snapshots are application-consistent.

## 18. Reports endpoints

All server reports: `GET /regions/{region}/reports/{id}`. Specific metric: `GET /regions/{region}/reports/{id}/{metric}`. A period parameter may be `1m`, `1h`, or `1d`; exact encoding is `NEEDS_LIVE_VALIDATION`.

Do not implement traffic accounting until controlled calibration identifies RX/receive series, TX/send series, bits vs bytes, cumulative counter vs rate, sample interval, timezone, missing-sample behavior, reset behavior, and report lag.

## 19. Tags

List `GET /regions/{region}/tags`, create `POST /regions/{region}/tags`, update `PUT /regions/{region}/tags/{id}`, attach `PUT /regions/{region}/tags/{id}/attach`, detach `POST /regions/{region}/tags/{id}/detach`, batch `POST /regions/{region}/tags/batch`, delete `DELETE /regions/{region}/tags/{id}`.

Tag every managed resource when supported with `managed-by`, `service`, `environment`, `template-version`, and `operation-id`.

## 20. PTR endpoints

Create PTR `POST /regions/{region}/ptr/`; delete PTR `DELETE /regions/{region}/ptr/{ip}`. Not required initially unless reverse DNS is part of the workload.

## 21. Port endpoints

Enable port `PATCH /regions/{region}/ports/{id}/enable`, disable port `PATCH /regions/{region}/ports/{id}/disable`, enable port security `PATCH /regions/{region}/ports/{id}/enablePortSecurity`, disable port security `PATCH /regions/{region}/ports/{id}/disablePortSecurity`. Do not confuse network ports with TCP/UDP firewall ports.

## Part B — Traffic accounting

## 22. Traffic usage and rotation trigger

The orchestrator monitors download traffic of each active server. When accumulated download traffic reaches a predefined threshold (250 GB), it triggers automatic rotation to the next authorized account in the pool.

Guest OS counters, Arvan Reports API values, and billing/account traffic values may differ. The Reports API is only an indicator; actual billing data is not available via API and calibrated safety thresholds must be used.

Store `billing_cycle_start`, `billing_cycle_end`, `provider_account_id`, `server_id`, `sample_time`, `metric_name`, `raw_value`, `normalized_value`, `direction`, `unit`, `source`, and `quality`.

Safe thresholds:

```yaml
traffic_policy:
  warning_gb: 200
  prepare_gb: 230
  switch_gb: 240
  emergency_stop_gb: 250
```

Automatic threshold action is disabled until calibration passes.

### 22.3 Calibration procedure

Implement `scripts/calibrate_network_reports.py` to record guest RX/TX counters, fetch Reports before and after known download/upload transfers, wait for propagation, compare network series, identify direction/unit, save sanitized fixture, and add a contract test.

## Part C — Orchestrator behavior

## 23. Account model

```python
class CloudAccountStatus(StrEnum):
    NEW = "NEW"
    VALIDATING = "VALIDATING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    USAGE_UNCERTAIN = "USAGE_UNCERTAIN"
    AUTH_FAILED = "AUTH_FAILED"
    QUOTA_BLOCKED = "QUOTA_BLOCKED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"
```

Required fields: `id`, `display_name`, `credential_ref`, `status`, `enabled`, `allowed_regions`, `cross_account_authorized`, `approval_reference`, timestamps, validation/sync timestamps, and redacted last error.

## 24. Server model

```python
class ManagedServerStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    CREATE_REQUESTED = "CREATE_REQUESTED"
    PROVISIONING = "PROVISIONING"
    BOOTSTRAPPING = "BOOTSTRAPPING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    POWERING_OFF = "POWERING_OFF"
    STOPPED = "STOPPED"
    DELETE_PENDING = "DELETE_PENDING"
    DELETING = "DELETING"
    DELETED = "DELETED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"
```

Required fields include internal/account/region/provider identifiers, names, provider and managed status, template/image/flavor/network IDs, addresses, root volume ID, timestamps, and raw response hash.

## 25. Handover state machine

States include `PLANNED`, `PRECHECK`, `TARGET_CREATE_REQUESTED`, `TARGET_PROVISIONING`, `TARGET_BOOTSTRAPPING`, `TARGET_VERIFYING`, `TARGET_READY`, `TRAFFIC_SWITCHING`, `TRAFFIC_VERIFYING`, `SOURCE_DRAINING`, `SOURCE_POWERING_OFF`, `SOURCE_STOPPED`, `SOURCE_DELETE_PENDING`, `SOURCE_DELETING`, `COMPLETE`, `ROLLBACK`, `FAILED`, `WAITING_FOR_THRESHOLD`, `PREPARING_NEXT_ACCOUNT`, `NEXT_SERVER_CREATE_REQUESTED`, `NEXT_SERVER_PROVISIONING`, `NEXT_SERVER_READY`, `DNS_UPDATE_REQUESTED`, `DNS_UPDATE_VERIFIED`, `SOURCE_RETENTION`, and `PERIODIC_CLEANUP`.

Forbidden transitions include `TARGET_PROVISIONING -> TRAFFIC_SWITCHING`, `TARGET_BOOTSTRAPPING -> SOURCE_POWERING_OFF`, `TARGET_VERIFYING -> SOURCE_DELETING`, `TRAFFIC_SWITCHING -> SOURCE_DELETING`, and `SOURCE_POWERING_OFF -> COMPLETE`.

## 26. Server template

Templates must be logical and portable between authorized accounts. Do not store provider-specific IDs that differ per account. At runtime resolve image, flavor, network, security group, and SSH key selectors to concrete IDs/names.

## 27. Bootstrap policy

Use minimal cloud-init, wait for SSH, run Ansible, restart services, run health checks, and persist configuration version/hash. Bootstrap must be idempotent and must not duplicate users, firewall rules, config, secrets, or systemd units or corrupt data.

## 28. Health verification

Minimum checks: provider state, public IP, TCP 22, SSH auth, cloud-init completion, required systemd services, application port, HTTP `/healthz`, dependency checks, and synthetic application request. Require consecutive successes, not a single pass.

## 29. Traffic entry point

Do not expose users directly to ephemeral server IPs if the server will be replaced. Supported stable entry points are DNS, reverse proxy, load balancer, and service discovery. The old server must remain operational during propagation and verification.

## 30. Source shutdown and deletion

Power-off sequence: stop accepting new traffic, drain requests, finish or transfer jobs, flush state, sync data, verify target, call power-off, poll provider state.

Deletion sequence: verify source is no longer serving, verify target remains healthy, record dependent resources, create backup/snapshot if required, obtain approval, call delete, poll/re-query, verify absence/deleted state, verify volumes/IPs/snapshots, record final audit event.

Powering off may not stop costs for disk, snapshot, public IPv4, floating IP, backup, or load balancer; current billing behavior requires validation.

## 31. Idempotency and reconciliation

Every write operation needs operation ID, idempotency key, request fingerprint, attempt number, pre-state, post-state, provider resource ID, and provider request ID. If ArvanCloud does not document an idempotency header, do not invent one.

For create/power-off/delete timeouts, reconcile with list/details before retrying or declaring success. Ambiguous write results must fail closed and require reconciliation.

## 32. Retry policy

Safe automatic retries: GET requests on timeout, transient 5xx, or 429 respecting `Retry-After`. Unsafe blind retries: server create, server delete, snapshot, add public IP, create SSH key, create network. Recommended read backoff: base 1s, factor 2, max 30s, full jitter, max 3 attempts.

## 33. Error normalization

```python
class ProviderErrorCode(StrEnum):
    AUTH_INVALID = "AUTH_INVALID"
    AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_5XX = "PROVIDER_5XX"
    UNEXPECTED_RESPONSE = "UNEXPECTED_RESPONSE"
    STATE_MISMATCH = "STATE_MISMATCH"
    AMBIGUOUS_WRITE_RESULT = "AMBIGUOUS_WRITE_RESULT"
```

Provider errors carry code, HTTP status, retryability, operation, request ID, redacted message, and raw body hash. Never store raw bodies containing secrets.

## Part D — Persistence and project layout

## 34. Required database tables

Required tables: `cloud_accounts`, `account_regions`, `server_templates`, `cloud_servers`, `traffic_samples`, `billing_cycles`, `operations`, `operation_steps`, `audit_events`, `notification_outbox`, and `rotation_state`. Store only secret references and redacted payloads where applicable.

## 35. Repository structure

```text
project/
├── Agent.md
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── settings.example.yaml
│   └── templates/
├── src/arvan_orchestrator/
│   ├── main.py
│   ├── settings.py
│   ├── domain/
│   ├── providers/arvan/
│   ├── services/
│   ├── repositories/
│   ├── scheduler/
│   ├── audit/
│   ├── notifications/
│   ├── api/
│   └── cli/
├── alembic/
├── ansible/
├── bootstrap/
├── scripts/
│   ├── probe_arvan_api.py
│   ├── calibrate_network_reports.py
│   └── sanitize_fixture.py
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    └── fixtures/
```

## Part E — Required probes and tests

## 36. `probe_arvan_api.py`

The first implementation task must be a read-only API probe. It must call:

```text
GET /regions/{region}/servers
GET /regions/{region}/servers/options
GET /regions/{region}/images
GET /regions/{region}/sizes
GET /regions/{region}/quota
GET /regions/{region}/ssh-keys
GET /regions/{region}/securities
GET /regions/{region}/networks
```

For each response, print status and shape, never print secrets, save sanitized JSON fixture, hash raw response, and record `retrieved_at`. Optional when a test server ID is supplied: details, actions, and reports. The script must perform no write request.

## 37. Contract tests

Required fixtures: `servers_empty.json`, `servers_nonempty.json`, `server_details.json`, `server_options.json`, `images.json`, `sizes.json`, `quota.json`, `ssh_keys.json`, `security_groups.json`, `networks.json`, `reports.json`, `auth_401.json`, `permission_403.json`, and `validation_4xx.json`.

Tests must verify unknown fields are preserved, missing optional fields do not crash parsing, IDs remain strings, status parsing tolerates unknown provider states, error bodies are normalized, and secrets are redacted.

## 38. Controlled write validation

Before production writes, validate create, poll, details, power off/on, delete, deletion verification, and remaining volume/IP inspection in an authorized test account. Store sanitized requests/responses, HTTP status, provider state sequence, timings, and cleanup result.

## 39. Unit tests

Minimum tests: authorization redaction, URL construction, region encoding, create payload validation, idempotent create reconciliation, power-off timeout reconciliation, delete timeout reconciliation, state-machine forbidden transitions, traffic threshold evaluation, counter reset handling, report unit conversion, account locking, operation resume after crash, notification deduplication.

## 40. Integration tests

Use a mock HTTP server to simulate 200/201/202/204/400/401/403/404/409/422/429/500/502/503, timeout before/after provider write, malformed JSON, unexpected schema, duplicate resource, slow transition, creation failure, and delete pending.

## Part F — CLI and Phase 2 Telegram

## 41. Phase 1 CLI

Recommended commands: `arvanctl account add`, `account validate`, `account list`, `account disable`, `inventory sync`, `server list`, `server create`, `server details`, `server power-off`, `server power-on`, `server delete-plan`, `operation list`, `operation resume`, `usage status`, and `doctor`. Every write command must support `--dry-run`, `--operation-id`, and `--json`; deletion requires explicit approval.

## 42. Phase 2 Telegram boundary

Telegram is an interface, not the orchestrator. Telegram handlers must call application services/domain orchestrator, not direct Arvan API calls. Planned commands: `/status`, `/accounts`, `/account <name>`, `/usage`, `/servers`, `/operations`, `/events`, `/approve <operation-id>`, `/abort <operation-id>`. Do not accept Machine User keys in normal Telegram chat.

## 43. Notification events

Create outbox events for account lifecycle, usage warnings/uncertainty, server create, bootstrap, health, traffic switch, source power-off, delete approval/start/success/failure, rollback, and operation failure. Every notification must have a deduplication key.

## Part G — Agent execution discipline

## 44. Before coding

Report files inspected, current behavior, API endpoints involved, evidence level for each endpoint, unknowns, risk, and planned tests.

## 45. During coding

Make small changes with type hints, Pydantic at API boundaries, database migrations, structured errors/logs, no secrets, contract fixtures, unit tests, fail-closed handling, no undocumented endpoint, and no blind write retries.

## 46. After coding

Report summary, files changed, API contracts used, evidence labels, migrations, tests run, test results, known unknowns, rollback method, and next safe step.

## 47. Hard prohibitions for the coding agent

The agent must not invent API paths, replace provider field names because they look wrong, infer schema from UI screenshots, log access keys, store secrets in Git, retry server creation blindly, delete source before target verification, assume power-off removes all costs, assume deletion removes every disk/IP/snapshot, assume Reports API equals billing, assume billing-cycle UTC boundary, assume floating IP movement between accounts, assume plan/image/network IDs are portable, implement account signup or identity bypass, or place orchestration logic in Telegram handlers.

## 48. Known unresolved API questions

Unresolved questions requiring live validation or official support include exact schemas for servers/details, status values and transitions, create/write return bodies/statuses, additional create fields, init script limits, delete parameters, force delete, volume/IP deletion behavior, snapshot consistency, Reports period encoding, network metric names/units/lag, billing-cycle timezone, billing usage endpoint, rate limits, pagination, idempotency keys, tag-on-create support, valid regions, cross-account portability, and cost behavior of stopped servers. Until resolved, related production actions must fail closed.

## 49. First implementation sequence

```text
1. Create project skeleton.
2. Implement settings and secret references.
3. Implement read-only Arvan HTTP client.
4. Implement redaction.
5. Implement probe_arvan_api.py.
6. Collect sanitized fixtures.
7. Implement Pydantic response models.
8. Implement inventory database.
9. Implement read-only sync.
10. Implement Reports collection.
11. Calibrate traffic metrics.
12. Implement threshold alerts.
13. Implement create-server dry-run.
14. Controlled create test.
15. Implement bootstrap.
16. Implement health checks.
17. Implement traffic switching.
18. Implement power-off.
19. Implement delete planning and approval.
20. Controlled deletion test.
21. Implement operation resume and rollback.
22. Stabilize Phase 1.
23. Add Telegram Phase 2.
```

## 50. Definition of Done

A feature is complete only when API evidence is recorded, request/response models are validated, errors normalized, secrets redacted, operation idempotency/reconciliation handled, state transition persisted, audit event created, unit and contract tests pass, dry-run works, rollback exists, and documentation is updated.

## 51. Compact reference card

```text
BASE:
https://napi.arvancloud.ir/ecc/v1

AUTH:
Authorization: <complete Machine User key>
Accept: application/json

LIST SERVERS:
GET /regions/{region}/servers

CREATE SERVER:
POST /regions/{region}/servers

OFFICIAL CORE BODY:
{
  "name": "...",
  "network_id": "...",
  "flavor_id": "...",
  "image_id": "...",
  "security_groups": [{"name": "..."}],
  "ssh_key": true,
  "key_name": "...",
  "count": 1
}

SERVER DETAILS:
GET /regions/{region}/servers/{id}

POWER OFF:
POST /regions/{region}/servers/{id}/power-off

POWER ON:
POST /regions/{region}/servers/{id}/power-on

DELETE:
DELETE /regions/{region}/servers/{id}

IMAGES:
GET /regions/{region}/images

SIZES:
GET /regions/{region}/sizes

QUOTA:
GET /regions/{region}/quota

REPORTS:
GET /regions/{region}/reports/{id}
GET /regions/{region}/reports/{id}/{metric}

RULE:
No blind write retries.
No deletion before target health and traffic verification.
No assumption that Reports equals billing.
No secret in logs.
```

## 52. Final instruction to the AI coding agent

Your task is not to “make the API call somehow.” Your task is to build a deterministic, observable, recoverable and testable provider integration.

Whenever an API detail is uncertain:

```text
stop
mark NEEDS_LIVE_VALIDATION
write a read-only probe or controlled test
capture a sanitized fixture
update this document
then implement
```

Never hide uncertainty behind guessed code.
