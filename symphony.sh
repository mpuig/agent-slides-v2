#!/usr/bin/env fish

set -l script_dir (cd (dirname (status --current-filename)); pwd)
set -l workflow_file
set -l symphony_elixir_dir
set -l symphony_port 4050

if set -q SYMPHONY_WORKFLOW_FILE
    set workflow_file "$SYMPHONY_WORKFLOW_FILE"
else
    set workflow_file "$script_dir/WORKFLOW.github.md"
end

if set -q SYMPHONY_PORT
    set symphony_port "$SYMPHONY_PORT"
end

if set -q SYMPHONY_ELIXIR_DIR
    set symphony_elixir_dir "$SYMPHONY_ELIXIR_DIR"
else if test -d "$script_dir/../symphony/elixir"
    set symphony_elixir_dir "$script_dir/../symphony/elixir"
else if test -d "$script_dir/symphony/elixir"
    set symphony_elixir_dir "$script_dir/symphony/elixir"
else
    echo "Missing Symphony Elixir directory. Set SYMPHONY_ELIXIR_DIR or clone Symphony next to this project." >&2
    exit 1
end

if not test -f "$workflow_file"
    echo "Missing workflow file: $workflow_file" >&2
    exit 1
end

if not command -q mise
    echo "Missing required tool: mise" >&2
    exit 1
end

if not set -q GITHUB_TOKEN
    if not command -q gh
        echo "Missing gh; cannot infer GITHUB_TOKEN automatically." >&2
        exit 1
    end

    set -l github_token (gh auth token 2>/dev/null)

    if test -z "$github_token"
        echo "Missing GITHUB_TOKEN and unable to read one from gh auth token." >&2
        exit 1
    end

    set -gx GITHUB_TOKEN "$github_token"
end

cd "$symphony_elixir_dir"; or exit 1

mise trust >/dev/null; or exit 1
mise install; or exit 1

if not test -x "$symphony_elixir_dir/bin/symphony"
    echo "Bootstrapping Symphony in $symphony_elixir_dir" >&2
    mise exec -- mix setup; or exit 1
end

echo "Building Symphony from $symphony_elixir_dir" >&2
mise exec -- mix build; or exit 1

exec mise exec -- ./bin/symphony \
    --i-understand-that-this-will-be-running-without-the-usual-guardrails \
    --port "$symphony_port" \
    $argv \
    "$workflow_file"
