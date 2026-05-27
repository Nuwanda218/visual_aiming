# -*- coding: utf-8 -*-
"""Manual probe for raw relative mouse movement gain."""

import argparse
import ctypes
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Tuple

Move = Tuple[int, int]
Sender = Callable[[int, int], None]
Sleeper = Callable[[float], None]
CursorReader = Callable[[], Tuple[int, int]]
Printer = Callable[[str], None]

MOUSEEVENTF_MOVE = 0x0001


@dataclass
class ProbeArgs:
    dx: int = 80
    dy: int = 0
    count: int = 2
    delay: float = 1.5
    interval: float = 0.25
    backend: str = "ctypes"
    verify_cursor: bool = True


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def build_move_sequence(dx: int, dy: int, count: int) -> List[Move]:
    return [(int(dx), int(dy)) for _ in range(max(0, int(count)))]


def send_with_ctypes(dx: int, dy: int) -> None:
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


def get_cursor_pos() -> Tuple[int, int]:
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def select_sender(backend: str) -> Sender:
    normalized = (backend or "ctypes").strip().lower()
    if normalized in {"ctypes", "mouse_event", "win32"}:
        return send_with_ctypes
    raise ValueError(f"unsupported mouse backend: {backend}")


def run_probe(
    args: ProbeArgs,
    sender: Sender,
    sleeper: Sleeper = time.sleep,
    cursor_reader: CursorReader = get_cursor_pos,
    verify_cursor: bool = True,
    printer: Printer = print,
) -> None:
    sequence = build_move_sequence(args.dx, args.dy, args.count)
    start_pos = cursor_reader() if verify_cursor else None

    if args.delay > 0:
        sleeper(args.delay)

    for index, (dx, dy) in enumerate(sequence):
        sender(dx, dy)
        if index < len(sequence) - 1 and args.interval > 0:
            sleeper(args.interval)

    if verify_cursor and start_pos is not None:
        end_pos = cursor_reader()
        delta_x = end_pos[0] - start_pos[0]
        delta_y = end_pos[1] - start_pos[1]
        printer(f"observed cursor delta: dx={delta_x}, dy={delta_y}")


def parse_args(argv: Iterable[str] | None = None) -> ProbeArgs:
    parser = argparse.ArgumentParser(description="Probe raw relative mouse movement gain.")
    parser.add_argument("--dx", type=int, default=80)
    parser.add_argument("--dy", type=int, default=0)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--backend", default="ctypes")
    parser.add_argument("--no-verify", action="store_true")
    ns = parser.parse_args(argv)
    return ProbeArgs(
        dx=ns.dx,
        dy=ns.dy,
        count=ns.count,
        delay=ns.delay,
        interval=ns.interval,
        backend=ns.backend,
        verify_cursor=not ns.no_verify,
    )


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    sender = select_sender(args.backend)
    run_probe(args, sender=sender, verify_cursor=args.verify_cursor)


if __name__ == "__main__":
    main()
