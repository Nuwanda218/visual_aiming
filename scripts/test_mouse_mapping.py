"""鼠标移动映射测试：发送固定 SendInput 值，测量桌面鼠标实际移动像素。"""

import ctypes
import ctypes.wintypes
import time

# ---- 跟 WinMouseOutput 完全一样的 SendInput 实现 ----
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
user32.GetCursorPos.argtypes = (ctypes.POINTER(ctypes.wintypes.POINT),)
user32.GetCursorPos.restype = ctypes.wintypes.BOOL

def get_pos():
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)

def send_rel(dx, dy):
    mi = MOUSEINPUT(dx=int(dx), dy=int(dy), mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
    inp = (INPUT * 1)(INPUT(type=INPUT_MOUSE, value=_INPUT_VALUE(mi=mi)))
    user32.SendInput(1, inp, ctypes.sizeof(INPUT))

# ---- 测试 ----
print("=== 鼠标移动映射测试 ===")
print("将鼠标移到屏幕中央区域（3 秒倒计时）...")
for i in range(3, 0, -1):
    print(f"  {i}...")
    time.sleep(1)

before = get_pos()
print(f"起点: {before}\n")

test_values = [1, 5, 10, 20, 50, 100, 200]
for val in test_values:
    send_rel(val, 0)
    time.sleep(0.1)
    after = get_pos()
    actual = after[0] - before[0]
    print(f"SendInput dx={val:>4d}  →  实际移动 {actual:>4d} 像素  → 比率 {actual/val:.2f} 像素/SendInput单位")

    # 移回原点
    send_rel(-actual, 0)
    time.sleep(0.2)
    before = get_pos()

print("\n提示：比率 >1 表示 SendInput 1 单位 > 1 像素。")
print("桌面测试时请关闭 Windows 指针精确度（鼠标设置 -> 指针选项）。")
