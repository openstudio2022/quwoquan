package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestContentPreviewTrackManifestGeneratorReadsFixedContractGraphAndExportsPublicOwner(
	t *testing.T,
) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	appDir := t.TempDir()
	if err := generateContentPreviewTrackManifestContract(appDir); err != nil {
		t.Fatal(err)
	}
	generated := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/content/preview_track_manifest_contracts.g.dart",
	))
	if !strings.Contains(generated, "final class PreviewTrackManifestWire") {
		t.Fatal("fixed ContractGraph did not generate PreviewTrackManifestWire")
	}
	publicOwner := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/generated/content_preview_track_contracts.dart",
	))
	if !strings.Contains(
		publicOwner,
		"export '../src/content/preview_track_manifest_contracts.g.dart';",
	) {
		t.Fatal("preview-track wire has no generated public package owner")
	}
}

func TestContentPreviewTrackManifestGeneratorOwnsStrictTypedAssetWire(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(
		"..",
		"..",
		"services",
		"content-service",
		"contracts",
		"media",
		"media_asset",
		"preview_track_manifest.schema.json",
	))
	if err != nil {
		t.Fatalf("read canonical preview manifest schema: %v", err)
	}
	generated, err := renderContentPreviewTrackManifestContract(raw)
	if err != nil {
		t.Fatalf("render preview manifest contract: %v", err)
	}
	for _, required := range []string{
		"final class PreviewTrackManifestWire",
		"final class PreviewTrackSpriteWire",
		"final class PreviewTrackFrameWire",
		"enum PreviewTrackAccessPolicy",
		"enum PreviewTrackSpriteMimeType",
		"_previewRejectUnknownFields",
		"_previewRequiredConstString",
		"quwoquan.content.preview_track_manifest",
		"minItems: 1",
		"maxItems: 64",
		"maxItems: 1000",
		"pattern: \"^sha256:[0-9a-f]{64}\\$\"",
		"max: 3600000",
		"Map<String, Object?> toWire()",
	} {
		if !strings.Contains(generated, required) {
			t.Fatalf("generated preview manifest contract misses %q", required)
		}
	}
	for _, forbidden := range []string{
		"Map<String, dynamic>",
		"fromMap(",
		"schemaVersion",
		"Legacy",
		"fallback",
	} {
		if strings.Contains(generated, forbidden) {
			t.Fatalf("generated preview manifest contract contains forbidden %q", forbidden)
		}
	}
}

func TestContentPreviewTrackManifestGeneratorReadsOnlyFixedContractGraph(t *testing.T) {
	source, err := os.ReadFile("content_preview_track_manifest_codegen.go")
	if err != nil {
		t.Fatalf("read generator source: %v", err)
	}
	text := string(source)
	if strings.Contains(text, "os.ReadFile(") {
		t.Fatal("App preview-track emitter must not bypass the fixed ContractGraph bundle")
	}
	if !strings.Contains(text, "readMetadataDocument(previewTrackManifestSchemaPath)") {
		t.Fatal("App preview-track emitter must read the schema embedded in the fixed ContractGraph")
	}
}

func TestContentPreviewTrackManifestGeneratorFailsClosedOnSchemaDrift(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(
		"..",
		"..",
		"services",
		"content-service",
		"contracts",
		"media",
		"media_asset",
		"preview_track_manifest.schema.json",
	))
	if err != nil {
		t.Fatalf("read canonical preview manifest schema: %v", err)
	}

	withOptionalField := strings.Replace(
		string(raw),
		`"properties": {`,
		`"properties": {"unexpectedOptional": {"type": "string"},`,
		1,
	)
	if _, err := renderContentPreviewTrackManifestContract([]byte(withOptionalField)); err == nil {
		t.Fatal("optional schema drift must fail until its typed ownership is explicit")
	}

	withOpenObjects := strings.Replace(
		string(raw),
		`"additionalProperties": false`,
		`"additionalProperties": true`,
		1,
	)
	if _, err := renderContentPreviewTrackManifestContract([]byte(withOpenObjects)); err == nil {
		t.Fatal("open preview manifest objects must fail closed")
	}
}
