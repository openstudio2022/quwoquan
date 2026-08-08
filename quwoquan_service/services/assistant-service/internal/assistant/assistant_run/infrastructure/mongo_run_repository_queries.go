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

func (r *MongoRunRepository) Load(
	ctx context.Context,
	runID string,
) (runruntime.Run, error) {
	return r.load(ctx, bson.M{"_id": strings.TrimSpace(runID)})
}

func (r *MongoRunRepository) LoadByRequest(
	ctx context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (runruntime.Run, error) {
	return r.load(ctx, bson.M{
		"userId":          strings.TrimSpace(userID),
		"sessionId":       strings.TrimSpace(sessionID),
		"clientRequestId": strings.TrimSpace(clientRequestID),
	})
}

// ListSkillActivityEvents exposes only the redacted current Run lifecycle
// needed by SkillActivityView. The projection is intentionally owner-scoped
// and never returns user input, output, ContextSnapshot, Items, or evidence.
func (r *MongoRunRepository) ListSkillActivityEvents(
	ctx context.Context,
	userID string,
	skillID string,
	limit int,
) ([]runruntime.SkillActivityEvent, error) {
	userID = strings.TrimSpace(userID)
	skillID = strings.TrimSpace(skillID)
	if userID == "" || skillID == "" {
		return nil, runruntime.ErrInvalidRun
	}
	if limit <= 0 || limit > 100 {
		limit = 100
	}
	filter := bson.M{
		"userId": userID,
		"$or": bson.A{
			bson.M{"snapshot.frozenPolicySelection.template.skillId": skillID},
			bson.M{"snapshot.requestedSkillId": skillID},
		},
	}
	cursor, err := r.runs.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("list assistant run skill activity: %w", err)
	}
	defer cursor.Close(ctx)
	documents := []runDocument{}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf("decode assistant run skill activity: %w", err)
	}
	activities := make([]runruntime.SkillActivityEvent, 0, len(documents))
	for _, document := range documents {
		selectedSkillID := strings.TrimSpace(
			document.Snapshot.FrozenPolicySelection.Template.SkillID,
		)
		if selectedSkillID == "" {
			selectedSkillID = strings.TrimSpace(document.Snapshot.RequestedSkillID)
		}
		if selectedSkillID != skillID {
			continue
		}
		state := strings.TrimSpace(document.State)
		failureCode := ""
		if state == "failed" {
			failureCode = strings.TrimSpace(document.Snapshot.TerminalReason)
		}
		activities = append(activities, runruntime.SkillActivityEvent{
			RunID:       document.ID,
			UserID:      document.UserID,
			SkillID:     selectedSkillID,
			State:       state,
			FailureCode: failureCode,
			Revision:    document.Revision,
			OccurredAt:  document.UpdatedAt.UTC(),
		})
	}
	return activities, nil
}

// ListTerminalRunsAfter exposes committed terminal runs through the
// AssistantRun application boundary. Projection objects must consume this
// typed source instead of opening assistant_runs themselves.
func (r *MongoRunRepository) ListTerminalRunsAfter(
	ctx context.Context,
	afterUpdatedAt time.Time,
	afterRunID string,
	limit int,
) ([]runruntime.TerminalRunRecord, error) {
	if limit <= 0 || limit > 500 {
		limit = 200
	}
	filter := bson.M{"status": bson.M{"$in": bson.A{
		"completed", "failed", "cancelled",
	}}}
	if !afterUpdatedAt.IsZero() {
		filter["$or"] = bson.A{
			bson.M{"updatedAt": bson.M{"$gt": afterUpdatedAt.UTC()}},
			bson.M{
				"updatedAt": afterUpdatedAt.UTC(),
				"_id":       bson.M{"$gt": strings.TrimSpace(afterRunID)},
			},
		}
	}
	cursor, err := r.runs.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "updatedAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("list terminal assistant runs: %w", err)
	}
	defer cursor.Close(ctx)
	documents := []runDocument{}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf("decode terminal assistant runs: %w", err)
	}
	records := make([]runruntime.TerminalRunRecord, 0, len(documents))
	for _, document := range documents {
		records = append(records, runruntime.TerminalRunRecord{
			Run:             document.Snapshot,
			SourceUpdatedAt: document.UpdatedAt.UTC(),
			SourceRunID:     document.ID,
		})
	}
	return records, nil
}

func (r *MongoRunRepository) LoadCommandReceipt(
	ctx context.Context,
	runID string,
	commandID string,
) (runruntime.CommandReceipt, error) {
	var document commandReceiptDocument
	err := r.receipts.FindOne(ctx, bson.M{
		"runId":     strings.TrimSpace(runID),
		"commandId": strings.TrimSpace(commandID),
	}).Decode(&document)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.CommandReceipt{}, runruntime.ErrRunNotFound
		}
		return runruntime.CommandReceipt{}, fmt.Errorf(
			"load assistant run command receipt: %w",
			err,
		)
	}
	return runruntime.CommandReceipt{
		RunID:         document.RunID,
		CommandID:     document.CommandID,
		CommandKind:   document.CommandKind,
		PayloadDigest: document.PayloadDigest,
		Revision:      document.Revision,
		CreatedAt:     document.CreatedAt,
	}, nil
}

func (r *MongoRunRepository) load(
	ctx context.Context,
	filter bson.M,
) (runruntime.Run, error) {
	var document runDocument
	if err := r.runs.FindOne(ctx, filter).Decode(&document); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.Run{}, runruntime.ErrRunNotFound
		}
		return runruntime.Run{}, fmt.Errorf("load assistant run: %w", err)
	}
	document.Snapshot.Trigger = normalizeBSONMap(document.Snapshot.Trigger)
	document.Snapshot.ContextSnapshot = normalizeBSONMap(
		document.Snapshot.ContextSnapshot,
	)
	document.Snapshot.SurfaceCapabilities = normalizeBSONMap(
		document.Snapshot.SurfaceCapabilities,
	)
	document.Snapshot.PresentationDocument = normalizeBSONMap(
		document.Snapshot.PresentationDocument,
	)
	for index := range document.Snapshot.Items {
		document.Snapshot.Items[index].Payload = normalizeBSONMap(
			document.Snapshot.Items[index].Payload,
		)
	}
	return document.Snapshot, nil
}

// normalizeBSONMap converts Mongo driver's generic bson.D/bson.A values back
// to the JSON-shaped maps and slices owned by AssistantRun. Without this
// repository-boundary normalization, a persisted PresentationDocument can be
// read successfully but its typed action cannot be inspected by the domain
// command service after a restart or a later HTTP request.
func normalizeBSONMap(document map[string]any) map[string]any {
	if document == nil {
		return nil
	}
	for key, value := range document {
		document[key] = normalizeBSONValue(value)
	}
	return document
}

func normalizeBSONValue(value any) any {
	switch current := value.(type) {
	case bson.D:
		document := make(map[string]any, len(current))
		for _, element := range current {
			document[element.Key] = normalizeBSONValue(element.Value)
		}
		return document
	case bson.A:
		values := make([]any, len(current))
		for index, element := range current {
			values[index] = normalizeBSONValue(element)
		}
		return values
	case map[string]any:
		return normalizeBSONMap(current)
	case []any:
		values := make([]any, len(current))
		for index, element := range current {
			values[index] = normalizeBSONValue(element)
		}
		return values
	default:
		return value
	}
}

func (r *MongoRunRepository) EventsAfter(
	ctx context.Context,
	runID string,
	afterSequence int64,
	limit int,
) ([]runruntime.JournalEvent, error) {
	if strings.TrimSpace(runID) == "" || afterSequence < 0 {
		return nil, runruntime.ErrInvalidRun
	}
	if limit <= 0 || limit > 1000 {
		limit = 256
	}
	cursor, err := r.events.Find(
		ctx,
		bson.M{"runId": strings.TrimSpace(runID), "seq": bson.M{"$gt": afterSequence}},
		options.Find().SetSort(bson.D{{Key: "seq", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read assistant run journal: %w", err)
	}
	defer cursor.Close(ctx)
	result := make([]runruntime.JournalEvent, 0)
	for cursor.Next(ctx) {
		var document journalDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode assistant run journal: %w", err)
		}
		result = append(result, runruntime.JournalEvent{
			EventID:   document.ID,
			RunID:     document.RunID,
			Sequence:  document.Sequence,
			Revision:  document.Revision,
			Kind:      document.Kind,
			Payload:   clonePayload(document.Payload),
			CreatedAt: document.CreatedAt,
			ExpiresAt: document.ExpiresAt,
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate assistant run journal: %w", err)
	}
	run, err := r.Load(ctx, runID)
	if err != nil {
		return nil, err
	}
	if run.JournalSequence > afterSequence {
		if len(result) == 0 || result[0].Sequence != afterSequence+1 {
			if terminal, ok := runruntime.TerminalReplayEvent(run); ok {
				return []runruntime.JournalEvent{terminal}, nil
			}
			return nil, runruntime.ErrJournalGap
		}
	}
	for index := 1; index < len(result); index++ {
		if result[index].Sequence != result[index-1].Sequence+1 {
			return nil, runruntime.ErrJournalCorrupt
		}
	}
	return result, nil
}

func (r *MongoRunRepository) LatestSequence(
	ctx context.Context,
	runID string,
) (int64, error) {
	run, err := r.Load(ctx, runID)
	if err != nil {
		return 0, err
	}
	return run.JournalSequence, nil
}
