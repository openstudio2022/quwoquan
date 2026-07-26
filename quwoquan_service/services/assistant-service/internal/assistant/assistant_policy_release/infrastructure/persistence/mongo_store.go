package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

type MongoStore struct {
	releases *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

type stageReceipt struct {
	ID             string        `bson:"_id"`
	PolicyID       string        `bson:"policyId"`
	ReleaseVersion string        `bson:"releaseVersion"`
	CommandDigest  string        `bson:"commandDigest"`
	Release        model.Release `bson:"release"`
	CreatedAt      time.Time     `bson:"createdAt"`
}

type stageAuditRecord struct {
	ID              string     `bson:"_id"`
	EventType       string     `bson:"eventType"`
	PolicyID        string     `bson:"policyId"`
	ReleaseVersion  string     `bson:"releaseVersion"`
	CanonicalDigest string     `bson:"canonicalDigest"`
	TemplateCount   int        `bson:"templateCount"`
	RuleCount       int        `bson:"ruleCount"`
	OccurredAt      time.Time  `bson:"occurredAt"`
	PublishedAt     *time.Time `bson:"publishedAt,omitempty"`
	PublishedRef    string     `bson:"publishedRef,omitempty"`
	ClaimOwner      string     `bson:"claimOwner,omitempty"`
	ClaimUntil      time.Time  `bson:"claimUntil,omitempty"`
}

type stageAuditPayload struct {
	ID               string    `json:"eventId"`
	EventType        string    `json:"eventType"`
	AggregateType    string    `json:"aggregateType"`
	PolicyID         string    `json:"policyId"`
	AggregateVersion int       `json:"aggregateVersion"`
	ReleaseVersion   string    `json:"releaseVersion,omitempty"`
	CanonicalDigest  string    `json:"canonicalDigest,omitempty"`
	TemplateCount    int       `json:"templateCount,omitempty"`
	RuleCount        int       `json:"ruleCount,omitempty"`
	OccurredAt       time.Time `json:"occurredAt"`
}

const assistantPolicyReleaseOutboxPendingIndex = "idx_assistant_policy_release_outbox_pending"

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		releases: database.Collection("assistant_policy_releases"),
		receipts: database.Collection("assistant_policy_release_receipts"),
		outbox:   database.Collection("assistant_policy_release_outbox"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if store == nil || store.releases == nil ||
		store.receipts == nil || store.outbox == nil {
		return model.ErrStorageUnavailable
	}
	if _, err := store.releases.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "policyId", Value: 1}, {Key: "releaseVersion", Value: 1}},
			Options: options.Index().SetName("uq_assistant_policy_release_identity").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "policyId", Value: 1}, {Key: "canonicalDigest", Value: 1}},
			Options: options.Index().SetName("uq_assistant_policy_release_digest").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("%w: ensure release indexes: %v", model.ErrStorageUnavailable, err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "policyId", Value: 1}, {Key: "releaseVersion", Value: 1}},
		Options: options.Index().SetName("idx_assistant_policy_release_receipt_identity"),
	}); err != nil {
		return fmt.Errorf("%w: ensure receipt index: %v", model.ErrStorageUnavailable, err)
	}
	if err := store.ensureOutboxPendingIndex(ctx); err != nil {
		return fmt.Errorf("%w: ensure outbox indexes: %v", model.ErrStorageUnavailable, err)
	}
	return nil
}

func (store *MongoStore) ensureOutboxPendingIndex(ctx context.Context) error {
	index := mongo.IndexModel{
		Keys:    bson.D{{Key: "publishedAt", Value: 1}, {Key: "occurredAt", Value: 1}},
		Options: options.Index().SetName(assistantPolicyReleaseOutboxPendingIndex),
	}
	_, err := store.outbox.Indexes().CreateOne(ctx, index)
	if err == nil {
		return nil
	}
	var commandErr mongo.CommandError
	if !errors.As(err, &commandErr) || commandErr.Code != 86 {
		return err
	}
	if dropErr := store.outbox.Indexes().DropOne(
		ctx,
		assistantPolicyReleaseOutboxPendingIndex,
	); dropErr != nil {
		return fmt.Errorf("drop obsolete pending index: %w", dropErr)
	}
	if _, createErr := store.outbox.Indexes().CreateOne(ctx, index); createErr != nil {
		return fmt.Errorf("create replacement pending index: %w", createErr)
	}
	return nil
}

func (store *MongoStore) Stage(
	ctx context.Context,
	release model.Release,
	commandID string,
) (model.Release, bool, error) {
	if store == nil || store.releases == nil ||
		store.receipts == nil || store.outbox == nil {
		return model.Release{}, false, model.ErrStorageUnavailable
	}
	commandID = strings.TrimSpace(commandID)
	if commandID == "" {
		return model.Release{}, false, model.ErrInvalidArgument
	}
	session, err := store.releases.Database().Client().StartSession()
	if err != nil {
		return model.Release{}, false, fmt.Errorf("%w: start transaction: %v", model.ErrStorageUnavailable, err)
	}
	defer session.EndSession(ctx)

	var result model.Release
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		created := false
		var receipt stageReceipt
		receiptErr := store.receipts.FindOne(txCtx, bson.M{"_id": commandID}).Decode(&receipt)
		if receiptErr == nil {
			if receipt.CommandDigest != release.CanonicalDigest ||
				receipt.PolicyID != release.PolicyID ||
				receipt.ReleaseVersion != release.ReleaseVersion {
				return nil, model.ErrIdempotencyConflict
			}
			result = receipt.Release
			replayed = true
			return nil, nil
		}
		if !errors.Is(receiptErr, mongo.ErrNoDocuments) {
			return nil, receiptErr
		}

		var existing model.Release
		existingErr := store.releases.FindOne(txCtx, bson.M{
			"policyId":       release.PolicyID,
			"releaseVersion": release.ReleaseVersion,
		}).Decode(&existing)
		switch {
		case existingErr == nil:
			if existing.CanonicalDigest != release.CanonicalDigest {
				return nil, model.ErrIdempotencyConflict
			}
			result = existing
			replayed = true
		case errors.Is(existingErr, mongo.ErrNoDocuments):
			if _, insertErr := store.releases.InsertOne(txCtx, release); insertErr != nil {
				return nil, insertErr
			}
			result = release
			created = true
		default:
			return nil, existingErr
		}
		now := time.Now().UTC()
		_, receiptErr = store.receipts.InsertOne(txCtx, stageReceipt{
			ID:             commandID,
			PolicyID:       result.PolicyID,
			ReleaseVersion: result.ReleaseVersion,
			CommandDigest:  result.CanonicalDigest,
			Release:        result,
			CreatedAt:      now,
		})
		if receiptErr != nil || !created {
			return nil, receiptErr
		}
		_, outboxErr := store.outbox.InsertOne(txCtx, stageAuditRecord{
			ID:              commandID,
			EventType:       "AssistantPolicyReleaseStaged",
			PolicyID:        result.PolicyID,
			ReleaseVersion:  result.ReleaseVersion,
			CanonicalDigest: result.CanonicalDigest,
			TemplateCount:   len(result.Templates),
			RuleCount:       len(result.RoutingRules),
			OccurredAt:      now,
		})
		return nil, outboxErr
	})
	if err != nil {
		if errors.Is(err, model.ErrIdempotencyConflict) {
			return model.Release{}, false, err
		}
		return model.Release{}, false, fmt.Errorf("%w: stage transaction: %v", model.ErrStorageUnavailable, err)
	}
	return result, replayed, nil
}

func (store *MongoStore) Get(
	ctx context.Context,
	policyID string,
	releaseVersion string,
) (model.Release, bool, error) {
	if store == nil || store.releases == nil {
		return model.Release{}, false, model.ErrStorageUnavailable
	}
	var release model.Release
	err := store.releases.FindOne(ctx, bson.M{
		"policyId":       strings.TrimSpace(policyID),
		"releaseVersion": strings.TrimSpace(releaseVersion),
	}).Decode(&release)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Release{}, false, nil
	}
	if err != nil {
		return model.Release{}, false, fmt.Errorf("%w: get release: %v", model.ErrStorageUnavailable, err)
	}
	return release, true, nil
}

func (store *MongoStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]runtimemessaging.LeasedDurableOutboxEvent, error) {
	if store == nil || store.outbox == nil {
		return nil, model.ErrStorageUnavailable
	}
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" || lease <= 0 {
		return nil, model.ErrInvalidArgument
	}
	if limit <= 0 || limit > 512 {
		limit = 128
	}
	events := make([]runtimemessaging.LeasedDurableOutboxEvent, 0, limit)
	for len(events) < limit {
		now := time.Now().UTC()
		var record stageAuditRecord
		err := store.outbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"publishedAt": bson.M{"$exists": false},
				"$or": bson.A{
					bson.M{"claimUntil": bson.M{"$exists": false}},
					bson.M{"claimUntil": bson.M{"$lte": now}},
				},
			},
			bson.M{"$set": bson.M{
				"claimOwner": ownerID,
				"claimUntil": now.Add(lease),
			}},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "occurredAt", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&record)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("%w: claim policy release outbox: %v", model.ErrStorageUnavailable, err)
		}
		payload, err := json.Marshal(stageAuditPayload{
			ID:               record.ID,
			EventType:        record.EventType,
			AggregateType:    "AssistantPolicyRelease",
			PolicyID:         record.PolicyID,
			AggregateVersion: 1,
			ReleaseVersion:   record.ReleaseVersion,
			CanonicalDigest:  record.CanonicalDigest,
			TemplateCount:    record.TemplateCount,
			RuleCount:        record.RuleCount,
			OccurredAt:       record.OccurredAt,
		})
		if err != nil {
			return nil, fmt.Errorf("%w: marshal policy release outbox payload: %v", model.ErrStorageUnavailable, err)
		}
		events = append(events, runtimemessaging.LeasedDurableOutboxEvent{
			ID:               record.ID,
			EventType:        record.EventType,
			AggregateType:    "AssistantPolicyRelease",
			AggregateID:      record.PolicyID,
			AggregateVersion: 1,
			OccurredAt:       record.OccurredAt,
			Payload:          string(payload),
		})
	}
	return events, nil
}

func (store *MongoStore) ReleaseOutboxClaim(
	ctx context.Context,
	eventID string,
	ownerID string,
) error {
	if store == nil || store.outbox == nil {
		return model.ErrStorageUnavailable
	}
	_, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{"$unset": bson.M{"claimOwner": "", "claimUntil": ""}},
	)
	if err != nil {
		return fmt.Errorf("%w: release policy release outbox claim: %v", model.ErrStorageUnavailable, err)
	}
	return nil
}

func (store *MongoStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedRef string,
	publishedAt time.Time,
) error {
	if store == nil || store.outbox == nil {
		return model.ErrStorageUnavailable
	}
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"publishedAt":  publishedAt.UTC(),
				"publishedRef": strings.TrimSpace(publishedRef),
			},
			"$unset": bson.M{"claimOwner": "", "claimUntil": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("%w: mark policy release outbox published: %v", model.ErrStorageUnavailable, err)
	}
	if result.MatchedCount == 0 {
		return fmt.Errorf("%w: policy release outbox claim lost", model.ErrStorageUnavailable)
	}
	return nil
}
