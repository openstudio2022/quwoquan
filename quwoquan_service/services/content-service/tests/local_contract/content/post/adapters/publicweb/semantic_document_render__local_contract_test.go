// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-004
package publicweb_test

import (
	"strings"
	"testing"

	semantic "quwoquan_service/services/content-service/generated/content/post/semantic_document"
	publicweb "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/publicweb"
)

func TestLegacyReadOnlyMarkdownProjectionPreservesSupportedSequenceAndSafeHTML(t *testing.T) {
	markdown := "# 标题\n\n正文[^route]。\n\n术语\n: 定义\n\n| 地点 | 天数 |\n| :--- | ---: |\n| 西湖 | 2 |\n\n:::directory\ngroup:journey label=\"行程\"\n- [第一章](#chapter-1)\n:::\n\n[^route]: 路线说明。"
	html, err := publicweb.RenderLegacyReadOnlyMarkdownBodyHTML(markdown, "qwq-rich-md", nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		`<p>正文<a class="qwq-footnote-ref" href="#fn-route">[route]</a>。</p>`,
		`<dl><dt>术语</dt><dd>定义</dd></dl>`,
		`<table><tr><th>地点</th><th class="align-end">天数</th></tr><tr><td>西湖</td><td class="align-end">2</td></tr></table>`,
		`<nav class="qwq-directory"><section><h2>行程</h2><ul><li><a href="#chapter-1">第一章</a></li></ul></section></nav>`,
		`<aside class="qwq-footnote" id="fn-route"><p>路线说明。</p></aside>`,
	} {
		if !strings.Contains(html, expected) {
			t.Fatalf("missing %q in %s", expected, html)
		}
	}
	if strings.Index(html, "<table>") > strings.Index(html, "qwq-directory") {
		t.Fatalf("node order changed: %s", html)
	}
}

func TestCanonicalSemanticConsumerRejectsMissingOrAdapterDigests(t *testing.T) {
	cases := []struct{ name, fingerprint, digest, code string }{
		{"empty_fingerprint", "", "sha256:" + strings.Repeat("b", 64), "INVALID.SEMANTIC_FINGERPRINT"},
		{"adapter_fingerprint", "adapter:semantic", "sha256:" + strings.Repeat("b", 64), "INVALID.SEMANTIC_FINGERPRINT"},
		{"empty_digest", "sha256:" + strings.Repeat("a", 64), "", "INVALID.CANONICAL_DIGEST"},
		{"adapter_digest", "sha256:" + strings.Repeat("a", 64), "adapter:canonical", "INVALID.CANONICAL_DIGEST"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			doc := validSemanticEnvelope(semantic.NodeKindParagraph)
			doc.SemanticFingerprint, doc.CanonicalDigest = tc.fingerprint, tc.digest
			html, err := publicweb.RenderSemanticDocumentBodyHTML(doc, allSemanticCapabilities(), nil)
			if err == nil || html != "" || !strings.Contains(err.Error(), tc.code) {
				t.Fatalf("html=%q err=%v", html, err)
			}
		})
	}
}

func TestSemanticConsumerFailsClosedOnVersionOffsetCapabilityAndExperimentalNode(t *testing.T) {
	base := validSemanticEnvelope(semantic.NodeKindParagraph)
	cases := []struct {
		name   string
		mutate func(*semantic.DocumentEnvelope, map[semantic.CapabilityID]bool)
		code   string
	}{
		{"unknown_major", func(d *semantic.DocumentEnvelope, _ map[semantic.CapabilityID]bool) { d.SchemaVersion = "2.0.0" }, string(semantic.ValidationSchemaMajorMismatch)},
		{"canonicalization", func(d *semantic.DocumentEnvelope, _ map[semantic.CapabilityID]bool) {
			d.CanonicalizationVersion = "1.1.0"
		}, string(semantic.ValidationCanonicalizationMismatch)},
		{"offset", func(d *semantic.DocumentEnvelope, _ map[semantic.CapabilityID]bool) {
			d.OffsetEncoding = "utf16_code_unit"
		}, string(semantic.ValidationOffsetEncodingMismatch)},
		{"capability", func(_ *semantic.DocumentEnvelope, a map[semantic.CapabilityID]bool) {
			delete(a, semantic.CapabilityIDRenderWeb)
		}, string(semantic.ValidationCapabilityMissing)},
		{"experimental", func(d *semantic.DocumentEnvelope, _ map[semantic.CapabilityID]bool) {
			d.Nodes[0] = semanticNode(semantic.NodeKindTimeline, "timeline")
		}, string(semantic.ValidationExperimentalNode)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			doc := base
			doc.Nodes = append([]semantic.SemanticNode(nil), base.Nodes...)
			available := allSemanticCapabilities()
			tc.mutate(&doc, available)
			html, err := publicweb.RenderSemanticDocumentBodyHTML(doc, available, nil)
			if err == nil || html != "" || !strings.Contains(err.Error(), tc.code) {
				t.Fatalf("html=%q err=%v want %s", html, err, tc.code)
			}
		})
	}
}

func TestLegacyReadOnlyMarkdownProjectionRejectsUnsafeOrUnknownInput(t *testing.T) {
	cases := []struct{ name, markdown, dialect, code string }{
		{"missing_dialect", "正文", "", "DIALECT_MISSING"},
		{"unknown_directive", ":::timeline\n- 08:00\n:::", "qwq-rich-md", "UNSUPPORTED.NODE"},
		{"raw_html", "<script>alert(1)</script>", "qwq-rich-md", "UNSAFE.RAW_HTML"},
		{"broken_grid", "| A | B |\n| --- | --- |\n| only |", "qwq-rich-md", "INVALID.TABLE_GRID"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			html, err := publicweb.RenderLegacyReadOnlyMarkdownBodyHTML(tc.markdown, tc.dialect, nil)
			if err == nil || html != "" || !strings.Contains(err.Error(), tc.code) {
				t.Fatalf("html=%q err=%v", html, err)
			}
		})
	}
}

func validSemanticEnvelope(kind semantic.NodeKind) semantic.DocumentEnvelope {
	node := semanticNode(kind, "正文")
	return semantic.DocumentEnvelope{SchemaVersion: semantic.SchemaVersion, DialectVersion: semantic.DialectVersion, CanonicalizationVersion: semantic.CanonicalizationVersion, OffsetEncoding: semantic.OffsetEncoding, Nodes: []semantic.SemanticNode{node}, RequiredCapabilities: append([]semantic.CapabilityID(nil), node.RequiredCapabilities...), Assets: map[string]semantic.SemanticAsset{}, SourceMap: map[string]semantic.SourceAnchor{}, PolicyVersion: "test", Losses: []semantic.SemanticLoss{}, SemanticFingerprint: "sha256:" + strings.Repeat("a", 64), CanonicalDigest: "sha256:" + strings.Repeat("b", 64)}
}
func semanticNode(kind semantic.NodeKind, text string) semantic.SemanticNode {
	descriptor := semantic.NodeRegistry[kind]
	return semantic.SemanticNode{NodeID: "n1", Kind: kind, Disposition: semantic.ProcessingDispositionPreserved, PolicyVersion: "test", RequiredCapabilities: append([]semantic.CapabilityID(nil), descriptor.RequiredCapabilities...), Losses: []semantic.SemanticLoss{}, SemanticFingerprint: "sha256:" + strings.Repeat("c", 64), SourceAnchor: semantic.SourceAnchor{Origin: "fixture", Start: 0, End: 1}, Attributes: map[string]any{"text": text}}
}
func allSemanticCapabilities() map[semantic.CapabilityID]bool {
	result := map[semantic.CapabilityID]bool{}
	for id, available := range semantic.CapabilityRegistry {
		result[id] = available
	}
	return result
}
