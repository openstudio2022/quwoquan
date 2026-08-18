// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-002

package runtimemedia

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// publicSliceDerivationCases mirrors the shared contract consumed by the Data
// packager test of the same cases. Both sides assert the recorded
// publicSliceKey, so a one-sided derivation change fails here.
type publicSliceDerivationCases struct {
	Schema string `json:"schema"`
	Domain struct {
		Kinds        []string `json:"kinds"`
		ContentTypes []string `json:"contentTypes"`
	} `json:"domain"`
	Cases []struct {
		Name           string `json:"name"`
		MediaType      string `json:"mediaType"`
		AssetID        string `json:"assetId"`
		Version        int64  `json:"version"`
		ContentType    string `json:"contentType"`
		PublicSliceKey string `json:"publicSliceKey"`
	} `json:"cases"`
}

func loadPublicSliceDerivationCases(t *testing.T) publicSliceDerivationCases {
	t.Helper()
	path := filepath.Join(
		"..", "..", "..",
		"quwoquan_service", "services", "content-service",
		"contracts", "media", "media_asset",
		"public_slice_derivation_cases.json",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("shared public slice cases are unreadable: %v", err)
	}
	var document publicSliceDerivationCases
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatalf("shared public slice cases are invalid JSON: %v", err)
	}
	if document.Schema != "content_media_public_slice_derivation_cases" {
		t.Fatalf("unexpected shared case schema: %q", document.Schema)
	}
	if len(document.Cases) == 0 {
		t.Fatal("shared public slice cases must not be empty")
	}
	return document
}

func TestContentMediaPublicSliceDerivationMatchesSharedCases(t *testing.T) {
	document := loadPublicSliceDerivationCases(t)
	for _, testCase := range document.Cases {
		t.Run(testCase.Name, func(t *testing.T) {
			got := BuildContentMediaPublicSliceKey(
				testCase.MediaType,
				testCase.AssetID,
				testCase.Version,
				testCase.ContentType,
			)
			if got != testCase.PublicSliceKey {
				t.Fatalf(
					"public slice derivation drift: got %q want %q",
					got,
					testCase.PublicSliceKey,
				)
			}
			if got == "" {
				return
			}
			if _, ok := PublicSliceVersion(got); !ok {
				t.Fatalf("derived public slice has no version: %q", got)
			}
		})
	}
}

func TestSharedPublicSliceCasesCoverTheReleaseMediaDomainOnly(t *testing.T) {
	document := loadPublicSliceDerivationCases(t)
	wantKinds := []string{"avatar", "image", "video"}
	if len(document.Domain.Kinds) != len(wantKinds) {
		t.Fatalf("unexpected shared case kinds: %v", document.Domain.Kinds)
	}
	for index, kind := range wantKinds {
		if document.Domain.Kinds[index] != kind {
			t.Fatalf("unexpected shared case kinds: %v", document.Domain.Kinds)
		}
	}
	for _, contentType := range document.Domain.ContentTypes {
		if contentMediaPublicExtension(contentType) == ".bin" {
			t.Fatalf("release media content type has no explicit extension: %q", contentType)
		}
	}
}
