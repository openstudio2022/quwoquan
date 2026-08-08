package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

type MongoStore struct {
	releases    *mongo.Collection
	activations *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
}

type commandReceipt struct {
	ID            string            `bson:"_id"`
	CommandID     string            `bson:"commandId"`
	CommandKind   string            `bson:"commandKind"`
	CommandDigest string            `bson:"commandDigest"`
	PackageID     string            `bson:"packageId"`
	Release       *model.Release    `bson:"release,omitempty"`
	Activation    *model.Activation `bson:"activation,omitempty"`
	CreatedAt     time.Time         `bson:"createdAt"`
}

type activationOutboxRecord struct {
	ID            string    `bson:"_id"`
	EventType     string    `bson:"eventType"`
	PackageID     string    `bson:"packageId"`
	ReleaseDigest string    `bson:"releaseDigest"`
	Revision      int       `bson:"revision"`
	OccurredAt    time.Time `bson:"occurredAt"`
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		releases:    database.Collection("assistant_skill_package_releases"),
		activations: database.Collection("assistant_skill_package_activations"),
		receipts:    database.Collection("assistant_skill_package_command_receipts"),
		outbox:      database.Collection("assistant_skill_package_outbox"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if !store.available() {
		return model.ErrReleaseNotFound
	}
	if _, err := store.releases.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "packageId", Value: 1},
				{Key: "releaseDigest", Value: 1},
			},
			Options: options.Index().
				SetName("uq_assistant_skill_package_release_identity").
				SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("ensure skill package release indexes: %w", err)
	}
	if _, err := store.activations.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "packageId", Value: 1}},
		Options: options.Index().
			SetName("uq_assistant_skill_package_activation").
			SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure skill package activation index: %w", err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "commandId", Value: 1}},
		Options: options.Index().
			SetName("uq_assistant_skill_package_command_receipt").
			SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure skill package receipt index: %w", err)
	}
	if _, err := store.outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "packageId", Value: 1},
			{Key: "revision", Value: 1},
		},
		Options: options.Index().
			SetName("uq_assistant_skill_package_outbox_revision").
			SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure skill package outbox index: %w", err)
	}
	return nil
}

func (store *MongoStore) GetRelease(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (model.Release, bool, error) {
	if !store.available() {
		return model.Release{}, false, model.ErrReleaseNotFound
	}
	var release model.Release
	err := store.releases.FindOne(ctx, bson.M{
		"packageId":     strings.TrimSpace(packageID),
		"releaseDigest": strings.TrimSpace(releaseDigest),
	}).Decode(&release)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Release{}, false, nil
	}
	if err != nil {
		return model.Release{}, false, fmt.Errorf("get skill package release: %w", err)
	}
	return release, true, nil
}

func (store *MongoStore) Stage(
	ctx context.Context,
	commandID string,
	commandDigest string,
	release model.Release,
) (model.Release, bool, error) {
	commandID = strings.TrimSpace(commandID)
	commandDigest = strings.TrimSpace(commandDigest)
	if !store.available() || commandID == "" || commandDigest == "" {
		return model.Release{}, false, model.ErrInvalidRelease
	}
	session, err := store.releases.Database().Client().StartSession()
	if err != nil {
		return model.Release{}, false, fmt.Errorf("start skill package stage transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var stored model.Release
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, found, readErr := store.readReceipt(txCtx, commandID)
		if readErr != nil {
			return nil, readErr
		}
		if found {
			if receipt.CommandKind != "stage" ||
				receipt.CommandDigest != commandDigest ||
				receipt.PackageID != release.PackageID ||
				receipt.Release == nil {
				return nil, model.ErrInvalidRelease
			}
			stored = *receipt.Release
			replayed = true
			return nil, nil
		}

		existing, found, readErr := store.GetRelease(
			txCtx,
			release.PackageID,
			release.ReleaseDigest,
		)
		if readErr != nil {
			return nil, readErr
		}
		if found {
			stored = existing
			replayed = true
		} else {
			if _, insertErr := store.releases.InsertOne(txCtx, release); insertErr != nil {
				return nil, insertErr
			}
			stored = release
		}
		_, insertErr := store.receipts.InsertOne(txCtx, commandReceipt{
			ID:            commandID,
			CommandID:     commandID,
			CommandKind:   "stage",
			CommandDigest: commandDigest,
			PackageID:     release.PackageID,
			Release:       &stored,
			CreatedAt:     time.Now().UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if errors.Is(err, model.ErrInvalidRelease) {
			return model.Release{}, false, err
		}
		return model.Release{}, false, fmt.Errorf("commit skill package stage: %w", err)
	}
	return stored, replayed, nil
}

func (store *MongoStore) GetActivation(
	ctx context.Context,
	packageID string,
) (model.Activation, bool, error) {
	if !store.available() {
		return model.Activation{}, false, model.ErrActivationAbsent
	}
	var activation model.Activation
	err := store.activations.FindOne(ctx, bson.M{
		"packageId": strings.TrimSpace(packageID),
	}).Decode(&activation)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Activation{}, false, nil
	}
	if err != nil {
		return model.Activation{}, false, fmt.Errorf("get skill package activation: %w", err)
	}
	return activation, true, nil
}

func (store *MongoStore) GetCommandResult(
	ctx context.Context,
	commandID string,
	commandDigest string,
	packageID string,
) (model.Activation, bool, error) {
	receipt, found, err := store.readReceipt(ctx, strings.TrimSpace(commandID))
	if err != nil || !found {
		return model.Activation{}, false, err
	}
	if receipt.CommandDigest != strings.TrimSpace(commandDigest) ||
		receipt.PackageID != strings.TrimSpace(packageID) ||
		receipt.Activation == nil {
		return model.Activation{}, false, model.ErrInvalidRelease
	}
	return *receipt.Activation, true, nil
}

func (store *MongoStore) CommitActivation(
	ctx context.Context,
	commandID string,
	commandDigest string,
	expectedRevision int,
	next model.Activation,
	eventType string,
) (model.Activation, bool, error) {
	commandID = strings.TrimSpace(commandID)
	commandDigest = strings.TrimSpace(commandDigest)
	eventType = strings.TrimSpace(eventType)
	if !store.available() || commandID == "" || commandDigest == "" ||
		expectedRevision < 0 || eventType == "" {
		return model.Activation{}, false, model.ErrInvalidRelease
	}
	session, err := store.activations.Database().Client().StartSession()
	if err != nil {
		return model.Activation{}, false, fmt.Errorf("start skill package activation transaction: %w", err)
	}
	defer session.EndSession(ctx)

	stored := model.Activation{}
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, found, readErr := store.readReceipt(txCtx, commandID)
		if readErr != nil {
			return nil, readErr
		}
		if found {
			if receipt.CommandDigest != commandDigest ||
				receipt.PackageID != next.PackageID ||
				receipt.Activation == nil {
				return nil, model.ErrInvalidRelease
			}
			stored = *receipt.Activation
			replayed = true
			return nil, nil
		}
		current, currentFound, readErr := store.GetActivation(txCtx, next.PackageID)
		if readErr != nil {
			return nil, readErr
		}
		if (!currentFound && expectedRevision != 0) ||
			(currentFound && current.Revision != expectedRevision) {
			return nil, model.ErrRevisionConflict
		}
		if !currentFound {
			if _, insertErr := store.activations.InsertOne(txCtx, next); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, model.ErrRevisionConflict
				}
				return nil, insertErr
			}
		} else {
			update, updateErr := store.activations.UpdateOne(
				txCtx,
				bson.M{
					"packageId": next.PackageID,
					"revision":  expectedRevision,
				},
				bson.M{"$set": next},
			)
			if updateErr != nil {
				return nil, updateErr
			}
			if update.MatchedCount != 1 {
				return nil, model.ErrRevisionConflict
			}
		}
		if _, updateErr := store.releases.UpdateMany(
			txCtx,
			bson.M{"packageId": next.PackageID, "status": model.StatusActive},
			bson.M{"$set": bson.M{"status": model.StatusRetired}},
		); updateErr != nil {
			return nil, updateErr
		}
		releaseUpdate, updateErr := store.releases.UpdateOne(
			txCtx,
			bson.M{
				"packageId":     next.PackageID,
				"releaseDigest": next.ActiveReleaseDigest,
			},
			bson.M{"$set": bson.M{
				"status":      model.StatusActive,
				"activatedAt": next.ActivatedAt,
			}},
		)
		if updateErr != nil {
			return nil, updateErr
		}
		if releaseUpdate.MatchedCount != 1 {
			return nil, model.ErrReleaseNotFound
		}
		stored = next
		if _, insertErr := store.receipts.InsertOne(txCtx, commandReceipt{
			ID:            commandID,
			CommandID:     commandID,
			CommandKind:   eventType,
			CommandDigest: commandDigest,
			PackageID:     next.PackageID,
			Activation:    &stored,
			CreatedAt:     next.ActivatedAt,
		}); insertErr != nil {
			return nil, insertErr
		}
		_, insertErr := store.outbox.InsertOne(txCtx, activationOutboxRecord{
			ID:            fmt.Sprintf("%s:%d", next.PackageID, next.Revision),
			EventType:     eventType,
			PackageID:     next.PackageID,
			ReleaseDigest: next.ActiveReleaseDigest,
			Revision:      next.Revision,
			OccurredAt:    next.ActivatedAt,
		})
		return nil, insertErr
	})
	if err != nil {
		switch {
		case errors.Is(err, model.ErrInvalidRelease),
			errors.Is(err, model.ErrRevisionConflict),
			errors.Is(err, model.ErrReleaseNotFound):
			return model.Activation{}, false, err
		default:
			return model.Activation{}, false, fmt.Errorf(
				"commit skill package activation: %w",
				err,
			)
		}
	}
	return stored, replayed, nil
}

func (store *MongoStore) readReceipt(
	ctx context.Context,
	commandID string,
) (commandReceipt, bool, error) {
	if !store.available() {
		return commandReceipt{}, false, model.ErrReleaseNotFound
	}
	var receipt commandReceipt
	err := store.receipts.FindOne(ctx, bson.M{
		"_id": strings.TrimSpace(commandID),
	}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return commandReceipt{}, false, nil
	}
	if err != nil {
		return commandReceipt{}, false, fmt.Errorf(
			"get skill package command receipt: %w",
			err,
		)
	}
	return receipt, true, nil
}

func (store *MongoStore) available() bool {
	return store != nil && store.releases != nil && store.activations != nil &&
		store.receipts != nil && store.outbox != nil
}
