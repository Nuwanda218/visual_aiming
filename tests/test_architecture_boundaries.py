import ast
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class ArchitectureBoundaryTest(unittest.TestCase):
    def test_legacy_runtime_path_has_been_removed(self):
        forbidden_paths = [
            SRC_ROOT / "visual_aiming" / "core" / "runtime.py",
            SRC_ROOT / "visual_aiming" / "core" / "runtime_services.py",
            SRC_ROOT / "visual_aiming" / "core" / "runtime_state.py",
        ]
        existing = [_display_path(path, SRC_ROOT) for path in forbidden_paths if path.exists()]

        self.assertEqual(existing, [])

    def test_modular_app_does_not_import_legacy_runtime_modules(self):
        violations = _forbidden_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "app",
            forbidden_groups={"actions", "vision"},
        )

        self.assertEqual(violations, [])

    def test_algorithms_stay_independent_from_apps_and_adapters(self):
        violations = _forbidden_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "algorithms",
            forbidden_groups={"actions", "adapters", "app", "vision"},
        )

        self.assertEqual(violations, [])

    def test_core_stays_independent_from_apps_adapters_and_legacy_runtime(self):
        violations = _forbidden_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "core",
            forbidden_groups={"actions", "adapters", "app", "ports", "ui", "vision"},
        )

        self.assertEqual(violations, [])

    def test_ports_stay_independent_from_runtime_implementations(self):
        violations = _forbidden_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "ports",
            forbidden_groups={"actions", "adapters", "algorithms", "app", "config", "ui", "vision"},
        )

        self.assertEqual(violations, [])

    def test_config_stays_independent_from_runtime_layers(self):
        violations = _forbidden_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "config",
            forbidden_groups={"actions", "adapters", "algorithms", "app", "core", "ports", "ui", "vision"},
        )

        self.assertEqual(violations, [])

    def test_adapters_do_not_depend_on_apps_or_algorithms(self):
        violations = _forbidden_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "adapters",
            forbidden_groups={"actions", "algorithms", "app", "ui"},
        )

        self.assertEqual(violations, [])

    def test_modular_app_uses_output_factory_instead_of_concrete_outputs(self):
        violations = _forbidden_module_imports(
            package_dir=SRC_ROOT / "visual_aiming" / "app",
            forbidden_modules={
                "visual_aiming.adapters.outputs.log_output",
                "visual_aiming.adapters.outputs.null_output",
                "visual_aiming.adapters.outputs.win_mouse",
            },
        )

        self.assertEqual(violations, [])

    def test_forbidden_import_scan_handles_group_import_forms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir)
            (package_dir / "module.py").write_text(
                "\n".join([
                    "import visual_aiming.config, visual_aiming.vision.detection",
                    "from visual_aiming import actions",
                ]),
                encoding="utf-8",
            )

            violations = _forbidden_imports(package_dir, forbidden_groups={"actions", "vision"})

        self.assertEqual(len(violations), 2)
        self.assertTrue(any("visual_aiming.vision.detection" in item for item in violations))
        self.assertTrue(any("visual_aiming.actions" in item for item in violations))


def _forbidden_imports(package_dir: Path, forbidden_groups: set[str]) -> list[str]:
    violations = []
    for file_path in sorted(package_dir.rglob("*.py")):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules = _import_from_modules(node)
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            for module in modules:
                group = _visual_aiming_group(module)
                if group in forbidden_groups:
                    rel = _display_path(file_path, package_dir)
                    violations.append(f"{rel}:{node.lineno}: {module}")
    return violations


def _forbidden_module_imports(package_dir: Path, forbidden_modules: set[str]) -> list[str]:
    violations = []
    for file_path in sorted(package_dir.rglob("*.py")):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules = _import_from_modules(node)
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            for module in modules:
                if module in forbidden_modules:
                    rel = _display_path(file_path, package_dir)
                    violations.append(f"{rel}:{node.lineno}: {module}")
    return violations


def _import_from_modules(node: ast.ImportFrom) -> list[str]:
    module = node.module
    if module == "visual_aiming":
        return [f"visual_aiming.{alias.name}" for alias in node.names]
    return [module] if module else []


def _visual_aiming_group(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "visual_aiming":
        return None
    return parts[1]


def _display_path(file_path: Path, package_dir: Path) -> str:
    try:
        return file_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return file_path.relative_to(package_dir).as_posix()
