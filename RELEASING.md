# Releasing silica-eda

Releases go to [PyPI](https://pypi.org/project/silica-eda/) and the
[official MCP registry](https://registry.modelcontextprotocol.io) from a
version tag. Pushing `vX.Y.Z` runs
[`.github/workflows/publish.yml`](.github/workflows/publish.yml), which builds,
publishes with PyPI trusted publishing, checks the published package, and then
publishes `server.json` to the MCP registry with GitHub OIDC, and creates the
GitHub release with the version's `CHANGELOG.md` section as its notes. None of
these steps uses a stored token.

## One-time setup

- **PyPI trusted publisher.** On PyPI, under silica-eda → *Manage* →
  *Publishing*, there must be a GitHub publisher with owner `simaanc`,
  repository `silica-eda`, workflow `publish.yml` and environment `pypi`. The
  workflow filename is part of the match, so don't rename the file.
- **GitHub environment.** The repository needs an environment named `pypi`
  (*Settings* → *Environments*). Under *Deployment branches and tags* it must
  allow the release tags: add a tag rule `v*.*.*`. With only a `main` branch
  rule, the publish job is refused, because it runs on the tag, not on a
  branch. The same rule from the command line:

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

## Cutting a release

1. **Check main is green**, and that `CHANGELOG.md` has an entry under
   "Unreleased" for every user-visible change since the last release.

2. **Bump the version** on an up-to-date main:

   ```bash
   uv run python scripts/bump_version.py minor     # or major, patch, or e.g. 0.4.0
   ```

   This updates `pyproject.toml`, `uv.lock` and the Claude Code plugin's
   `plugin/.claude-plugin/plugin.json` (a test fails if the plugin and package
   versions differ), moves the "Unreleased" entries
   under `## [X.Y.Z] - <today>`, adds the PyPI link at the bottom of the
   changelog, and prints the commands for the next steps. It doesn't commit,
   tag or push anything.

3. **Open the release PR** with the printed commands (`release/vX.Y.Z` branch,
   `chore: release X.Y.Z` commit, signed off). Review the changelog section and
   merge it once CI passes.

4. **Tag the merge commit and push the tag:**

   ```bash
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

   The tag must match the version in `pyproject.toml`, or the build job stops.

5. **Watch the Publish workflow** (*Actions* → *Publish to PyPI*):
   - **build**: checks the tag, builds the sdist and wheel, and starts the
     wheel in a clean environment to compare it with the tagged source over
     MCP.
   - **publish**: uploads to PyPI with trusted publishing.
   - **verify**: installs the release the way users do
     (`uvx silica-eda==X.Y.Z`) and checks that it starts, reports X.Y.Z, serves
     exactly the tools the tagged source serves, and that its `doctor` tool
     runs. It retries for a few minutes while PyPI's index catches up.
   - **registry**: runs only after verify passes. It checks that `server.json`
     names X.Y.Z, installs a pinned `mcp-publisher` (checksum-verified), and
     runs `validate`, `login github-oidc` and `publish`. It then checks that
     the registry serves X.Y.Z. Registry versions can't be changed or published
     twice, so if X.Y.Z is already there the job skips the publish and only
     runs the final check. That makes a re-run safe.
   - **github-release**: also runs after verify. It creates the `vX.Y.Z`
     GitHub release, titled `silica-eda X.Y.Z`, with the `## [X.Y.Z]` section
     of `CHANGELOG.md` as its notes (printed by `scripts/release_notes.py`)
     and the sdist and wheel attached. The build job already checked that the
     section exists and isn't empty. If the release already exists, a re-run
     only replaces the attached files and leaves the notes alone.

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
3. From a checkout of the tag:

   ```bash
   mcp-publisher validate      # checks server.json against the registry's schema
   mcp-publisher publish
   curl "https://registry.modelcontextprotocol.io/v0.1/servers/io.github.simaanc%2Fsilica-eda/versions/X.Y.Z"
   ```

`server.json` already names the new version, because the bump script updates it
along with the package version.

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
