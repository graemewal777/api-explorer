import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "commit-health.sh"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class CommitHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.remote = base / "remote.git"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.remote))

        self.work = base / "work"
        git(base, "clone", "-q", str(self.remote), str(self.work))
        self.configure(self.work)
        git(self.work, "checkout", "-q", "-b", "main")
        (self.work / "README.md").write_text("hello\n")
        (self.work / "data").mkdir()
        (self.work / "data" / "health.json").write_text('{"last_run": "2026-10-21", "failing": {}}\n')
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "initial")
        git(self.work, "push", "-q", "-u", "origin", "main")

    def configure(self, repo):
        git(repo, "config", "user.name", "someone-else")
        git(repo, "config", "user.email", "someone@example.com")

    def run_script(self):
        return subprocess.run(["bash", str(SCRIPT)], cwd=self.work, capture_output=True, text=True)

    def remote_head(self):
        return git(self.remote, "rev-parse", "main")

    def write_state(self, text):
        # like healthcheck.save_state, create the folder if the first run finds it missing
        (self.work / "data").mkdir(exist_ok=True)
        (self.work / "data" / "health.json").write_text(text)

    def test_unchanged_state_makes_no_commit(self):
        before = self.remote_head()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), before)
        self.assertEqual(self.remote_head(), before)

    def test_changed_state_is_committed_by_the_bot_and_pushed(self):
        self.write_state('{"last_run": "2026-10-22", "failing": {}}\n')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote_head(), git(self.work, "rev-parse", "HEAD"))
        self.assertEqual(git(self.remote, "log", "-1", "--format=%an <%ae>", "main"), "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>")
        self.assertIn("Link health check", git(self.remote, "log", "-1", "--format=%s", "main"))
        self.assertEqual(git(self.remote, "rev-list", "--count", "main"), "2")

    def test_only_the_health_file_is_committed(self):
        self.write_state('{"last_run": "2026-10-22", "failing": {}}\n')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = git(self.remote, "show", "--name-only", "--format=", "main").splitlines()
        self.assertEqual(changed, ["data/health.json"])

    def test_first_ever_run_creates_the_file(self):
        git(self.work, "rm", "-q", "data/health.json")
        git(self.work, "commit", "-q", "-m", "remove state")
        git(self.work, "push", "-q", "origin", "main")
        self.write_state('{"last_run": "2026-10-22", "failing": {}}\n')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("data/health.json", git(self.remote, "show", "--name-only", "--format=", "main"))

    def test_main_moving_while_the_job_ran_is_rebased_over_not_clobbered(self):
        other = Path(self.tmp.name) / "other"
        git(Path(self.tmp.name), "clone", "-q", str(self.remote), str(other))
        self.configure(other)
        (other / "bump.txt").write_text("a bot bumped the submodule meanwhile\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "concurrent change")
        git(other, "push", "-q", "origin", "main")

        self.write_state('{"last_run": "2026-10-22", "failing": {}}\n')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        files = git(self.remote, "ls-tree", "-r", "--name-only", "main").splitlines()
        self.assertIn("bump.txt", files)
        self.assertEqual(git(self.remote, "show", "main:data/health.json"), '{"last_run": "2026-10-22", "failing": {}}')
        self.assertEqual(self.remote_head(), git(self.work, "rev-parse", "HEAD"))

    def test_losing_a_race_after_the_rebase_fails_instead_of_overwriting(self):
        # main moves once before the job (so the rebase has real work to do) and again in the
        # instant after the rebase, before the push (a post-rewrite hook pushes from another
        # clone). A normal push is rejected; a forced one would silently erase that commit.
        other = Path(self.tmp.name) / "other"
        git(Path(self.tmp.name), "clone", "-q", str(self.remote), str(other))
        self.configure(other)
        (other / "bump.txt").write_text("moved before the job\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "concurrent change")
        git(other, "push", "-q", "origin", "main")

        hook = self.work / ".git" / "hooks" / "post-rewrite"
        hook.write_text(
            "#!/usr/bin/env bash\n"
            f'[ -e "{other}/race.txt" ] && exit 0\n'
            f'cd "{other}"\n'
            "unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE\n"
            "echo racing > race.txt && git add -A && git commit -q -m race && git push -q origin main\n"
        )
        hook.chmod(0o755)

        self.write_state('{"last_run": "2026-10-22", "failing": {}}\n')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        files = git(self.remote, "ls-tree", "-r", "--name-only", "main").splitlines()
        self.assertIn("race.txt", files)  # the concurrent commit survived
        self.assertEqual(git(self.remote, "show", "main:data/health.json"), '{"last_run": "2026-10-21", "failing": {}}')

    def test_missing_state_file_is_an_error_and_pushes_nothing(self):
        before = self.remote_head()
        (self.work / "data" / "health.json").unlink()
        git(self.work, "rm", "-q", "--cached", "data/health.json")
        git(self.work, "commit", "-q", "-m", "drop it locally only")
        local_only = git(self.work, "rev-parse", "HEAD")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("health.json", result.stderr)  # a real complaint about the file, not just "script not found"
        self.assertEqual(self.remote_head(), before)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), local_only)


if __name__ == "__main__":
    unittest.main()
