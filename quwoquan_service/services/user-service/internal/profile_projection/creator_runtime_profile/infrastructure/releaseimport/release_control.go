package releaseimport

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

	"quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
	creatorpersistence "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/persistence"
)

const (
	CreatorReleaseCandidateReceiptSchema = "quwoquan.creator_release_candidate_receipt"
	CreatorFencedReadbackReceiptSchema   = "quwoquan.creator_fenced_readback_receipt"
	contentFenceDatabase                 = "quwoquan_content"
)

var canonicalReceiptDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type CandidateReceiptCounts struct {
	Expected  int `json:"expected"`
	Projected int `json:"projected"`
}

type CreatorReleaseCandidateReceipt struct {
	Schema            string                              `json:"schema"`
	Status            string                              `json:"status"`
	Environment       string                              `json:"environment"`
	SourceOwner       string                              `json:"sourceOwner"`
	ReleaseID         string                              `json:"releaseId"`
	ManifestDigest    string                              `json:"manifestDigest"`
	ProjectionVersion int64                               `json:"projectionVersion,omitempty"`
	VerifiedAt        *time.Time                          `json:"verifiedAt,omitempty"`
	ClosureDigest     string                              `json:"closureDigest,omitempty"`
	Counts            *CandidateReceiptCounts             `json:"counts,omitempty"`
	AuthorIDs         []string                            `json:"authorIds,omitempty"`
	ProfileDigests    []model.CreatorProfileDigestBinding `json:"profileDigests,omitempty"`
	GeneratedAt       time.Time                           `json:"generatedAt"`
}

type ReleaseControlCommand struct {
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

func ParseReleaseControlCommand(args []string) (ReleaseControlCommand, error) {
	set := flag.NewFlagSet("creator-release-control", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command ReleaseControlCommand
	set.StringVar(&command.Operation, "operation", "", "query-candidate|readback-at-content-fence")
	set.StringVar(&command.MongoURI, "mongo-uri", "", "MongoDB URI")
	set.StringVar(&command.Database, "database", projectionDatabase, "Creator projection database")
	set.StringVar(&command.ContentDatabase, "content-db", contentFenceDatabase, "Content owner database holding the active pointer")
	set.StringVar(&command.Environment, "env", "", "exact Content fence environment")
	set.StringVar(&command.SourceOwner, "source-owner", dataSourceOwner, "exact Content fence owner")
	set.StringVar(&command.ReleaseID, "release-id", "", "exact Content fence release id")
	set.StringVar(&command.ManifestDigest, "manifest-digest", "", "exact Content fence manifest digest")
	set.Int64Var(&command.ContentRevision, "content-revision", 0, "exact Content active pointer revision")
	set.StringVar(&command.ReportPath, "report", "", "create-once candidate receipt")
	if err := set.Parse(args); err != nil {
		return ReleaseControlCommand{}, fmt.Errorf("parse creator release-control flags: %w", err)
	}
	if set.NArg() != 0 {
		return ReleaseControlCommand{}, fmt.Errorf("creator release-control does not accept positional arguments")
	}
	provided := make(map[string]bool)
	set.Visit(func(item *flag.Flag) { provided[item.Name] = true })
	command.Operation = strings.TrimSpace(command.Operation)
	command.MongoURI, command.Database = strings.TrimSpace(command.MongoURI), strings.TrimSpace(command.Database)
	command.ContentDatabase = strings.TrimSpace(command.ContentDatabase)
	command.Environment, command.SourceOwner = strings.TrimSpace(command.Environment), strings.TrimSpace(command.SourceOwner)
	command.ReleaseID, command.ManifestDigest, command.ReportPath = strings.TrimSpace(command.ReleaseID), strings.TrimSpace(command.ManifestDigest), strings.TrimSpace(command.ReportPath)
	if command.MongoURI == "" || command.Database == "" || command.Environment == "" || command.SourceOwner != dataSourceOwner || command.ReleaseID == "" || !canonicalReceiptDigestPattern.MatchString(command.ManifestDigest) || command.ReportPath == "" {
		return ReleaseControlCommand{}, fmt.Errorf("creator release-control requires canonical --mongo-uri, --database, --env, --source-owner=qwq_data, --release-id, --manifest-digest and --report")
	}
	switch command.Operation {
	case "query-candidate":
		if provided["content-revision"] {
			return ReleaseControlCommand{}, fmt.Errorf("--content-revision is valid only for readback-at-content-fence")
		}
	case "readback-at-content-fence":
		if command.ContentDatabase == "" || command.ContentRevision <= 0 {
			return ReleaseControlCommand{}, fmt.Errorf("readback-at-content-fence requires --content-db and positive --content-revision")
		}
	default:
		return ReleaseControlCommand{}, fmt.Errorf("--operation must be query-candidate or readback-at-content-fence")
	}
	return command, nil
}

// CreatorFencedReadbackReceipt proves the Creator verified candidate for the
// exact tuple is readable while Content's active pointer sits on that same
// tuple and revision. It never widens to latest or to another revision.
type CreatorFencedReadbackReceipt struct {
	Schema             string                              `json:"schema"`
	Status             string                              `json:"status"`
	Owner              string                              `json:"owner"`
	Environment        string                              `json:"environment"`
	SourceOwner        string                              `json:"sourceOwner"`
	ReleaseID          string                              `json:"releaseId"`
	ManifestDigest     string                              `json:"manifestDigest"`
	Revision           int64                               `json:"revision"`
	Reason             string                              `json:"reason,omitempty"`
	ContentActivatedAt *time.Time                          `json:"contentActivatedAt,omitempty"`
	ProjectionVersion  int64                               `json:"projectionVersion,omitempty"`
	VerifiedAt         *time.Time                          `json:"verifiedAt,omitempty"`
	ClosureDigest      string                              `json:"closureDigest,omitempty"`
	Counts             *CandidateReceiptCounts             `json:"counts,omitempty"`
	ProfileDigests     []model.CreatorProfileDigestBinding `json:"profileDigests,omitempty"`
	GeneratedAt        time.Time                           `json:"generatedAt"`
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
	if pointer.Kind != "active_pointer" || pointer.Status != "active" || pointer.Environment != environment || pointer.SourceOwner != sourceOwner || pointer.ActiveReleaseID == "" || !canonicalReceiptDigestPattern.MatchString(pointer.ManifestDigest) || pointer.ProjectionVersion <= 0 || pointer.Revision <= 0 || pointer.ActivatedAt.IsZero() {
		return contentActivePointer{}, false, fmt.Errorf("Content active pointer is incomplete")
	}
	return pointer, true, nil
}

func BuildCreatorFencedReadbackReceipt(command ReleaseControlCommand, pointer contentActivePointer, pointerFound bool, state model.CreatorReleaseCandidateState, candidateFound bool, generatedAt time.Time) CreatorFencedReadbackReceipt {
	receipt := CreatorFencedReadbackReceipt{
		Schema: CreatorFencedReadbackReceiptSchema, Status: "failed", Owner: "creator",
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
		receipt.Reason = "Creator verified candidate is absent for the fence tuple"
	case state.Status != "verified" || state.ExpectedCount != state.ProjectedCount:
		receipt.Reason = "Creator candidate for the fence tuple is not verified"
	default:
		activatedAt, verifiedAt := pointer.ActivatedAt.UTC(), state.VerifiedAt.UTC()
		receipt.Status = "passed"
		receipt.ContentActivatedAt = &activatedAt
		receipt.ProjectionVersion, receipt.VerifiedAt, receipt.ClosureDigest = state.ProjectionVersion, &verifiedAt, state.ClosureDigest
		receipt.Counts = &CandidateReceiptCounts{Expected: state.ExpectedCount, Projected: state.ProjectedCount}
		receipt.ProfileDigests = append([]model.CreatorProfileDigestBinding(nil), state.ProfileDigests...)
	}
	return receipt
}

func BuildCreatorReleaseCandidateReceipt(state model.CreatorReleaseCandidateState, found bool, generatedAt time.Time) (CreatorReleaseCandidateReceipt, error) {
	if generatedAt.IsZero() || strings.TrimSpace(state.Environment) == "" || state.SourceOwner != dataSourceOwner || strings.TrimSpace(state.ReleaseID) == "" || !canonicalReceiptDigestPattern.MatchString(state.ManifestDigest) {
		return CreatorReleaseCandidateReceipt{}, fmt.Errorf("Creator candidate receipt identity is incomplete")
	}
	receipt := CreatorReleaseCandidateReceipt{Schema: CreatorReleaseCandidateReceiptSchema, Status: "not_found", Environment: state.Environment, SourceOwner: state.SourceOwner, ReleaseID: state.ReleaseID, ManifestDigest: state.ManifestDigest, GeneratedAt: generatedAt.UTC()}
	if !found {
		return receipt, nil
	}
	if state.Status != "verified" || state.ProjectionVersion <= 0 || state.VerifiedAt.IsZero() || !canonicalReceiptDigestPattern.MatchString(state.ClosureDigest) || state.ExpectedCount < 0 || state.ExpectedCount != state.ProjectedCount {
		return CreatorReleaseCandidateReceipt{}, fmt.Errorf("Creator candidate receipt state is not verified")
	}
	verifiedAt := state.VerifiedAt.UTC()
	receipt.Status, receipt.ProjectionVersion, receipt.VerifiedAt, receipt.ClosureDigest = "found", state.ProjectionVersion, &verifiedAt, state.ClosureDigest
	receipt.Counts = &CandidateReceiptCounts{Expected: state.ExpectedCount, Projected: state.ProjectedCount}
	receipt.AuthorIDs = append([]string(nil), state.AuthorIDs...)
	receipt.ProfileDigests = append([]model.CreatorProfileDigestBinding(nil), state.ProfileDigests...)
	return receipt, nil
}

func RunReleaseControl(ctx context.Context, args []string) error {
	if ctx == nil {
		return fmt.Errorf("creator release-control context is required")
	}
	command, err := ParseReleaseControlCommand(args)
	if err != nil {
		return err
	}
	if _, err := validateCreateOnceDestination(command.ReportPath); err != nil {
		return err
	}
	client, err := mongo.Connect(options.Client().ApplyURI(command.MongoURI))
	if err != nil {
		return fmt.Errorf("connect Creator release-control MongoDB: %w", err)
	}
	defer client.Disconnect(context.Background())
	store := creatorpersistence.NewCreatorReleaseCandidateStore(client.Database(command.Database))
	identity := model.ReleaseIdentity{Environment: command.Environment, SourceOwner: command.SourceOwner, ReleaseID: command.ReleaseID, ManifestDigest: command.ManifestDigest}
	generatedAt := time.Now().UTC().Truncate(time.Millisecond)
	switch command.Operation {
	case "query-candidate":
		state, found, err := store.ReadVerifiedCandidate(ctx, identity)
		if err != nil {
			return err
		}
		receipt, err := BuildCreatorReleaseCandidateReceipt(state, found, generatedAt)
		if err != nil {
			return err
		}
		return WriteCreateOnceReport(command.ReportPath, receipt)
	case "readback-at-content-fence":
		pointer, pointerFound, err := readContentActivePointer(ctx, client.Database(command.ContentDatabase), command.Environment, command.SourceOwner)
		if err != nil {
			return err
		}
		state, candidateFound, err := store.ReadVerifiedCandidate(ctx, identity)
		if err != nil {
			return err
		}
		receipt := BuildCreatorFencedReadbackReceipt(command, pointer, pointerFound, state, candidateFound, generatedAt)
		if err := WriteCreateOnceReport(command.ReportPath, receipt); err != nil {
			return err
		}
		if receipt.Status != "passed" {
			return fmt.Errorf("GATE_BLOCK: Creator fenced readback failed: %s", receipt.Reason)
		}
		return nil
	default:
		return fmt.Errorf("unsupported creator release-control operation %q", command.Operation)
	}
}

// WriteCreateOnceReport uses O_EXCL and rejects a symlink destination or any
// symlink directory component. It never creates directories or overwrites.
func WriteCreateOnceReport(path string, report any) error {
	resolved, err := validateCreateOnceDestination(path)
	if err != nil {
		return err
	}
	raw, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("encode Creator release report: %w", err)
	}
	raw = append(raw, '\n')
	file, err := os.OpenFile(resolved, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create Creator release report: %w", err)
	}
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.Remove(resolved)
		}
	}()
	if _, err := file.Write(raw); err != nil {
		_ = file.Close()
		return fmt.Errorf("write Creator release report: %w", err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return fmt.Errorf("sync Creator release report: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close Creator release report: %w", err)
	}
	cleanup = false
	return nil
}

func validateCreateOnceDestination(path string) (string, error) {
	resolved := filepath.Clean(strings.TrimSpace(path))
	if resolved == "." || resolved == string(filepath.Separator) {
		return "", fmt.Errorf("Creator release report path is invalid")
	}
	if _, err := os.Lstat(resolved); err == nil {
		return "", fmt.Errorf("Creator release report already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", fmt.Errorf("inspect Creator release report destination: %w", err)
	}
	parent := filepath.Dir(resolved)
	info, err := os.Lstat(parent)
	if err != nil {
		return "", fmt.Errorf("inspect Creator release report directory: %w", err)
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", fmt.Errorf("Creator release report parent must be a real directory")
	}
	return resolved, nil
}
