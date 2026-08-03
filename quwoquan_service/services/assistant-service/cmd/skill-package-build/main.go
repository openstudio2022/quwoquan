// Command skill-package-build compiles source-controlled official Skill assets
// into one signed immutable package directory. It never stages or activates the
// release; publication remains an explicit environment operation.
package main

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	packageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
)

const signingPrivateKeyEnv = "ASSISTANT_SKILL_PACKAGE_SIGNING_PRIVATE_KEY_BASE64"

type options struct {
	SourceRoot       string
	OutputRoot       string
	PackageVersion   string
	BuildID          string
	SourceRepository string
	SourceRevision   string
	BuiltAt          time.Time
	SigningKeyID     string
	CommandID        string
	ExpectedRevision int
	ActivatedBy      string
	SigningKey       ed25519.PrivateKey
}

type report struct {
	PackageID        string `json:"packageId"`
	ReleaseDigest    string `json:"releaseDigest"`
	BuildID          string `json:"buildId"`
	PublicationRef   string `json:"publicationRef"`
	AssetCount       int    `json:"assetCount"`
	SourceRevision   string `json:"sourceRevision"`
	ExpectedRevision int    `json:"expectedRevision"`
}

func main() {
	options, err := parseOptions(os.Args[1:], os.Getenv)
	if err != nil {
		fmt.Fprintln(os.Stderr, "assistant Skill package build options invalid:", err)
		os.Exit(2)
	}
	if err := run(options, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "assistant Skill package build failed:", err)
		os.Exit(1)
	}
}

func parseOptions(
	args []string,
	getenv func(string) string,
) (options, error) {
	flags := flag.NewFlagSet("assistant-skill-package-build", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	sourceRoot := flags.String("source-root", "", "official Skill source root")
	outputRoot := flags.String("output-root", "", "official immutable package root")
	packageVersion := flags.String("package-version", "", "semantic package version")
	buildID := flags.String("build-id", "", "immutable build identity")
	sourceRepository := flags.String("source-repository", "", "source repository identity")
	sourceRevision := flags.String("source-revision", "", "source revision")
	builtAtValue := flags.String("built-at", "", "RFC3339 deterministic build time")
	keyID := flags.String("key-id", "", "trusted signing key identity")
	commandID := flags.String("command-id", "", "stage/activation idempotency identity")
	expectedRevision := flags.Int("expected-revision", 0, "expected active pointer revision")
	activatedBy := flags.String("activated-by", "", "protected publication principal")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected positional arguments")
	}
	builtAt, err := time.Parse(time.RFC3339, strings.TrimSpace(*builtAtValue))
	if err != nil {
		return options{}, fmt.Errorf("--built-at must be RFC3339")
	}
	privateKey, err := decodePrivateKey(getenv(signingPrivateKeyEnv))
	if err != nil {
		return options{}, err
	}
	parsed := options{
		SourceRoot:       strings.TrimSpace(*sourceRoot),
		OutputRoot:       strings.TrimSpace(*outputRoot),
		PackageVersion:   strings.TrimSpace(*packageVersion),
		BuildID:          strings.TrimSpace(*buildID),
		SourceRepository: strings.TrimSpace(*sourceRepository),
		SourceRevision:   strings.TrimSpace(*sourceRevision),
		BuiltAt:          builtAt.UTC(),
		SigningKeyID:     strings.TrimSpace(*keyID),
		CommandID:        strings.TrimSpace(*commandID),
		ExpectedRevision: *expectedRevision,
		ActivatedBy:      strings.TrimSpace(*activatedBy),
		SigningKey:       privateKey,
	}
	if parsed.SourceRoot == "" || parsed.OutputRoot == "" ||
		parsed.PackageVersion == "" || parsed.BuildID == "" ||
		parsed.SourceRepository == "" || parsed.SourceRevision == "" ||
		parsed.SigningKeyID == "" || parsed.CommandID == "" ||
		parsed.ExpectedRevision < 0 || parsed.ActivatedBy == "" {
		return options{}, fmt.Errorf("all build, provenance, signing, and publication fields are required")
	}
	return parsed, nil
}

func decodePrivateKey(encoded string) (ed25519.PrivateKey, error) {
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encoded))
	if err != nil || len(raw) != ed25519.PrivateKeySize {
		return nil, fmt.Errorf("%s must contain one base64 Ed25519 private key", signingPrivateKeyEnv)
	}
	return ed25519.PrivateKey(append([]byte(nil), raw...)), nil
}

func run(options options, output io.Writer) error {
	bundle, err := resourcebuilder.NewSourceBuilderAt(options.SourceRoot).
		Compile(context.Background())
	if err != nil {
		return err
	}
	built, err := resourcebuilder.BuildPackage(
		bundle,
		resourcebuilder.PackageBuildOptions{
			PackageID:        "assistant.session.skills",
			PackageVersion:   options.PackageVersion,
			BuildID:          options.BuildID,
			SourceRepository: options.SourceRepository,
			SourceRevision:   options.SourceRevision,
			BuiltAt:          options.BuiltAt,
			RuntimeCompatibility: packagemodel.RuntimeCompatibility{
				APIVersion:            packagemodel.RuntimeAPIVersion,
				MinimumRuntimeVersion: packagemodel.RuntimeVersion,
				MaximumRuntimeVersion: packagemodel.RuntimeVersion,
			},
			CapabilityGrants: []packagemodel.CapabilityGrant{{
				CapabilityID: "assistant.skill",
				Scope:        "official",
			}},
			SigningKeyID:      options.SigningKeyID,
			SigningPrivateKey: options.SigningKey,
		},
	)
	if err != nil {
		return err
	}
	publication := packageartifact.PublicationArtifact{
		CommandID:        options.CommandID,
		ExpectedRevision: options.ExpectedRevision,
		ActivatedBy:      options.ActivatedBy,
		Release:          built.Release,
	}
	publicationRef, err := writePackage(options.OutputRoot, options.BuildID, built, publication)
	if err != nil {
		return err
	}
	return json.NewEncoder(output).Encode(report{
		PackageID:        built.Release.PackageID,
		ReleaseDigest:    built.Release.ReleaseDigest,
		BuildID:          options.BuildID,
		PublicationRef:   publicationRef,
		AssetCount:       len(built.Release.Assets),
		SourceRevision:   options.SourceRevision,
		ExpectedRevision: options.ExpectedRevision,
	})
}

func writePackage(
	root string,
	buildID string,
	built resourcebuilder.BuiltPackage,
	publication packageartifact.PublicationArtifact,
) (string, error) {
	if err := publication.Validate(); err != nil {
		return "", err
	}
	absoluteRoot, err := filepath.Abs(root)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(absoluteRoot, 0o755); err != nil {
		return "", err
	}
	destination := filepath.Join(absoluteRoot, "releases", buildID)
	if _, err := os.Stat(destination); err == nil {
		return "", fmt.Errorf("immutable Skill package build %q already exists", buildID)
	} else if !os.IsNotExist(err) {
		return "", err
	}
	staging, err := os.MkdirTemp(absoluteRoot, ".skill-package-build-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(staging)
	prefix := filepath.ToSlash(filepath.Join("releases", buildID)) + "/"
	for _, file := range built.Files {
		if !strings.HasPrefix(file.RelativePath, prefix) {
			return "", fmt.Errorf("built asset path is outside immutable release")
		}
		relative := strings.TrimPrefix(file.RelativePath, prefix)
		path := filepath.Join(staging, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return "", err
		}
		if err := os.WriteFile(path, file.Content, 0o644); err != nil {
			return "", err
		}
	}
	publicationContent, err := json.MarshalIndent(publication, "", "  ")
	if err != nil {
		return "", err
	}
	publicationContent = append(publicationContent, '\n')
	if err := os.WriteFile(
		filepath.Join(staging, "publication.json"),
		publicationContent,
		0o644,
	); err != nil {
		return "", err
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return "", err
	}
	if err := os.Rename(staging, destination); err != nil {
		return "", err
	}
	return filepath.ToSlash(filepath.Join("releases", buildID, "publication.json")), nil
}
