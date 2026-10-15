# AS IO Modularization Dashboard

This repository builds and publishes the AS IO Modularization Dashboard. The published site is the handbook for Category Owners, Feature Owners, content contributors, Test Managers, and platform operators.

**Published dashboard:** [Open the AS IO Modularization Dashboard](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/)

## Start Here

| I need to... | Go to |
| --- | --- |
| Use, review, or coordinate dashboard content | [About: role guides](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/) |
| Own category meaning, organization, or content quality | [Category Owners](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/category-owners/) |
| Edit Markdown, images, links, or YAML | [Content Contributors](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/content-contributors/) |
| Own a Feature or its metadata | [Feature Owner Guide](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/feature-owners/) |
| Manage test content | [Test Managers](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/test-managers/) |
| Operate GitHub, builds, source mounts, or access | [DevOps and Dashboard Maintainers](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/devops-and-dashboard-maintainers/) |
| Understand Dashboard implementation and operations | [DevOps and Dashboard Maintainers](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/devops-and-dashboard-maintainers/) |

## First Local Setup

Prerequisites: Git, Python 3.14+, `uv`, VS Code, PowerShell, and access to the required Siemens GitHub repositories. On Linux or WSL2, install PowerShell 7 so the `pwsh` command is available. On Windows, enable long paths; the setup manager checks the setting but cannot change the machine policy. It synchronizes locked packages but does not install missing prerequisites; request support through the published [Roles and Ownership](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/) page when access or tooling is unavailable.

```powershell
Set-Location C:\Work
git clone https://github.siemens.cloud/AS-IO/Modul-Dashboard.git
Set-Location Modul-Dashboard
python scripts\workspace_bootstrap.py
```

The manager keeps the Dashboard checkout and every repository marked `workspace: required` in `repositories.yaml`. It offers the remaining registered repositories as selections and creates the workspace file beside the repository folders, named after the Dashboard repository's `origin` remote (`Modul-Dashboard.code-workspace`). It does not overwrite dirty, non-`main`, or diverged checkouts. After the initial Dashboard checkout, **Workspace: Configure** is the supported way to create or update this workspace and add or remove repositories. Manually cloning a repository is not a substitute because the repository is not AI-visible until it is included in the generated workspace; the task detects existing sibling checkouts when adding them.

| Task | Use |
| --- | --- |
| **Workspace: Configure** | Add or remove optional repositories from the workspace |
| **Docs: Serve** | Preview available local content |
| **Docs: Validate (Strict)** | Check Agent Skills, formatting, lint, tests, coverage, and strict MkDocs rendering |

Once **Workspace: Configure** finishes, reopen the generated
`.code-workspace` file in VS Code and start using the normal Copilot
Agent chat. Ask questions or describe the task in ordinary language; the
available workspace skills are selected as needed. See [Support Function (AI -
User Interface)](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Processes/Agentic_Support/)
for an overview of what the assistant can do and how requests are handled.

Run **Docs: Validate (Strict)** before every push to `main`. The task first validates the required `Modul-Agents` root skills; if that checkout is missing, run **Workspace: Configure** and repeat validation. Direct pushes remain possible today; a broken content change can block the next complete site build. Pull requests are recommended even though they are not yet required in every content repository.

### Build modes

The local serve task and validation task use the same assembled source tree. The validation task and central workflows share the `validate.py` stages, but central workflows materialize all mounted sources at immutable Git SHAs:

| Mode | Source checkouts | Missing source behavior | Main output |
| --- | --- | --- | --- |
| **Local preview** | Available sibling checkouts beside Dashboard; the registered root source is required | Missing non-root sources are omitted; a warning is shown and the status file records the omissions | Preview server and `.local-preview/virtual-docs/` |
| **Local validation** | Available sibling checkouts beside Dashboard; the registered root source is required | Missing non-root sources are omitted; `mkdocs build --strict` validates what is present | Formatting, lint, tests, coverage, and strict MkDocs results |
| **Central CI or Pages** | All mounted sources materialized at immutable Git SHAs | Fails before MkDocs when a mounted source is missing | Complete site and deployment manifest |

For local discovery, use **Workspace: Configure** to add a source beside Dashboard using the repository basename. The task can detect an existing sibling checkout and include it in the generated workspace:

```text
C:\Work\
	Modul-Dashboard\
	Modul-Documents\
	Modul-Hardware\
```

Assembly links these checkouts into the disposable documentation tree. It uses directory junctions on Windows and symbolic links on Unix; it does not copy the source content. Read `.local-preview/content-assembly-status.json` after a local run. `missing_source_ids` records registered repositories without local checkouts; `missing_mount_paths` lists only effective documentation paths unavailable locally. A shadowed Feature child can therefore be missing while its old Documents directory remains available; `shadowed_sources` identifies that fallback. Central builds still materialize and require every registered source.

An empty or README-only new Feature repository may be registered after its initial `main` commit. While `overview.yaml` is absent, Feature-generated pages, summaries, and navigation omit it; ordinary strict metadata validation resumes when an overview file is added. The bootstrap README may still be directly rendered and searchable temporarily and is removed automatically with the first real Feature content change.

In Feature process overviews, an unavailable registered repository may appear as orange **REPO MISSING** during local preview. This marker identifies an omitted local checkout; a missing path inside an available repository remains **MISSING**. Central validation requires all registered repositories and does not use the local-preview marker.

For AI work, only repositories included as folders in the active VS Code
workspace are available by default. A repository that exists beside Dashboard
but is not included in that workspace remains unavailable to the assistant.
The assistant should continue with a sufficient visible subset and state the
limitation, or recommend **Workspace: Configure** for only the specific
repository needed. It should not require every repository or silently inspect
sibling folders.

AI-assisted changes follow a smallest-scope rule. Ordinary content owners
should normally change only files in their owning repository. When a proposed
plan would edit another repository or a shared contract, the assistant asks
whether that broader effect is intended and explains that owner or
Dashboard-team coordination and write access may be required. Authorized
Dashboard maintainers can still use the full cross-repository workflow. A
local edit with possible incoming references is allowed with an explicit note
that only visible repositories were checked; unrelated repositories are not
required by default.

Shared Feature template changes are treated as cross-repository schema
migrations. The assistant must inventory all Feature metadata consumers before
editing `Features/000_TEMPLATES/overview.yaml`. If any affected Feature
repository is unavailable in the current workspace, it must stop before
changing the template or visible instances and recommend **Workspace:
Configure** for that specific repository. A template-only edit is not treated
as complete unless the user explicitly approves a documented staged migration.

For an information-only request, the assistant may offer the published
Dashboard site as a third option when the rendered page is likely to contain
the answer: continue with the visible workspace, read the published site, or
add the specific repository through **Workspace: Configure**. Published pages
represent deployed state and may differ from local changes or `main`; they are
not a substitute for source metadata, editing, migration, or validation. The
assistant must ask before accessing the official site and must not send local
content or credentials to it.

## Repository Responsibilities

| Area | Location |
| --- | --- |
| Dashboard configuration, scripts, theme, workflows, deployment, source registry | This repository |
| User-managed pages, metadata, templates, attachments, category navigation | Registered content repositories |
| Registered repositories and published mounts | [repositories.yaml](repositories.yaml) |
| Implementation architecture, routing, and code/configuration ownership | [DevOps and Dashboard Maintainers](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/devops-and-dashboard-maintainers/) |

Every Feature and category is intended to have a dedicated registered repository. Existing unsplit content in `Modul-Documents` is transitional; do not use it as the permanent home for a new Feature or category. During an existing Feature move, a registered direct `Features/<Feature>` child may overlap the exact old Documents directory: Documents remains published regardless of child contents until that directory is removed, then the child becomes effective at the same URL. All other nested mount collisions remain errors. The deployment manifest records both every registered source revision and any effective Documents fallback; preflight uses the source and registry revisions to detect changes, not the derived fallback annotation as a separate trigger. Follow the published [DevOps and Dashboard Maintainers guide](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/devops-and-dashboard-maintainers/) for onboarding and migration.

The repository registry also manages workspace support repositories. `Modul-Agents` is required for the shared VS Code Agent Skills, while `Modul-Tools` is optional for users who need conversion or inspection scripts. A repository's `workspace` value controls local checkout and workspace inclusion. A valid `mount_path` means that the repository is also assembled into the published documentation tree; repositories without a mount are never checked out by the Pages build.

The active VS Code workspace is the assistant's default access boundary. A
repository that is cloned beside Dashboard but is not included in the active
workspace is unavailable to the assistant. Use **Workspace: Configure** to
include it; do not manually clone every repository or require all repositories
for an unrelated task.

For Dashboard work, use the normal VS Code Copilot Agent chat after **Workspace: Configure** has completed. The Dashboard instructions require a skill-first workflow: the assistant checks the available `Modul-Agents` skills, announces applicable skill use, chains relevant skills, and refuses the requested work when the required Agents checkout is unavailable until setup is completed.

`Modul-Agents` is the central home for reusable cross-repository skills and
skill-authoring guidance. Project-specific `AGENTS.md`, `CLAUDE.md`,
`.github/copilot-instructions.md`, and file-scoped instruction files remain in
the repository that owns the architecture, specifications, CLI, tests, or
standalone-tool workflow. A sibling checkout is not searched automatically
unless it is included as a workspace folder or parent-repository discovery is
enabled. Check Chat customization diagnostics and response References when
verifying that a customization was discovered and used.

Always-on instructions are kept intentionally concise because they are included
in every applicable chat request. Task procedures and detailed examples belong
in scoped instructions, Agent Skills, or maintained documentation.

Generated output is written to `.local-preview/site/`; do not edit or commit it. The content assembly tree at `.local-preview/virtual-docs/` is disposable.

## Page Responsibility

Ordinary published pages show a Responsibility table in the shared content footer. It contains responsible role, owner, the Content Request project link, and the source location. Feature pages use their existing Feature tables; generated file viewers and system pages are excluded. Pages resolve responsibility from the root `responsibility.yaml`, owning category/subcategory policies, Feature `overview.yaml` overrides, and document frontmatter `owner`. See the [Page Responsibility guide](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/page-responsibility/) for precedence, exclusions, missing-value behavior, and the stakeholder workflow.

## Maintainers

For Dashboard code or configuration changes, read [DevOps and Dashboard Maintainers](https://pages.github.siemens.cloud/AS-IO/Modul-Dashboard/About/Roles-and-Ownership/devops-and-dashboard-maintainers/) and [`.github/copilot-instructions.md`](.github/copilot-instructions.md). Run the shared validation command before sharing a change:

```powershell
uv run --locked python scripts\validate.py
```
