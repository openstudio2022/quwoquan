package semanticfixture

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"

	semantic "quwoquan_service/services/content-service/generated/content/post/semantic_document"
)

// Envelope 返回合法、最小且 canonicalDigest 可重算的 semantic document 测试值。
func Envelope(t testing.TB) semantic.DocumentEnvelope {
	t.Helper()
	doc := semantic.DocumentEnvelope{
		SchemaVersion: semantic.SchemaVersion, DialectVersion: semantic.DialectVersion,
		CanonicalizationVersion: semantic.CanonicalizationVersion, OffsetEncoding: semantic.OffsetEncoding,
		Nodes: []semantic.SemanticNode{}, RequiredCapabilities: []semantic.CapabilityID{},
		Assets: map[string]semantic.SemanticAsset{}, SourceMap: map[string]semantic.SourceAnchor{},
		PolicyVersion: "test-v1", Losses: []semantic.SemanticLoss{},
		SemanticFingerprint: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
	raw, err := json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatal(err)
	}
	delete(fields, "semanticFingerprint")
	delete(fields, "canonicalDigest")
	semanticBytes, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	semanticSum := sha256.Sum256(semanticBytes)
	doc.SemanticFingerprint = "sha256:" + hex.EncodeToString(semanticSum[:])
	raw, err = json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatal(err)
	}
	delete(fields, "canonicalDigest")
	canonical, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(canonical)
	doc.CanonicalDigest = "sha256:" + hex.EncodeToString(sum[:])
	return doc
}

func Map(t testing.TB) map[string]any {
	t.Helper()
	raw, err := json.Marshal(Envelope(t))
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func AddToManifestJSON(t testing.TB, content string) string {
	t.Helper()
	var manifest map[string]any
	if err := json.Unmarshal([]byte(content), &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest["contentType"] == "article" {
		if _, explicit := manifest["semanticDocument"]; !explicit {
			manifest["semanticDocument"] = Map(t)
		}
	}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}
