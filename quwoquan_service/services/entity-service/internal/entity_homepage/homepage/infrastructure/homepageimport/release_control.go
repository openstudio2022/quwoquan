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
	"strings"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

type ReleaseControlCommand struct {
	Operation      string
	MongoURI       string
	EntityDB       string
	Environment    string
	SourceOwner    string
	ReleaseID      string
	ManifestDigest string
	ReportPath     string
}

func ParseReleaseControlCommand(args []string) (ReleaseControlCommand, error) {
	set := flag.NewFlagSet("homepage-release-control", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command ReleaseControlCommand
	set.StringVar(&command.Operation, "operation", "", "query-candidate")
	set.StringVar(&command.MongoURI, "mongo-uri", "", "MongoDB connection URI")
	set.StringVar(&command.EntityDB, "entity-db", "quwoquan_entity", "Entity database")
	set.StringVar(&command.Environment, "env", "", "exact environment")
	set.StringVar(&command.SourceOwner, "source-owner", "qwq_data", "exact source owner")
	set.StringVar(&command.ReleaseID, "release-id", "", "exact release id")
	set.StringVar(&command.ManifestDigest, "manifest-digest", "", "exact manifest digest")
	set.StringVar(&command.ReportPath, "report", "", "create-once receipt path")
	if err := set.Parse(args); err != nil {
		return ReleaseControlCommand{}, err
	}
	if set.NArg() != 0 {
		return ReleaseControlCommand{}, fmt.Errorf("homepage-release-control does not accept positional arguments")
	}
	command.Operation = strings.TrimSpace(command.Operation)
	command.MongoURI = strings.TrimSpace(command.MongoURI)
	command.EntityDB = strings.TrimSpace(command.EntityDB)
	command.Environment = strings.TrimSpace(command.Environment)
	command.SourceOwner = strings.TrimSpace(command.SourceOwner)
	command.ReleaseID = strings.TrimSpace(command.ReleaseID)
	command.ManifestDigest = strings.TrimSpace(command.ManifestDigest)
	command.ReportPath = strings.TrimSpace(command.ReportPath)
	if command.Operation != "query-candidate" {
		return ReleaseControlCommand{}, fmt.Errorf("--operation must be query-candidate")
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

func WriteHomepageReleaseCandidateReceipt(path string, receipt application.HomepageReleaseCandidateReceipt) error {
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
	service := application.NewHomepageServiceWithStore(ctx, store)
	receipt, err := service.QueryHomepageReleaseCandidate(ctx, application.HomepageReleaseIdentity{
		Environment: command.Environment, SourceOwner: command.SourceOwner,
		ReleaseID: command.ReleaseID, ManifestDigest: command.ManifestDigest,
	})
	if err != nil {
		return err
	}
	return WriteHomepageReleaseCandidateReceipt(command.ReportPath, receipt)
}
