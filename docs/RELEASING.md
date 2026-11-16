# Releasing persistent-memory

Maintainer guide. Only the memory is published to PyPI, as the distribution `persistent-memory-mcp`. The policy registry in `packages/policy-registry` is not published.

The release is made by `.github/workflows/release.yml` with PyPI Trusted Publishing (OpenID Connect). No PyPI token is created or stored anywhere.

## How the workflow runs

```text
build -> qualify -> publish-testpypi -> verify-testpypi -> publish-pypi -> github-release
                                                           (tag only,       publish-mcp-registry
                                                            manual approval)
```

| Job | What it does |
| --- | --- |
| `build` | Builds the sdist and the wheel once with `python -m build`, checks that their version equals the tag without its leading `v` and equals `hermes_memory.__version__`, runs `twine check --strict`, writes `SHA256SUMS`, uploads `dist/` and the checksums as artifacts. On a tag push it also refuses a tag that is not on `main`. |
| `qualify` | Ubuntu, macOS and Windows with Python 3.11 and 3.14: installs the exact built wheel in a fresh venv, runs the test suite from `tests/` with a working directory outside the checkout, and fails on any skipped test. One more run installs the built sdist (Ubuntu, Python 3.14). |
| `publish-testpypi` | Environment `testpypi`. Uploads the built files to TestPyPI. |
| `verify-testpypi` | Ubuntu and Windows: installs `persistent-memory-mcp==<version>` from TestPyPI in a fresh venv (retrying while the index catches up), checks that TestPyPI serves the same SHA256 as the built wheel, runs `persistent-memory --version` and a smoke test (create a store, remember, search). |
| `publish-pypi` | Tag pushes only. Environment `pypi`, which waits for the required reviewer. Uploads the same files to PyPI with attestations. |
| `github-release` | Tag pushes only, after PyPI. Creates the GitHub release with the wheel, the sdist and `SHA256SUMS`; marked pre-release when the version is a pre-release. |
| `publish-mcp-registry` | Tag pushes only, after PyPI. Checks that `server.json` names the released version, waits until PyPI serves it, then publishes `server.json` to the [MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.Musyg/persistent-memory`. GitHub OIDC proves the namespace; no token is stored. `mcp-publisher` is pinned and its Sigstore bundle is verified before use. The registry accepts the entry only if the README on PyPI contains the line `mcp-name: io.github.Musyg/persistent-memory` (kept as an HTML comment at the top of README.md). |

Every job after `build` downloads the artifacts and checks their SHA256 before using them, so the files tested are the files published.

A run started by hand (`workflow_dispatch`) is a dry run: it stops after `verify-testpypi`. It stamps the files with a `.devN` suffix (for example `0.4.0a2.dev1234567890121`) because TestPyPI never accepts the same file twice. The dry run can therefore be repeated and does not use up the real version on TestPyPI.

## One-time setup

### 1. PyPI and TestPyPI accounts

The two sites have separate accounts.

1. Register at <https://pypi.org/account/register/> and at <https://test.pypi.org/account/register/>. Use an address you control.
2. Verify the e-mail address.
3. Enable two-factor authentication on both (Account settings, "Two factor authentication"). Register a security key or an authenticator app, and store the recovery codes offline.
4. Do not create an API token. Trusted Publishing replaces it.

### 2. Pending publishers

A pending publisher lets the first upload create the project, so the name `persistent-memory-mcp` is claimed by the first release. Add one on each site.

The distribution is not called `persistent-memory`: PyPI and TestPyPI refuse that name because an unrelated project, `PersistentMemory`, already exists, and the indexes treat names that differ only in case or separators as the same. The repository, the command names and the import name `persistent_memory` are not affected.

PyPI: <https://pypi.org/manage/account/publishing/>, section "Add a new pending publisher", GitHub tab.

| Field | Value |
| --- | --- |
| PyPI project name | `persistent-memory-mcp` |
| Owner | `Musyg` |
| Repository name | `persistent-memory` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

TestPyPI: <https://test.pypi.org/manage/account/publishing/>, same form.

| Field | Value |
| --- | --- |
| PyPI project name | `persistent-memory-mcp` |
| Owner | `Musyg` |
| Repository name | `persistent-memory` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

Check first that the name is free on both sites: <https://pypi.org/project/persistent-memory-mcp/> and <https://test.pypi.org/project/persistent-memory-mcp/> should answer 404, and the form must not report the name as too similar to an existing project. A pending publisher does not reserve the name until the first upload succeeds, so do not leave a long delay between setup and release.

### 3. GitHub environments

In the repository: Settings, Environments, New environment.

`testpypi`: no protection rule is needed.

`pypi`:

1. Required reviewers: add `Musyg`. If the repository has a single maintainer, leave "Prevent self-review" off, otherwise nobody can approve.
2. Deployment branches and tags: choose "Selected branches and tags", add a tag rule `v*`, and no branch rule.
3. Do not add any secret. There is none to add.

If the "Required reviewers" option is missing (some plans do not offer it on a private repository), the approval gate does not exist: do not release until it does.

### 4. Existing tag

The tag `v0.4.0a1` already exists: it is a public pre-release of 14 October 2026 ("native-effect assessment"), made before the rename. It stays as it is; this is why the first release on PyPI is `0.4.0a2`. Never delete or move a tag that has a GitHub release or files on PyPI.

## Before a release

1. `main` holds the commit to release, with the version in `pyproject.toml`, `src/hermes_memory/__init__.py` and both `version` fields of `server.json` equal, and `CHANGELOG.md` updated (replace "not yet released" by the date).
2. The CI workflow "Installed distributions" is green on that commit.
3. `python -m build` and `python -m twine check --strict dist/*` pass locally, in a clean checkout.

## Dry run (TestPyPI only)

1. Actions, "Release", "Run workflow", branch `main`.
2. The run builds, qualifies and uploads `<version>.devN` to TestPyPI, then installs it and runs the smoke test. Nothing is sent to PyPI and no GitHub release is created.
3. Look at the project at <https://test.pypi.org/project/persistent-memory-mcp/>: description, links, license and classifiers.

If the first run fails on the upload with "invalid-publisher", the pending publisher does not match: compare each field with the tables above (the workflow file name and the environment name are case-sensitive).

## Real release

1. On `main`, after the dry run:

   ```sh
   git switch main
   git pull --ff-only
   git tag -a v0.4.0a3 -m "persistent-memory 0.4.0a3"
   git push origin v0.4.0a3
   ```

2. The tag push starts the workflow. It publishes to TestPyPI and verifies there. This upload is the real version `0.4.0a3`, so it only works once: if a run fails after that upload, fix the cause and publish the next version number, as described below.
3. When `verify-testpypi` is green, the `publish-pypi` job waits for approval. Open the run, "Review deployments", check that the files and the commit are the expected ones, select `pypi` and approve.
4. After the upload, `github-release` creates the GitHub release with the wheel, the sdist and `SHA256SUMS`.

## Verify the release

```sh
python -m venv /tmp/verify && /tmp/verify/bin/python -m pip install persistent-memory-mcp==0.4.0a3
/tmp/verify/bin/persistent-memory --version
uvx --from persistent-memory-mcp==0.4.0a3 persistent-memory --version
```

Both commands print `persistent-memory 0.4.0a3`. On Windows the interpreter is `\tmp\verify\Scripts\python.exe`.

Then on <https://pypi.org/project/persistent-memory-mcp/0.4.0a3/#files>, each file shows a "Provenance" or attestation entry that names this repository, the workflow `release.yml` and the tag. Compare the SHA256 of the files with `SHA256SUMS` on the GitHub release.

The MCP Registry entry: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Musyg/persistent-memory"` lists the new version. If `publish-mcp-registry` failed while PyPI succeeded, fix the cause and re-run that job alone; the registry entry does not change the files on PyPI.

While every published version is a pre-release, `pip install persistent-memory-mcp` selects the newest one without `--pre` (checked with pip 26.2 and 26.3). Once a final version exists, pip prefers it and a pre-release needs `--pre` or an exact version.

## If something goes wrong

A version number is never reused. PyPI and TestPyPI refuse a second upload of a file name, even after the file is deleted.

- The run fails before `publish-pypi`: nothing reached PyPI. Fix the cause. If TestPyPI already holds the version, move to the next version number (`0.4.0a3`) in `pyproject.toml`, `src/hermes_memory/__init__.py` and `CHANGELOG.md`, and tag that. Delete the unused tag only if nothing was published from it.
- The approval was refused or the run was cancelled at `publish-pypi`: nothing reached PyPI. Re-run the `publish-pypi` job from the same run if the cause was only the approval; the files are the ones that were tested.
- A bad version reached PyPI: on the project page, Manage, Releases, "Yank" the release with a reason. A yanked release is skipped by `pip install persistent-memory-mcp` and stays installable by exact pin. Publish a corrected version with a new number and mention it in `CHANGELOG.md`.
- A secret or private data was published: yank at once, then ask PyPI to delete the file through the project's "Delete" option or the PyPI support form; rotate whatever leaked. Deleting does not free the version number.
- `github-release` failed after the upload: create the release by hand from the tag with the files of the run's `dist` artifact and `SHA256SUMS`. Do not rebuild them.
- Trusted Publisher misconfigured or compromised repository access: remove the publisher in the project's "Publishing" settings on PyPI, fix, add it again.
