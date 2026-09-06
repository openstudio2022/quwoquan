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

const (
	TagReleaseCandidateReceiptSchema = "quwoquan.tag_release_candidate_receipt"
	TagFencedReadbackReceiptSchema   = "quwoquan.tag_fenced_readback_receipt"
	contentFenceDatabase             = "quwoquan_content"
)

var sha256DigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type Command struct {
	Operation       string
	MongoURI        string
	Database        string
	ContentDatabase string
	Environment     string
	SourceOwner     string
	ReleaseID       string
	ManifestDigest  string
	ContentRevision int64
	ReportPath      string
}

func ParseCommand(args []string) (Command, error) {
	set := flag.NewFlagSet("tag-release-control", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command Command
	set.StringVar(&command.Operation, "operation", "", "query-candidate|readback-at-content-fence")
	set.StringVar(&command.MongoURI, "mongo-uri", "", "MongoDB connection URI")
	set.StringVar(&command.Database, "db", "quwoquan_tag", "Tag database")
	set.StringVar(&command.ContentDatabase, "content-db", contentFenceDatabase, "Content owner database holding the active pointer")
	set.StringVar(&command.Environment, "env", "", "exact Content environment")
	set.StringVar(&command.SourceOwner, "source-owner", "qwq_data", "exact Content source owner")
	set.StringVar(&command.ReleaseID, "release-id", "", "exact Content release id")
	set.StringVar(&command.ManifestDigest, "manifest-digest", "", "exact Content manifest digest")
	set.Int64Var(&command.ContentRevision, "content-revision", 0, "exact Content active pointer revision")
	set.StringVar(&command.ReportPath, "report", "", "create-once candidate receipt")
	if err := set.Parse(args); err != nil {
		return Command{}, fmt.Errorf("parse Tag release-control flags: %w", err)
	}
	if set.NArg() != 0 {
		return Command{}, errors.New("Tag release-control does not accept positional arguments")
	}
	provided := make(map[string]bool)
	set.Visit(func(item *flag.Flag) { provided[item.Name] = true })
	command.Operation = strings.TrimSpace(command.Operation)
	command.MongoURI = strings.TrimSpace(command.MongoURI)
	command.Database = strings.TrimSpace(command.Database)
	command.ContentDatabase = strings.TrimSpace(command.ContentDatabase)
	command.Environment = strings.TrimSpace(command.Environment)
	command.SourceOwner = strings.TrimSpace(command.SourceOwner)
	command.ReleaseID = strings.TrimSpace(command.ReleaseID)
	command.ManifestDigest = strings.TrimSpace(command.ManifestDigest)
	command.ReportPath = strings.TrimSpace(command.ReportPath)
	if command.MongoURI == "" || command.Database == "" || command.Environment == "" ||
		command.SourceOwner != "qwq_data" || command.ReleaseID == "" || command.ReportPath == "" ||
		!sha256DigestPattern.MatchString(command.ManifestDigest) {
		return Command{}, errors.New("Tag release-control requires canonical --mongo-uri, --db, --env, --source-owner=qwq_data, --release-id, --manifest-digest, and --report")
	}
	switch command.Operation {
	case "query-candidate":
		if provided["content-revision"] {
			return Command{}, errors.New("--content-revision is valid only for readback-at-content-fence")
		}
	case "readback-at-content-fence":
		if command.ContentDatabase == "" || command.ContentRevision <= 0 {
			return Command{}, errors.New("readback-at-content-fence requires --content-db and positive --content-revision")
		}
	default:
		return Command{}, errors.New("--operation must be query-candidate or readback-at-content-fence")
	}
	return command, nil
}

// FencedReadbackReceipt proves the Tag verified candidate for the exact tuple
// is readable while Content's active pointer sits on that tuple and revision.
type FencedReadbackReceipt struct {
	Schema             string     `json:"schema"`
	Status             string     `json:"status"`
	Owner              string     `json:"owner"`
	Environment        string     `json:"environment"`
	SourceOwner        string     `json:"sourceOwner"`
	ReleaseID          string     `json:"releaseId"`
	ManifestDigest     string     `json:"manifestDigest"`
	Revision           int64      `json:"revision"`
	Reason             string     `json:"reason,omitempty"`
	ContentActivatedAt *time.Time `json:"contentActivatedAt,omitempty"`
	ProjectionVersion  int64      `json:"projectionVersion,omitempty"`
	VerifiedAt         *time.Time `json:"verifiedAt,omitempty"`
	ClosureDigest      string     `json:"closureDigest,omitempty"`
	ProjectedNodeCount *int       `json:"projectedNodeCount,omitempty"`
	CanonicalDigest    string     `json:"canonicalDigest,omitempty"`
	TagRefsDigest      string     `json:"tagRefsDigest,omitempty"`
	GeneratedAt        time.Time  `json:"generatedAt"`
}

type contentActivePointer struct {
	Kind              string    `bson:"kind"`
	Status            string    `bson:"status"`
	Environment       string    `bson:"environment"`
	SourceOwner       string    `bson:"sourceOwner"`
	ActiveReleaseID   string    `bson:"activeReleaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	ProjectionVersion int64     `bson:"projectionVersion"`
	Revision          int64     `bson:"revision"`
	ActivatedAt       time.Time `bson:"activatedAt"`
}

func readContentActivePointer(ctx context.Context, contentDatabase *mongo.Database, environment, sourceOwner string) (contentActivePointer, bool, error) {
	var pointer contentActivePointer
	err := contentDatabase.Collection("data_release_state").FindOne(ctx, map[string]any{
		"kind": "active_pointer", "status": "active",
		"environment": environment, "sourceOwner": sourceOwner,
	}).Decode(&pointer)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return contentActivePointer{}, false, nil
	}
	if err != nil {
		return contentActivePointer{}, false, fmt.Errorf("read Content active pointer: %w", err)
	}
	if pointer.Kind != "active_pointer" || pointer.Status != "active" || pointer.Environment != environment || pointer.SourceOwner != sourceOwner ||
		pointer.ActiveReleaseID == "" || !sha256DigestPattern.MatchString(pointer.ManifestDigest) ||
		pointer.ProjectionVersion <= 0 || pointer.Revision <= 0 || pointer.ActivatedAt.IsZero() {
		return contentActivePointer{}, false, errors.New("Content active pointer is incomplete")
	}
	return pointer, true, nil
}

func BuildFencedReadbackReceipt(
	command Command,
	pointer contentActivePointer,
	pointerFound bool,
	candidate taxonomyreleasestore.ContentCandidate,
	candidateFound bool,
	generatedAt time.Time,
) FencedReadbackReceipt {
	receipt := FencedReadbackReceipt{
		Schema: TagFencedReadbackReceiptSchema, Status: "failed", Owner: "tag",
		Environment: command.Environment, SourceOwner: command.SourceOwner,
		ReleaseID: command.ReleaseID, ManifestDigest: command.ManifestDigest,
		Revision: command.ContentRevision, GeneratedAt: generatedAt.UTC(),
	}
	switch {
	case !pointerFound:
		receipt.Reason = "Content active pointer is absent"
	case pointer.ActiveReleaseID != command.ReleaseID || pointer.ManifestDigest != command.ManifestDigest || pointer.Revision != command.ContentRevision:
		receipt.Reason = "Content active pointer differs from the requested fence"
	case !candidateFound:
		receipt.Reason = "Tag verified candidate is absent for the fence tuple"
	case candidate.Status != "verified" || candidate.ExpectedNodeCount != candidate.ProjectedNodeCount:
		receipt.Reason = "Tag candidate for the fence tuple is not verified"
	default:
		activatedAt, verifiedAt := pointer.ActivatedAt.UTC(), candidate.VerifiedAt.UTC()
		projected := candidate.ProjectedNodeCount
		receipt.Status = "passed"
		receipt.ContentActivatedAt = &activatedAt
		receipt.ProjectionVersion = candidate.ProjectionVersion
		receipt.VerifiedAt = &verifiedAt
		receipt.ClosureDigest = candidate.ClosureDigest
		receipt.ProjectedNodeCount = &projected
		receipt.CanonicalDigest = candidate.CanonicalDigest
		receipt.TagRefsDigest = candidate.TagRefsDigest
	}
	return receipt
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
func WriteReceipt(path string, receipt any) error {
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
	generatedAt := time.Now().UTC().Truncate(time.Millisecond)
	switch command.Operation {
	case "query-candidate":
		receipt, err := BuildCandidateReceipt(candidate, found, generatedAt)
		if err != nil {
			return err
		}
		return WriteReceipt(command.ReportPath, receipt)
	case "readback-at-content-fence":
		pointer, pointerFound, err := readContentActivePointer(
			ctx, client.Database(command.ContentDatabase), command.Environment, command.SourceOwner,
		)
		if err != nil {
			return err
		}
		receipt := BuildFencedReadbackReceipt(command, pointer, pointerFound, candidate, found, generatedAt)
		if err := WriteReceipt(command.ReportPath, receipt); err != nil {
			return err
		}
		if receipt.Status != "passed" {
			return fmt.Errorf("GATE_BLOCK: Tag fenced readback failed: %s", receipt.Reason)
		}
		return nil
	default:
		return fmt.Errorf("unsupported Tag release-control operation %q", command.Operation)
	}
}
