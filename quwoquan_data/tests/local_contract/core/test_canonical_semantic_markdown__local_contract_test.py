# spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
import sys
import unittest
from copy import deepcopy
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.canonical_semantic_markdown import (  # noqa: E402
    CanonicalMarkdownError,
    _digest,
    parse_canonical_markdown,
    serialize_envelope,
)
from generated.semantic_document import (  # noqa: E402
    CANONICALIZATION_VERSION,
    DIALECT_VERSION,
    OFFSET_ENCODING,
    SCHEMA_VERSION,
)


BODY = "历代帝王庙位于北京。"


def _canonical_envelope() -> dict:
    """仓内自包含 envelope，不依赖 host `.qwq_output` 执行产物。"""

    capabilities = [
        "parse.markdown",
        "parse.html",
        "serialize.markdown",
        "render.app",
        "render.web",
        "render.workbench",
        "author.editContent",
    ]
    anchor = {"origin": "source-gfm", "start": 0, "end": len(BODY), "selector": "p:1"}
    node = {
        "nodeId": "n1",
        "kind": "paragraph",
        "disposition": "normalized",
        "policyVersion": "1.0.0",
        "requiredCapabilities": capabilities,
        "losses": [],
        "semanticFingerprint": "node-fp",
        "sourceAnchor": anchor,
        "diagnostics": [],
        "rawSlice": None,
        "rawSliceFingerprint": None,
        "attributes": {"plainText": BODY},
        "children": [],
        "inlines": [],
    }
    envelope = {
        "schemaVersion": SCHEMA_VERSION,
        "dialectVersion": DIALECT_VERSION,
        "canonicalizationVersion": CANONICALIZATION_VERSION,
        "offsetEncoding": OFFSET_ENCODING,
        "nodes": [node],
        "requiredCapabilities": capabilities,
        "assets": {},
        "sourceMap": {"n1": anchor},
        "policyVersion": "1.0.0",
        "losses": [],
    }
    envelope["semanticFingerprint"] = _digest(envelope, frozenset({"semanticFingerprint", "canonicalDigest"}))
    envelope["canonicalDigest"] = _digest(envelope, frozenset({"canonicalDigest"}))
    return envelope


class CanonicalSemanticMarkdownTest(unittest.TestCase):
    def test_real_candidate_round_trip(self) -> None:
        envelope = _canonical_envelope()
        markdown = serialize_envelope(envelope)
        self.assertEqual(parse_canonical_markdown(markdown), envelope)
        self.assertEqual(serialize_envelope(parse_canonical_markdown(markdown)), markdown)

    def test_invalid_fails_closed(self) -> None:
        envelope = _canonical_envelope()
        for mutate in [
            lambda x: x.__setitem__("schemaVersion", "2.0.0"),
            lambda x: x.__setitem__("canonicalizationVersion", "2.0.0"),
            lambda x: x.__setitem__("requiredCapabilities", ["missing"]),
            lambda x: x["nodes"][0].__setitem__("kind", "unknown"),
        ]:
            bad = deepcopy(envelope)
            mutate(bad)
            with self.assertRaises(CanonicalMarkdownError):
                serialize_envelope(bad)
        markdown = serialize_envelope(envelope)
        for bad in [
            markdown.replace("\n", "\r\n"),
            markdown.replace(":::qwq-meta ", ":::qwq-meta unknown ", 1),
            markdown.replace('"attributes":', '"unknown":', 1),
            markdown.replace(BODY, f"<script>x</script>{BODY}", 1),
        ]:
            with self.assertRaises(CanonicalMarkdownError):
                parse_canonical_markdown(bad)


if __name__ == "__main__":
    unittest.main()
