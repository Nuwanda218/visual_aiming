import importlib.util
from pathlib import Path
import unittest


def load_probe_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "mouse_gain_probe.py"
    spec = importlib.util.spec_from_file_location("mouse_gain_probe", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MouseGainProbeTests(unittest.TestCase):
    def test_build_move_sequence_repeats_requested_delta(self):
        probe = load_probe_module()

        sequence = probe.build_move_sequence(dx=100, dy=-25, count=3)

        self.assertEqual(sequence, [(100, -25), (100, -25), (100, -25)])

    def test_run_probe_uses_injected_sender_and_timing(self):
        probe = load_probe_module()
        sent = []
        sleeps = []
        positions = iter([(10, 20), (90, 20)])
        printed = []

        args = probe.ProbeArgs(dx=80, dy=0, count=2, delay=1.5, interval=0.25)
        probe.run_probe(
            args,
            sender=lambda dx, dy: sent.append((dx, dy)),
            sleeper=lambda seconds: sleeps.append(seconds),
            cursor_reader=lambda: next(positions),
            verify_cursor=True,
            printer=lambda message: printed.append(message),
        )

        self.assertEqual(sent, [(80, 0), (80, 0)])
        self.assertEqual(sleeps, [1.5, 0.25])
        self.assertTrue(any("observed cursor delta: dx=80, dy=0" in item for item in printed))
        self.assertTrue(any("send 1/2: dx=80, dy=0" in item for item in printed))
        self.assertTrue(any("done" in item for item in printed))

    def test_select_sender_rejects_unknown_backend(self):
        probe = load_probe_module()

        with self.assertRaises(ValueError):
            probe.select_sender("bad-backend")

    def test_select_sender_accepts_setcursor_and_sendinput(self):
        probe = load_probe_module()

        self.assertTrue(callable(probe.select_sender("set_cursor")))
        self.assertTrue(callable(probe.select_sender("sendinput")))

    def test_parse_args_enables_elevation_by_default(self):
        probe = load_probe_module()

        args = probe.parse_args(["--backend", "sendinput"])

        self.assertTrue(args.elevate)

    def test_parse_args_can_disable_elevation(self):
        probe = load_probe_module()

        args = probe.parse_args(["--no-elevate"])

        self.assertFalse(args.elevate)

    def test_ensure_elevated_relaunches_when_not_admin(self):
        probe = load_probe_module()
        calls = []

        result = probe.ensure_elevated(
            ["scripts/mouse_gain_probe.py", "--backend", "sendinput"],
            is_admin=lambda: False,
            relaunch=lambda argv: calls.append(argv),
        )

        self.assertTrue(result)
        self.assertEqual(calls, [["scripts/mouse_gain_probe.py", "--backend", "sendinput", "--no-elevate"]])

    def test_ensure_elevated_noops_when_admin(self):
        probe = load_probe_module()
        calls = []

        result = probe.ensure_elevated(
            ["scripts/mouse_gain_probe.py"],
            is_admin=lambda: True,
            relaunch=lambda argv: calls.append(argv),
        )

        self.assertFalse(result)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
