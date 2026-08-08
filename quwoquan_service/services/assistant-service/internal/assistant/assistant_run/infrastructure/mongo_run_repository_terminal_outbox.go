package infrastructure

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func (r *MongoRunRepository) ClaimPendingTerminalEvents(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
	limit int,
) ([]runruntime.TerminalEvent, error) {
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if ownerID == "" || now.IsZero() || lease <= 0 {
		return nil, runruntime.ErrInvalidRun
	}
	if limit <= 0 || limit > 1000 {
		limit = 128
	}
	events := make([]runruntime.TerminalEvent, 0, limit)
	for len(events) < limit {
		claimUntil := now.Add(lease)
		var document terminalOutboxDocument
		err := r.terminalOutbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"processedAt": bson.M{"$exists": false},
				"$and": bson.A{
					bson.M{"$or": bson.A{
						bson.M{"nextAttemptAt": bson.M{"$exists": false}},
						bson.M{"nextAttemptAt": bson.M{"$lte": now}},
					}},
					bson.M{"$or": bson.A{
						bson.M{"claimUntil": bson.M{"$exists": false}},
						bson.M{"claimUntil": bson.M{"$lte": now}},
					}},
				},
			},
			bson.M{
				"$set": bson.M{
					"claimOwner": ownerID,
					"claimUntil": claimUntil,
				},
				"$inc": bson.M{"attemptCount": 1},
			},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&document)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("claim assistant run terminal outbox: %w", err)
		}
		events = append(events, runruntime.TerminalEvent{
			EventID: document.ID, RunID: document.RunID,
			UserID: document.UserID, PersonaID: document.PersonaID,
			PersonaContextVersion: document.PersonaContextVersion,
			SessionID:             document.SessionID, DomainID: document.DomainID,
			Outcome: document.Outcome, ToolsCalled: document.ToolsCalled,
			LLMModel: document.LLMModel, LLMTokensUsed: document.LLMTokensUsed,
			LatencyMS:         document.LatencyMS,
			SatisfactionScore: document.SatisfactionScore,
			OccurredAt:        document.OccurredAt, AttemptCount: document.AttemptCount,
		})
	}
	return events, nil
}

func (r *MongoRunRepository) AcknowledgeTerminalEvent(
	ctx context.Context,
	eventID string,
	ownerID string,
	processedAt time.Time,
) error {
	if strings.TrimSpace(eventID) == "" || strings.TrimSpace(ownerID) == "" ||
		processedAt.IsZero() {
		return runruntime.ErrInvalidRun
	}
	result, err := r.terminalOutbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"claimUntil":  bson.M{"$gt": processedAt.UTC()},
			"processedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{"processedAt": processedAt.UTC()},
			"$unset": bson.M{
				"claimOwner": "", "claimUntil": "", "nextAttemptAt": "",
				"lastErrorCode": "",
			},
		},
	)
	if err != nil {
		return fmt.Errorf("mark assistant run terminal outbox processed: %w", err)
	}
	if result.MatchedCount != 1 {
		return runruntime.ErrTerminalEventClaimLost
	}
	return nil
}

func (r *MongoRunRepository) ScheduleTerminalEventRetry(
	ctx context.Context,
	eventID string,
	ownerID string,
	failedAt time.Time,
	nextAttemptAt time.Time,
	failureCode string,
) error {
	if strings.TrimSpace(eventID) == "" || strings.TrimSpace(ownerID) == "" ||
		failedAt.IsZero() || nextAttemptAt.IsZero() || nextAttemptAt.Before(failedAt) {
		return runruntime.ErrInvalidRun
	}
	result, err := r.terminalOutbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"claimUntil":  bson.M{"$gt": failedAt.UTC()},
			"processedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"nextAttemptAt": nextAttemptAt.UTC(),
				"lastErrorCode": boundedTerminalFailureCode(failureCode),
			},
			"$unset": bson.M{"claimOwner": "", "claimUntil": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("schedule assistant run terminal outbox retry: %w", err)
	}
	if result.MatchedCount != 1 {
		return runruntime.ErrTerminalEventClaimLost
	}
	return nil
}

func boundedTerminalFailureCode(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > 64 {
		return "delivery_failed"
	}
	return value
}

func (r *MongoRunRepository) ReleaseTerminalEventClaim(
	ctx context.Context,
	eventID string,
	ownerID string,
) error {
	if strings.TrimSpace(eventID) == "" || strings.TrimSpace(ownerID) == "" {
		return runruntime.ErrInvalidRun
	}
	_, err := r.terminalOutbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"processedAt": bson.M{"$exists": false},
		},
		bson.M{"$unset": bson.M{
			"claimOwner": "",
			"claimUntil": "",
		}},
	)
	if err != nil {
		return fmt.Errorf("release assistant run terminal outbox claim: %w", err)
	}
	return nil
}
