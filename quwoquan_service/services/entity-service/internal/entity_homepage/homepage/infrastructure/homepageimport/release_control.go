package homepageimport

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

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

const (
	HomepageFencedReadbackReceiptSchema = "quwoquan.homepage_fenced_readback_receipt"
	contentFenceDatabase                = "quwoquan_content"
)

var sha256DigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type ReleaseControlCommand struct {
	Operation       string
	MongoURI        string
	EntityDB        string
	ContentDB       string
	Environment     string
	SourceOwner     string
	ReleaseID       string
	ManifestDigest  string
	ContentRevision int64
	ReportPath      string
}

func ParseReleaseControlCommand(args []string) (ReleaseControlCommand, error) {
	set := flag.NewFlagSet("homepage-release-control", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command ReleaseControlCommand
	set.StringVar(&command.Operation, "operation", "", "query-candidate|readback-at-content-fence")
	set.StringVar(&command.MongoURI, "mongo-uri", "", "MongoDB connection URI")
	set.StringVar(&command.EntityDB, "entity-db", "quwoquan_entity", "Entity database")
	set.StringVar(&command.ContentDB, "content-db", contentFenceDatabase, "Content owner database holding the active pointer")
	set.StringVar(&command.Environment, "env", "", "exact environment")
	set.StringVar(&command.SourceOwner, "source-owner", "qwq_data", "exact source owner")
	set.StringVar(&command.ReleaseID, "release-id", "", "exact release id")
	set.StringVar(&command.ManifestDigest, "manifest-digest", "", "exact manifest digest")
	set.Int64Var(&command.ContentRevision, "content-revision", 0, "exact Content active pointer revision")
	set.StringVar(&command.ReportPath, "report", "", "create-once receipt path")
	if err := set.Parse(args); err != nil {
		return ReleaseControlCommand{}, err
	}
	if set.NArg() != 0 {
		return ReleaseControlCommand{}, fmt.Errorf("homepage-release-control does not accept positional arguments")
	}
	provided := make(map[string]bool)
	set.Visit(func(item *flag.Flag) { provided[item.Name] = true })
	command.Operation = strings.TrimSpace(command.Operation)
	command.MongoURI = strings.TrimSpace(command.MongoURI)
	command.EntityDB = strings.TrimSpace(command.EntityDB)
	command.ContentDB = strings.TrimSpace(command.ContentDB)
	command.Environment = strings.TrimSpace(command.Environment)
	command.SourceOwner = strings.TrimSpace(command.SourceOwner)
	command.ReleaseID = strings.TrimSpace(command.ReleaseID)
	command.ManifestDigest = strings.TrimSpace(command.ManifestDigest)
	command.ReportPath = strings.TrimSpace(command.ReportPath)
	switch command.Operation {
	case "query-candidate":
		if provided["content-revision"] {
			return ReleaseControlCommand{}, fmt.Errorf("--content-revision is valid only for readback-at-content-fence")
		}
	case "readback-at-content-fence":
		if command.ContentDB == "" || command.ContentRevision <= 0 {
			return ReleaseControlCommand{}, fmt.Errorf("readback-at-content-fence requires --content-db and positive --content-revision")
		}
	default:
		return ReleaseControlCommand{}, fmt.Errorf("--operation must be query-candidate or readback-at-content-fence")
	}
	if command.MongoURI == "" || command.EntityDB == "" || command.ReportPath == "" {
		return ReleaseControlCommand{}, fmt.Errorf("--mongo-uri, --entity-db, and --report are required")
	}
	if _, err := application.NormalizeHomepageReleaseIdentity(application.HomepageReleaseIdentity{
		Environment: command.Environment, SourceOwner: command.SourceOwner,
		ReleaseID: command.ReleaseID, ManifestDigest: command.ManifestDigest,
	}); err != nil {
		return ReleaseControlCommand{}, err
	}
	return command, nil
}

// HomepageFencedReadbackReceipt proves the Homepage verified candidate for the
// exact tuple is readable while Content's active pointer sits on that tuple
// and revision. Identity fields stay top-level so the fence compares directly.
type HomepageFencedReadbackReceipt struct {
	Schema                 string     `json:"schema"`
	Status                 string     `json:"status"`
	Owner                  string     `json:"owner"`
	Environment            string     `json:"environment"`
	SourceOwner            string     `json:"sourceOwner"`
	ReleaseID              string     `json:"releaseId"`
	ManifestDigest         string     `json:"manifestDigest"`
	Revision               int64      `json:"revision"`
	Reason                 string     `json:"reason,omitempty"`
	ContentActivatedAt     *time.Time `json:"contentActivatedAt,omitempty"`
	ProjectionVersion      int64      `json:"projectionVersion,omitempty"`
	VerifiedAt             *time.Time `json:"verifiedAt,omitempty"`
	ClosureDigest          string     `json:"closureDigest,omitempty"`
	ProjectedCount         *int       `json:"projectedCount,omitempty"`
	EntityRefMappingDigest string     `json:"entityRefMappingDigest,omitempty"`
	GeneratedAt            time.Time  `json:"generatedAt"`
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

func BuildHomepageFencedReadbackReceipt(
	command ReleaseControlCommand,
	pointer contentActivePointer,
	pointerFound bool,
	state homepageports.ReleaseCandidateState,
	candidateFound bool,
	generatedAt time.Time,
) HomepageFencedReadbackReceipt {
	receipt := HomepageFencedReadbackReceipt{
		Schema: HomepageFencedReadbackReceiptSchema, Status: "failed", Owner: "homepage",
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
		receipt.Reason = "Homepage verified candidate is absent for the fence tuple"
	case state.ExpectedCount != state.ProjectedCount || state.VerifiedAt.IsZero():
		receipt.Reason = "Homepage candidate for the fence tuple is not verified"
	default:
		activatedAt, verifiedAt := pointer.ActivatedAt.UTC(), state.VerifiedAt.UTC()
		projected := state.ProjectedCount
		receipt.Status = "passed"
		receipt.ContentActivatedAt = &activatedAt
		receipt.ProjectionVersion = state.ProjectionVersion
		receipt.VerifiedAt = &verifiedAt
		receipt.ClosureDigest = state.ClosureDigest
		receipt.ProjectedCount = &projected
		receipt.EntityRefMappingDigest = state.EntityRefMappingDigest
	}
	return receipt
}

func WriteHomepageReleaseCandidateReceipt(path string, receipt any) error {
	path = filepath.Clean(strings.TrimSpace(path))
	if path == "." || path == string(filepath.Separator) {
		return fmt.Errorf("homepage release receipt path is invalid")
	}
	if _, err := os.Lstat(path); err == nil {
		return fmt.Errorf("homepage release receipt already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("inspect homepage release receipt: %w", err)
	}
	parent, err := os.Lstat(filepath.Dir(path))
	if err != nil || !parent.IsDir() || parent.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("homepage release receipt directory must be a non-symlink directory")
	}
	raw, err := json.MarshalIndent(receipt, "", "  ")
	if err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create homepage release receipt: %w", err)
	}
	remove := true
	defer func() {
		_ = file.Close()
		if remove {
			_ = os.Remove(path)
		}
	}()
	if _, err := file.Write(append(raw, '\n')); err != nil {
		return err
	}
	if err := file.Sync(); err != nil {
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	remove = false
	return nil
}

func RunHomepageReleaseControl(ctx context.Context, args []string) error {
	command, err := ParseReleaseControlCommand(args)
	if err != nil {
		return err
	}
	client, err := mongo.Connect(options.Client().ApplyURI(command.MongoURI))
	if err != nil {
		return err
	}
	defer client.Disconnect(context.Background())
	store := persistence.NewMongoHomepageStore(client.Database(command.EntityDB))
	identity := application.HomepageReleaseIdentity{
		Environment: command.Environment, SourceOwner: command.SourceOwner,
		ReleaseID: command.ReleaseID, ManifestDigest: command.ManifestDigest,
	}
	switch command.Operation {
	case "query-candidate":
		service := application.NewHomepageServiceWithStore(ctx, store)
		receipt, err := service.QueryHomepageReleaseCandidate(ctx, identity)
		if err != nil {
			return err
		}
		return WriteHomepageReleaseCandidateReceipt(command.ReportPath, receipt)
	case "readback-at-content-fence":
		pointer, pointerFound, err := readContentActivePointer(
			ctx, client.Database(command.ContentDB), command.Environment, command.SourceOwner,
		)
		if err != nil {
			return err
		}
		state, candidateFound, err := store.ReadVerifiedReleaseCandidate(ctx, identity)
		if err != nil {
			return err
		}
		receipt := BuildHomepageFencedReadbackReceipt(
			command, pointer, pointerFound, state, candidateFound, time.Now().UTC().Truncate(time.Millisecond),
		)
		if err := WriteHomepageReleaseCandidateReceipt(command.ReportPath, receipt); err != nil {
			return err
		}
		if receipt.Status != "passed" {
			return fmt.Errorf("GATE_BLOCK: Homepage fenced readback failed: %s", receipt.Reason)
		}
		return nil
	default:
		return fmt.Errorf("unsupported homepage-release-control operation %q", command.Operation)
	}
}
