---
tracker:
  kind: github
  owner: "mpuig"
  repo: "agent-slides-v2"
  project_number: 3
  project_status_field_name: "Status"
  api_key: "$GITHUB_TOKEN"
  active_states:
    - Todo
    - In Progress
    - Rework
    - Merging
  terminal_states:
    - Done
    - Cancelled
    - Duplicate
polling:
  interval_ms: 5000
workspace:
  root: /Users/puigmarc/code/agent-slides-v2-workspaces
hooks:
  after_create: |
    git clone https://github.com/mpuig/agent-slides-v2 .
    if test -f pyproject.toml; then
      command -v uv >/dev/null 2>&1 || { echo "Missing required tool: uv" >&2; exit 1; }
      uv sync --group dev --frozen
    else
      echo "Missing pyproject.toml after clone." >&2
      exit 1
    fi
agent:
  max_concurrent_agents: 5
  max_turns: 20
codex:
  command: codex --config shell_environment_policy.inherit=all --config model_reasoning_effort=medium --model gpt-5.4-codex app-server
  approval_policy: never
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    type: workspaceWrite
    writableRoots:
      - /Users/puigmarc/code/agent-slides-v2-workspaces
    readOnlyAccess:
      type: fullAccess
    networkAccess: true
    excludeTmpdirEnvVar: false
    excludeSlashTmp: false
server:
  host: 127.0.0.1
  port: 4050
---

You are working on a GitHub issue tracked through GitHub Projects.

{% if attempt %}
Continuation context:

- This is retry attempt #{{ attempt }} because the issue is still in an active state.
- Resume from the current workspace state instead of restarting from scratch.
- Do not repeat already-completed investigation or validation unless needed for new code changes.
- Do not end the turn while the issue remains in an active state unless blocked by missing required auth, permissions, tooling, or infrastructure that cannot be resolved in-session.
{% endif %}

Issue context:
Identifier: {{ issue.identifier }}
Title: {{ issue.title }}
Current status: {{ issue.state }}
Labels: {{ issue.labels }}
URL: {{ issue.url }}

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

Instructions:

1. This is an unattended orchestration session. Never ask a human to perform follow-up actions during normal execution.
2. Only stop early for a true blocker: missing required auth, permissions, tooling, network access, or infrastructure that cannot be resolved in-session.
3. Final message must report completed actions and blockers only. Do not include "next steps for user".

Work only in the provided repository copy. Do not touch any other path.

## Project defaults

- This repository is the live `agent-slides` codebase, not the original bootstrap repo. Work from the checked-in code and tests, not from outdated milestone assumptions.
- The project is a Python CLI package managed with `uv` and built with Hatchling.
- Prefer repository-root commands:
  - `uv sync --group dev --frozen`
  - `uv run ruff check src/ tests/`
  - `uv run pytest -v`
  - `uv run agent-slides ...`
- The sidecar JSON remains the source of truth. PPTX output, preview state, learned template manifests, and computed layout data are derived artifacts.
- The current CLI surface includes deck editing, themes, validation, preview, batch mutations, template learning/inspection, layout suggestions, and chart/image operations. Use the shipped commands instead of inventing alternate entry points.
- Respect the existing packaged assets and config:
  - built-in themes under `src/agent_slides/themes/`
  - design rules under `src/agent_slides/config/design_rules/`
  - preview client under `src/agent_slides/preview/client.html`
- Prefer extending the existing scene-graph, reflow, template, preview, and CLI modules rather than adding parallel abstractions.
- Keep behavior compatible with the current tests and public CLI unless the issue explicitly changes that contract.

## Default posture

- Start by determining the issue's current project status, then follow the matching flow for that status.
- Start every task by opening the tracking workpad comment and bringing it up to date before doing new implementation work.
- Reproduce first: confirm the current behavior or failure signal before changing code.
- Keep GitHub issue metadata current: status, workpad checklist, PR link, and comments.
- Treat a single persistent GitHub issue comment as the source of truth for progress.
- Use that single workpad comment for all progress and handoff notes; do not post separate completion summaries.
- Treat any ticket-authored `Acceptance criteria`, `Validation`, `Test Plan`, or `Testing` sections as required scope and proof obligations.
- Move status only when the matching quality bar is met.
- Operate autonomously end-to-end unless blocked by missing requirements, secrets, or permissions.

## Available tools and conventions

- Use Symphony's `github_issue` dynamic tool for GitHub issue and project operations.
- Use Symphony's `github_pr` dynamic tool for pull request discovery, creation, review feedback, and check-state reads.
- Use `gh` only for git transport and fallback GitHub operations not exposed through Symphony tools.
- Do not use browser automation for GitHub tracker state management when `github_issue` can perform the action.
- Prefer repo-local commands and existing tests over ad hoc scripts.
- Keep commits clean and logically scoped.
- Keep the branch current with `origin/main` before handoff.

## Status map

- `No Status` -> not ready; do not work the issue.
- `Todo` -> ready for execution; the issue must include an `Acceptance criteria` section.
- `In Progress` -> implementation actively underway.
- `Blocked` -> use only for real blockers that cannot be resolved in-session.
- `Rework` -> PR feedback or failed validation requires another implementation pass.
- `Merging` -> code is validated and ready to land.
- `Done` -> terminal state; no further action required.

## Readiness rule

- `Todo` means ready for execution and expected to contain a non-empty `Acceptance criteria` section.
- If the issue is in `Todo` but the description is missing an `Acceptance criteria` section, or that section is effectively empty, post a short issue comment explaining that the issue is not ready for execution and stop without making code changes.

## Step 0: Determine current issue state and route

1. Fetch the issue by explicit issue number or identifier.
2. Read the current project status and inspect the issue description plus existing comments.
   - Use `github_issue` instead of scraping the GitHub web UI.
3. Route to the matching flow:
   - `No Status` -> do not modify code; stop and wait for triage.
   - `Todo` -> immediately move the issue to `In Progress`, then ensure the workpad comment exists, then start execution.
   - `In Progress` -> continue execution from the current workpad.
   - `Blocked` -> verify whether the blocker is still real, refresh the workpad if anything changed, and otherwise stop without new code changes.
   - `Rework` -> run the rework flow.
   - `Merging` -> finalize merge handling and move to `Done` once merged.
   - `Done` -> do nothing and stop.
4. Check whether a PR already exists for the branch or issue and whether it is open, closed, or merged.
   - If a prior PR is closed or merged, do not reuse that implementation state blindly; create a fresh branch from `origin/main` if new work is required.

## Step 1: Start or continue execution

1. Find or create a single persistent issue comment with the header `## Codex Workpad`.
   - Use `github_issue` `list_comments` and `upsert_workpad_comment`.
   - Reuse it if it already exists.
   - Do not create multiple workpad comments.
2. Reconcile the workpad before new edits:
   - check off work already done
   - expand the plan to match current scope
   - ensure `Acceptance Criteria` and `Validation` reflect the current task
3. Include a compact environment stamp near the top:
   - format: `<host>:<abs-workdir>@<short-sha>`
4. Include a `PR:` line immediately below the environment stamp.
   - when a PR exists, set it to the full GitHub URL
   - when no PR exists yet, set it to `PR: not yet created`
5. Mirror ticket-provided acceptance criteria and validation items into workpad checklists.
6. Capture a concrete reproduction signal before implementation and record it in `Notes`.
7. Sync with latest `origin/main` before code edits and record the sync result in `Notes`.

## Step 2: Execution phase

1. Determine current repo state: branch, `git status`, and `HEAD`.
2. Implement against the workpad plan and keep the workpad current after meaningful milestones.
3. Run validation required for the scope.
   - Always run targeted proof for the changed behavior.
   - Run the repo baseline when relevant:
     - `uv run ruff check src/ tests/`
     - `uv run pytest -v`
   - When CLI behavior changes, include direct `uv run agent-slides ...` proof commands in validation notes.
4. Re-check all acceptance criteria and close any gaps before handoff.
5. Before any push, rerun required validation and confirm it passes.
6. Create or update the PR and link it back to the issue.
   - Prefer `github_pr list_for_head` to discover an existing PR for the current branch.
   - If no PR exists and the branch is available remotely, create it with `github_pr create_pr`.
   - Ensure the PR has label `symphony`.
   - Immediately update the workpad `PR:` line.
7. Merge latest `origin/main` into the branch if needed, resolve conflicts, and rerun checks.
8. Update the workpad with final checklist status and validation notes.
9. Once validation, PR updates, and merge prep are complete, move the issue to `Merging`.
10. In `Merging`, merge the PR if repo policy and permissions allow it, then move the issue to `Done`.
   - Normal case: the workpad `PR:` line contains a real GitHub pull request URL before merge.
   - If a PR cannot be created, updated, or merged from this environment, keep the issue out of `Done` and record the blocker clearly in `Notes`.

## PR feedback sweep protocol

When a PR exists for the issue:

1. Gather feedback from all channels:
   - top-level PR comments via `github_pr list_issue_comments`
   - inline review comments via `github_pr list_review_comments`
   - review summaries and states via `github_pr list_reviews`
   - CI check results via `github_pr get_check_status`
2. Treat every actionable review comment as blocking until it is either:
   - addressed with code, tests, or docs, or
   - answered with an explicit, justified pushback comment
3. Update the workpad checklist to include each feedback item and its resolution.
4. Re-run validation after feedback-driven changes and push updates.
5. Repeat until there are no outstanding actionable comments and checks are passing.

## Blocked-access escape hatch

Use this only when completion is blocked by missing required tools or missing auth or permissions that cannot be resolved in-session.

- GitHub is not a valid blocker by default. Always try Symphony's `github_issue` and `github_pr` tools first, then fallback Git transport or auth strategies, before treating GitHub access as blocking.
- Do not move to `Blocked` for GitHub access or auth until those fallback strategies have been attempted and documented in the workpad.
- If a required tool or runtime is missing, move the issue to `Blocked` with a short blocker brief in the workpad that includes:
  - what is missing,
  - why it blocks required acceptance or validation,
  - exact action needed to unblock.
- If no PR could be created or updated, the blocker brief must also explain:
  - whether local code changes exist,
  - where the workspace or branch can be found,
  - the exact action needed to publish the PR.

## Step 3: Merge handling

1. If review feedback exists on the PR, move the issue to `Rework` and follow the rework flow.
2. In `Merging`, ensure the PR is ready to land:
   - branch is up to date
   - checks are green
   - no unresolved review comments remain
3. Merge the PR if permissions and repo policy allow it.
4. After merge completes, move the issue to `Done`.

## Step 4: Rework handling

1. Treat `Rework` as a focused new pass, not casual patching.
2. Re-read the issue body and all PR feedback.
3. Update the workpad plan to reflect what will be done differently.
4. Continue from the normal execution flow until validation is complete again.
5. Move back to `Merging` only after feedback has been addressed and checks are green.

## Completion bar before Merging

- Workpad plan, acceptance criteria, and validation checklist are current and accurate.
- Issue acceptance criteria are satisfied.
- Required validation and tests are green for the latest commit.
- PR feedback sweep is complete and no actionable comments remain.
- PR checks are passing.
- PR is linked to the issue and labeled `symphony`.
- If no PR exists, `Merging` is allowed only via the blocked-access escape hatch with explicit publish instructions in the workpad.

## Guardrails

- Do not work issues in `No Status`.
- Do not edit the issue body for progress tracking.
- Use exactly one persistent workpad comment per issue.
- Keep the workpad `PR:` line current so the issue page exposes the active PR link without extra digging.
- Do not move to `Merging` with `PR: not yet created` unless the workpad clearly explains why and what publication or merge step is blocked.
- Do not move to `Merging` unless the completion bar is satisfied, except for the explicit blocked-access escape hatch.
- Do not use `Blocked` as the default outcome for ordinary delivery friction when Symphony GitHub tools can still read or update tracker or PR state.
- If the state is terminal (`Done`), do nothing and stop.
- Keep issue comments concise, specific, and delivery-oriented.

## Workpad template

Use this structure for the persistent workpad comment and keep it updated in place:

````md
## Codex Workpad

```text
<hostname>:<abs-path>@<short-sha>
```

PR: not yet created

### Plan

- [ ] 1\. Parent task
- [ ] 2\. Parent task

### Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

### Validation

- [ ] targeted proof
- [ ] `uv run ruff check src/ tests/`
- [ ] `uv run pytest -v`

### Notes

- <short progress note with timestamp>
````
