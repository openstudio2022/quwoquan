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

const filterCatalogTransactionAttempts = 3

func (store *MongoStore) Stage(
	ctx context.Context,
	commit filtercatalogports.StageCommit,
) (filtercatalogports.CommandResult, error) {
	if err := validateStageCommit(commit); err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	for attempt := 0; attempt < filterCatalogTransactionAttempts; attempt++ {
		result, err := store.stageOnce(ctx, commit)
		if err == nil {
			return result, nil
		}
		if !mongo.IsDuplicateKeyError(err) ||
			attempt == filterCatalogTransactionAttempts-1 {
			return filtercatalogports.CommandResult{}, err
		}
	}
	panic("unreachable FilterCatalogRelease Stage retry")
}

func (store *MongoStore) stageOnce(
	ctx context.Context,
	commit filtercatalogports.StageCommit,
) (filtercatalogports.CommandResult, error) {
	session, err := store.releases.Database().Client().StartSession()
	if err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	defer session.EndSession(ctx)

	var committed filtercatalogports.CommandResult
	now := time.Now().UTC()
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, found, receiptErr := store.findReceipt(
			txCtx,
			commit.IdempotencyKey,
			filtercatalogports.CommandStageFilterCatalogRelease,
			commit.CommandDigest,
			now,
		)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if found {
			committed = replayed
			return nil, nil
		}

		snapshot := commit.Release.Snapshot()
		existingDocument, digestFound, findDigestErr := store.loadDocument(
			txCtx,
			bson.M{"canonicalDigest": snapshot.CanonicalDigest},
		)
		if findDigestErr != nil {
			return nil, findDigestErr
		}
		if digestFound {
			existing, restoreErr := existingDocument.release()
			if restoreErr != nil {
				return nil, restoreErr
			}
			if receiptErr := store.insertReceipt(
				txCtx,
				commit.IdempotencyKey,
				filtercatalogports.CommandStageFilterCatalogRelease,
				commit.CommandDigest,
				existing,
				false,
				now,
				commit.ReceiptExpiresAt,
			); receiptErr != nil {
				return nil, receiptErr
			}
			committed = filtercatalogports.CommandResult{
				Release:  existing,
				Changed:  false,
				Replayed: true,
			}
			return nil, nil
		}

		_, releaseIDFound, findReleaseErr := store.loadDocument(
			txCtx,
			bson.M{"releaseId": snapshot.ReleaseID},
		)
		if findReleaseErr != nil {
			return nil, findReleaseErr
		}
		if releaseIDFound {
			return nil, fmt.Errorf(
				"%w: releaseId %q already binds another catalog",
				model.ErrIdempotencyConflict,
				snapshot.ReleaseID,
			)
		}
		if _, insertErr := store.releases.InsertOne(
			txCtx,
			filterCatalogDocumentFromRelease(commit.Release),
		); insertErr != nil {
			return nil, insertErr
		}
		if receiptErr := store.insertReceipt(
			txCtx,
			commit.IdempotencyKey,
			filtercatalogports.CommandStageFilterCatalogRelease,
			commit.CommandDigest,
			commit.Release,
			true,
			now,
			commit.ReceiptExpiresAt,
		); receiptErr != nil {
			return nil, receiptErr
		}
		committed = filtercatalogports.CommandResult{
			Release: commit.Release,
			Changed: true,
		}
		return nil, nil
	})
	if err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	return committed, nil
}

func validateStageCommit(commit filtercatalogports.StageCommit) error {
	if commit.Release == nil ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" ||
		commit.ReceiptExpiresAt.IsZero() {
		return fmt.Errorf("%w: incomplete Stage commit", model.ErrInvalidArgument)
	}
	if commit.Release.Status() != model.StatusStaged ||
		commit.Release.Version() != 1 {
		return fmt.Errorf(
			"%w: Stage requires a new staged release",
			model.ErrInvalidTransition,
		)
	}
	return nil
}
