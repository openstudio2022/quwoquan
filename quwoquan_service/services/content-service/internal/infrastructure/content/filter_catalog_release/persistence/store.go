package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
	filtercatalogports "quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/ports"
)

type MongoStore struct {
	releases *mongo.Collection
	receipts *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("FilterCatalogRelease Mongo database is required")
	}
	return &MongoStore{
		releases: database.Collection(filterCatalogReleaseCollection),
		receipts: database.Collection(filterCatalogReceiptCollection),
	}
}

func (store *MongoStore) Load(
	ctx context.Context,
	releaseID string,
) (*model.FilterCatalogRelease, bool, error) {
	document, found, err := store.loadDocument(
		ctx,
		bson.M{"releaseId": strings.TrimSpace(releaseID)},
	)
	if err != nil || !found {
		return nil, found, err
	}
	release, err := document.release()
	if err != nil {
		return nil, false, fmt.Errorf("restore FilterCatalogRelease: %w", err)
	}
	return release, true, nil
}

func (store *MongoStore) GetActive(
	ctx context.Context,
) (*model.FilterCatalogRelease, bool, error) {
	document, found, err := store.loadDocument(
		ctx,
		bson.M{"status": string(model.StatusActive)},
	)
	if err != nil || !found {
		return nil, found, err
	}
	release, err := document.release()
	if err != nil {
		return nil, false, fmt.Errorf("restore active FilterCatalogRelease: %w", err)
	}
	return release, true, nil
}

func (store *MongoStore) loadDocument(
	ctx context.Context,
	filter any,
) (filterCatalogReleaseDocument, bool, error) {
	var document filterCatalogReleaseDocument
	err := store.releases.FindOne(ctx, filter).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return filterCatalogReleaseDocument{}, false, nil
	}
	if err != nil {
		return filterCatalogReleaseDocument{}, false, err
	}
	return document, true, nil
}

func (store *MongoStore) findReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
	now time.Time,
) (filtercatalogports.CommandResult, bool, error) {
	var receipt filterCatalogReceiptDocument
	err := store.receipts.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(idempotencyKey)},
	).Decode(&receipt)
	if err == mongo.ErrNoDocuments {
		return filtercatalogports.CommandResult{}, false, nil
	}
	if err != nil {
		return filtercatalogports.CommandResult{}, false, err
	}
	if !receipt.ExpiresAt.After(now) {
		if _, deleteErr := store.receipts.DeleteOne(
			ctx,
			bson.M{"_id": receipt.ID},
		); deleteErr != nil {
			return filtercatalogports.CommandResult{}, false, deleteErr
		}
		return filtercatalogports.CommandResult{}, false, nil
	}
	if receipt.CommandName != commandName ||
		receipt.CommandDigest != commandDigest {
		return filtercatalogports.CommandResult{},
			false,
			fmt.Errorf(
				"%w: receipt %q command payload differs",
				model.ErrIdempotencyConflict,
				receipt.ID,
			)
	}
	release, restoreErr := receipt.Result.release()
	if restoreErr != nil {
		return filtercatalogports.CommandResult{}, false, restoreErr
	}
	return filtercatalogports.CommandResult{
		Release:  release,
		Changed:  receipt.Changed,
		Replayed: true,
	}, true, nil
}

func (store *MongoStore) insertReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
	release *model.FilterCatalogRelease,
	changed bool,
	createdAt time.Time,
	expiresAt time.Time,
) error {
	snapshot := release.Snapshot()
	_, err := store.receipts.InsertOne(ctx, filterCatalogReceiptDocument{
		ID:               strings.TrimSpace(idempotencyKey),
		AggregateID:      snapshot.ReleaseID,
		AggregateVersion: snapshot.Version,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		Result:           filterCatalogDocumentFromRelease(release),
		Changed:          changed,
		CreatedAt:        normalizeDocumentTime(createdAt),
		ExpiresAt:        normalizeDocumentTime(expiresAt),
	})
	return err
}

func normalizeDocumentTime(value time.Time) time.Time {
	return value.UTC().Truncate(time.Millisecond)
}

var _ filtercatalogports.AggregateStore = (*MongoStore)(nil)
var _ filtercatalogports.ActiveFilterCatalogReader = (*MongoStore)(nil)
