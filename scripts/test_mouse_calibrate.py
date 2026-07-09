"""鼠标校准工具：3 秒后发送固定 dx 移动，用于在游戏中测量映射比率。

用法：
  1. 进入游戏训练场，准星对准一个有参考标记的点（墙缝、箱子边缘等）
  2. Alt-Tab 回终端运行此脚本
  3. Alt-Tab 切回游戏
  4. 3 秒倒计时后自动发送移动
  5. 用手枪或标记弹在墙上标记准星偏移后的位置
  6. 估算准星偏移的实际像素数（可用画面分辨率做参考）
"""

import ctypes
import ctypes.wintypes
import sys
import time


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


if not _is_admin():
    print("正在请求管理员权限...")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit(0)

# ---- SendInput ----
user32 = ctypes.WinDLL("user32", use_last_error=True)
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG), ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]

class _INPUT_VALUE(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("value", _INPUT_VALUE)]

user32.SendInput.argtypes = (ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = ctypes.wintypes.UINT

def send_rel(dx, dy):
    mi = MOUSEINPUT(dx=int(dx), dy=int(dy), mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
    inp = (INPUT * 1)(INPUT(type=INPUT_MOUSE, value=_INPUT_VALUE(mi=mi)))
    user32.SendInput(1, inp, ctypes.sizeof(INPUT))


def main():
    dx = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    dy = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    print(f"即将发送 {count} 次 dx={dx}, dy={dy}")
    print("切回游戏，准星对准参考点...")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    for c in range(count):
        send_rel(dx, dy)
        print(f"  第 {c+1} 次: dx={dx}, dy={dy}")
        if count > 1:
            time.sleep(0.2)

    print("\n完成。估算准星偏移量（像素），计算：")
    print(f"  游戏像素 / SendInput单位 = 偏移像素 / {dx}")
    print(f"  把这个值填到 config.v2.json 的 control.output_scale")


if __name__ == "__main__":
    main()
