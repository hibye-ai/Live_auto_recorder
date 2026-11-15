"""Exercise cleanup race handling without touching remote branches."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class BranchCleanupTests(unittest.TestCase):
    def run_cleanup(self, delete_result, remote_status):
        workflow = yaml.safe_load((ROOT / ".github/workflows/branch-cleanup.yml").read_text())
        steps = workflow["jobs"]["cleanup"]["steps"]
        script = next(step["run"] for step in steps if step.get("name") == "Delete completed work branches")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            git = directory / "git"
            git.write_text("""#!/bin/bash
case "$1" in
  fetch) exit 0 ;;
  for-each-ref) echo 'origin/dependabot/example' ;;
  ls-remote) exit "$REMOTE_STATUS" ;;
  *) exit 1 ;;
esac
""")
            gh = directory / "gh"
            gh.write_text("""#!/bin/bash
if [[ "$*" == *"--method DELETE"* ]]; then
  case "$DELETE_RESULT" in
    ok) exit 0 ;;
    missing) echo 'gh: Reference does not exist (HTTP 422)' >&2; exit 1 ;;
    forbidden) echo 'gh: Forbidden (HTTP 403)' >&2; exit 1 ;;
  esac
fi
exit 0
""")
            git.chmod(0o755)
            gh.chmod(0o755)
            env = os.environ.copy()
            env.update(PATH=tmp + os.pathsep + env["PATH"],
                       GITHUB_REPOSITORY="owner/repo",
                       DELETE_RESULT=delete_result,
                       REMOTE_STATUS=str(remote_status))
            return subprocess.run(["bash", "-c", script], cwd=ROOT, env=env,
                                  capture_output=True, text=True)

    def test_deleted_branch_succeeds(self):
        self.assertEqual(self.run_cleanup("ok", 0).returncode, 0)

    def test_already_absent_branch_is_a_benign_race(self):
        result = self.run_cleanup("missing", 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Already deleted", result.stdout)

    def test_missing_error_with_existing_branch_fails(self):
        self.assertNotEqual(self.run_cleanup("missing", 0).returncode, 0)

    def test_permission_error_even_if_absent_fails(self):
        self.assertNotEqual(self.run_cleanup("forbidden", 2).returncode, 0)

    def test_remote_lookup_failure_is_not_hidden(self):
        self.assertNotEqual(self.run_cleanup("missing", 128).returncode, 0)


if __name__ == "__main__":
    unittest.main()
