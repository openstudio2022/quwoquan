// Package tagreleasecontrol exposes the Tag-owned exact Data release candidate
// query and create-once receipt surface.
package tagreleasecontrol

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

const TagReleaseCandidateReceiptSchema = "quwoquan.tag_release_candidate_receipt"

var sha256DigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type Command struct {
	Operation      string
	MongoURI       string
	Database       string
	Environment    string
	SourceOwner    string
	ReleaseID      string
	ManifestDigest string
	ReportPath     string
}

func ParseCommand(args []string) (Command, error) {
	set := flag.NewFlagSet("tag-release-control", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command Command
	set.StringVar(&command.Operation, "operation", "", "query-candidate")
	set.StringVar(&command.MongoURI, "mongo-uri", "", "MongoDB connection URI")
	set.StringVar(&command.Database, "db", "quwoquan_tag", "Tag database")
	set.StringVar(&command.Environment, "env", "", "exact Content environment")
	set.StringVar(&command.SourceOwner, "source-owner", "qwq_data", "exact Content source owner")
	set.StringVar(&command.ReleaseID, "release-id", "", "exact Content release id")
	set.StringVar(&command.ManifestDigest, "manifest-digest", "", "exact Content manifest digest")
	set.StringVar(&command.ReportPath, "report", "", "create-once candidate receipt")
	if err := set.Parse(args); err != nil {
		return Command{}, fmt.Errorf("parse Tag release-control flags: %w", err)
	}
	if set.NArg() != 0 {
		return Command{}, errors.New("Tag release-control does not accept positional arguments")
	}
	command.Operation = strings.TrimSpace(command.Operation)
	command.MongoURI = strings.TrimSpace(command.MongoURI)
	command.Database = strings.TrimSpace(command.Database)
	command.Environment = strings.TrimSpace(command.Environment)
	command.SourceOwner = strings.TrimSpace(command.SourceOwner)
	command.ReleaseID = strings.TrimSpace(command.ReleaseID)
	command.ManifestDigest = strings.TrimSpace(command.ManifestDigest)
	command.ReportPath = strings.TrimSpace(command.ReportPath)
	if command.Operation != "query-candidate" {
		return Command{}, errors.New("--operation must be query-candidate")
	}
	if command.MongoURI == "" || command.Database == "" || command.Environment == "" ||
		command.SourceOwner != "qwq_data" || command.ReleaseID == "" || command.ReportPath == "" ||
		!sha256DigestPattern.MatchString(command.ManifestDigest) {
		return Command{}, errors.New("query-candidate requires canonical --mongo-uri, --db, --env, --source-owner=qwq_data, --release-id, --manifest-digest, and --report")
	}
	return command, nil
}

type CandidateReceipt struct {
	Schema             string     `json:"schema"`
	Status             string     `json:"status"`
	Environment        string     `json:"environment"`
	SourceOwner        string     `json:"sourceOwner"`
	ReleaseID          string     `json:"releaseId"`
	ManifestDigest     string     `json:"manifestDigest"`
	ProjectionVersion  int64      `json:"projectionVersion,omitempty"`
	VerifiedAt         *time.Time `json:"verifiedAt,omitempty"`
	ClosureDigest      string     `json:"closureDigest,omitempty"`
	ExpectedNodeCount  *int       `json:"expectedNodeCount,omitempty"`
	ProjectedNodeCount *int       `json:"projectedNodeCount,omitempty"`
	CanonicalDigest    string     `json:"canonicalDigest,omitempty"`
	ReleaseKind        string     `json:"releaseKind,omitempty"`
	TagRefsDigest      string     `json:"tagRefsDigest,omitempty"`
	GeneratedAt        time.Time  `json:"generatedAt"`
}

func BuildCandidateReceipt(
	identity taxonomyreleasestore.ContentCandidate,
	found bool,
	generatedAt time.Time,
) (CandidateReceipt, error) {
	if identity.Environment == "" || identity.SourceOwner != "qwq_data" || identity.ReleaseID == "" ||
		!sha256DigestPattern.MatchString(identity.ManifestDigest) || generatedAt.IsZero() {
		return CandidateReceipt{}, errors.New("Tag candidate receipt binding is invalid")
	}
	receipt := CandidateReceipt{
		Schema: TagReleaseCandidateReceiptSchema, Status: "not_found",
		Environment: identity.Environment, SourceOwner: identity.SourceOwner,
		ReleaseID: identity.ReleaseID, ManifestDigest: identity.ManifestDigest,
		GeneratedAt: generatedAt.UTC(),
	}
	if !found {
		return receipt, nil
	}
	if identity.Status != "verified" || identity.ProjectionVersion <= 0 || identity.VerifiedAt.IsZero() ||
		!sha256DigestPattern.MatchString(identity.ClosureDigest) ||
		!sha256DigestPattern.MatchString(identity.CanonicalDigest) ||
		!sha256DigestPattern.MatchString(identity.TagRefsDigest) ||
		identity.ExpectedNodeCount < 0 || identity.ExpectedNodeCount != identity.ProjectedNodeCount {
		return CandidateReceipt{}, errors.New("Tag candidate receipt source is not verified")
	}
	verifiedAt := identity.VerifiedAt.UTC()
	receipt.Status = "found"
	receipt.ProjectionVersion = identity.ProjectionVersion
	receipt.VerifiedAt = &verifiedAt
	receipt.ClosureDigest = identity.ClosureDigest
	expected := identity.ExpectedNodeCount
	projected := identity.ProjectedNodeCount
	receipt.ExpectedNodeCount = &expected
	receipt.ProjectedNodeCount = &projected
	receipt.CanonicalDigest = identity.CanonicalDigest
	receipt.ReleaseKind = identity.ReleaseKind
	receipt.TagRefsDigest = identity.TagRefsDigest
	return receipt, nil
}

// WriteReceipt uses O_EXCL and rejects both a symlink destination and any
// symlinked parent component.
func WriteReceipt(path string, receipt CandidateReceipt) error {
	resolved, err := validateReceiptDestination(path)
	if err != nil {
		return err
	}
	payload, err := json.MarshalIndent(receipt, "", "  ")
	if err != nil {
		return fmt.Errorf("encode Tag candidate receipt: %w", err)
	}
	payload = append(payload, '\n')
	file, err := os.OpenFile(resolved, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create Tag candidate receipt: %w", err)
	}
	if _, err := file.Write(payload); err != nil {
		_ = file.Close()
		_ = os.Remove(resolved)
		return fmt.Errorf("write Tag candidate receipt: %w", err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		_ = os.Remove(resolved)
		return fmt.Errorf("sync Tag candidate receipt: %w", err)
	}
	if err := file.Close(); err != nil {
		_ = os.Remove(resolved)
		return fmt.Errorf("close Tag candidate receipt: %w", err)
	}
	return nil
}

func validateReceiptDestination(path string) (string, error) {
	resolved := filepath.Clean(strings.TrimSpace(path))
	if resolved == "." || resolved == string(filepath.Separator) {
		return "", errors.New("Tag candidate receipt path is invalid")
	}
	if _, err := os.Lstat(resolved); err == nil {
		return "", errors.New("Tag candidate receipt already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", fmt.Errorf("inspect Tag candidate receipt: %w", err)
	}
	parent := filepath.Dir(resolved)
	info, err := os.Lstat(parent)
	if err != nil {
		return "", fmt.Errorf("inspect Tag candidate receipt directory: %w", err)
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", errors.New("Tag candidate receipt parent must be a non-symlink directory")
	}
	return resolved, nil
}

func Run(ctx context.Context, args []string) error {
	if ctx == nil {
		return errors.New("Tag release-control context is required")
	}
	command, err := ParseCommand(args)
	if err != nil {
		return err
	}
	if _, err := validateReceiptDestination(command.ReportPath); err != nil {
		return err
	}
	client, err := mongo.Connect(options.Client().ApplyURI(command.MongoURI))
	if err != nil {
		return fmt.Errorf("connect Tag release-control MongoDB: %w", err)
	}
	defer client.Disconnect(context.Background())
	store := taxonomyreleasestore.NewContentCandidateStore(client.Database(command.Database))
	candidate, found, err := store.ReadVerifiedContentCandidate(
		ctx, command.Environment, command.SourceOwner, command.ReleaseID, command.ManifestDigest,
	)
	if err != nil {
		return fmt.Errorf("query verified Tag content candidate: %w", err)
	}
	receipt, err := BuildCandidateReceipt(candidate, found, time.Now().UTC().Truncate(time.Millisecond))
	if err != nil {
		return err
	}
	return WriteReceipt(command.ReportPath, receipt)
}
