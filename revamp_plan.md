# Saffier Revamp Plan

Date: 2026-03-06

This plan follows the required order:

1. Audit Saffier
2. Audit Edgy comparison
3. Gap analysis document
4. Phased plan
5. Tooling baseline modernization
6. Core functionality parity (priority order)
7. Tests expansion per phase
8. Docs revamp with Zensical
9. CI/version/dependency finalization
10. Stabilization and release hardening

## Phase 0 - Baseline modernization and project hygiene

Goal:

- Establish modern tooling/runtime baseline without changing core ORM behavior.

Likely files/modules:

- `pyproject.toml`
- `Taskfile.yaml` (new)
- `saffier/cli/cli.py`
- `.github/workflows/test-suite.yml`
- `.github/workflows/publish.yml`
- `scripts/docs.py` (new)
- `scripts/docs_pipeline.py` (new)
- `tests/**` integration/cli modules using framework test apps
- `scripts/docs`
- `docs_internal/saffier_edgy_gap_analysis.md`
- `revamp_plan.md`

Public API impact:

- None for ORM API.

Migration concerns:

- Developer workflow changes from Makefile to Taskfile entrypoints.

Tests to add/update:

- Validate baseline test suite still runs on supported versions.
- Add small tests around tooling-related refactors where code changed.

Docs to add/update:

- Add internal planning docs.
- Add/update contributor workflow docs for Taskfile and docs commands.

Acceptance criteria:

- Python support updated to 3.10–3.14.
- Taskfile exists with required commands.
- Saffier CLI client uses Sayer while preserving existing command semantics.
- Test app integration stack switched from Esmerald to Ravyn (`0.3.9`).
- Ruff + Ty integrated in project workflow.
- CI matrix updated and green for baseline checks.
- Zensical docs tooling scaffold added.

## Phase 1 - No-Pydantic foundation (internal primitives first)

Goal:

- Remove low-risk Pydantic couplings from core internals while preserving behavior.

Likely files/modules:

- `saffier/core/db/datastructures.py`
- `saffier/core/utils/schemas.py`
- `saffier/cli/operations/shell/utils.py`
- `saffier/core/datastructures.py`
- `saffier/core/db/fields/_internal.py`
- `saffier/core/db/models/model_proxy.py`
- `pyproject.toml` dependencies

Public API impact:

- None intended.

Migration concerns:

- Potential subtle validation behavior differences in edge cases.

Tests to add/update:

- Index/UniqueConstraint validation behavior tests.
- Field/schema validation regression tests (null/default/required, format validations).
- Shell import defaults tests if needed.

Docs to add/update:

- Remove Pydantic framing from docs/README where no longer accurate.

Acceptance criteria:

- No Pydantic usage remains in completed target modules.
- Existing tests for affected behavior pass; new regressions covered.

## Phase 2 - Query system parity (additive, low breaking risk)

Goal:

- Deliver highest-value QuerySet capability gaps with additive APIs.

Likely files/modules:

- `saffier/core/db/querysets/base.py`
- `saffier/core/db/querysets/*` (new internal split where needed)
- `saffier/protocols/queryset.py`
- `tests/querysets/**` (new)
- `tests/clauses/**`
- `tests/select_for_update/**` (new)
- `tests/combined/**` (new)

Public API impact:

- New QuerySet methods: `select_for_update`, set operations (`union/intersect/except`), potential `reverse`.

Migration concerns:

- SQL behavior differences across database backends.

Tests to add/update:

- Query combinators and locking tests.
- Count/exists semantics with joins/grouping.
- Async iteration and caching behavior.

Docs to add/update:

- Query docs for new methods and backend caveats.

Acceptance criteria:

- Feature parity for targeted query APIs with passing integration tests.

## Phase 3 - Relationship and manager parity hardening

Goal:

- Improve relationship correctness/performance and manager ergonomics.

Likely files/modules:

- `saffier/core/db/relationships/*`
- `saffier/core/db/models/managers.py`
- `saffier/core/db/models/metaclasses.py`
- `tests/foreign_keys/**`
- `tests/prefetch/**`
- `tests/managers/**`

Public API impact:

- Additive manager APIs (e.g., base/redirect manager patterns) if implemented.

Migration concerns:

- Related-name and reverse-access behavior compatibility.

Tests to add/update:

- Deep/nested relation loading.
- M2M edge cases and reverse managers.
- Manager inheritance/composition behavior.

Docs to add/update:

- Relationships and managers guides/reference.

Acceptance criteria:

- Relationship behavior parity goals achieved with regression coverage.

## Phase 4 - Transactions and database lifecycle robustness

Goal:

- Raise transactional safety and lifecycle correctness to Edgy-level confidence.

Likely files/modules:

- `saffier/core/connection/registry.py`
- `saffier/core/connection/database.py`
- `saffier/core/db/querysets/base.py`
- `tests/test_transactions.py` (new/expanded)
- `tests/test_database_rollback.py` (new/expanded)
- `tests/registry/**`

Public API impact:

- Potential additive transaction helpers on queryset/model managers.

Migration concerns:

- Transaction behavior in existing integrations.

Tests to add/update:

- Nested transactions.
- Force rollback semantics.
- Connection leak prevention and db lifecycle checks.

Docs to add/update:

- Transactions and testing docs.

Acceptance criteria:

- Transaction suite reliably passes across supported DB backends.

## Phase 5 - Documentation revamp with Zensical

Goal:

- Replace current docs structure with high-quality, code-faithful, Zensical-driven docs.

Likely files/modules:

- `docs/**`
- `docs_src/**`
- `mkdocs.yml` (Zensical-compatible build config)
- `scripts/docs.py`
- `scripts/docs_pipeline.py`

Public API impact:

- None.

Migration concerns:

- Link/section breakage during restructure.

Tests to add/update:

- Docs build check in CI.
- Snippet validation where practical.

Docs to add/update:

- Full IA: introduction, quickstart, models, fields, queries, relationships, managers, transactions, migrations, testing, advanced patterns, internals, FAQ, release notes.

Acceptance criteria:

- Docs build through Zensical.
- No docs sections describe unimplemented behavior.

## Phase 6 - Final stabilization and release readiness

Goal:

- Finish dependency refresh, harden CI, and close parity gaps selected for this release train.

Likely files/modules:

- `pyproject.toml`
- `.github/workflows/**`
- `README.md`
- `docs/release-notes.md`

Public API impact:

- Documented additive changes only.

Migration concerns:

- Communicate behavior changes and deprecations clearly.

Tests to add/update:

- Full suite across targeted matrix.
- Lint/type/docs checks in CI.

Docs to add/update:

- Migration notes and changelog updates.

Acceptance criteria:

- CI green on configured matrix.
- Tooling/docs/test baselines in place.
- Remaining deferred gaps explicitly documented.

## Immediate execution checklist (current workstream)

- [x] Complete Saffier + Edgy audits
- [x] Create gap analysis document
- [x] Create phased revamp plan
- [ ] Implement Phase 0 baseline modernization
- [ ] Start Phase 1 no-Pydantic low-risk refactors
- [ ] Run targeted tests and fix regressions
- [ ] Update docs tied to implemented changes
