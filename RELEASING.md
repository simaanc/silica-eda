# Releasing silica-eda

Releases are automatic. Every push to `main` runs
[`.github/workflows/publish.yml`](.github/workflows/publish.yml). When the
push changes the package (anything under `silica/` or `plugin/`, or
`pyproject.toml`, `uv.lock` or `server.json`) since the latest `vX.Y.Z` tag,
the workflow releases the next patch version: it builds, publishes to
[PyPI](https://pypi.org/project/silica-eda/) with trusted publishing, tags
the commit, checks the published package, publishes `server.json` to the
[official MCP registry](https://registry.modelcontextprotocol.io) with GitHub
OIDC, and creates the GitHub release. None of these steps uses a stored
token, and nothing is committed: the version lives only in the tags.

## One-time setup

- **PyPI trusted publisher.** On PyPI, under silica-eda → *Manage* →
  *Publishing*, there must be a GitHub publisher with owner `simaanc`,
  repository `silica-eda`, workflow `publish.yml` and environment `pypi`. The
  workflow filename is part of the match, so don't rename the file.
- **GitHub environment.** The repository needs an environment named `pypi`
  (*Settings* → *Environments*). Under *Deployment branches and tags* it must
  allow the `main` branch (automatic and manually started releases run there)
  and the tag rule `v*.*.*` (a hand-pushed tag). Without the rule a run
  needs, the publish job is refused. The tag rule from the command line:

  ```bash
  gh api -X POST repos/simaanc/silica-eda/environments/pypi/deployment-branch-policies \
    -f name='v*.*.*' -f type=tag
  ```

  Adding required reviewers there makes every publish wait for an approval.
- **MCP registry.** Nothing to configure. The registry job logs in with
  `mcp-publisher login github-oidc`, which uses the job's GitHub OIDC token
  (`id-token: write`). The registry grants the `io.github.<owner>/` namespace
  of the repository that ran the workflow, so this repository can publish
  `io.github.simaanc/silica-eda` with no secret, DNS record or PAT. It only
  works from `simaanc/silica-eda`; a fork's run gets the fork owner's
  namespace and is rejected.

## How versions work

The version isn't stored in the repository. `pyproject.toml` takes it from
git tags through hatch-vcs, so a checkout between releases reports something
like `0.5.1.dev3+g1a2b3c4`. The release build sets it explicitly with
`SETUPTOOLS_SCM_PRETEND_VERSION`. `server.json` holds a placeholder that the
registry job replaces with the release version, and the Claude Code plugin's
`plugin.json` has no version, so Claude Code versions the plugin by commit
and users get plugin changes without a bump.

## Cutting a release

**Patch releases (0.5.1, 0.5.2, …) need nothing.** Merge the PR. If it
changes the package, the next patch is released. A PR that changes only CI,
tests or docs releases nothing; its changes go out with the next release
that does. The GitHub release notes are generated from the titles of the PRs
merged since the previous release, so write PR titles for users.

**Minor and major releases (0.6.0, 1.0.0) are started by hand,** and
patches then continue from them (0.6.1, 0.6.2, …): open *Actions* →
*Publish to PyPI* → *Run workflow*, keep the `main` branch, and pick
`minor` or `major`. From the command line:

```bash
gh workflow run publish.yml -f bump=minor
```

A manual run always releases, even if nothing changed since the last tag.
Pushing a `vX.Y.Z` tag by hand also releases that tag's commit as `X.Y.Z`.

Runs are queued one at a time, so two quick merges can't claim the same
version. If a run fails partway, use *Re-run failed jobs*: it keeps the
version the first attempt picked. Every publishing step skips what is
already done, so a re-run is safe.

### What the workflow does

Watch it under *Actions* → *Publish to PyPI*:

- **prepare**: finds the latest `vX.Y.Z` tag and decides whether this run is
  a release and which version it gets. For a push to `main` that is the next
  patch, and only if the package changed since that tag.
- **build**: builds the sdist and wheel with that version, and starts the
  wheel in a clean environment to compare it with the source over MCP.
- **publish**: uploads to PyPI with trusted publishing. `--check-url` skips
  files PyPI already has.
- **tag**: tags the released commit `vX.Y.Z` as soon as PyPI has it, so the
  tag marks what was published even if a later job fails. Tags created with
  the workflow's token don't start the workflow again.
- **verify**: installs the release the way users do
  (`uvx silica-eda==X.Y.Z`) and checks that it starts, reports X.Y.Z, serves
  exactly the tools the source serves, and that its `doctor` tool runs. It
  retries for a few minutes while PyPI's index catches up.
- **registry**: runs only after verify passes. It writes X.Y.Z into
  `server.json`, installs a pinned `mcp-publisher` (checksum-verified), and
  runs `validate`, `login github-oidc` and `publish`. It then checks that
  the registry serves X.Y.Z. Registry versions can't be changed or published
  twice, so if X.Y.Z is already there the job skips the publish and only
  runs the final check.
- **github-release**: also runs after verify. It creates the `vX.Y.Z`
  GitHub release, titled `silica-eda X.Y.Z`, with notes generated from the
  merged PRs and the sdist and wheel attached. If the release already
  exists, a re-run only replaces the attached files.

## Publish to the MCP registry by hand

The registry job normally does this. Publish by hand only if the job can't
run, for example while the registry rejects the pinned `mcp-publisher`. The
registry verifies the PyPI package by reading the published release's
description (the README) for `mcp-name: io.github.simaanc/silica-eda`, so this
only works once the release is on PyPI.

1. Install `mcp-publisher` from the
   [registry releases](https://github.com/modelcontextprotocol/registry/releases)
   (`brew install mcp-publisher` also works).
2. Run `mcp-publisher login github` and authorize with the `simaanc` GitHub
   account. Run it again when the token expires ("Invalid or expired Registry
   JWT token").
3. From a checkout of the tag, with `server.json` set to the release version
   (`jq '.version = "X.Y.Z" | .packages[0].version = "X.Y.Z"'`):

   ```bash
   mcp-publisher validate      # checks server.json against the registry's schema
   mcp-publisher publish
   curl "https://registry.modelcontextprotocol.io/v0.1/servers/io.github.simaanc%2Fsilica-eda/versions/X.Y.Z"
   ```

### Updating mcp-publisher

The workflow pins `MCP_PUBLISHER_VERSION` and `MCP_PUBLISHER_SHA256`. The
registry rejects logins from publishers that are too old with "invalid
audience". To update, take the version from the
[releases page](https://github.com/modelcontextprotocol/registry/releases) and
the `mcp-publisher_linux_amd64.tar.gz` line from that release's
`registry_<version>_checksums.txt`.

## Post-release check

The verify job does this automatically. To repeat it by hand from a checkout of
the tag:

```bash
uv run python scripts/check_release.py --version X.Y.Z \
  --server "uvx --refresh silica-eda==X.Y.Z" \
  --expect-from "uv run silica serve"
```

To try the release the way an MCP client starts it, run
`uvx --refresh silica-eda==X.Y.Z`. It waits for MCP messages on stdin (press
Ctrl-C to stop); errors at startup show up immediately. Clients configured with
`uvx silica-eda@latest` pick up the new release the next time they start the
server.

## If a release is broken

PyPI never lets a version be uploaded twice, even after deletion. Fix forward:
land the fix, release a new patch version, and
[yank](https://pypi.org/help/#yanked) the broken one on PyPI so installers skip
it. Users pinned to the broken version can roll back by pinning the previous
one (`uvx silica-eda==<previous>`).
