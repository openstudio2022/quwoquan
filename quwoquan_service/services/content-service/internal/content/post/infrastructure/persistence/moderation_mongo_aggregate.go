package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
	moderationports "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/ports"
)

type postModerationCaseDocument struct {
	ID             string                 `bson:"_id"`
	Version        int64                  `bson:"version"`
	PostID         string                 `bson:"postId"`
	PostVersion    int64                  `bson:"postVersion"`
	ContentDigest  string                 `bson:"contentDigest"`
	Status         moderationmodel.Status `bson:"status"`
	ReviewerID     string                 `bson:"reviewerId,omitempty"`
	DecisionReason string                 `bson:"decisionReason,omitempty"`
	CreatedAt      time.Time              `bson:"createdAt"`
	UpdatedAt      time.Time              `bson:"updatedAt"`
	DecidedAt      *time.Time             `bson:"decidedAt,omitempty"`
}

type postModerationReceiptDocument struct {
	ID               string                     `bson:"_id"`
	AggregateID      string                     `bson:"aggregateId"`
	AggregateVersion int64                      `bson:"aggregateVersion"`
	CommandName      string                     `bson:"commandName"`
	CommandDigest    string                     `bson:"commandDigest"`
	Result           postModerationCaseDocument `bson:"result"`
	CreatedAt        time.Time                  `bson:"createdAt"`
	ExpiresAt        time.Time                  `bson:"expiresAt"`
}

type postModerationOutboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

type postModerationAuditDocument struct {
	ID             string                      `bson:"_id"`
	CaseID         string                      `bson:"caseId"`
	CaseVersion    int64                       `bson:"caseVersion"`
	PostID         string                      `bson:"postId"`
	PostVersion    int64                       `bson:"postVersion"`
	ContentDigest  string                      `bson:"contentDigest"`
	ReviewerID     string                      `bson:"reviewerId,omitempty"`
	Action         moderationports.AuditAction `bson:"action"`
	DecisionReason string                      `bson:"decisionReason,omitempty"`
	OccurredAt     time.Time                   `bson:"occurredAt"`
}

func (s *MongoPostModerationCaseStore) Load(
	ctx context.Context,
	caseID string,
) (*moderationmodel.PostModerationCase, bool, error) {
	var document postModerationCaseDocument
	err := s.cases.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(caseID)}},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load post moderation case: %w", err)
	}
	caseItem, err := moderationCaseFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return caseItem, true, nil
}

func (s *MongoPostModerationCaseStore) LoadByPostRevision(
	ctx context.Context,
	postID string,
	postVersion int64,
	contentDigest string,
) (*moderationmodel.PostModerationCase, bool, error) {
	var document postModerationCaseDocument
	err := s.cases.FindOne(
		ctx,
		bson.D{
			{Key: "postId", Value: strings.TrimSpace(postID)},
			{Key: "postVersion", Value: postVersion},
			{Key: "contentDigest", Value: normalizeModerationDigest(contentDigest)},
		},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load post moderation case revision: %w", err)
	}
	caseItem, err := moderationCaseFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return caseItem, true, nil
}

func (s *MongoPostModerationCaseStore) FindReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (moderationports.CommitResult, bool, error) {
	var receipt postModerationReceiptDocument
	err := s.receipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return moderationports.CommitResult{}, false, nil
	}
	if err != nil {
		return moderationports.CommitResult{}, false, fmt.Errorf("find post moderation receipt: %w", err)
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		return moderationports.CommitResult{}, false, nil
	}
	if err := validateModerationReceipt(
		receipt.CommandName,
		receipt.CommandDigest,
		commandName,
		commandDigest,
	); err != nil {
		return moderationports.CommitResult{}, false, err
	}
	caseItem, err := moderationCaseFromDocument(receipt.Result)
	if err != nil {
		return moderationports.CommitResult{}, false, err
	}
	return moderationports.CommitResult{
		Aggregate: caseItem,
		Replayed:  true,
	}, true, nil
}

func (s *MongoPostModerationCaseStore) Commit(
	ctx context.Context,
	commit moderationports.Commit,
) (moderationports.CommitResult, error) {
	if err := validateModerationCommit(commit); err != nil {
		return moderationports.CommitResult{}, err
	}
	session, err := s.cases.Database().Client().StartSession()
	if err != nil {
		return moderationports.CommitResult{}, fmt.Errorf("start moderation transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var result moderationports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, found, err := s.findReceiptTx(
			txCtx,
			commit.IdempotencyKey,
			commit.CommandName,
			commit.CommandDigest,
		)
		if err != nil {
			return nil, err
		}
		if found {
			result = replayed
			return nil, nil
		}

		next := moderationCaseDocumentFromAggregate(commit.Aggregate)
		if err := s.writeCaseVersion(txCtx, next, commit.ExpectedVersion); err != nil {
			return nil, err
		}
		if err := s.writeAudit(txCtx, commit.Audit); err != nil {
			return nil, err
		}
		if err := s.writeOutbox(txCtx, commit.Events); err != nil {
			return nil, err
		}
		expiresAt := commit.ReceiptExpiresAt.UTC()
		if expiresAt.IsZero() {
			expiresAt = time.Now().UTC().Add(24 * time.Hour)
		}
		if _, err := s.receipts.InsertOne(txCtx, postModerationReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      next.ID,
			AggregateVersion: next.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           next,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        expiresAt,
		}); err != nil {
			return nil, err
		}
		persisted, err := moderationCaseFromDocument(next)
		if err != nil {
			return nil, err
		}
		result = moderationports.CommitResult{Aggregate: persisted}
		return nil, nil
	})
	if err != nil {
		return moderationports.CommitResult{}, err
	}
	return result, nil
}

func (s *MongoPostModerationCaseStore) writeCaseVersion(
	ctx context.Context,
	next postModerationCaseDocument,
	expectedVersion int64,
) error {
	if expectedVersion == 0 {
		if _, err := s.cases.InsertOne(ctx, next); err != nil {
			return err
		}
		return nil
	}
	result, err := s.cases.ReplaceOne(
		ctx,
		bson.D{
			{Key: "_id", Value: next.ID},
			{Key: "version", Value: expectedVersion},
		},
		next,
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"post moderation case version changed before commit",
		)
	}
	return nil
}

func (s *MongoPostModerationCaseStore) writeAudit(
	ctx context.Context,
	entry moderationports.AuditEntry,
) error {
	if _, err := s.audit.InsertOne(ctx, postModerationAuditDocument{
		ID:             moderationAuditDocumentID(entry),
		CaseID:         entry.CaseID,
		CaseVersion:    entry.CaseVersion,
		PostID:         entry.PostID,
		PostVersion:    entry.PostVersion,
		ContentDigest:  entry.ContentDigest,
		ReviewerID:     entry.ReviewerID,
		Action:         entry.Action,
		DecisionReason: entry.DecisionReason,
		OccurredAt:     entry.OccurredAt.UTC(),
	}); err != nil {
		return err
	}
	return nil
}

func (s *MongoPostModerationCaseStore) writeOutbox(
	ctx context.Context,
	events []moderationports.OutboxEvent,
) error {
	for _, event := range events {
		if _, err := s.outbox.InsertOne(ctx, postModerationOutboxDocument{
			ID:               event.EventID,
			EventType:        event.EventType,
			AggregateID:      event.AggregateID,
			AggregateVersion: event.AggregateVersion,
			Payload:          append([]byte(nil), event.Payload...),
			OccurredAt:       event.OccurredAt.UTC(),
		}); err != nil {
			return err
		}
	}
	return nil
}
