from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_ops" / "gate" / "scaffold" / "verify_test_no_fake.py"


def _load_gate():
    script_dir = str(SCRIPT.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("verify_test_no_fake", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoFakeGateContractTest(unittest.TestCase):
    def test_api_integration_substitute_libraries_are_rejected_by_import_edge(
        self,
    ) -> None:
        gate = _load_gate()
        samples = (
            (
                Path("tests/api_integration/x/store__api_integration_test.go"),
                'package x\n\nimport (\n\t"testing"\n\t'
                '"go.uber.org/mock/gomock"\n)\n',
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.go"),
                'package x\n\nimport "github.com/alicebob/miniredis/v2"\n',
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.py"),
                "from unittest.mock import MagicMock\n",
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.py"),
                "from unittest import mock\n",
            ),
            (
                Path("test/api_integration/x/store__api_integration_test.dart"),
                "import 'package:mocktail/mocktail.dart';\n",
            ),
        )
        for path, text in samples:
            with self.subTest(path=path.name, text=text.splitlines()[-1]):
                self.assertTrue(gate.substitute_library_imports(path, text), text)

    def test_cleanly_named_double_is_caught_by_structure_not_vocabulary(self) -> None:
        """干净名字由 import 边命中；可识别的 same-file 名字由词法规则补齐。"""
        gate = _load_gate()
        path = Path(
            "quwoquan_service/services/chat-service/tests/api_integration/chat/"
            "message/message_store__api_integration_test.go"
        )
        text = (
            "package message\n\n"
            "import (\n"
            '\t"testing"\n'
            '\t"go.uber.org/mock/gomock"\n'
            ")\n\n"
            "func TestListMessages(t *testing.T) {\n"
            "\tctrl := gomock.NewController(t)\n"
            "\tstore := NewStore(ctrl)\n"
            "\t_ = store\n"
            "}\n"
        )
        self.assertEqual(
            gate.substitute_library_imports(path, text),
            ["go.uber.org/mock/gomock"],
        )
        self.assertEqual(gate.lexical_substitute_names(path, text), [])

    def test_new_memory_constructor_is_rejected_but_httptest_is_not(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_service/services/assistant-service/tests/api_integration/"
            "assistant/skill_package_release/memory_profile__api_integration_test.go"
        )
        text = (
            "package skillpackagerelease\n\n"
            "import (\n"
            '\t"net/http/httptest"\n'
            '\t"testing"\n'
            ")\n\n"
            "func TestMemoryProfileAssets(t *testing.T) {\n"
            "\tprofile := NewMemoryProfile(t.Context())\n"
            "\trecorder := httptest.NewRecorder()\n"
            "\thandler.ServeHTTP(recorder, httptest.NewRequest(\"GET\", \"/x\", nil))\n"
            "\t_ = profile\n"
            "}\n"
        )
        self.assertEqual(gate.substitute_library_imports(path, text), [])
        self.assertIsNone(gate.FAKE_BUILD_TAG_RE.search(text))
        self.assertEqual(gate.lexical_substitute_names(path, text), ["NewMemoryProfile"])

    def test_lowercase_memory_factory_and_memory_noop_composites_are_rejected(
        self,
    ) -> None:
        gate = _load_gate()
        path = Path("tests/api_integration/x/store__api_integration_test.go")
        text = (
            "package x\n"
            "func TestX(t *testing.T) {\n"
            "  _ = newMemoryReviewStore()\n"
            "  _ = MemoryStore{}\n"
            "  _ = NoopWriter{}\n"
            "}\n"
        )
        self.assertEqual(
            gate.lexical_substitute_names(path, text),
            ["MemoryStore", "NoopWriter", "newMemoryReviewStore"],
        )

    def test_business_memory_value_name_is_not_a_substitute_by_vocabulary(self) -> None:
        gate = _load_gate()
        path = Path("tests/api_integration/x/profile__api_integration_test.go")
        text = (
            "package x\n"
            "type MemoryProfile struct{}\n"
            "func TestX(t *testing.T) { _ = MemoryProfile{} }\n"
        )
        self.assertEqual(gate.lexical_substitute_names(path, text), [])

    def test_same_file_substitute_constructors_are_lexically_rejected(self) -> None:
        gate = _load_gate()
        samples = (
            (
                Path("tests/api_integration/x/store__api_integration_test.go"),
                "package x\nfunc TestX(t *testing.T) { _ = FakeStore{}; _ = NewMemoryStore() }\n",
                ["FakeStore", "NewMemoryStore"],
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.dart"),
                "void main() { MockClient(); NoopWriter(); StubReader(); }\n",
                ["MockClient", "NoopWriter", "StubReader"],
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.py"),
                "def test_x():\n    return FakeStore(), MemoryClient()\n",
                ["FakeStore", "MemoryClient"],
            ),
        )
        for path, text, expected in samples:
            with self.subTest(path=path):
                self.assertEqual(gate.lexical_substitute_names(path, text), expected)

    def test_same_file_substitute_declarations_are_lexically_rejected(self) -> None:
        gate = _load_gate()
        samples = (
            (
                Path("tests/api_integration/x/store__api_integration_test.go"),
                "package x\ntype FakeStore struct{}\n",
                ["FakeStore"],
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.dart"),
                "class NoopWriter implements Writer {}\n",
                ["NoopWriter"],
            ),
            (
                Path("tests/api_integration/x/store__api_integration_test.py"),
                "class StubClient:\n    pass\n",
                ["StubClient"],
            ),
        )
        for path, text, expected in samples:
            with self.subTest(path=path):
                self.assertEqual(gate.lexical_substitute_names(path, text), expected)

    def test_substitute_names_inside_comments_or_strings_are_ignored(self) -> None:
        gate = _load_gate()
        path = Path("tests/api_integration/x/store__api_integration_test.go")
        text = (
            "package x\n"
            "// NewMemoryStore()\n"
            "/* FakeStore{} */\n"
            "const decoy = \"MockClient()\"\n"
        )
        self.assertEqual(gate.lexical_substitute_names(path, text), [])

    def test_memory_mode_configuration_is_still_rejected(self) -> None:
        gate = _load_gate()
        path = Path("tests/api_integration/x/store__api_integration_test.go")
        self.assertEqual(
            gate.lexical_memory_modes(path, 'router := SceneConfig{Mode: "memory"}'),
            ["mode:memory"],
        )
        self.assertEqual(
            gate.lexical_memory_modes(
                path,
                '// SceneConfig{Mode: "memory"}\nconst decoy = "Mode: memory"',
            ),
            [],
        )

    def test_first_party_support_imports_are_lexically_resolved(self) -> None:
        gate = _load_gate()
        samples = (
            (
                Path("quwoquan_service/services/x/tests/api_integration/x/y/case.go"),
                'package y\nimport "quwoquan_service/services/x/tests/support"\n',
            ),
            (
                Path("quwoquan_app/test/api_integration/x/y/z/case.dart"),
                "import '../../../../support/x/y/z/double.dart';\n",
            ),
            (
                Path("quwoquan_app/test/api_integration/x/y/z/case.py"),
                "from tests.support.fixture import value\n",
            ),
        )
        for path, text in samples:
            with self.subTest(path=path):
                self.assertTrue(gate.first_party_support_imports(path, text), text)

    def test_first_party_support_is_rejected_only_when_it_carries_a_double(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "quwoquan_app/test/api_integration/x/y/z/case.dart"
            support = root / "quwoquan_app/test/support/x/y/z"
            api.parent.mkdir(parents=True)
            support.mkdir(parents=True)
            fake = support / "state.dart"
            fake.write_text(
                "class FakeStore implements Store {}\n", encoding="utf-8"
            )
            real = support / "remote_http_harness.dart"
            real.write_text("class RemoteHttpHarness {}\n", encoding="utf-8")
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                fake_text = "import '../../../../support/x/y/z/state.dart';\n"
                real_text = (
                    "import '../../../../support/x/y/z/remote_http_harness.dart';\n"
                )
                self.assertEqual(
                    gate.first_party_substitute_support_imports(api, fake_text),
                    ["../../../../support/x/y/z/state.dart"],
                )
                self.assertEqual(
                    gate.first_party_substitute_support_imports(api, real_text),
                    [],
                )
            finally:
                gate.ROOT = previous_root

    def test_relative_python_support_import_resolves_to_a_double(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "quwoquan_app/test/api_integration/x/y/case.py"
            support = root / "quwoquan_app/test/support/x/state.py"
            api.parent.mkdir(parents=True)
            support.parent.mkdir(parents=True)
            support.write_text("class FakeState:\n    pass\n", encoding="utf-8")
            text = "from ....support.x.state import FakeState\n"
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                self.assertEqual(
                    gate.first_party_substitute_support_imports(api, text),
                    ["....support.x.state"],
                )
            finally:
                gate.ROOT = previous_root

    def test_first_party_support_substitute_is_followed_transitively(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "quwoquan_app/test/api_integration/x/y/z/case.dart"
            support = root / "quwoquan_app/test/support/x/y/z"
            api.parent.mkdir(parents=True)
            support.mkdir(parents=True)
            (support / "remote_harness.dart").write_text(
                "import 'recording_sink.dart';\nclass RemoteHarness {}\n",
                encoding="utf-8",
            )
            (support / "recording_sink.dart").write_text(
                "class RecordingSink implements Sink {}\n", encoding="utf-8"
            )
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                text = "import '../../../../support/x/y/z/remote_harness.dart';\n"
                self.assertEqual(
                    gate.first_party_substitute_support_imports(api, text),
                    ["../../../../support/x/y/z/remote_harness.dart"],
                )
            finally:
                gate.ROOT = previous_root

    def test_dart_support_export_part_and_conditional_edges_are_followed(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "quwoquan_app/test/api_integration/x/y/z/case.dart"
            support = root / "quwoquan_app/test/support/x/y/z"
            api.parent.mkdir(parents=True)
            support.mkdir(parents=True)
            (support / "fake.dart").write_text(
                "class FakeStore implements Store {}\n", encoding="utf-8"
            )
            (support / "real.dart").write_text(
                "class RemoteStore {}\n", encoding="utf-8"
            )
            cases = {
                "export": "export 'fake.dart';\n",
                "part": "part 'fake.dart';\n",
                "conditional": (
                    "import 'real.dart' if (dart.library.io) 'fake.dart';\n"
                ),
            }
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                for name, entry_text in cases.items():
                    with self.subTest(name=name):
                        (support / "entry.dart").write_text(
                            entry_text, encoding="utf-8"
                        )
                        self.assertEqual(
                            gate.first_party_substitute_support_imports(
                                api,
                                "import '../../../../support/x/y/z/entry.dart';\n",
                            ),
                            ["../../../../support/x/y/z/entry.dart"],
                        )
            finally:
                gate.ROOT = previous_root

    def test_dart_part_of_uri_follows_owning_support_library(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "quwoquan_app/test/api_integration/x/y/z/case.dart"
            support = root / "quwoquan_app/test/support/x/y/z"
            api.parent.mkdir(parents=True)
            support.mkdir(parents=True)
            (support / "entry.dart").write_text(
                "part 'entry_part.dart';\nclass FakeStore implements Store {}\n",
                encoding="utf-8",
            )
            (support / "entry_part.dart").write_text(
                "part of 'entry.dart';\n", encoding="utf-8"
            )
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                self.assertEqual(
                    gate.first_party_substitute_support_imports(
                        api,
                        "import '../../../../support/x/y/z/entry_part.dart';\n",
                    ),
                    ["../../../../support/x/y/z/entry_part.dart"],
                )
            finally:
                gate.ROOT = previous_root

    def test_go_support_import_does_not_recurse_into_a_child_package(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / (
                "quwoquan_service/services/x/tests/api_integration/x/y/"
                "case__api_integration_test.go"
            )
            support = root / "quwoquan_service/services/x/tests/support"
            api.parent.mkdir(parents=True)
            (support / "child").mkdir(parents=True)
            (support / "remote.go").write_text(
                "package support\ntype RemoteHarness struct{}\n", encoding="utf-8"
            )
            (support / "child/fake.go").write_text(
                "package child\ntype FakeStore struct{}\n", encoding="utf-8"
            )
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                module = "quwoquan_service/services/x/tests/support"
                self.assertEqual(
                    gate.first_party_substitute_support_imports(
                        api, f'import "{module}"\n'
                    ),
                    [],
                )
            finally:
                gate.ROOT = previous_root

    def test_fake_build_constraint_is_rejected(self) -> None:
        gate = _load_gate()
        self.assertIsNotNone(
            gate.FAKE_BUILD_TAG_RE.search("//go:build mock\n\npackage x\n")
        )
        self.assertIsNone(
            gate.FAKE_BUILD_TAG_RE.search("//go:build integration\n\npackage x\n")
        )

    def test_skip_and_placeholder_patterns_ignore_comments_and_strings(self) -> None:
        gate = _load_gate()
        samples = (
            (
                Path("x_test.go"),
                '// t.Skip("decoy")\nconst note = "assert(true)"\n',
            ),
            (
                Path("test_x.py"),
                "# pytest.skip('decoy')\nnote = 'assert(true)'\n",
            ),
            (
                Path("x_test.dart"),
                "// expect(true, isTrue)\nconst note = 'skip: true';\n",
            ),
        )
        for path, text in samples:
            with self.subTest(path=path):
                code = gate._lexical_code_text(path, text)
                self.assertFalse(
                    any(pattern.search(code) for pattern in gate.SKIP_PATTERNS)
                )
                self.assertFalse(
                    any(pattern.search(code) for pattern in gate.PLACEHOLDER_PATTERNS)
                )
        real = gate._lexical_code_text(
            Path("x_test.dart"),
            "test('x', () { expect(true, isTrue); }, skip: true);\n",
        )
        self.assertTrue(any(pattern.search(real) for pattern in gate.SKIP_PATTERNS))
        self.assertTrue(
            any(pattern.search(real) for pattern in gate.PLACEHOLDER_PATTERNS)
        )

    def test_app_user_acceptance_local_injection_is_rejected(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/user_acceptance/journeys/example/"
            "example__user_acceptance_test.dart"
        )
        samples = (
            "ProviderScope(overrides: [])",
            "profileQueryProvider.overrideWithValue(query)",
            "await tester.pumpWidget(app)",
            "final query = FakeLocationQueryAdapter()",
            "import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';",
            "buildAlphaCloudOverrides()",
            "providerScopeOverrides: businessOverrides",
            "HttpOverrides.global = overrides;",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    gate.app_user_acceptance_local_injection_markers(path, sample),
                    sample,
                )

    def test_app_user_acceptance_comment_and_string_decoys_are_ignored(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/user_acceptance/journeys/example/"
            "example__user_acceptance_test.dart"
        )
        text = """
// ProviderScope(overrides: [fakeProvider.overrideWithValue(FakeStore())])
const decoy = 'FakeStore() HttpOverrides.global';
"""
        self.assertEqual(
            gate.app_user_acceptance_local_injection_markers(path, text),
            [],
        )

    def test_app_user_acceptance_scans_part_library_closure_from_snapshot(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / (
                "quwoquan_app/test/user_acceptance/journeys/example/"
                "example__user_acceptance_test.dart"
            )
            part = test.with_name("example_steps.dart")
            test.parent.mkdir(parents=True)
            root_text = "part 'example_steps.dart';\nvoid main() {}\n"
            part_text = (
                "part of 'example__user_acceptance_test.dart';\n"
                "void mount() { ProviderScope(overrides: const []); }\n"
            )
            test.write_text(root_text, encoding="utf-8")
            part.write_text(part_text, encoding="utf-8")
            snapshot_files = frozenset({test.resolve(), part.resolve()})
            source_texts = {
                test.resolve(): root_text,
                part.resolve(): part_text,
            }
            self.assertIn(
                "ProviderScope",
                gate.app_user_acceptance_local_injection_markers(
                    test,
                    root_text,
                    source_texts=source_texts,
                    snapshot_files=snapshot_files,
                ),
            )

    def test_app_user_acceptance_resolves_named_part_of_owner(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner = root / (
                "quwoquan_app/test/user_acceptance/journeys/example/owner.dart"
            )
            part = owner.with_name("example__user_acceptance_test.dart")
            owner.parent.mkdir(parents=True)
            owner_text = (
                "library example.journey;\n"
                "part 'example__user_acceptance_test.dart';\n"
                "void mount() { ProviderScope(overrides: const []); }\n"
            )
            part_text = "part of example.journey;\nvoid main() {}\n"
            owner.write_text(owner_text, encoding="utf-8")
            part.write_text(part_text, encoding="utf-8")
            snapshot_files = frozenset({owner.resolve(), part.resolve()})
            source_texts = {
                owner.resolve(): owner_text,
                part.resolve(): part_text,
            }
            self.assertIn(
                "ProviderScope",
                gate.app_user_acceptance_local_injection_markers(
                    part,
                    part_text,
                    source_texts=source_texts,
                    snapshot_files=snapshot_files,
                ),
            )

    def test_local_contract_object_typed_double_is_allowed_by_layer(self) -> None:
        gate = _load_gate()
        local_contract = Path(
            "quwoquan_app/test/local_contract/service/user_service/profile_projection/"
            "user_profile/profile_query__local_contract_test.dart"
        )
        user_acceptance = Path(
            "quwoquan_app/test/user_acceptance/service/user_service/profile_projection/"
            "user_profile/profile_query__user_acceptance_test.dart"
        )

        self.assertFalse(gate.is_app_user_acceptance_source(local_contract))
        self.assertTrue(gate.is_app_user_acceptance_source(user_acceptance))

    def test_alpha_named_typed_double_class_is_rejected(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/support/service/user_service/account/user_account/"
            "user_account_typed_double.dart"
        )
        class_names, data_names = gate.app_local_fixture_environment_names(
            path,
            "final class AlphaUserAccountFacet implements UserAccountReader {}\n",
        )
        self.assertEqual(class_names, ["AlphaUserAccountFacet"])
        self.assertEqual(data_names, [])

    def test_production_noun_class_is_not_a_prod_fixture_identity(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/local_contract/runtime/"
            "production_release_artifact__local_contract_test.py"
        )
        class_names, data_names = gate.app_local_fixture_environment_names(
            path,
            "class ProductionReleaseArtifactContractTest:\n    pass\n",
        )
        self.assertEqual(class_names, [])
        self.assertEqual(data_names, [])

    def test_private_alpha_fake_defined_inside_local_contract_is_rejected(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/local_contract/service/chat_service/chat/conversation/"
            "conversation_widget__local_contract_test.dart"
        )
        class_names, data_names = gate.app_local_fixture_environment_names(
            path,
            "final class _AlphaConversationQuery extends Fake "
            "implements ConversationQuery {}\n",
        )
        self.assertEqual(class_names, ["_AlphaConversationQuery"])
        self.assertEqual(data_names, [])

    def test_all_environment_class_prefixes_are_rejected_lexically(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/local_contract/service/chat_service/chat/conversation/"
            "conversation_widget__local_contract_test.dart"
        )
        class_names, _ = gate.app_local_fixture_environment_names(
            path,
            "class _AlphaQuery implements Query {}\n"
            "class BetaWriter implements Writer {}\n"
            "class GammaFixture {}\n"
            "class ProdGolden {}\n"
            "// class AlphaComment {}\n"
            "const decoy = 'class BetaString {}';\n",
        )
        self.assertEqual(
            class_names,
            ["BetaWriter", "GammaFixture", "ProdGolden", "_AlphaQuery"],
        )

    def test_alpha_prefixed_fixture_data_name_is_rejected(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/local_contract/service/content_service/content/post/"
            "post_projection__local_contract_test.dart"
        )
        class_names, data_names = gate.app_local_fixture_environment_names(
            path,
            "const postId = 'alpha_fixture_post';\n"
            "// const decoy = 'alpha_commented_fixture';\n",
        )
        self.assertEqual(class_names, [])
        self.assertEqual(data_names, ["alpha_fixture_post"])

    def test_alpha_fixture_data_embedded_in_generated_json_is_rejected(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/support/service/content_service/content/post/"
            "post_fixture.g.dart"
        )
        class_names, data_names = gate.app_local_fixture_environment_names(
            path,
            "const payload = r'''[{\"postId\":\"alpha_fixture_post\"}]''';\n",
        )
        self.assertEqual(class_names, [])
        self.assertEqual(data_names, ["alpha_fixture_post"])

    def test_local_environment_named_fixture_is_rejected_but_acceptance_is_outside_scope(
        self,
    ) -> None:
        gate = _load_gate()
        local_config = Path(
            "quwoquan_app/test/local_contract/runtime/config/"
            "runtime_environment__local_contract_test.dart"
        )
        class_names, data_names = gate.app_local_fixture_environment_names(
            local_config,
            "const environment = 'alpha';\n"
            "const endpointKey = 'alpha_provider_endpoint';\n"
            "final class GammaContentClientContext {}\n",
        )
        self.assertEqual(class_names, ["GammaContentClientContext"])
        self.assertEqual(data_names, ["alpha_provider_endpoint"])
        real_acceptance = Path(
            "quwoquan_app/test/user_acceptance/journeys/app_startup/"
            "alpha_startup__user_acceptance_test.dart"
        )
        self.assertFalse(gate.is_app_local_fixture_source(real_acceptance))
        self.assertEqual(
            gate.app_local_fixture_environment_names(
                real_acceptance,
                "final class AlphaReleaseCandidate {}\n"
                "const candidate = 'alpha_release_candidate';\n",
            ),
            ([], []),
        )

    def test_environment_fixture_file_names_and_structured_values_are_rejected(self) -> None:
        gate = _load_gate()
        json_path = Path(
            "quwoquan_app/test/support/service/content_service/content/post/alpha_post_fixture.json"
        )
        yaml_path = Path(
            "quwoquan_app/test/local_contract/service/content_service/content/post/fixture.yaml"
        )
        golden_path = Path(
            "quwoquan_app/test/local_contract/service/content_service/content/post/goldens/"
            "prod_post_golden.png"
        )
        self.assertEqual(
            gate.app_local_fixture_environment_path_names(json_path),
            ["alpha_post_fixture.json"],
        )
        self.assertEqual(
            gate._environment_data_names_for_file(
                json_path, json.dumps({"id": "beta_fixture_post"})
            ),
            ["beta_fixture_post"],
        )
        self.assertEqual(
            gate._environment_data_names_for_file(
                yaml_path, "id: gamma_fixture_post\n"
            ),
            ["gamma_fixture_post"],
        )
        self.assertEqual(
            gate.app_local_fixture_environment_path_names(golden_path),
            ["prod_post_golden.png"],
        )

    def test_repository_source_scan_is_stably_sorted(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            tests = root / "quwoquan_app/test/local_contract/runtime"
            tests.mkdir(parents=True)
            (tests / "z.dart").write_text("const z = 1;\n", encoding="utf-8")
            (tests / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                paths, source_texts = gate.scan_repository_snapshot()
            finally:
                gate.ROOT = previous_root
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(source_texts[tests / "a.py"], "VALUE = 1\n")
        self.assertEqual(source_texts[tests / "z.dart"], "const z = 1;\n")

    def test_main_reuses_one_repository_scan_for_source_checks(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        main_source = source[source.index("def main()") :]
        self.assertEqual(main_source.count("scan_repository_snapshot()"), 1)
        self.assertEqual(main_source.count("scan_repository_files()"), 0)
        self.assertIn("iter_canonical_files(all_files)", main_source)
        self.assertIn("verify_all_test_sources(\n", main_source)
        self.assertIn("verify_app_local_fixture_naming(failures, all_files", main_source)

    def test_support_recursion_reads_the_captured_snapshot_not_live_source(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "quwoquan_app/test/api_integration/x/y/z/case.dart"
            support = root / "quwoquan_app/test/support/x/y/z/state.dart"
            api.parent.mkdir(parents=True)
            support.parent.mkdir(parents=True)
            support.write_text(
                "class FakeStore implements Store {}\n", encoding="utf-8"
            )
            snapshot_files = frozenset({api.resolve(), support.resolve()})
            source_texts = {
                support.resolve(): support.read_text(encoding="utf-8")
            }
            support.write_text("class RemoteStore {}\n", encoding="utf-8")
            previous_root = gate.ROOT
            gate.ROOT = root
            try:
                self.assertEqual(
                    gate.first_party_substitute_support_imports(
                        api,
                        "import '../../../../support/x/y/z/state.dart';\n",
                        source_texts=source_texts,
                        snapshot_files=snapshot_files,
                    ),
                    ["../../../../support/x/y/z/state.dart"],
                )
            finally:
                gate.ROOT = previous_root

    def test_app_user_acceptance_evidence_checklist_is_rejected(self) -> None:
        gate = _load_gate()
        path = Path(
            "quwoquan_app/test/user_acceptance/journeys/example/"
            "example__user_acceptance_test.dart"
        )
        samples = (
            "test('page coverage evidence is declared', () {})",
            "const sourceEvidence = <String>[];",
            "const requiredCaseIds = <String>[];",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    gate.app_user_acceptance_local_injection_markers(path, sample),
                    sample,
                )


if __name__ == "__main__":
    unittest.main()
