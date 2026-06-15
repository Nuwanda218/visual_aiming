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
    parser.add_argument("--legacy-runtime", action="store_true", help="Temporary fallback to the old realtime runtime")
    parser.add_argument("--output", choices=["null", "log", "win_mouse"], default="null", help="Modular output backend")
    parser.add_argument("--real-mouse", action="store_true", help="Allow real mouse movement when --output win_mouse is selected")
    parser.add_argument("--mouse-method", choices=["set_cursor", "sendinput"], default="set_cursor", help="Windows mouse sender for --output win_mouse")
    parser.add_argument("--diagnostics", default="", help="Write modular diagnostics JSONL to this path")
    parser.add_argument("--analyze-log", default="", help="Analyze a modular diagnostics JSONL file")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    from visual_aiming.core.runtime_modes import RuntimeMode, choose_runtime_mode

    mode = choose_runtime_mode(args)
    if mode == RuntimeMode.ANALYZE_LOG:
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        print(format_report(analyze_jsonl(args.analyze_log)))
        return 0
    if mode == RuntimeMode.VIDEO_TEST:
        from visual_aiming.app.video_test import run_video_test

        return run_video_test()
    if mode in (RuntimeMode.MODULAR_REPLAY, RuntimeMode.MODULAR_REALTIME):
        return _run_modular(args, mode=mode)
    from visual_aiming.core.runtime import main as legacy_main

    return legacy_main()


def _run_modular(args, mode=None):
    from visual_aiming.config.loader import load_modular_config
    from visual_aiming.core.runtime_modes import RuntimeMode

    config = load_modular_config("config.json")
    config.output.backend = args.output
    config.output.enable_real_mouse = bool(args.real_mouse)
    config.output.mouse_method = args.mouse_method
    config.diagnostics.jsonl_path = args.diagnostics
    if mode == RuntimeMode.MODULAR_REPLAY:
        from visual_aiming.app.replay import run_video_file

        run_video_file(config, args.video)
        return 0
    if mode == RuntimeMode.MODULAR_REALTIME:
        from visual_aiming.app.realtime import run_realtime

        run_realtime(config)
        return 0
    raise ValueError(f"Unsupported modular mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
