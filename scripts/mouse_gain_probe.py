# -*- coding: utf-8 -*-
"""Manual probe for raw relative mouse movement gain."""

import argparse
import ctypes
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from visual_aiming.common.mouse_sender import create_mouse_sender, get_cursor_pos

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
    backend: str = "set_cursor"
    verify_cursor: bool = True


def build_move_sequence(dx: int, dy: int, count: int) -> List[Move]:
    return [(int(dx), int(dy)) for _ in range(max(0, int(count)))]


def send_with_ctypes(dx: int, dy: int) -> None:
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


def select_sender(backend: str) -> Sender:
    normalized = (backend or "set_cursor").strip().lower().replace("-", "_")
    if normalized in {"ctypes", "mouse_event", "win32"}:
        return send_with_ctypes
    if normalized in {"set_cursor", "setcursor", "cursor", "sendinput", "send_input"}:
        return create_mouse_sender(normalized)
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
    printer(f"backend={args.backend}, moves={len(sequence)}, delay={args.delay}, interval={args.interval}")
    start_pos = cursor_reader() if verify_cursor else None
    if verify_cursor and start_pos is not None:
        printer(f"start cursor: x={start_pos[0]}, y={start_pos[1]}")

    if args.delay > 0:
        printer(f"waiting {args.delay:.2f}s before first move")
        sleeper(args.delay)

    for index, (dx, dy) in enumerate(sequence):
        printer(f"send {index + 1}/{len(sequence)}: dx={dx}, dy={dy}")
        sender(dx, dy)
        if index < len(sequence) - 1 and args.interval > 0:
            sleeper(args.interval)

    if verify_cursor and start_pos is not None:
        end_pos = cursor_reader()
        delta_x = end_pos[0] - start_pos[0]
        delta_y = end_pos[1] - start_pos[1]
        printer(f"observed cursor delta: dx={delta_x}, dy={delta_y}")
    printer("done")


def parse_args(argv: Iterable[str] | None = None) -> ProbeArgs:
    parser = argparse.ArgumentParser(description="Probe raw relative mouse movement gain.")
    parser.add_argument("--dx", type=int, default=80)
    parser.add_argument("--dy", type=int, default=0)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--backend", default="set_cursor", choices=["set_cursor", "sendinput", "mouse_event"])
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
    run_probe(args, sender=sender, verify_cursor=args.verify_cursor, printer=lambda message: print(message, flush=True))


if __name__ == "__main__":
    main()
