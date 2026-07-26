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

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
	moderationports "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/ports"
)

func (s *MongoPostModerationCaseStore) GetPublicationEligibility(
	ctx context.Context,
	query moderationports.PublicationEligibilityQuery,
) (moderationports.PublicationEligibility, error) {
	now := time.Now().UTC()
	var document postModerationCaseDocument
	err := s.cases.FindOne(
		ctx,
		bson.D{
			{Key: "postId", Value: strings.TrimSpace(query.PostID)},
			{Key: "postVersion", Value: query.PostVersion},
			{Key: "contentDigest", Value: normalizeModerationDigest(query.ContentDigest)},
		},
		options.FindOne().SetProjection(bson.D{
			{Key: "_id", Value: 1},
			{Key: "version", Value: 1},
			{Key: "status", Value: 1},
			{Key: "decidedAt", Value: 1},
		}),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return moderationports.PublicationEligibility{
			Eligible:      false,
			CheckedAt:     now,
			FailureReason: "moderation_approval_required",
		}, nil
	}
	if err != nil {
		return moderationports.PublicationEligibility{}, fmt.Errorf(
			"read post publication eligibility: %w",
			err,
		)
	}
	eligible := document.Status == moderationmodel.StatusApproved
	failureReason := ""
	if !eligible {
		failureReason = "moderation_approval_required"
	}
	return moderationports.PublicationEligibility{
		Eligible:      eligible,
		CaseID:        document.ID,
		CaseVersion:   document.Version,
		Moderation:    document.Status,
		CheckedAt:     now,
		DecisionAt:    cloneModerationTime(document.DecidedAt),
		FailureReason: failureReason,
	}, nil
}

func (s *MongoPostModerationCaseStore) FindCurrentByPostID(
	ctx context.Context,
	postID string,
) (moderationapp.PostModerationCaseOpsSlice, bool, error) {
	var document postModerationCaseDocument
	err := s.cases.FindOne(
		ctx,
		bson.D{
			{Key: "postId", Value: strings.TrimSpace(postID)},
			{Key: "status", Value: bson.D{{Key: "$ne", Value: moderationmodel.StatusSuperseded}}},
		},
		options.FindOne().SetSort(
			bson.D{
				{Key: "postVersion", Value: -1},
				{Key: "updatedAt", Value: -1},
				{Key: "_id", Value: -1},
			},
		),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return moderationapp.PostModerationCaseOpsSlice{}, false, nil
	}
	if err != nil {
		return moderationapp.PostModerationCaseOpsSlice{}, false, fmt.Errorf(
			"read current post moderation case: %w",
			err,
		)
	}
	return moderationapp.PostModerationCaseOpsSlice{
		ID:             document.ID,
		Version:        document.Version,
		PostID:         document.PostID,
		PostVersion:    document.PostVersion,
		ContentDigest:  document.ContentDigest,
		Status:         document.Status,
		ReviewerID:     document.ReviewerID,
		DecisionReason: document.DecisionReason,
		CreatedAt:      document.CreatedAt,
		UpdatedAt:      document.UpdatedAt,
		DecidedAt:      document.DecidedAt,
	}, true, nil
}

func (s *MongoPostModerationCaseStore) ReadModerationOutboxAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]moderationports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.D{}
	if strings.TrimSpace(checkpoint) != "" {
		occurredAt, eventID, err := parseModerationOutboxCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter = bson.D{{
			Key: "$or",
			Value: bson.A{
				bson.D{{Key: "occurredAt", Value: bson.D{{Key: "$gt", Value: occurredAt}}}},
				bson.D{
					{Key: "occurredAt", Value: occurredAt},
					{Key: "_id", Value: bson.D{{Key: "$gt", Value: eventID}}},
				},
			},
		}}
	}
	cursor, err := s.outbox.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read moderation outbox: %w", err)
	}
	defer cursor.Close(ctx)

	events := make([]moderationports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document postModerationOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode moderation outbox: %w", err)
		}
		events = append(events, moderationports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt,
			Checkpoint:       moderationOutboxCheckpoint(document.OccurredAt, document.ID),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate moderation outbox: %w", err)
	}
	return events, nil
}

func (s *MongoPostModerationCaseStore) findReceiptTx(
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
		return moderationports.CommitResult{}, false, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(
			ctx,
			bson.D{{Key: "_id", Value: receipt.ID}},
		); err != nil {
			return moderationports.CommitResult{}, false, err
		}
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

func validateModerationCommit(commit moderationports.Commit) error {
	if commit.Aggregate == nil ||
		strings.TrimSpace(commit.Aggregate.ID()) == "" ||
		commit.ExpectedVersion < 0 ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" {
		return contentgenerated.AppErrorFromVersionConflict(
			"invalid post moderation case commit",
		)
	}
	if commit.Audit.CaseID != commit.Aggregate.ID() ||
		commit.Audit.CaseVersion != commit.Aggregate.Version() ||
		commit.Audit.PostID != commit.Aggregate.PostID() ||
		commit.Audit.PostVersion != commit.Aggregate.PostVersion() ||
		commit.Audit.ContentDigest != commit.Aggregate.ContentDigest() ||
		commit.Audit.Action == "" ||
		commit.Audit.OccurredAt.IsZero() {
		return contentgenerated.AppErrorFromVersionConflict(
			"post moderation audit does not match aggregate commit",
		)
	}
	if len(commit.Events) != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"post moderation case commit requires exactly one outbox event",
		)
	}
	event := commit.Events[0]
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.EventType) == "" ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() ||
		event.OccurredAt.IsZero() {
		return contentgenerated.AppErrorFromVersionConflict(
			"post moderation outbox does not match aggregate commit",
		)
	}
	return nil
}

func validateModerationReceipt(
	actualName string,
	actualDigest string,
	expectedName string,
	expectedDigest string,
) error {
	if actualName != expectedName || actualDigest != expectedDigest {
		return contentgenerated.AppErrorFromIdempotencyConflict(
			"idempotency key was reused with a different moderation command",
		)
	}
	return nil
}

func moderationCaseDocumentFromAggregate(
	caseItem *moderationmodel.PostModerationCase,
) postModerationCaseDocument {
	snapshot := caseItem.Snapshot()
	return postModerationCaseDocument{
		ID:             snapshot.ID,
		Version:        snapshot.Version,
		PostID:         snapshot.PostID,
		PostVersion:    snapshot.PostVersion,
		ContentDigest:  snapshot.ContentDigest,
		Status:         snapshot.Status,
		ReviewerID:     snapshot.ReviewerID,
		DecisionReason: snapshot.DecisionReason,
		CreatedAt:      snapshot.CreatedAt,
		UpdatedAt:      snapshot.UpdatedAt,
		DecidedAt:      cloneModerationTime(snapshot.DecidedAt),
	}
}

func moderationCaseFromDocument(
	document postModerationCaseDocument,
) (*moderationmodel.PostModerationCase, error) {
	caseItem, err := moderationmodel.Restore(moderationmodel.Snapshot{
		ID:             document.ID,
		Version:        document.Version,
		PostID:         document.PostID,
		PostVersion:    document.PostVersion,
		ContentDigest:  document.ContentDigest,
		Status:         document.Status,
		ReviewerID:     document.ReviewerID,
		DecisionReason: document.DecisionReason,
		CreatedAt:      document.CreatedAt,
		UpdatedAt:      document.UpdatedAt,
		DecidedAt:      cloneModerationTime(document.DecidedAt),
	})
	if err != nil {
		return nil, fmt.Errorf("restore post moderation case: %w", err)
	}
	return caseItem, nil
}

func moderationAuditDocumentID(entry moderationports.AuditEntry) string {
	return entry.CaseID + ":" + fmt.Sprint(entry.CaseVersion) + ":" + string(entry.Action)
}

func moderationOutboxCheckpoint(occurredAt time.Time, eventID string) string {
	return occurredAt.UTC().Format(time.RFC3339Nano) + "|" + eventID
}

func parseModerationOutboxCheckpoint(checkpoint string) (time.Time, string, error) {
	occurredAtValue, eventID, ok := strings.Cut(strings.TrimSpace(checkpoint), "|")
	if !ok || strings.TrimSpace(eventID) == "" {
		return time.Time{}, "", fmt.Errorf("invalid moderation outbox checkpoint")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, occurredAtValue)
	if err != nil {
		return time.Time{}, "", fmt.Errorf("invalid moderation outbox checkpoint: %w", err)
	}
	return occurredAt.UTC(), eventID, nil
}

func normalizeModerationDigest(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}

func cloneModerationTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
