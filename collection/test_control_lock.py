"""教師とadapterは同時取得できず、例外終了後も再取得できる。"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from control_lock import acquire_control


class ControlLockTests(unittest.TestCase):
    def test_exclusion_and_release_after_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("control_lock.LOCK_DIRECTORY", Path(directory)):
                with self.assertRaisesRegex(RuntimeError, "test interruption"):
                    with acquire_control():
                        process = subprocess.run(
                            [sys.executable, "-c", "import sys; from pathlib import Path; "
                             "import control_lock; control_lock.LOCK_DIRECTORY = Path(sys.argv[1]); "
                             "ctx = control_lock.acquire_control(); ctx.__enter__()", directory],
                            cwd=os.path.dirname(__file__), capture_output=True, text=True)
                        self.assertNotEqual(process.returncode, 0)
                        self.assertIn("already owns control", process.stderr)
                        raise RuntimeError("test interruption")
                with acquire_control():
                    pass

    def test_unknown_model(self):
        with self.assertRaises(ValueError):
            with acquire_control("unknown"):
                self.fail("unsupported model acquired control")


if __name__ == "__main__":
    unittest.main()
