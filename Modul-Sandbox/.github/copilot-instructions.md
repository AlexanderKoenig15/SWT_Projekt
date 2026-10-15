# Project Instructions for AI Agents

This repository publishes a MkDocs-based documentation site on GitHub Pages (Siemens GHES), including auto-generated dashboard pages driven by YAML metadata files.

```
docs/                           Logical assembled documentation root (usually .local-preview/virtual-docs)
docs/categories.yaml            Source of truth for first-level category order and inclusion
docs/responsibility.yaml        Root fallback for page responsibility and system pages
docs/<Category>/                Top-level category content (for example Home, Features, Hardware, Firmware)
docs/<Category>/responsibility.yaml  Category-level responsibility and request routing
docs/<Category>/000_TEMPLATES/  User-maintained editable schema and source templates for a generated category
docs/<Category>/index.md        Committed category layout file with summary placeholders
docs/<Category>/<item>/         One item folder (for example a feature), with overview.yaml and document folders
docs/<Category>/<item>/**/*.md  User-provided or converted documents; customer-owned content
docs/Home/index.md              Landing-page content source, mirrored to the site root by the hook
scripts/                        Developer-maintained Python generation and MkDocs hook logic
theme/                          Developer-maintained local theme overrides and brand assets
mkdocs.yml                      MkDocs configuration; hooks and navigation are managed here
```

For the user editing workflow, read the local [Modul-Documents/About/index.md](../../Modul-Documents/About/index.md) and its role guides. For detailed architecture, operations, and routing, read the local [DevOps and Dashboard Maintainers guide](../../Modul-Documents/About/Roles-and-Ownership/devops-and-dashboard-maintainers.md). In this multi-root workspace, prefer these local Markdown sources over the published website. Use the website only when the local source is unavailable, when checking deployed rendering, or when the question specifically concerns the currently published site. Here, `docs/` is the logical assembled root; its editable sources normally live in `Modul-Documents` and registered mounted repositories, not in a physical `Modul-Dashboard/docs/` checkout.

## Decision Gates

- Treat every rule and convention in this file as an active implementation constraint, not a suggestion: content ownership, editable templates, page-generation ownership, preferred tools, module boundaries, validation, and clean-code practices.
- Preserve user editability as a primary design requirement. User-owned Markdown, YAML metadata, category layouts, and committed templates must stay understandable and directly editable by their maintainers. Keep page structure in Markdown templates; keep calculations, data selection, validation, and repetitive generation in Python.
- For every new page, generated section, or repeated layout block, extend the nearest existing Markdown template, placeholder contract, MkDocs extension, or category processor instead of adding a parallel mechanism. Never replace an editable template with script-only generation silently.
- Prefer this order where it fits the requirement: Markdown and YAML, then existing MkDocs extensions, then committed templates and placeholders, then existing category processors, then narrowly scoped Python. Use raw HTML, CSS, JavaScript, new rendering mechanisms, or new dependencies only when no preferred layer can express the requirement cleanly.
- Stop and ask when a request conflicts with a rule here, or when the best implementation you can identify would invalidate one. Ask whether to follow the rule, treat this as an approved exception, or change the rule. Never infer approval from an exception being simpler or producing the wanted output.
- Before asking, inspect the nearest existing implementation, then state: the conflicting rule, affected files and ownership boundary, the compliant approach, the smallest exception or rule change, and what each option gives up.
- Ask before adding dependencies, changing placeholder contracts, introducing a new rendering mechanism, broadening category-specific code into shared infrastructure, or changing any rule in this file.
- Record an approved exception as a comment at its implementation site rather than as a rule here, and do not extend it to other code.
- Treat repository, user, and session memory as advisory context only. Verify reusable project facts against current code, tests, workflows, and maintained documentation before promoting them into version-controlled instructions; do not keep mandatory project rules only in memory.
- For bounded tasks, prefer one focused tool or terminal invocation and project structured results to the fields needed for the response. Reuse authoritative results instead of repeating reads or recalculating them. Keep output bounded; if a command spills output into a generated user-profile or VS Code artifact, rerun it with a compact projection rather than opening that artifact solely to recover output. Preserve required diagnostics, provenance checks, and validation. Use the workspace working directory where supported, or one directory wrapper around the complete command when it is not.

## Skill-First Agent Policy

`Modul-Agents` is a required workspace repository containing the authoritative
task skills for this Dashboard. Apply this policy to every user prompt before
planning or performing work:

1. Check whether one or more available skills can fulfill all or part of the
  request. Prefer the relevant skill over a freehand workflow.
2. Use every applicable skill that is needed, and prefer clear skill chaining
  or nesting when a request spans multiple workflows. Each skill remains
  authoritative for its own procedure, safety boundary, and confirmation
  rules.
  For Dashboard requests involving a Feature or category, including wording
  such as “create a new repository for this Feature/category” or “set up a
  repo for...”, use `dashboard-content-structure` as the entry point. It
  delegates to `dashboard-repository-provisioning` when repository, Project,
  permission, App-access, or initialized-main readiness is missing. Use
  `dashboard-repository-provisioning` directly only for an explicitly
  provisioning-only Dashboard repository/Project request with no Feature or
  category structure work.
3. Before using a skill, announce it in the response with this form:
  `Using skill <skill-name> to <purpose>.`
  Announce each additional skill when the workflow moves to it. Do not claim
  that a skill was used unless its instructions were actually loaded and
  followed.
4. If no applicable skill is available, say:
  `No applicable skill was found in the available Modul-Agents skills. I will answer without a skill.`
  Then provide a freehand answer only when the request is safe and does not
  require a documented workflow.
5. Before normal work, verify that the `Modul-Agents` workspace folder and its
  root skill directory are available. If they are missing, do not perform the
  requested work. Explain that the required skills are unavailable and offer
  to run **Workspace: Configure**. Setup assistance is the exception: after
  user confirmation, the setup command may restore required repositories, and
  normal work may resume only after the skill directory is available.
6. Treat this policy as an instruction-level contract. VS Code and Copilot may
  not mechanically expose every skill, intercept every conversational reply,
  or prove every model delegation. Use customization diagnostics and response
  References to verify loaded skills; never invent a successful skill use.

The runtime skill discovery surface is the root-level
`Modul-Agents/.github/skills/` directory. Project-specific agent instructions
inside nested skill-project folders are maintainer guidance and do not replace
the root skill workflow. Do not create a second universal policy in
`Modul-Agents`; Dashboard architecture, ownership, security, and validation
rules remain authoritative here.

## Partial Workspace Access

The active VS Code workspace is the default access boundary for every AI
request. Before repository or content work, identify which workspace folders
are visible and whether they are sufficient for the requested scope. A
repository that may exist beside Dashboard but is not an active workspace
folder is unavailable for this request; do not silently scan sibling folders,
read another workspace file, or use external discovery to fill the gap.

- Continue when the visible repositories are sufficient, and disclose the
  limited scope for repository or data work, validation, changes, and decisions.
  Use plain wording such as “unavailable in the current workspace”; do not
  claim a complete category or Feature inventory from partial sources.
- When a relevant repository is unavailable, explain what cannot be verified
  and, for an information-only request, ask whether to proceed with the
  partial scope, read the published Dashboard site, or add that specific
  repository. Offer the published site only when the requested information is
  likely present in the rendered pages. Never require every repository by
  default.
- The published Dashboard site is a read-only fallback for the currently
  deployed rendered state. It may be stale or differ from local changes or
  `main`, and it does not replace source-level metadata, ownership files,
  templates, unpublished content, editing, migration, or validation. State
  clearly when it was consulted and label conclusions as published-site state.
- Accessing the published site is an external read that requires the user's
  explicit choice for the current request. Use only the official Dashboard
  site; do not follow arbitrary external links, send local content or
  credentials, or retain approval for later requests.
- **Workspace: Configure** is the supported way to create or update the
  generated workspace and add or remove repositories after the initial
  Dashboard checkout. A manual clone is not enough to make a repository
  available to the AI; the Configure task can detect an existing sibling
  checkout and include it in the workspace.
- Inspecting a named path outside the active workspace is an exception that
  requires explicit approval for that request. Keep the scope limited to the
  named repository or path; do not retain blanket approval.

Any workspace inventory helper must receive explicit workspace folders and
must remain read-only. It must not read the generated workspace file or scan
parent directories implicitly. Content-level category and Feature discovery
is task-scoped; repository availability checks should stay cheap.

## Change Impact and Authority

Plan repository and content changes before editing. Minimize cross-repository
impact and prefer a valid change in the owning repository when it achieves the
user's goal. Treat these as separate facts:

- **Write scope**: repositories the plan will change;
- **Impact scope**: repositories that may consume, link to, or be affected by
  the change;
- **Validation scope**: repositories needed before claiming the complete site
  is compatible and validated.

Classify the concrete plan, not only the user's wording. Ordinary edits to an
existing local content item are local by default. Escalate when the plan
changes a shared contract, generated behavior, publication structure, source
mapping, inherited policy, path or anchor identity, shared tool, or a broad
collection of instances. User words such as “all” or “every” are signals, not
proof of intended scope; do not silently broaden or narrow the plan.

- If the plan stays within the owning repository and no likely consumer is
  identified, proceed with the normal confirmation and report the repositories
  and references actually checked.
- If the plan would write to another repository, or would change a shared
  contract consumed by other repositories, ask whether that cross-repository
  effect is intended before editing. Explain that coordination with the
  relevant owner or Dashboard team may be needed and do not assume that
  workspace visibility grants write permission.
- If the user confirms an authorized cross-repository change, support it with
  a complete impact list, the minimum required visible repositories, explicit
  confirmation, and combined validation. Dashboard maintainers are allowed to
  perform such changes when the workflow and permissions support them.
- If the user cannot or does not intend to change the other repository, keep
  the change local when a compatible local option exists; otherwise stop and
  prepare a maintainer or owner handoff. Never work around repository
  permissions.
- If an ordinary local edit may have incoming links or consumers in unavailable
  repositories, it may proceed when the risk is limited and no cross-repository
  write is needed, but state that only the visible workspace was checked. For
  destructive, shared-contract, bulk, or clearly consumer-affecting plans,
  stop before writing until the relevant repositories are available or a
  documented staged change is explicitly approved.

Do not claim complete compatibility or validation when the impact or validation
scope extends beyond the visible workspace. A local content edit does not by
itself require every repository; a cross-repository plan does require an
explicit authority and coordination decision.

## AI Customization Governance

Use the narrowest customization surface that owns the rule:

- Keep Dashboard architecture, repository ownership, security, generated
  output, and validation rules in this always-on file.
- Put reusable workflows that span Dashboard repositories in
  `Modul-Agents/.github/skills/`.
- Keep file- or project-specific conventions in the owning repository's
  `.github/instructions/`, `AGENTS.md`, `CLAUDE.md`, or
  `.github/copilot-instructions.md` when they must apply to that project even
  outside the Dashboard workspace.
- Keep small local compatibility or entry-point files when they help a
  repository work correctly as a standalone checkout.

Do not move a project contract into a skill merely because it is written for
an AI. Skills are task-specific and loaded on demand; repository instructions
are the correct home for rules that must always apply. Do not maintain two
runtime skills with the same name or duplicate one workflow across
`Modul-Agents` and another workspace repository.

Keep always-on instructions concise. Before adding a rule, confirm that it
applies to nearly every request in its scope and cannot be expressed more
precisely as a skill, a file-scoped instruction, or maintained documentation.
Do not put task procedures, long examples, troubleshooting steps, or
acceptance matrices into an always-on file. Include only the decision-critical
summary and keep the details in the narrowest applicable source.

Every shared skill must have valid frontmatter and a discoverable `Use when`
description with ordinary user wording. Its workflow must state the required
repositories and tools, facts to inspect, readable and writable files,
questions for missing or contradictory information, announcements before
chaining another skill or tool, confirmation boundaries, validation and human
review, dependency or permission failures, and synthetic acceptance cases in
its local evaluation matrix.

In the generated multi-root workspace, `Modul-Agents` is available because the
Dashboard registry marks it as required. A sibling repository is not searched
automatically merely because it exists beside Dashboard. When a customization
or skill is not applied, check the Chat customization diagnostics and response
References before changing the architecture or claiming that it was used.

## Repository Rules

- `docs/categories.yaml` is the content-manager-owned source of truth for first-level navigation order and inclusion.
- `docs/Home/index.md` is manually maintained landing-page content. Adding a
  published top-level category normally requires a matching Home card; the
  Home grid is not generated from `categories.yaml`.
- `docs/responsibility.yaml` is the root fallback for responsible role, owner names, and Dashboard/Content request routing. Each category and Feature is planned to have its own GitHub project and should set its scope-specific request routing when that project exists. Until then, ordinary category and subcategory `responsibility.yaml` files, and Feature `overview.yaml` policies, inherit the nearest available route from Root. Generated `Features` uses its editable `000_TEMPLATES/overview.yaml` for category defaults and Feature overview files for item overrides. A policy file configures only its own directory and descendants; it must not contain path-based rules for lower directories.
- `repositories.yaml` is dashboard-owned registry configuration. `workspace` controls local checkout/workspace inclusion; a relative `mount_path` controls publication, while omitted mounts are workspace-only. New Features and categories require dedicated repositories. Mounts are exclusive except for one direct Feature fallback: if the root `Modul-Documents` source still has the exact directory for a registered `Features/<Feature>` mount, Documents wins regardless of child contents and the child is omitted from assembled docs until that directory is removed. The child remains registered and revision-tracked. All other nested mount collisions remain hard errors. Never put credentials or user-maintained content in the registry.
- `Modul-Agents` is a required workspace-only repository containing shared VS Code Agent Skills. `Modul-Tools` is an optional workspace-only repository containing deterministic conversion and inspection tools. Do not add either repository to the published documentation navigation unless an explicit publication change is approved. Before invoking a tool from `Modul-Tools`, confirm that the checkout exists and follow its documented entry point.
- Content source/edit links must resolve through the most-specific effective mount, including the direct-Feature Documents fallback above. Content-owned paths link to the effective source repository-relative path; dashboard-owned paths link below `docs/` in `Modul-Dashboard`. Do not hard-code a content repository URL in generators, hooks, templates, or viewer code.
- Generated categories have `000_TEMPLATES/overview.yaml` plus item `overview.yaml` files. Plain categories are normal Markdown directories.
A shared generated-category or Feature template/schema change is a
cross-repository change. Before writing it, identify every configured instance
source and classify whether the proposal requires instance edits or consumer
compatibility checks. For a template-only regrouping that preserves all
declared process IDs, fields, defaults, weights, and generated-page contracts,
enumerate unavailable consumers from the registry and report partial local
validation, but do not require every Feature checkout to be visible. If the
proposal requires instance edits or compatibility checks, stop before changing
the template or instances when an affected source is unavailable; tell the
user which repository is needed or obtain approval for a documented staged
migration. Never silently update only visible instances when the change is not
compatible with that partial scope.
- The site is document-driven: `docs/` is primarily user-maintained content, and its structure determines what users see on the published site. Prefer Markdown and YAML changes there over Python changes when they meet the request.
- In `docs/Features`, document owners are typically non-developers. Treat `docs/Features/<item>/...` as customer-owned, including converted document bodies. Do not deeply inspect or edit those bodies unless the task explicitly requires document-content work.
- Fully consider editable category templates under `docs/<Category>/000_TEMPLATES/`, static category layouts, `scripts/`, `theme/`, and `mkdocs.yml` when the task concerns site behavior or presentation.
- Dashboard pages, summary tables, group pages, file-view pages, and Templates indexes are generated during builds. Do not commit generated data under `docs/`; `site/` is build output.
- Local partial previews use the ignored `.local-preview/virtual-docs/` link tree and the standard ignored `site/` output. Never copy or synchronize source content, and never modify a dashboard or content checkout while constructing the preview.
- Central assembly uses `--require-all` with immutable source revisions; workspace-only repositories are not materialized. Deployment manifests record the Dashboard, registry, and source revisions for reconciliation. Credentials remain in the centrally managed GitHub App workflow; never place them in content repositories or source files. Pull-request validation is complete; Pages deployment is restricted to `main` and content publication remains Dashboard-triggered until DevOps approves another mechanism.
- Manual Pages dispatch accepts generic `source-id=SHA` values, one per line, so every registered source can be pinned; do not add source-specific workflow inputs when a generic revision list suffices.
- Use `scripts/workspace_bootstrap.py` after cloning Dashboard to create/update the generated multi-root workspace. It preserves dirty, non-`main`, ahead, and diverged worktrees, always retains required repositories, and does not change local content-assembly discovery; detailed setup belongs in the Dashboard README.
- Keep static page content in Markdown. Do not rename or remove `[[AUTO:...]]` placeholders unless their generator changes too.
- `search-policy.yaml` is the dashboard-owned source of truth for published path prefixes excluded from global client-side search. It is distinct from `repositories.yaml`: the hook sets `search.exclude: true` page metadata before the Material search plugin indexes matching pages, so exclusion leaves pages built, linkable, and strictly validated. `not_in_nav` does not exclude a page from search. Before a bulk import, new generated collection, category/feature split, or content move, assess its search value and scale; update affected search-policy prefixes and their synthetic tests in the same change.
- Generated Markdown templates use the shared `scripts/markdown_templates.py` renderer. A placeholder on its own line inherits the template's indentation for all generated lines, and replacements are single-pass so generated content cannot invoke another placeholder; keep block structure and indentation in Markdown, and keep calculations and repetitive content generation in Python.
- The Features page templates are `docs/Features/000_TEMPLATES/feature_detail.md` and `docs/Features/000_TEMPLATES/group_detail.md`; preserve their placeholder contracts when changing generated page behavior.
- Treat existing committed, staged, and unstaged changes as intentional. Do not revert, overwrite, or broadly refactor them unless the task explicitly requires it.
- Do not commit, amend, reset, or otherwise change Git history unless the user explicitly asks. When asked to commit, split unrelated concerns into separate focused commits.

## Features Metadata

- The schema is [Modul-Documents/Features/000_TEMPLATES/overview.yaml](../../Modul-Documents/Features/000_TEMPLATES/overview.yaml); the owner-facing explanation is the [Feature Owner Guide](../../Modul-Documents/About/Roles-and-Ownership/feature-owners.md). Keep detailed generated-page behavior in those sources, not in this always-loaded rule file.
- Recognized metadata states are `required`, `optional`, `template`, `template_only`, and `append`. Feature instances may use only fields, process IDs, and process fields declared by the shared template.
- A Feature directory without `overview.yaml` is a pending source: omit it from generated Feature pages, summaries, and navigation while the file is absent. A present malformed or structurally invalid overview remains subject to normal strict validation; valid null, empty, or missing required values remain publishable and appear as `MISSING`. The workspace-level `get_feature_status_for_workspace()` helper reports pending metadata without fabricating readiness.
- The Features metadata merger is the only consumer interface for non-structural feature/process leaves. Use `get_value_many(field)` or `get_value_one(field)` and honor `required_missing`; do not read raw leaves outside configuration construction or structural validation.
- `sources` is structural and accepts local paths, mounted paths, external URLs, labelled Markdown links, or the explicit `not_applicable` value. `groups.items` must reference declared process IDs, and every process must belong to exactly one group.
- Readiness combines applicable linked sources, required metadata, and reported progress using the template weights. A `not_applicable` source is excluded from source-coverage denominators; template defaults do not satisfy missing required process metadata.
- Feature status and readiness reporting must use the read-only
  `scripts/generate_features_dashboard.py:get_feature_status_for_workspace()`
  helper and its generator-owned calculation path. Do not scrape generated
  HTML or duplicate metadata, front-matter fallback, source, progress, weight,
  or group logic in another consumer.
- Keep Feature page responsibility separate from process metadata: top-level Feature `owner` and `responsible` values are distinct from process-level fields. Resolve routes through the metadata merger and the documented inheritance rules.
- Preserve the generated-page contracts in `feature_detail.md` and `group_detail.md`; change the templates before adding generated structure.
- Ordinary-page responsibility, feedback routing, source links, and search behavior follow the maintained guides and the current hooks/tests. Do not invent a parallel policy in agent instructions.

## Code Boundaries

- Keep category-specific behavior in a category processor such as `scripts/features_section.py`; keep shared orchestration in `scripts/mkdocs_hooks.py`. The code-level interface remains `GeneratedSectionProcessor` and its `SECTION_PROCESSORS` registry.
- Add a generated category through a dedicated processor registered in `SECTION_PROCESSORS`, not through category-specific branches in the generic hook.
- Keep file-view routes in `scripts/viewer_routes.py` and rendering in `scripts/viewer_pages.py`. Content-display links for viewer-supported text documents must use file-view pages; intentionally direct-linked PDF and MSG assets use encoded source paths instead.
- Keep `docs/Home/index.md` as the landing-page content source and `theme/brand-banner.html` presentation-only. Do not add upstream template JavaScript without an approved requirement.

## Documentation Sync

- Documentation and implementation change together. When page behavior, a placeholder contract, template ownership, or a validation rule changes, update every affected document in the same change.
- The four audiences are `README.md` (developer setup and maintenance), [Modul-Documents/About/index.md](../../Modul-Documents/About/index.md) (site users), [Modul-Documents/About/Roles-and-Ownership/devops-and-dashboard-maintainers.md](../../Modul-Documents/About/Roles-and-Ownership/devops-and-dashboard-maintainers.md) (architecture, operations, and routing), and this file (AI rules).
- Describe the same contract consistently across those documents; wording may differ per audience, but ownership and behavior must not.

## Test Strategy

- For every behavior-changing code edit, assess whether focused automated tests are needed before considering the change complete. Add tests when they can meaningfully protect a changed contract, validation rule, transformation, route, generated page, error path, or user-visible behavior.
- Responsibility changes require synthetic temporary-repository tests for inheritance, partial routing merges, malformed policy data, document owner precedence, missing values, and system fallback. Production code referenced only by tests is dead and must be removed with those tests.
- Scale test scope to risk and ownership: prefer fast focused unit or fixture tests for deterministic `scripts/` behavior; rely on the existing strict MkDocs build for end-to-end rendering; inspect generated HTML for presentation changes.
- Treat all content under `docs/`, including `categories.yaml`, category layouts, `000_TEMPLATES/`, item `overview.yaml` files, and document bodies, as user-maintained and editable.
- Unit tests must not depend on the current inventory of user-owned content. Do not assert that a particular feature, category, process folder, document, testcase, filename, or current item count exists.
- Do not use live `docs/` content as fixtures for unit tests. When testing generation, navigation, routing, scanning, or validation behavior, create the smallest synthetic repository or feature structure in `TemporaryDirectory()` or construct the input in memory.
- Tests may enforce contracts required for the site to work, including YAML shape, required fields, allowed keys, process-group membership, testcase relationships, valid routing metadata, safe links, and other documented validation rules.
- Tests must not enforce user-chosen values, labels, names, ordering, quantities, document contents, or progress totals unless the test creates those values as part of its own fixture.
- Prefer invariant assertions such as “configured order is preserved,” “every generated item has a valid route,” or “unmapped documents appear under Related Documents” over assertions tied to the current repository corpus.
- If a test needs a real file path only for logging or routing, use a neutral synthetic path or temporary file. Do not reference a current customer feature merely because it exists.
- The strict MkDocs build is the integration check for the current `docs/` corpus. Unit tests should protect generator behavior and documented contracts, not freeze the corpus.
- When adding a test for a user-visible generated result, include only the minimum fixture content needed to exercise that result. Avoid asserting unrelated generated pages or repository-wide counts.
- If a proposed test would fail because a user adds, removes, renames, or edits a valid document, rewrite the test around a synthetic fixture before adding it.
- During review, scan new and modified tests for live `docs/` paths, hardcoded feature/category names, repository-wide counts, and assertions over discovered files. Treat these as defects unless they target an explicitly approved integration test.
- Do not add tests solely to raise coverage or pursue 100%. Do not weaken, delete, skip, or replace a meaningful test merely to make validation pass. Coverage is a regression guard, not the purpose of the test suite.
- During code review, identify production code that is referenced only by tests. Treat test-only production code as unused and remove it together with tests that exist only for that code once the requested behavior is settled, before final validation or commit. If the code may be a deliberate public or compatibility API, inspect its callers and history; document the reason or ask for clarification rather than guessing.
- When a new or existing test fails after an implementation change, stop and reassess the failure against the user request and the established repository contract:
  - Update the test only when the requested behavior intentionally changes the prior contract and the test's expectation is therefore obsolete.
  - Fix the implementation when the failure exposes behavior that conflicts with the request, an established contract, or a valid existing expectation.
  - Treat ambiguous failures as evidence to inspect the nearest controlling code, template, fixture, or call site before choosing either path.
- After repairing a failing test or implementation, rerun the same focused validation before expanding the change. Report pre-existing unrelated failures without changing them unless the task explicitly includes them.

## Validation

- Use `uv run --locked python scripts/validate.py` before considering a change complete. The shared command synchronizes missing locked dependencies, runs the unit tests through `coverage`, requires at least 85% line coverage for `scripts/`, and then runs the strict MkDocs build. It is used by the VS Code strict task and the Pages workflow; the existing MkDocs 2.0 / Material compatibility warning is expected, and new warnings are not. Use `uv sync --locked` for the first checkout or to explicitly recreate the local environment.
- The shared validation checks skill structure, registry/assembly inputs, Ruff formatting and lint, coverage-enforced unit tests, and the strict MkDocs build.
- Strict validation covers every Markdown document, including customer Markdown under generated-category item folders and template sources. A temporary, narrowly scoped exception suppresses only unresolved legacy `[TMSIMG]` image references originating under the `TestCases` mount while their assets are being exported; ordinary broken links, missing anchors, excluded targets, and references from other mounts remain strict. Remove this exception after the TestCases assets and links are repaired.
- MkDocs unresolved anchor links are configured as warnings, so strict validation fails when an anchor target is missing.
- The automated test suite is run by `scripts/validate.py` through `python -m coverage run --source=scripts -m unittest discover -s tests`; add focused tests for generator changes, then confirm the built page under `site/`.
- For presentation changes, inspect the generated HTML rather than assuming the Markdown or template is rendered as intended.
- Restart `mkdocs serve` after changing files in `scripts/`; hook and generator code is not hot-reloaded, and a stale server serves outdated pages.
- Do not invoke Ruff directly during normal validation; use the shared validation command so local and CI behavior stay aligned. Run a direct Ruff command only when diagnosing a Ruff failure, testing Ruff configuration, or when the user explicitly requests it.

## PoC Scope

- This PoC is intentionally centered on `Features`. Logging of Security Events (SecLog) remains the primary deep source-document collection; other Feature entries may begin with metadata-only dashboard content.
- Other top-level categories may remain placeholders for months; preserve them as examples of extensibility and editing patterns.
- Avoid over-engineering placeholder categories while keeping extension points clean for future category processors.

## Upstream Template Sync

- Landing-page sync scope is usually limited to: `docs/Home/index.md`, `theme/brand-banner.html`, `theme/assets/brand/background.png`, `theme/assets/brand/asio-hub.png`, and `theme/assets/brand/favicon.png`.
- The local header overrides `theme/partials/header.html` and `theme/partials/siemens/top-nav.html` are maintained separately. When upgrading the Siemens theme, compare them with their upstream partials as described in the published DevOps and Dashboard Maintainers guide.

## Dependencies

- Prefer the standard library (`pathlib`, `yaml`, etc.) and existing project patterns over new packages.
- Do not add a Python or MkDocs dependency without a clear, specific benefit. State the justification and get approval first.

## Code Style

- Read existing code before changing it, and prefer small, focused edits over broad rewrites.
- Keep clear module ownership, reuse existing helpers and abstractions, keep functions focused, and prefer simple, testable, Pythonic code.
- Define shared policy values, such as status colors or thresholds, in exactly one place.
- Keep the established approach: YAML-driven schema, hook-based injection, template-owned page structure, and no committed generated output.

## Task Workflows

Procedural content-structure work is provided by the
`dashboard-content-structure` skill in the required
`Modul-Agents/.github/skills/` directory. Use it for adding Feature or
category repositories, registering mounts, changing category order, or
changing generated-category templates and instance metadata. Keep the rules
above as the always-on authority for ownership, architecture, safety, and
validation; the skill does not replace this file or create a second global
policy.
