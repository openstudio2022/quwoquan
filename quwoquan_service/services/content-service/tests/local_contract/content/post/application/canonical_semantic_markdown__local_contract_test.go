// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
package post_test

import (
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/services/content-service/tests/support/semanticfixture"
	"testing"
)

func TestCanonicalSemanticMarkdownRoundTrip(t *testing.T) {
	envelope := semanticfixture.Envelope(t)
	markdown, err := SerializeEnvelope(envelope)
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := ParseCanonicalMarkdown(markdown)
	if err != nil {
		t.Fatal(err)
	}
	again, err := SerializeEnvelope(parsed)
	if err != nil || again != markdown {
		t.Fatalf("bytes differ: %v", err)
	}
	a, _ := json.Marshal(envelope)
	b, _ := json.Marshal(parsed)
	if string(a) != string(b) {
		t.Fatal("normalized payload differs")
	}
}
func TestCanonicalSemanticMarkdownFailsClosed(t *testing.T) {
	if _, e := ParseCanonicalMarkdown("# legacy\n"); e == nil {
		t.Fatal("legacy markdown upgraded")
	}
	if _, e := ParseCanonicalMarkdown("---\n{}\n---\n"); e == nil {
		t.Fatal("missing identity accepted")
	}
}
