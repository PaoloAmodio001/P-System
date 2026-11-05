"""The hook refuses a commit when the fast tests or the proofs fail, in a real repository.

`python3` and `lake` are stand-ins that exit as a test says, so nothing here runs the suite. Each
case that expects a refusal is the proof that the test can fail: see the two with the hook altered.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = (ROOT / "scripts" / "pre-commit").read_text()
INSTALLER = (ROOT / "scripts" / "install_hooks.sh").read_text()


def _stand_in(directory: Path, name: str, code: int, log: Path) -> None:
    path = directory / name
    path.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit {code}\n')
    path.chmod(0o755)


def _git(repository: Path, *arguments: str, env: dict | None = None):
    return subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *arguments],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "formal" / "lean").mkdir(parents=True)
    (repo / "scripts" / "pre-commit").write_text(HOOK)
    (repo / "scripts" / "install_hooks.sh").write_text(INSTALLER)
    assert _git(repo, "init", "-q").returncode == 0
    return repo


def _install(repository: Path) -> None:
    result = subprocess.run(
        ["sh", "scripts/install_hooks.sh"],
        cwd=repository,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _commit(repository: Path, tmp_path: Path, pytest_code: int, lake_code: int):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    _stand_in(bin_dir, "python3", pytest_code, log)
    _stand_in(bin_dir, "lake", lake_code, log)
    (repository / "file").write_text(str((pytest_code, lake_code)))
    assert _git(repository, "add", "file").returncode == 0
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    result = _git(repository, "commit", "-q", "-m", "a commit", env=env)
    calls = log.read_text() if log.exists() else ""
    return result, calls


def _has_commit(repository: Path) -> bool:
    return _git(repository, "rev-parse", "-q", "--verify", "HEAD").returncode == 0


def test_both_green_lets_the_commit_through(repository, tmp_path):
    _install(repository)
    result, calls = _commit(repository, tmp_path, 0, 0)
    assert result.returncode == 0, result.stderr
    assert _has_commit(repository)
    assert 'python3 -m pytest -q -m not slow' in calls
    assert "lake build" in calls


def test_failing_tests_refuse_the_commit(repository, tmp_path):
    _install(repository)
    result, calls = _commit(repository, tmp_path, 1, 0)
    assert result.returncode != 0
    assert not _has_commit(repository)
    assert "fast tests failed" in result.stderr
    assert "lake" not in calls


def test_failing_proofs_refuse_the_commit(repository, tmp_path):
    _install(repository)
    result, _ = _commit(repository, tmp_path, 0, 1)
    assert result.returncode != 0
    assert not _has_commit(repository)
    assert "lake build failed" in result.stderr


def test_a_hook_that_exists_is_not_overwritten(repository):
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n")
    result = subprocess.run(
        ["sh", "scripts/install_hooks.sh"],
        cwd=repository,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert hook.read_text() == "#!/bin/sh\nexit 0\n"


@pytest.mark.parametrize(
    "old,pytest_code,lake_code",
    [
        ('if ! python3 -m pytest -q -m "not slow"; then', 1, 0),
        ("if ! lake build; then", 0, 1),
    ],
)
def test_a_hook_without_the_check_lets_a_bad_commit_through(
    repository, tmp_path, old, pytest_code, lake_code
):
    # The same run as the refusals above, with one check removed: they are what stops the commit.
    source = repository / "scripts" / "pre-commit"
    assert HOOK.count(old) == 1
    source.write_text(HOOK.replace(old, "if false; then"))
    _install(repository)
    result, _ = _commit(repository, tmp_path, pytest_code, lake_code)
    assert result.returncode == 0, result.stderr
    assert _has_commit(repository)
