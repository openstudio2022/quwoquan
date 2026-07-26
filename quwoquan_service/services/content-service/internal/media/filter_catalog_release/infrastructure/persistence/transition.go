package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
	filtercatalogports "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/ports"
)

type filterCatalogTransition string

const (
	filterCatalogActivate filterCatalogTransition = "activate"
	filterCatalogRollback filterCatalogTransition = "rollback"
)

func (store *MongoStore) Activate(
	ctx context.Context,
	commit filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	return store.transition(ctx, filterCatalogActivate, commit)
}

func (store *MongoStore) Rollback(
	ctx context.Context,
	commit filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	return store.transition(ctx, filterCatalogRollback, commit)
}

func (store *MongoStore) transition(
	ctx context.Context,
	transition filterCatalogTransition,
	commit filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	if err := validateTransitionCommit(commit); err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	for attempt := 0; attempt < filterCatalogTransactionAttempts; attempt++ {
		result, err := store.transitionOnce(ctx, transition, commit)
		if err == nil {
			return result, nil
		}
		if (!errors.Is(err, model.ErrVersionConflict) &&
			!mongo.IsDuplicateKeyError(err)) ||
			attempt == filterCatalogTransactionAttempts-1 {
			return filtercatalogports.CommandResult{}, err
		}
	}
	panic("unreachable FilterCatalogRelease transition retry")
}

func (store *MongoStore) transitionOnce(
	ctx context.Context,
	transition filterCatalogTransition,
	commit filtercatalogports.TransitionCommit,
) (filtercatalogports.CommandResult, error) {
	commandName := filterCatalogTransitionCommandName(transition)
	session, err := store.releases.Database().Client().StartSession()
	if err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	defer session.EndSession(ctx)

	var committed filtercatalogports.CommandResult
	now := time.Now().UTC()
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, receiptFound, receiptErr := store.findReceipt(
			txCtx,
			commit.IdempotencyKey,
			commandName,
			commit.CommandDigest,
			now,
		)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if receiptFound {
			committed = replayed
			return nil, nil
		}

		targetDocument, targetFound, targetErr := store.loadDocument(
			txCtx,
			bson.M{"releaseId": commit.ReleaseID},
		)
		if targetErr != nil {
			return nil, targetErr
		}
		if !targetFound {
			return nil, fmt.Errorf(
				"%w: releaseId %q",
				model.ErrReleaseNotFound,
				commit.ReleaseID,
			)
		}
		target, restoreErr := targetDocument.release()
		if restoreErr != nil {
			return nil, restoreErr
		}
		if target.Status() == model.StatusActive {
			if receiptErr := store.insertReceipt(
				txCtx,
				commit.IdempotencyKey,
				commandName,
				commit.CommandDigest,
				target,
				false,
				now,
				commit.ReceiptExpiresAt,
			); receiptErr != nil {
				return nil, receiptErr
			}
			committed = filtercatalogports.CommandResult{
				Release: target,
				Changed: false,
			}
			return nil, nil
		}

		targetExpectedVersion := target.Version()
		switch transition {
		case filterCatalogActivate:
			if activateErr := target.Activate(commit.TransitionedAt); activateErr != nil {
				return nil, activateErr
			}
		case filterCatalogRollback:
			if rollbackErr := target.Rollback(commit.TransitionedAt); rollbackErr != nil {
				return nil, rollbackErr
			}
		default:
			return nil, fmt.Errorf("unsupported filter catalog transition %q", transition)
		}

		activeDocument, activeFound, activeErr := store.loadDocument(
			txCtx,
			bson.M{"status": string(model.StatusActive)},
		)
		if activeErr != nil {
			return nil, activeErr
		}
		if transition == filterCatalogRollback && !activeFound {
			return nil, fmt.Errorf(
				"%w: rollback requires a current active release",
				model.ErrInvalidTransition,
			)
		}
		if activeFound {
			active, activeRestoreErr := activeDocument.release()
			if activeRestoreErr != nil {
				return nil, activeRestoreErr
			}
			activeExpectedVersion := active.Version()
			if retireErr := active.Retire(); retireErr != nil {
				return nil, retireErr
			}
			retired, replaceErr := store.releases.ReplaceOne(
				txCtx,
				bson.M{
					"releaseId": active.ID(),
					"version":   activeExpectedVersion,
					"status":    string(model.StatusActive),
				},
				filterCatalogDocumentFromRelease(active),
			)
			if replaceErr != nil {
				return nil, replaceErr
			}
			if retired.MatchedCount != 1 {
				return nil, model.ErrVersionConflict
			}
		}

		activated, replaceErr := store.releases.ReplaceOne(
			txCtx,
			bson.M{
				"releaseId": target.ID(),
				"version":   targetExpectedVersion,
				"status":    targetDocument.Status,
			},
			filterCatalogDocumentFromRelease(target),
		)
		if replaceErr != nil {
			return nil, replaceErr
		}
		if activated.MatchedCount != 1 {
			return nil, model.ErrVersionConflict
		}
		if receiptErr := store.insertReceipt(
			txCtx,
			commit.IdempotencyKey,
			commandName,
			commit.CommandDigest,
			target,
			true,
			now,
			commit.ReceiptExpiresAt,
		); receiptErr != nil {
			return nil, receiptErr
		}
		committed = filtercatalogports.CommandResult{
			Release: target,
			Changed: true,
		}
		return nil, nil
	})
	if err != nil {
		return filtercatalogports.CommandResult{}, err
	}
	return committed, nil
}

func filterCatalogTransitionCommandName(transition filterCatalogTransition) string {
	switch transition {
	case filterCatalogActivate:
		return filtercatalogports.CommandActivateFilterCatalogRelease
	case filterCatalogRollback:
		return filtercatalogports.CommandRollbackFilterCatalogRelease
	default:
		return ""
	}
}

func validateTransitionCommit(commit filtercatalogports.TransitionCommit) error {
	if strings.TrimSpace(commit.ReleaseID) == "" ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" ||
		commit.TransitionedAt.IsZero() ||
		commit.ReceiptExpiresAt.IsZero() {
		return fmt.Errorf(
			"%w: incomplete FilterCatalogRelease transition commit",
			model.ErrInvalidArgument,
		)
	}
	return nil
}
