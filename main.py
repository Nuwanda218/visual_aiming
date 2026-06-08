# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Visual aiming runtime")
    parser.add_argument("--modular", action="store_true", help="Run the new modular runtime")
    parser.add_argument("--video", default="", help="Run modular replay on a video file")
    parser.add_argument("--video-test", action="store_true", help="Interactive video test with GUI file picker")
    parser.add_argument("--output", choices=["null", "log", "win_mouse"], default="null", help="Modular output backend")
    parser.add_argument("--real-mouse", action="store_true", help="Allow real mouse movement when --output win_mouse is selected")
    parser.add_argument("--diagnostics", default="", help="Write modular diagnostics JSONL to this path")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.video_test:
        from visual_aiming.app.video_test import run_video_test
        return run_video_test()
    if args.modular:
        return _run_modular(args)
    from visual_aiming.core.runtime import main as legacy_main
    return legacy_main()


def _run_modular(args):
    from visual_aiming.config.loader import load_modular_config

    config = load_modular_config("config.json")
    config.output.backend = args.output
    config.output.enable_real_mouse = bool(args.real_mouse)
    config.diagnostics.jsonl_path = args.diagnostics
    if args.video:
        from visual_aiming.app.replay import run_video_file
        run_video_file(config, args.video)
        return 0
    from visual_aiming.core.runtime import main as legacy_main
    print("[modular] Realtime modular composition is available, but legacy realtime loop remains default until screen activation is migrated.")
    return legacy_main()


if __name__ == "__main__":
    raise SystemExit(main())
