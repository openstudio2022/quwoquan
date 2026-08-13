"""verify_object_assistant_access_closure 的 fail-closed 合约。

覆盖：未声明 assistant_access 必须阻断、scope 语法不得借用兄弟对象、
cite 不得越过 read、DomainReaderDescriptor 不得暴露契约关闭的对象、
空扫描必须 ScanError、门禁与本测试必须留在 gate 链上。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_object_assistant_access_closure.py"
GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE = ROOT / "Makefile"

SPEC = importlib.util.spec_from_file_location(
    "verify_object_assistant_access_closure", SCRIPT
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def declaration(read: str = "public", cite: str = "none", write: str = "none") -> dict:
    def block(capability: str, mode: str) -> dict:
        scopes = [] if mode == "none" else [f"assistant.circle.circle.{capability}"]
        payload: dict = {"mode": mode, "scopes": scopes}
        if capability == "write" and mode != "none":
            payload["requires_user_consent"] = True
            payload["consent_scope_ref"] = scopes[0]
        return payload

    access = {
        "read": block("read", read),
        "cite": block("cite", cite),
        "write": block("write", write),
    }
    if read == cite == write == "none":
        access["denied_reason"] = "deliberately closed for this contract test"
    return access


def objects_with(access: dict) -> dict:
    path = ROOT / "quwoquan_service/services/x/contracts/circle_management/circle/object.yaml"
    return {"circle.circle": (path, {"assistant_access": access})}


class DeclarationContract(unittest.TestCase):
    def test_undeclared_object_blocks(self) -> None:
        path = ROOT / "quwoquan_service/services/x/contracts/circle_management/circle/object.yaml"
        failures = gate.validate_declarations(ROOT, {"circle.circle": (path, {})})
        self.assertTrue(any("fail-closed" in item for item in failures))

    def test_sibling_scope_is_rejected(self) -> None:
        access = declaration()
        access["read"]["scopes"] = ["assistant.content.post.read"]
        failures = gate.validate_declarations(ROOT, objects_with(access))
        self.assertTrue(any("another" in item for item in failures))

    def test_cite_without_read_is_unreachable(self) -> None:
        failures = gate.validate_declarations(
            ROOT, objects_with(declaration(read="none", cite="public_citation"))
        )
        self.assertTrue(any("cannot quote" in item for item in failures))

    def test_fully_closed_requires_denied_reason(self) -> None:
        access = declaration(read="none", cite="none", write="none")
        del access["denied_reason"]
        failures = gate.validate_declarations(ROOT, objects_with(access))
        self.assertTrue(any("denied_reason" in item for item in failures))

    def test_well_formed_declaration_passes(self) -> None:
        failures = gate.validate_declarations(ROOT, objects_with(declaration()))
        self.assertEqual(failures, [])


class DescriptorDerivationContract(unittest.TestCase):
    def _repo_with_descriptor(self, object_type: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo_root = Path(tmp.name)
        catalogue = repo_root / gate.READER_CODEGEN_RELATIVE
        catalogue.parent.mkdir(parents=True)
        catalogue.write_text("package generated\n", encoding="utf-8")
        target = repo_root / gate.DESCRIPTORS_RELATIVE
        target.parent.mkdir(parents=True)
        target.write_text(
            "package skillcontext\n\n"
            "func catalogue() {\n"
            "\t_ = publicObjectDescriptor(\n"
            '\t\t"demo.context",\n'
            '\t\t"demo.resolver",\n'
            '\t\t"demo-service",\n'
            '\t\t"demo.op",\n'
            '\t\t"demo.Query",\n'
            f'\t\t"{object_type}",\n'
            "\t\t60,\n"
            "\t\t30,\n"
            "\t)\n"
            "}\n",
            encoding="utf-8",
        )
        return repo_root

    def test_descriptor_exposing_closed_object_blocks(self) -> None:
        repo_root = self._repo_with_descriptor("circle.Circle")
        objects = objects_with(declaration(read="none"))
        failures = gate.validate_descriptor_derivation(repo_root, objects)
        self.assertTrue(any("contract closes" in item for item in failures))

    def test_descriptor_of_unknown_object_blocks(self) -> None:
        repo_root = self._repo_with_descriptor("ghost.Object")
        failures = gate.validate_descriptor_derivation(repo_root, objects_with(declaration()))
        self.assertTrue(any("not an object on disk" in item for item in failures))

    def test_descriptor_of_open_object_passes(self) -> None:
        repo_root = self._repo_with_descriptor("circle.Circle")
        failures = gate.validate_descriptor_derivation(repo_root, objects_with(declaration()))
        self.assertEqual(failures, [])

    def test_missing_catalogue_raises(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.descriptor_object_type_refs(Path(empty))


class ReaderCodegenAlignmentContract(unittest.TestCase):
    def _repo_with_catalogue(self, ttl: int) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo_root = Path(tmp.name)
        target = repo_root / gate.READER_CODEGEN_RELATIVE
        target.parent.mkdir(parents=True)
        target.write_text(
            "package generated\n\n"
            "func ContractReaderDescriptors() []ContractReaderDescriptor {\n"
            "\treturn []ContractReaderDescriptor{\n"
            "\t\t{\n"
            '\t\t\tDescriptorID:        "circle.circle_context",\n'
            '\t\t\tResolverRef:         "circle.current_context",\n'
            '\t\t\tOwnerService:        "circle-service",\n'
            '\t\t\tOwnerOperationRef:   "circle.circle.GetCircle",\n'
            '\t\t\tInputSchemaRef:      "circle.CircleDetailQuery",\n'
            '\t\t\tOutputSchemaRef:     "assistant.ContextSegment",\n'
            '\t\t\tObjectTypeRef:       "circle.Circle",\n'
            '\t\t\tAuthority:           "domain_canonical",\n'
            '\t\t\tSensitivity:         "public",\n'
            '\t\t\tAcceptedSourceKinds: []string{"domain"},\n'
            '\t\t\tSurfaceKinds:        []string{"personal"},\n'
            "\t\t\tMaxFreshnessSeconds: 900,\n"
            f"\t\t\tCacheTTLSeconds:     {ttl},\n"
            '\t\t\tArtifactPolicy:      "inline_bounded",\n'
            '\t\t\tCitationPolicy:      "entity_reference",\n'
            "\t\t},\n"
            "\t}\n}\n",
            encoding="utf-8",
        )
        return repo_root

    def _objects(self) -> dict:
        access = declaration()
        access["read"]["reader"] = {
            "descriptor_id": "circle.circle_context",
            "resolver_ref": "circle.current_context",
            "owner_service": "circle-service",
            "owner_operation_ref": "circle.circle.GetCircle",
            "input_schema_ref": "circle.CircleDetailQuery",
            "output_schema_ref": "assistant.ContextSegment",
            "object_type_ref": "circle.Circle",
            "authority": "domain_canonical",
            "sensitivity": "public",
            "accepted_source_kinds": ["domain"],
            "surface_kinds": ["personal"],
            "max_freshness_seconds": 900,
            "cache_ttl_seconds": 60,
            "artifact_policy": "inline_bounded",
            "citation_policy": "entity_reference",
        }
        return objects_with(access)

    def test_matching_catalogue_passes(self) -> None:
        repo_root = self._repo_with_catalogue(ttl=60)
        failures = gate.validate_reader_codegen_alignment(repo_root, self._objects())
        self.assertEqual(failures, [])

    def test_field_drift_blocks(self) -> None:
        repo_root = self._repo_with_catalogue(ttl=61)
        failures = gate.validate_reader_codegen_alignment(repo_root, self._objects())
        self.assertTrue(any("cache_ttl_seconds=60" in item for item in failures))

    def test_undeclared_catalogue_entry_blocks(self) -> None:
        repo_root = self._repo_with_catalogue(ttl=60)
        failures = gate.validate_reader_codegen_alignment(
            repo_root, objects_with(declaration())
        )
        self.assertTrue(any("no object contract declares" in item for item in failures))

    def test_missing_catalogue_raises(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.generated_reader_entries(Path(empty))


class FailClosedContract(unittest.TestCase):
    def test_empty_scan_raises_instead_of_pass(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.load_objects(Path(empty))


class WiringContract(unittest.TestCase):
    def test_gate_is_on_gate_repo_chain(self) -> None:
        self.assertIn(
            "quwoquan_ops/gate/verify_object_assistant_access_closure.py",
            GATE_REPO.read_text(encoding="utf-8"),
        )

    def test_companion_test_is_executed(self) -> None:
        self.assertIn(Path(__file__).name, MAKEFILE.read_text(encoding="utf-8"))


class LiveRepositoryContract(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        scanned, failures = gate.run(ROOT)
        self.assertGreater(scanned, 0)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
