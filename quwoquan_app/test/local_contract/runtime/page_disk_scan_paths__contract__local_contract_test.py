from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "runtime"
    / "page"
    / "page_disk_scan_paths.py"
)
SPEC = importlib.util.spec_from_file_location("page_disk_scan_paths", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PageDiskScanPathsContractTest(unittest.TestCase):
    def test_scans_canonical_service_pages_shells_and_legacy_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app = root / "quwoquan_app"
            paths = (
                "lib/service/content_service/content/post/presentation/post_detail_page.dart",
                "lib/design_system/forms/settings/settings_inset_form_page.dart",
                "lib/ui/discovery/pages/discovery_page.dart",
                "lib/ui/welcome/pages/welcome_screen.dart",
                "lib/components/legacy_panel_page.dart",
                "lib/app/shell/legacy_app_shell.dart",
                "lib/runtime/di/shell/main_app_shell.dart",
                "lib/runtime/shell/recovery/recovery_page.dart",
                "lib/runtime/shell/welcome/welcome_screen.dart",
            )
            for relative in paths:
                target = app / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("// fixture\n", encoding="utf-8")

            self.assertEqual(set(paths), set(MODULE.matrix_disk_scan_paths(root)))

    def test_rejects_page_named_values_outside_presentation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app = root / "quwoquan_app"
            paths = (
                "lib/service/content_service/content/feed_delivery_page/domain/discovery_feed_page.dart",
                "lib/runtime/transport/models/cursor_page.dart",
                "lib/runtime/shell/shell_immersive_providers.dart",
            )
            for relative in paths:
                target = app / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("// fixture\n", encoding="utf-8")

            self.assertEqual(frozenset(), MODULE.matrix_disk_scan_paths(root))


if __name__ == "__main__":
    unittest.main()
