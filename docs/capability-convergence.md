# Capability Convergence

Saffier 2.2.0 completes the architectural convergence campaign against the
reference repository while keeping Saffier's own product shape intact. The final
state is a Saffier-native ORM: SQLAlchemy 2.x Async is the database runtime,
Lilya is the admin application layer, and Saffier owns the model, registry,
query, migration, admin, tenancy, marshalling, and storage contracts directly.

## Verdict

**OVERALL ACCEPTED.** Every capability required by the campaign is now either
adopted, adapted, or explicitly rejected with a Saffier-specific reason. The
accepted surface is implemented through Saffier modules and public APIs instead
of compatibility shims.

**ADMIN ACCEPTED.** The admin now uses Lilya, Saffier registries, Saffier model
configuration, Saffier marshalling hooks, Saffier permissions, Saffier static
assets, and Saffier URL generation. It supports configured branding, richer
HTML/CSS/JavaScript assets, create/edit/detail/list flows, authentication,
model visibility rules, form validation, reverse-proxy prefixes, and mounted
admin instances.

## Runtime Ownership

The database runtime is owned by SQLAlchemy 2.x Async. Saffier uses
`AsyncEngine`, `AsyncConnection`, `AsyncSession`, `async_sessionmaker`,
SQLAlchemy transactions, SQLAlchemy pools, SQLAlchemy dialects, SQLAlchemy
metadata, and SQLAlchemy compilation directly. No connector abstraction or
external database lifecycle layer remains in Saffier's runtime path.

## Decision Matrix

| Area | Decision | Rationale | Drift Risk | Follow-up |
| --- | --- | --- | --- | --- |
| Database runtime | Adopt | SQLAlchemy Async is now the single runtime authority for engines, connections, sessions, execution, transactions, pooling, and dialect behavior. | Low | Keep new runtime work on SQLAlchemy public APIs. |
| Connection lifecycle | Adapt | Saffier keeps its user-facing `Database` and registry ergonomics while delegating connection state and disposal to SQLAlchemy Async. | Low | Avoid adding new lifecycle layers unless they expose real Saffier behavior. |
| Transactions | Adopt | Transaction and savepoint behavior now maps to SQLAlchemy async transaction objects, including forced rollback scopes. | Low | Keep regression coverage around nested transactions and sync re-entry. |
| Schema management | Adopt | Create/drop/schema helpers run through `AsyncConnection.run_sync()` and SQLAlchemy metadata operations. | Low | Continue treating metadata as the canonical DDL source. |
| Models and fields | Adapt | Saffier keeps its Python-native model and field system while adopting missing field capabilities such as managed files and image metadata. | Low | Add new fields as Saffier fields, not external wrappers. |
| QuerySets and managers | Adapt | Query ergonomics remain Saffier-native while execution uses SQLAlchemy statements and async result handling directly. | Medium | Preserve public query behavior while removing redundant internal indirection. |
| Bulk operations | Adopt | Bulk create, update, delete, and projection flows use SQLAlchemy execution paths without a separate connector model. | Low | Keep performance-sensitive coverage around generated SQL and row counts. |
| Relationships | Adapt | Relationship behavior stays aligned with Saffier's declarative fields, lazy loading, select-related behavior, and tenancy-aware table resolution. | Medium | Keep relationship changes tied to Saffier metadata ownership. |
| Reflection | Adopt | Reflection remains powered by SQLAlchemy inspection and Saffier model construction. | Low | Extend reflection through SQLAlchemy inspection primitives. |
| Tenancy | Adapt | Tenant routing keeps Saffier's schema/database semantics and adds scoped request-level helpers. | Medium | Keep schema context rules explicit and avoid hidden global state. |
| Registry lifecycle | Adapt | Registries now expose Saffier-owned ASGI lifespan wrapping while SQLAlchemy manages the underlying database runtime. | Low | Keep framework integration thin and Lilya/ASGI-compatible. |
| Migrations | Adapt | Migration commands stay Saffier-facing while using Saffier registries, SQLAlchemy metadata, and Alembic integration. | Medium | Keep migration signals and nullable-field handling documented. |
| Admin application | Adapt | Admin capabilities were ported into a Lilya-native, Saffier-configured application rather than copied as another framework's app. | Medium | Treat `AdminConfig` as the source of branding, prefixes, and permissions. |
| Admin assets | Adopt | HTML, CSS, JavaScript, JSONEditor, and Font Awesome assets were brought into the Saffier admin surface and wired to Saffier URLs. | Low | Keep static assets versioned with admin templates. |
| Admin model hooks | Adopt | Admin create and update flows now call model-owned marshalling hooks for schema generation and write payloads. | Low | Keep hook behavior documented with examples. |
| Reverse proxy support | Adopt | Admin URL generation and redirects honor configured prefixes and forwarded request context. | Low | Keep mounted-admin coverage around prefixed routes. |
| Testing utilities | Adapt | Factory and client helpers use Saffier-native names and Saffier runtime behavior. | Low | Remove old reference-named aliases instead of preserving them. |
| Public exports | Adapt | Public imports expose Saffier-native names, including file objects, middleware, and model-copy helpers. | Low | Prefer explicit Saffier exports over aliases. |
| Optional model engines | Reject | Hard-coupling the ORM to any validation library would weaken Saffier's Python-native identity. Engine integrations remain optional adapters. | Low | Keep engine support opt-in. |
| Unsupported backend claims | Reject | Saffier documents and tests the database backends it can honestly support through SQLAlchemy async drivers. | Low | Add backend claims only with real runtime proof. |
| Compatibility shims | Reject | Shims that only preserve reference-repository names were removed because they add surface area without Saffier value. | Low | Avoid adding legacy aliases in new APIs. |

## Implemented Scope

- Replaced the database runtime with native SQLAlchemy 2.x Async ownership.
- Updated registry lifecycle, database creation/removal, transactions, schema
  helpers, sync re-entry, and framework lifespan behavior to use SQLAlchemy
  async primitives.
- Expanded the Lilya admin with richer templates, static assets, configured
  branding, URL helpers, reverse-proxy prefixes, authentication, permission
  classes, model visibility rules, mounted-admin support, and model marshalling
  hooks.
- Added ORM-managed `FileField` and `ImageField` behavior backed by Saffier
  storage, including field-bound file objects, optional size columns, metadata
  columns, approval columns, image dimensions, MIME extraction, and custom name
  generation.
- Added migration lifecycle hooks and forced-nullable migration selectors.
- Added scoped tenancy helpers and ASGI registry lifespan wrapping.
- Removed reference-named public aliases from model-copy and factory utilities.
- Updated public documentation, release notes, examples, and admin docs to
  describe the Saffier-native SQLAlchemy Async architecture.

## Verification Evidence

The final local verification was performed with Hatch. The local test
environment resolved to Python 3.13.12, matching the failing CI family reported
for this campaign.

| Command | Result |
| --- | --- |
| `hatch run test:python -V` | `Python 3.13.12` |
| `hatch run test:test -q` | `987 passed, 204 warnings in 84.93s` |
| `hatch run lint` | Passed |
| `hatch run docs:build` | Passed |
| `hatch run test:check_types` | Passed |

## Final Acceptance

- SQLAlchemy Async is the sole database runtime.
- Runtime execution, transaction, schema, and session paths use SQLAlchemy
  public async APIs.
- The admin is Lilya-native and configured through Saffier.
- Managed file and image fields are Saffier-owned and storage-backed.
- Public docs describe the new architecture.
- Dead reference-name aliases were removed instead of preserved.
- No remaining accepted/adapted gap is intentionally deferred.
