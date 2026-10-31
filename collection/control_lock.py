"""同じROSホスト上の教師とpolicy adapterの指令を排他にする。"""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path


LOCK_DIRECTORY = Path("/tmp")


@contextmanager
def acquire_control(model="v2_1_1"):
    if model != "v2_1_1":
        raise ValueError("only the pinned v2_1_1 model is supported")
    # 起動元ごとのTMPDIRの違いで教師とadapterが別lockを使わない。
    path = LOCK_DIRECTORY / f"lifth-pai-{os.getuid()}-{model}-control.lock"
    # ファイルをunlinkしない。別inodeへの再作成による二重取得を防ぐ。
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("teacher or policy adapter already owns control") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
