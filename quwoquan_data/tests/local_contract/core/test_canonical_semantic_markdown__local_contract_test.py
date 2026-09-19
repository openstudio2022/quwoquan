# spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
import unittest
from copy import deepcopy

from core import canonical_semantic_markdown as codec
from core.canonical_semantic_markdown import CanonicalMarkdownError, parse_canonical_markdown, serialize_envelope
from generated.semantic_document import CAPABILITY_IDS


def canonical_fixture():
    caps = sorted(CAPABILITY_IDS)
    anchor = {"origin": "fixture", "start": 0, "end": 4, "selector": "p:1"}
    node = {
        "nodeId": "n1", "kind": "paragraph", "disposition": "preserved",
        "policyVersion": "1.0.0", "requiredCapabilities": caps, "losses": [],
        "semanticFingerprint": "node-fingerprint", "sourceAnchor": anchor,
        "diagnostics": [], "rawSlice": None, "rawSliceFingerprint": None,
        "attributes": {"plainText": "历代帝王庙位于北京。"}, "children": [], "inlines": [],
    }
    envelope = {
        "schemaVersion": "1.0.0", "dialectVersion": "1.0.0",
        "canonicalizationVersion": "1.0.0", "offsetEncoding": "unicode_scalar_value",
        "nodes": [node], "requiredCapabilities": caps, "assets": {},
        "sourceMap": {"n1": anchor}, "policyVersion": "1.0.0", "losses": [],
        "semanticFingerprint": "", "canonicalDigest": "",
    }
    semantic = codec._digest(envelope, frozenset({"semanticFingerprint", "canonicalDigest"}))
    envelope["semanticFingerprint"] = "sha256:" + semantic
    canonical = codec._digest(envelope, frozenset({"canonicalDigest"}))
    envelope["canonicalDigest"] = "sha256:" + canonical
    return envelope


class CanonicalSemanticMarkdownTest(unittest.TestCase):
    def test_real_candidate_round_trip(self):
        envelope = canonical_fixture(); markdown = serialize_envelope(envelope)
        self.assertEqual(parse_canonical_markdown(markdown), envelope)
        self.assertEqual(serialize_envelope(parse_canonical_markdown(markdown)), markdown)

    def test_invalid_fails_closed(self):
        envelope = canonical_fixture()
        for mutate in [
            lambda x: x.__setitem__("schemaVersion", "2.0.0"),
            lambda x: x.__setitem__("canonicalizationVersion", "2.0.0"),
            lambda x: x.__setitem__("requiredCapabilities", ["missing"]),
            lambda x: x["nodes"][0].__setitem__("kind", "unknown"),
        ]:
            bad = deepcopy(envelope); mutate(bad)
            with self.assertRaises(CanonicalMarkdownError): serialize_envelope(bad)
        markdown = serialize_envelope(envelope)
        for bad in [
            markdown.replace("\n", "\r\n"),
            markdown.replace(":::qwq-meta ", ":::qwq-meta unknown ", 1),
            markdown.replace('"attributes":', '"unknown":', 1),
            markdown.replace("历代帝王庙位于", "<script>x</script>历代帝王庙位于", 1),
        ]:
            with self.assertRaises(CanonicalMarkdownError): parse_canonical_markdown(bad)
