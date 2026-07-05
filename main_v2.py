"""V2 入口 — 启动前自动请求管理员权限，确保 SendInput 在各种环境下都能正常工作。"""
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _is_admin() -> bool:
    """检查当前进程是否以管理员权限运行。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _request_admin() -> None:
    """以管理员身份重新启动当前脚本。"""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit(0)


if __name__ == "__main__":
    if not _is_admin():
        print("[V2] 正在请求管理员权限...")
        _request_admin()

    from visual_aiming_v2.interaction.cli import main
    raise SystemExit(main())
