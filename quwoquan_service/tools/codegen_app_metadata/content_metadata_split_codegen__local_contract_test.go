package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCanonicalContentMetadataWritesLayeredGeneratedOwners(t *testing.T) {
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-content-graph")
	if err := writeCanonicalContentMetadata(
		appDir,
		map[string]string{
			"following":   "micro",
			"recommended": "micro",
			"images":      "image",
		},
		[]string{"micro", "image"},
		map[string]int{
			"content": 8192,
			"title":   256,
		},
	); err != nil {
		t.Fatalf("write canonical Content metadata: %v", err)
	}

	feed := readCanonicalContentGeneratedTestFile(t, filepath.Join(
		appDir,
		"lib/service/content_service/content/post/application/generated/"+
			"content_feed_category_policy.g.dart",
	))
	for _, want := range []string{
		"final class ContentFeedCategoryPolicy",
		"static const Map<String, String> feedCategoryToRequestType",
		"'following': 'micro'",
		"'images': 'image'",
	} {
		if !strings.Contains(feed, want) {
			t.Fatalf("Content feed category policy misses %q", want)
		}
	}
	for _, duplicate := range []string{
		"appTabToFeedCategory",
		"feedDefaultLimit",
		"feedProjectionDefaults",
	} {
		if strings.Contains(feed, duplicate) {
			t.Fatalf("Content feed category policy duplicates %q", duplicate)
		}
	}

	snapshot := readCanonicalContentGeneratedTestFile(t, filepath.Join(
		appDir,
		"lib/service/content_service/content/post/domain/generated/"+
			"content_post_snapshot_policy.g.dart",
	))
	for _, want := range []string{
		"final class ContentPostSnapshotPolicy",
		"static const Map<String, int> postSnapshotFieldByteLimits",
		"'content': 8192",
		"'title': 256",
	} {
		if !strings.Contains(snapshot, want) {
			t.Fatalf("Content post snapshot policy misses %q", want)
		}
	}

	for _, relative := range []string{
		"lib/service/content_service/content/post/application/generated/" +
			"content_feed_category_policy.g.dart",
		"lib/service/content_service/content/post/domain/generated/" +
			"content_post_snapshot_policy.g.dart",
	} {
		if _, ok := generatedManifestOutputs[relative]; !ok {
			t.Fatalf("generated manifest did not record %s", relative)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCanonicalContentMetadataRejectsInvalidPolicyValues(t *testing.T) {
	for name, testCase := range map[string]struct {
		feed     map[string]string
		types    []string
		snapshot map[string]int
	}{
		"empty feed policy": {
			feed:  map[string]string{},
			types: []string{"micro"},
		},
		"empty feed category": {
			feed:  map[string]string{"": "micro"},
			types: []string{"micro"},
		},
		"empty request type": {
			feed:  map[string]string{"following": ""},
			types: []string{"micro"},
		},
		"empty ContentType vocabulary": {
			feed: map[string]string{"following": "micro"},
		},
		"unknown request type": {
			feed:  map[string]string{"following": "legacy_moment"},
			types: []string{"micro"},
		},
		"non-positive snapshot limit": {
			feed:     map[string]string{"following": "micro"},
			types:    []string{"micro"},
			snapshot: map[string]int{"title": 0},
		},
		"empty snapshot field": {
			feed:     map[string]string{"following": "micro"},
			types:    []string{"micro"},
			snapshot: map[string]int{"": 256},
		},
	} {
		t.Run(name, func(t *testing.T) {
			appDir := t.TempDir()
			beginGeneratedManifestForTest(t, appDir, "invalid-content-graph")
			if err := writeCanonicalContentMetadata(
				appDir,
				testCase.feed,
				testCase.types,
				testCase.snapshot,
			); err == nil {
				t.Fatal("invalid canonical Content metadata must fail closed")
			}
			if len(generatedManifestOutputs) != 0 {
				t.Fatal("invalid canonical Content metadata wrote partial outputs")
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCanonicalContentMetadataIsDerivedFromContractSource(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatalf("initialize metadata source: %v", err)
	}
	shared, err := readShared(filepath.Join(metadataDir, "_shared", "types.yaml"))
	if err != nil {
		t.Fatalf("load shared types: %v", err)
	}
	postDir := filepath.Join(metadataDir, "content", "content", "post")
	fields, err := readFields(filepath.Join(postDir, "fields.yaml"))
	if err != nil {
		t.Fatalf("read post fields: %v", err)
	}
	projection, err := readValidatedProjection(
		filepath.Join(postDir, "projections", "discovery_feed.yaml"),
		shared.Enums,
	)
	if err != nil {
		t.Fatalf("read discovery feed projection: %v", err)
	}
	post, ok := fields.Entities["Post"]
	if !ok {
		t.Fatal("Post entity not found in canonical fields")
	}
	contentTypes := shared.Enums["ContentType"]
	if len(contentTypes) == 0 {
		t.Fatal("canonical ContentType enum is empty")
	}
	uiDef, err := readUIConfig(filepath.Join(postDir, "ui_config.yaml"), true)
	if err != nil {
		t.Fatalf("read canonical Content UI config: %v", err)
	}
	if uiDef == nil {
		t.Fatal("canonical Content UI config is empty")
	}
	feedCategoryToType := uiDef.FeedRequestTypeByCategory
	snapshotLimits := buildPostSnapshotFieldByteLimits(
		post.Fields,
		projection.ClientProjection.Fields,
	)

	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "source-content-graph")
	if err := writeCanonicalContentMetadata(
		appDir,
		feedCategoryToType,
		contentTypes,
		snapshotLimits,
	); err != nil {
		t.Fatalf("write source-derived Content metadata: %v", err)
	}
	feed := readCanonicalContentGeneratedTestFile(t, filepath.Join(
		appDir,
		"lib/service/content_service/content/post/application/generated/"+
			"content_feed_category_policy.g.dart",
	))
	if want := renderContentFeedCategoryPolicyDart(feedCategoryToType); feed != want {
		t.Fatal("source-derived Content feed policy differs from canonical render")
	}
	for category, requestType := range feedCategoryToType {
		want := "'" + category + "': '" + requestType + "'"
		if !strings.Contains(feed, want) {
			t.Fatalf("source-derived Content feed policy misses %q", want)
		}
	}
	if strings.Contains(feed, "appTabToFeedCategory") {
		t.Fatal("source-derived Content feed policy emitted unused App tab mapping")
	}

	snapshot := readCanonicalContentGeneratedTestFile(t, filepath.Join(
		appDir,
		"lib/service/content_service/content/post/domain/generated/"+
			"content_post_snapshot_policy.g.dart",
	))
	if want := renderContentPostSnapshotPolicyDart(snapshotLimits); snapshot != want {
		t.Fatal("source-derived Content snapshot policy differs from canonical render")
	}
	for field, limit := range snapshotLimits {
		want := "'" + field + "': " + fmt.Sprint(limit)
		if !strings.Contains(snapshot, want) {
			t.Fatalf("source-derived Content snapshot policy misses %q", want)
		}
	}
}

func readCanonicalContentGeneratedTestFile(t *testing.T, path string) string {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated Content artifact %s: %v", path, err)
	}
	return string(payload)
}
