# spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
import json
import unittest
from copy import deepcopy
from pathlib import Path
from core.canonical_semantic_markdown import CanonicalMarkdownError, parse_canonical_markdown, serialize_envelope

ROOT=Path(__file__).resolve().parents[4]
CANDIDATE=ROOT/'.qwq_output/data/content-remediation/executions/temple-of-emperors-v2-rerun-a2b10ce21722/source.semantic.json'
class CanonicalSemanticMarkdownTest(unittest.TestCase):
 def test_real_candidate_round_trip(self):
  envelope=json.loads(CANDIDATE.read_text()); markdown=serialize_envelope(envelope)
  self.assertEqual(parse_canonical_markdown(markdown),envelope); self.assertEqual(serialize_envelope(parse_canonical_markdown(markdown)),markdown)
 def test_invalid_fails_closed(self):
  envelope=json.loads(CANDIDATE.read_text())
  for mutate in [lambda x:x.__setitem__('schemaVersion','2.0.0'),lambda x:x.__setitem__('canonicalizationVersion','2.0.0'),lambda x:x.__setitem__('requiredCapabilities',['missing']),lambda x:x['nodes'][0].__setitem__('kind','unknown')]:
   bad=deepcopy(envelope);mutate(bad)
   with self.assertRaises(CanonicalMarkdownError):serialize_envelope(bad)
  markdown=serialize_envelope(envelope)
  for bad in [markdown.replace('\n','\r\n'),markdown.replace(':::qwq-meta ',':::qwq-meta unknown ',1),markdown.replace('"attributes":','"unknown":',1),markdown.replace('历代帝王庙位于','<script>x</script>历代帝王庙位于',1)]:
   with self.assertRaises(CanonicalMarkdownError):parse_canonical_markdown(bad)
