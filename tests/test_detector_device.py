import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.vision.detection import TargetDetector
import torch


class DetectorDeviceResolutionTest(unittest.TestCase):
    def test_auto_prefers_cuda_when_available(self):
        with patch.object(torch.cuda, "is_available", return_value=True):
            device, use_half = TargetDetector()._resolve_runtime_device("auto", True)

        self.assertEqual(device, "cuda:0")
        self.assertTrue(use_half)

    def test_auto_uses_cpu_when_cuda_unavailable(self):
        with patch.object(torch.cuda, "is_available", return_value=False):
            device, use_half = TargetDetector()._resolve_runtime_device("auto", True)

        self.assertEqual(device, "cpu")
        self.assertFalse(use_half)

    def test_cuda_request_falls_back_to_cpu_when_unavailable(self):
        with patch.object(torch.cuda, "is_available", return_value=False):
            device, use_half = TargetDetector()._resolve_runtime_device("cuda", True)

        self.assertEqual(device, "cpu")
        self.assertFalse(use_half)

    def test_half_precision_is_disabled_on_cpu(self):
        with patch.object(torch.cuda, "is_available", return_value=True):
            device, use_half = TargetDetector()._resolve_runtime_device("cpu", True)

        self.assertEqual(device, "cpu")
        self.assertFalse(use_half)


if __name__ == "__main__":
    unittest.main()
