from __future__ import annotations

from typing import Callable, Iterable, Protocol


class RuntimeObserver(Protocol):
    def on_tick(self, frame, result) -> None:
        ...

    def close(self) -> None:
        ...


class RuntimeRunner:
    def __init__(
        self,
        frame_source,
        pipeline,
        observers: Iterable[RuntimeObserver] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.frame_source = frame_source
        self.pipeline = pipeline
        self.observers = list(observers or [])
        self.clock = clock

    def run_once(self):
        frame = self.frame_source.read()
        if frame is None:
            return False, None
        now = self.clock() if self.clock is not None else None
        result = self.pipeline.tick(frame, now=now)
        for observer in self.observers:
            observer.on_tick(frame, result)
        return True, result

    def run(self, max_frames: int | None = None):
        results = []
        while max_frames is None or len(results) < max_frames:
            has_frame, result = self.run_once()
            if not has_frame:
                break
            results.append(result)
        return results

    def close(self) -> None:
        for obj in [self.frame_source, *self.observers]:
            close = getattr(obj, "close", None)
            if close is not None:
                close()
