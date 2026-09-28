---
paths:
  - ".github/workflows/**"
  - "**/.github/workflows/**"
  - "**/Dockerfile"
  - "**/Dockerfile.*"
  - "**/.gitlab-ci.yml"
  - "**/Jenkinsfile"
  - "**/azure-pipelines.yml"
  - "**/.circleci/config.yml"
---
# You are editing the pipeline

CI has the credentials that production has and none of the review that production code gets. It is
the shortest path from a public pull request to your deployment keys, and it is usually written once
by whoever was unblocking themselves that afternoon.

## Supply chain

- **Pin third-party actions and images to a digest**, not a moving tag. `@v4` and `:latest` are
  whatever the publisher pushed this morning; a compromised or transferred repository becomes your
  build. Pin `uses: owner/action@<full-sha>` and images by digest, and let a bot bump them. This is
  not only for actions already in the file - it applies just as much to one you are adding right
  now for an unrelated, routine-sounding task ("add a lint step"). If other steps in the file are
  already SHA-pinned, that is the convention to match, not a detail to leave behind for the new
  one: `uses: actions/checkout@8ade135a41bc03ea155e62e844d188df1ea18608 # v4.1.0`, never
  `actions/checkout@v4`.
- A dependency install in CI resolves against the lockfile (`npm ci`, `uv sync --frozen`,
  `pip install -r` with hashes) - never a fresh resolve that can pick up a newly published version.
- New actions and new dependencies get the same "is this the real package" check as anything else.

## Permissions and secrets

- Start from `permissions: contents: read` at the workflow level and grant more per job, only where
  needed. The default token is usually broader than the job is.
- **`pull_request_target` runs with your secrets and write access.** Never combine it with checking
  out the PR's head - that runs a stranger's code against your credentials. If you only need the
  diff, use `pull_request`.
- Secrets reach a step through `env:` or `with:`, never interpolated into a `run:` script where they
  land in the log, the process list, and any error trace.
- Nothing echoes a secret, and nothing prints the full environment. `set -x` in a step that touches
  a credential writes it to a log others can read.
- Deployment credentials are short-lived and scoped to one environment. Prefer the platform's OIDC
  federation to a long-lived key in a repository secret.

## The pipeline is a test oracle, so it must not lie

- A security or quality gate that errors **fails the build**. `|| true`, `continue-on-error: true`
  and a swallowed non-zero exit turn a scanner into a decoration that reports green forever.
- Every job has a timeout. A hung job holds a runner and, worse, holds a lock nobody comes back to.
- Caches are keyed on the lockfile. A cache restored across dependency changes builds something that
  matches no manifest you can reproduce.
