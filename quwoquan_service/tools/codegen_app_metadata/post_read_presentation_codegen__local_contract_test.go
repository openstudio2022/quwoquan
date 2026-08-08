package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestRenderArticleWireKeysClassUsesNonProjectionIdentity(t *testing.T) {
	t.Parallel()

	generated, err := renderWireKeysClassDart([]byte(`
wire_keys_class: ArticleDetailWireKeys
description: canonical raw wire keys
keys:
- const_name: visibility
  json_key: visibility
`), "content/content/post/projections/article_detail_wire_keys.yaml")
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"abstract final class ArticleDetailWireKeys",
		"static const String visibility = 'visibility';",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("generated wire keys are missing %q:\n%s", expected, generated)
		}
	}
}

func TestPostReadPresentationWriterRetiresImmersiveWireKeysOutput(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatalf("initialize metadata source: %v", err)
	}
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-post-read-graph")
	if err := writePostReadPresentationArtifacts(
		appDir,
		filepath.Join(metadataDir, "content", "content", "post", "projections"),
	); err != nil {
		t.Fatalf("write Post read presentation artifacts: %v", err)
	}

	retired := contentPostAdaptersOutputPath(
		appDir,
		"content_post_immersive_wire_keys.g.dart",
	)
	if _, err := os.Stat(retired); !os.IsNotExist(err) {
		t.Fatalf("retired immersive wire keys output was emitted: %v", err)
	}
	for _, path := range []string{
		contentPostPresentationOutputPath(appDir, "post_read_surface_id.g.dart"),
		contentPostAdaptersOutputPath(appDir, "article_detail_wire_keys.g.dart"),
		contentPostPublicGeneratedOutputPath(appDir, "content_media_post_projection_keys.g.dart"),
	} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("canonical Post read artifact is missing at %s: %v", path, err)
		}
		relative, err := filepath.Rel(appDir, path)
		if err != nil {
			t.Fatalf("relative generated path: %v", err)
		}
		if _, ok := generatedManifestOutputs[filepath.ToSlash(relative)]; !ok {
			t.Fatalf("generated manifest did not record %s", relative)
		}
	}
}
