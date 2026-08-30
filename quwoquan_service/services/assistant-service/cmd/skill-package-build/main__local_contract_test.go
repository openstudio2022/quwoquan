// spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/service-core-composition/spec.md#gwt-001.t1
package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
)

func TestBuildCommandEmitsRuntimeConsumableOfficialPublication(t *testing.T) {
	_, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	serviceRoot, err := filepath.Abs(filepath.Join("..", "..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	outputRoot := t.TempDir()
	var output bytes.Buffer
	err = run(options{
		SourceRoot: filepath.Join(
			serviceRoot,
			"services",
			"assistant-service",
			"resources",
			"skill_packages",
			"official",
		),
		OutputRoot:       outputRoot,
		PackageVersion:   "1.0.0",
		BuildID:          "alpha-capsule-contract",
		SourceRepository: "quwoquan",
		SourceRevision:   strings.Repeat("a", 40),
		BuiltAt:          time.Date(2026, time.August, 18, 12, 0, 0, 0, time.UTC),
		SigningKeyID:     "alpha-local-contract",
		CommandID:        "official-bootstrap-alpha-capsule-contract",
		ExpectedRevision: 0,
		ActivatedBy:      "service:local-contract:alpha-local",
		SigningKey:       privateKey,
	}, &output)
	if err != nil {
		t.Fatalf("build official Skill publication: %v", err)
	}
	var report report
	if err := json.Unmarshal(output.Bytes(), &report); err != nil {
		t.Fatalf("decode build report: %v", err)
	}
	if report.PublicationRef != "releases/alpha-capsule-contract/publication.json" {
		t.Fatalf("publication ref = %q", report.PublicationRef)
	}
	publication, err := packageartifact.LoadPublicationArtifact(
		outputRoot,
		report.PublicationRef,
	)
	if err != nil {
		t.Fatalf("runtime cannot decode emitted publication: %v", err)
	}
	if publication.Release.ReleaseDigest != report.ReleaseDigest {
		t.Fatalf(
			"publication digest = %q, report digest = %q",
			publication.Release.ReleaseDigest,
			report.ReleaseDigest,
		)
	}
	trusted := map[string]ed25519.PublicKey{
		"alpha-local-contract": privateKey.Public().(ed25519.PublicKey),
	}
	if err := packageapplication.NewEd25519Verifier(trusted).Verify(
		t.Context(),
		publication.Release,
	); err != nil {
		t.Fatalf("runtime cannot verify emitted release signature: %v", err)
	}
	for _, asset := range publication.Release.Assets {
		const prefix = "skill-package://official/"
		if !strings.HasPrefix(asset.Locator, prefix) {
			t.Fatalf("asset %q locator = %q", asset.AssetID, asset.Locator)
		}
		path := filepath.Join(
			outputRoot,
			filepath.FromSlash(strings.TrimPrefix(asset.Locator, prefix)),
		)
		if info, err := os.Lstat(path); err != nil || !info.Mode().IsRegular() {
			t.Fatalf("runtime asset %q is unavailable at %s: %v", asset.AssetID, path, err)
		}
	}
}

func TestDecodePrivateKeyMatchesPublishedTrustRoot(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := decodePrivateKey(base64.StdEncoding.EncodeToString(privateKey))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(decoded.Public().(ed25519.PublicKey), publicKey) {
		t.Fatal("decoded signing key does not match its trusted public key")
	}
}
