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

func (r *MongoRunRepository) Commit(
	ctx context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	return r.commit(ctx, nil, expectedRevision, run, events, receipt)
}

func (r *MongoRunRepository) CommitClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if strings.TrimSpace(claim.RunID) == "" ||
		strings.TrimSpace(claim.RunID) != strings.TrimSpace(run.RunID) ||
		strings.TrimSpace(claim.WorkerID) == "" || claim.FencingToken <= 0 {
		return runruntime.ErrExecutionFenced
	}
	return r.commit(ctx, &claim, expectedRevision, run, events, receipt)
}

func (r *MongoRunRepository) commit(
	ctx context.Context,
	claim *runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if claim == nil && expectedRevision > 0 {
		var current struct {
			Revision int64 `bson:"runRevision"`
		}
		err := r.runs.FindOne(
			ctx,
			bson.M{"_id": strings.TrimSpace(run.RunID)},
			options.FindOne().SetProjection(bson.M{"runRevision": 1}),
		).Decode(&current)
		if errors.Is(err, mongo.ErrNoDocuments) ||
			(err == nil && current.Revision != expectedRevision) {
			return runruntime.ErrRevisionConflict
		}
		if err != nil {
			return fmt.Errorf("read assistant run revision: %w", err)
		}
	}
	document, eventDocuments, err := normalizeCommit(expectedRevision, run, events)
	if err != nil {
		return err
	}
	receiptDocument, err := normalizeCommandReceipt(run, receipt)
	if err != nil {
		return err
	}
	session, err := r.runs.Database().Client().StartSession()
	if err != nil {
		return fmt.Errorf("start assistant run transaction: %w", err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		previousState := ""
		if expectedRevision > 0 {
			var current struct {
				State string `bson:"status"`
			}
			readErr := r.runs.FindOne(
				txCtx,
				bson.M{"_id": document.ID, "runRevision": expectedRevision},
				options.FindOne().SetProjection(bson.M{"status": 1}),
			).Decode(&current)
			if errors.Is(readErr, mongo.ErrNoDocuments) {
				return nil, runruntime.ErrRevisionConflict
			}
			if readErr != nil {
				return nil, readErr
			}
			previousState = strings.TrimSpace(current.State)
		}
		if claim != nil {
			claimCheckAt := time.Now().UTC()
			claimResult, claimErr := r.work.UpdateOne(
				txCtx,
				workClaimFilter(*claim, claimCheckAt),
				bson.M{"$set": bson.M{
					"lastCommittedRunRevision": run.Revision,
					"updatedAt":                claimCheckAt,
				}},
			)
			if claimErr != nil {
				return nil, claimErr
			}
			if claimResult.MatchedCount != 1 {
				return nil, runruntime.ErrExecutionFenced
			}
		}
		if expectedRevision == 0 {
			if _, insertErr := r.runs.InsertOne(txCtx, document); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, insertErr
			}
		} else {
			result, updateErr := r.runs.ReplaceOne(
				txCtx,
				bson.M{"_id": document.ID, "runRevision": expectedRevision},
				document,
			)
			if updateErr != nil {
				return nil, updateErr
			}
			if result.MatchedCount != 1 {
				return nil, runruntime.ErrRevisionConflict
			}
		}
		if len(eventDocuments) > 0 {
			values := make([]any, len(eventDocuments))
			for index := range eventDocuments {
				values[index] = eventDocuments[index]
			}
			if _, insertErr := r.events.InsertMany(txCtx, values); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, insertErr
			}
		}
		if receiptDocument != nil {
			if _, insertErr := r.receipts.InsertOne(
				txCtx,
				*receiptDocument,
			); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, insertErr
			}
		}
		if terminal := terminalOutboxFromRun(run); terminal != nil {
			if _, outboxErr := r.terminalOutbox.InsertOne(txCtx, *terminal); outboxErr != nil {
				if mongo.IsDuplicateKeyError(outboxErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, outboxErr
			}
		}
		hook, hookErr := hookOutboxFromTransition(previousState, run)
		if hookErr != nil {
			return nil, hookErr
		}
		if hook != nil {
			if _, outboxErr := r.hookOutbox.InsertOne(txCtx, *hook); outboxErr != nil {
				if mongo.IsDuplicateKeyError(outboxErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, outboxErr
			}
		}
		if queueRunnable(run.State.WireName()) {
			if _, queueErr := r.work.UpdateOne(
				txCtx,
				bson.M{"_id": document.ID},
				bson.M{"$setOnInsert": bson.M{
					"status":       "ready",
					"fencingToken": int64(0),
					"availableAt":  run.UpdatedAt.UTC(),
					"updatedAt":    run.UpdatedAt.UTC(),
				}},
				options.UpdateOne().SetUpsert(true),
			); queueErr != nil {
				return nil, queueErr
			}
		} else {
			if _, queueErr := r.work.DeleteOne(
				txCtx,
				bson.M{"_id": document.ID},
			); queueErr != nil {
				return nil, queueErr
			}
		}
		return nil, nil
	})
	if err != nil {
		if errors.Is(err, runruntime.ErrRevisionConflict) ||
			errors.Is(err, runruntime.ErrExecutionFenced) {
			return err
		}
		return fmt.Errorf("commit assistant run: %w", err)
	}
	return nil
}

func terminalOutboxFromRun(run runruntime.Run) *terminalOutboxDocument {
	if run.CompletedAt == nil {
		return nil
	}
	outcome := strings.TrimSpace(run.State.WireName())
	switch outcome {
	case "completed", "failed", "cancelled":
	default:
		return nil
	}
	domainID := strings.TrimSpace(run.RequestedDomainID)
	if domainID == "" {
		domainID = strings.TrimSpace(run.FrozenPolicySelection.Template.DomainID)
	}
	if domainID == "" {
		domainID = "assistant"
	}
	var toolsCalled *[]string
	var llmModel *string
	var llmTokensUsed *int64
	if run.Checkpoint != nil {
		tools := make([]string, len(run.Checkpoint.ContextState.ToolHistory))
		copy(tools, run.Checkpoint.ContextState.ToolHistory)
		toolsCalled = &tools
		tokens := run.Checkpoint.BudgetConsumption.Tokens
		llmTokensUsed = &tokens
		modelHistory := run.Checkpoint.ContextState.ModelHistory
		if len(modelHistory) > 0 {
			modelID := strings.TrimSpace(modelHistory[len(modelHistory)-1])
			if modelID != "" {
				llmModel = &modelID
			}
		}
	}
	var latencyMS *int64
	if !run.CreatedAt.IsZero() && !run.CompletedAt.Before(run.CreatedAt) {
		latency := run.CompletedAt.Sub(run.CreatedAt).Milliseconds()
		latencyMS = &latency
	}
	return &terminalOutboxDocument{
		ID:            strings.TrimSpace(run.RunID) + ":terminal",
		RunID:         strings.TrimSpace(run.RunID),
		UserID:        strings.TrimSpace(run.UserID),
		PersonaID:     strings.TrimSpace(run.PersonaID),
		SessionID:     strings.TrimSpace(run.SessionID),
		DomainID:      domainID,
		Outcome:       outcome,
		ToolsCalled:   toolsCalled,
		LLMModel:      llmModel,
		LLMTokensUsed: llmTokensUsed,
		LatencyMS:     latencyMS,
		OccurredAt:    run.CompletedAt.UTC(),
	}
}

func normalizeCommit(
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
) (runDocument, []journalDocument, error) {
	runID := strings.TrimSpace(run.RunID)
	if runID == "" ||
		strings.TrimSpace(run.UserID) == "" ||
		strings.TrimSpace(run.SessionID) == "" ||
		strings.TrimSpace(run.ClientRequestID) == "" ||
		run.Revision <= expectedRevision ||
		run.JournalSequence <= 0 {
		return runDocument{}, nil, runruntime.ErrInvalidRun
	}
	document := runDocument{
		ID:              runID,
		UserID:          run.UserID,
		PersonaID:       run.PersonaID,
		SessionID:       run.SessionID,
		ClientRequestID: run.ClientRequestID,
		Revision:        run.Revision,
		State:           run.State.WireName(),
		Snapshot:        run,
		CreatedAt:       run.CreatedAt.UTC(),
		UpdatedAt:       run.UpdatedAt.UTC(),
	}
	normalized := make([]journalDocument, 0, len(events))
	var previousSequence int64
	for _, event := range events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.RunID) != runID ||
			event.Sequence <= previousSequence ||
			event.Revision <= expectedRevision ||
			event.Revision > run.Revision ||
			strings.TrimSpace(event.Kind) == "" ||
			event.CreatedAt.IsZero() {
			return runDocument{}, nil, runruntime.ErrInvalidRun
		}
		expiresAt := event.ExpiresAt.UTC()
		if event.ExpiresAt.IsZero() {
			expiresAt = event.CreatedAt.UTC().Add(runJournalRetention)
		}
		normalized = append(normalized, journalDocument{
			ID:        event.EventID,
			RunID:     runID,
			Sequence:  event.Sequence,
			Revision:  event.Revision,
			Kind:      strings.TrimSpace(event.Kind),
			Payload:   clonePayload(event.Payload),
			CreatedAt: event.CreatedAt.UTC(),
			ExpiresAt: expiresAt,
		})
		previousSequence = event.Sequence
	}
	if len(normalized) == 0 ||
		normalized[len(normalized)-1].Sequence != run.JournalSequence ||
		normalized[0].Sequence != run.JournalSequence-int64(len(normalized))+1 {
		return runDocument{}, nil, runruntime.ErrJournalCorrupt
	}
	return document, normalized, nil
}

func normalizeCommandReceipt(
	run runruntime.Run,
	receipt *runruntime.CommandReceipt,
) (*commandReceiptDocument, error) {
	if receipt == nil {
		return nil, nil
	}
	runID := strings.TrimSpace(receipt.RunID)
	commandID := strings.TrimSpace(receipt.CommandID)
	commandKind := strings.TrimSpace(receipt.CommandKind)
	payloadDigest := strings.TrimSpace(receipt.PayloadDigest)
	if runID != strings.TrimSpace(run.RunID) ||
		commandID == "" ||
		commandKind == "" ||
		payloadDigest == "" ||
		receipt.Revision != run.Revision ||
		receipt.CreatedAt.IsZero() {
		return nil, runruntime.ErrInvalidRun
	}
	return &commandReceiptDocument{
		ID:            runID + ":" + commandID,
		RunID:         runID,
		CommandID:     commandID,
		CommandKind:   commandKind,
		PayloadDigest: payloadDigest,
		Revision:      receipt.Revision,
		CreatedAt:     receipt.CreatedAt.UTC(),
	}, nil
}

func queueRunnable(state string) bool {
	switch strings.TrimSpace(state) {
	case "completed", "failed", "cancelled", "paused",
		"waiting_user", "waiting_approval", "waiting_external":
		return false
	default:
		return true
	}
}

func clonePayload(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}
