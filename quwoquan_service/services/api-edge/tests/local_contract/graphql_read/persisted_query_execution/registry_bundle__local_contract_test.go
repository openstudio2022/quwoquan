// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package local_contract

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"

	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

func TestSignedRegistryStrictlyRejectsUnknownBundleFields(t *testing.T) {
	entry := validRegistryEntry()
	entry.AppClientBundle = &domain.AppClientBundle{
		BundleID: "content.post.ContentPostDetail", Role: "base",
		SupportedContentTypes: []string{"article"},
		SelectedFields:        []string{"contentType"}, AssemblyMappings: []domain.AssemblyMapping{},
	}
	entryJSON, err := json.Marshal(entry)
	if err != nil {
		t.Fatal(err)
	}
	var entryMap map[string]any
	if err := json.Unmarshal(entryJSON, &entryMap); err != nil {
		t.Fatal(err)
	}
	entryMap["appClientBundle"].(map[string]any)["unexpected"] = true
	candidateDigest := "sha256:" + strings.Repeat("1", 64)
	schemaDigest := "sha256:" + strings.Repeat("2", 64)
	payload, err := json.Marshal(map[string]any{
		"candidateDigest": candidateDigest, "schemaDigest": schemaDigest,
		"entries": []any{entryMap},
	})
	if err != nil {
		t.Fatal(err)
	}
	secret := []byte("bundle-contract-signature-key")
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write(payload)
	payloadSum := sha256.Sum256(payload)
	envelope, err := json.Marshal(map[string]any{
		"keyId":         "bundle-contract-key",
		"payloadSha256": "sha256:" + hex.EncodeToString(payloadSum[:]),
		"payload":       base64.StdEncoding.EncodeToString(payload),
		"signature":     base64.StdEncoding.EncodeToString(mac.Sum(nil)),
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = domain.LoadSignedRegistry(
		context.Background(), strings.NewReader(string(envelope)),
		candidateDigest, schemaDigest, hmacContractVerifier{secret: secret},
	)
	if err == nil || !strings.Contains(err.Error(), `unknown field "unexpected"`) {
		t.Fatalf("unknown bundle field error=%v", err)
	}
}

func TestRegistryValidatesAndDefensivelyClonesSignedBundleMetadata(t *testing.T) {
	base := validRegistryEntry()
	base.OperationName = "ContentPostDetailBase"
	base.SHA256Hash = strings.Repeat("1", 64)
	base.AppClientBundle = &domain.AppClientBundle{
		BundleID: "content.post.ContentPostDetail", Role: "base",
		SupportedContentTypes: []string{"article", "image", "micro", "video"},
		SelectedFields:        []string{"contentType", "postId"},
		AssemblyMappings:      []domain.AssemblyMapping{},
	}
	extension := validRegistryEntry()
	extension.OperationName = "ContentPostDetailArticle"
	extension.CanonicalOperationID = "content.post.GetPostArticle"
	extension.SHA256Hash = strings.Repeat("2", 64)
	extension.AppClientBundle = &domain.AppClientBundle{
		BundleID: "content.post.ContentPostDetail", Role: "extension",
		RequiredForContentTypes: []string{"article"},
		SelectedFields:          []string{"articleAssetManifestSummary", "articleAssets"},
		AssemblyMappings: []domain.AssemblyMapping{{
			TargetField:         "articleAssetManifest",
			PresenceSourceField: "articleAssetManifestSummary",
			Sources: []domain.AssemblySource{
				{SourceField: "articleAssetManifestSummary", Strategy: "merge_object"},
				{SourceField: "articleAssets", Strategy: "assign_key", TargetKey: "assets"},
			},
		}},
	}

	registry, err := domain.NewRegistry([]domain.Entry{base, extension})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	base.AppClientBundle.SupportedContentTypes[0] = "tampered"
	lookedUp, ok := registry.Lookup(strings.Repeat("1", 64))
	if !ok || lookedUp.AppClientBundle.SupportedContentTypes[0] != "article" {
		t.Fatalf("defensive bundle clone=%+v", lookedUp.AppClientBundle)
	}
	lookedUp.AppClientBundle.SelectedFields[0] = "tampered"
	again, _ := registry.Lookup(strings.Repeat("1", 64))
	if again.AppClientBundle.SelectedFields[0] != "contentType" {
		t.Fatalf("lookup clone=%+v", again.AppClientBundle)
	}

	duplicateCanonical := extension
	duplicateCanonical.CanonicalOperationID = again.CanonicalOperationID
	if _, err := domain.NewRegistry([]domain.Entry{again, duplicateCanonical}); err == nil ||
		!strings.Contains(err.Error(), "duplicate persisted query canonicalOperationId") {
		t.Fatalf("duplicate canonical operation error=%v", err)
	}
}

func TestRegistryRejectsInvalidBundleMetadataBeforeServing(t *testing.T) {
	base := validRegistryEntry()
	base.AppClientBundle = &domain.AppClientBundle{
		BundleID: "content.post.ContentPostDetail", Role: "base",
		SupportedContentTypes: []string{"image", "article"},
		SelectedFields:        []string{"contentType"}, AssemblyMappings: []domain.AssemblyMapping{},
	}
	if _, err := domain.NewRegistry([]domain.Entry{base}); err == nil || !strings.Contains(err.Error(), "sorted") {
		t.Fatalf("unsorted content types error=%v", err)
	}

	base.AppClientBundle.SupportedContentTypes = []string{"article"}
	base.AppClientBundle.SelectedFields = []string{"postId"}
	if _, err := domain.NewRegistry([]domain.Entry{base}); err == nil || !strings.Contains(err.Error(), "contentType") {
		t.Fatalf("missing discriminator error=%v", err)
	}
}
