package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

const (
	planCollection     = "gathering_plans"
	receiptCollection  = "gathering_plan_command_receipts"
	eventLogCollection = "gathering_plan_event_log"
	sequenceCollection = "gathering_plan_event_log_sequences"
)

type MongoAggregateStore struct {
	plans     *mongo.Collection
	receipts  *mongo.Collection
	eventLog  *mongo.Collection
	sequences *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("GatheringPlan MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		plans: database.Collection(planCollection), receipts: database.Collection(receiptCollection),
		eventLog: database.Collection(eventLogCollection), sequences: database.Collection(sequenceCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.plans.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "gatheringId", Value: 1}}, Options: options.Index().SetName("uq_gathering_plan_gathering").SetUnique(true)},
		{Keys: bson.D{{Key: "_id", Value: 1}, {Key: "currentRevisionNumber", Value: -1}}, Options: options.Index().SetName("idx_gathering_plan_current_revision")},
		{Keys: bson.D{{Key: "_id", Value: 1}, {Key: "proposals.proposalId", Value: 1}}, Options: options.Index().SetName("idx_gathering_plan_proposal")},
		{Keys: bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_gathering_plan_updated")},
	}); err != nil {
		return err
	}
	// Mongo owns a unique _id index for command receipts. The explicit TTL
	// index below is the second half of the canonical receipt contract.
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("ttl_gathering_plan_command_receipt").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.eventLog.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "eventLogSequence", Value: 1}}, Options: options.Index().SetName("uq_gathering_plan_event_log_sequence").SetUnique(true)},
		{Keys: bson.D{{Key: "eventId", Value: 1}}, Options: options.Index().SetName("uq_gathering_plan_event_log_event").SetUnique(true)},
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_gathering_plan_event_log_aggregate").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, planID string) (model.GatheringPlan, bool, error) {
	var value model.GatheringPlan
	err := store.plans.FindOne(ctx, bson.M{"_id": strings.TrimSpace(planID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.GatheringPlan{}, false, nil
	}
	if err != nil {
		return model.GatheringPlan{}, false, err
	}
	if err := value.Validate(); err != nil {
		return model.GatheringPlan{}, false, err
	}
	return value, true, nil
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	if strings.TrimSpace(request.PlanID) == "" || strings.TrimSpace(request.ActorPersonaID) == "" ||
		strings.TrimSpace(request.ReceiptKey) == "" || strings.TrimSpace(request.CommandDigest) == "" ||
		request.ReceiptExpiresAt.IsZero() || strings.TrimSpace(request.EventType) == "" ||
		request.Authorize == nil || request.Mutate == nil {
		return ports.CommitReceipt{}, model.ErrInvalid
	}
	session, err := store.plans.Database().Client().StartSession()
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed ports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		// Revalidate delegated owner authority inside the same transaction used
		// for Plan state, receipt and owner event log. Receipt replay never bypasses a
		// Gathering closure/revocation decision.
		if authErr := request.Authorize(txCtx); authErr != nil {
			return nil, authErr
		}
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.Load(txCtx, request.PlanID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *model.GatheringPlan
		if found {
			currentCopy := current
			currentPointer = &currentCopy
		}
		next, event, mutateErr := request.Mutate(currentPointer)
		if mutateErr != nil {
			return nil, mutateErr
		}
		if next.ID != request.PlanID || event.PlanID != next.ID || event.GatheringID != next.GatheringID ||
			event.AggregateVersion != next.Version || event.OccurredAt.IsZero() {
			return nil, model.ErrInvalid
		}
		if (!found && next.Version != 1) || (found && next.Version != current.Version+1) {
			return nil, model.ErrVersionConflict
		}
		if found && !validMutationContinuity(current, next) {
			return nil, model.ErrRevisionConflict
		}
		if !found {
			if _, insertErr := store.plans.InsertOne(txCtx, next); insertErr != nil {
				return nil, mapPlanWriteError(insertErr)
			}
		} else {
			result, replaceErr := store.plans.ReplaceOne(
				txCtx, bson.M{"_id": next.ID, "version": current.Version}, next,
			)
			if replaceErr != nil {
				return nil, mapPlanWriteError(replaceErr)
			}
			if result.MatchedCount != 1 {
				return nil, model.ErrVersionConflict
			}
		}
		sequence, sequenceErr := store.nextEventLogSequence(txCtx)
		if sequenceErr != nil {
			return nil, sequenceErr
		}
		payload, marshalErr := json.Marshal(event)
		if marshalErr != nil {
			return nil, marshalErr
		}
		eventID := next.ID + ":" + request.EventType + ":" + strconv.FormatInt(next.Version, 10)
		if _, insertErr := store.eventLog.InsertOne(txCtx, bson.M{
			"_id": eventID, "eventId": eventID, "eventLogSequence": sequence,
			"eventType": request.EventType, "aggregateId": next.ID,
			"aggregateVersion": next.Version, "payloadJson": string(payload),
			"occurredAt": event.OccurredAt.UTC(),
		}); insertErr != nil {
			return nil, mapEventLogWriteError(insertErr)
		}
		var proposal *model.Proposal
		if event.ProposalID != "" {
			proposal = &model.Proposal{ProposalID: event.ProposalID, ProposalDigest: event.ProposalDigest}
		}
		result := model.CommandResultFromPlan(next, proposal, false)
		if _, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"actorPersonaId": request.ActorPersonaID, "operationId": request.EventType,
			"result": result, "expiresAt": request.ReceiptExpiresAt.UTC(),
		}); insertErr != nil {
			return nil, mapReceiptWriteError(insertErr)
		}
		committed = ports.CommitReceipt{Result: result}
		return nil, nil
	})
	if err != nil {
		// A concurrent identical request may win the transaction after this
		// transaction observed no receipt. Resolve only an exact digest match;
		// a reused key with different content remains fail-closed.
		if replay, found, replayErr := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); replayErr == nil && found {
			return replay, nil
		} else if replayErr != nil && errors.Is(replayErr, model.ErrIdempotencyConflict) {
			return ports.CommitReceipt{}, replayErr
		}
		return ports.CommitReceipt{}, err
	}
	return committed, nil
}

func validMutationContinuity(current, next model.GatheringPlan) bool {
	if next.ID != current.ID || next.GatheringID != current.GatheringID || !next.CreatedAt.Equal(current.CreatedAt) ||
		len(next.Revisions) < len(current.Revisions) || len(next.Revisions) > len(current.Revisions)+1 ||
		len(next.Proposals) < len(current.Proposals) || len(next.Proposals) > len(current.Proposals)+1 ||
		len(next.Acknowledgements) < len(current.Acknowledgements) {
		return false
	}
	for index := range current.Revisions {
		if !reflect.DeepEqual(current.Revisions[index], next.Revisions[index]) {
			return false
		}
	}
	for index := range current.Acknowledgements {
		if !reflect.DeepEqual(current.Acknowledgements[index], next.Acknowledgements[index]) {
			return false
		}
	}
	for index := range current.Proposals {
		before := current.Proposals[index]
		after := next.Proposals[index]
		if reflect.DeepEqual(before, after) {
			continue
		}
		// Commit may only transition one existing proposal from pending to
		// committed and attach its immutable revision identity/time.
		if before.Status != model.ProposalStatusPending || after.Status != model.ProposalStatusCommitted ||
			before.ProposalID != after.ProposalID || after.CommittedRevisionID == "" || after.CommittedAt == nil {
			return false
		}
		before.Status = after.Status
		before.CommittedRevisionID = after.CommittedRevisionID
		before.CommittedAt = after.CommittedAt
		if !reflect.DeepEqual(before, after) {
			return false
		}
	}
	return true
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, key, digest string) (ports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string              `bson:"commandDigest"`
		Result        model.CommandResult `bson:"result"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": key}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return ports.CommitReceipt{}, false, err
	}
	if document.CommandDigest != digest {
		return ports.CommitReceipt{}, false, model.ErrIdempotencyConflict
	}
	document.Result.Replayed = true
	return ports.CommitReceipt{Result: document.Result, Replayed: true}, true, nil
}

func (store *MongoAggregateStore) nextEventLogSequence(ctx context.Context) (int64, error) {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	err := store.sequences.FindOneAndUpdate(
		ctx, bson.M{"_id": "GatheringPlan"}, bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequence)
	return sequence.Value, err
}

func (store *MongoAggregateStore) ReadEventLogAfter(ctx context.Context, after int64, limit int) ([]ports.EventLogRecord, error) {
	if after < 0 {
		return nil, model.ErrInvalid
	}
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	cursor, err := store.eventLog.Find(
		ctx, bson.M{"eventLogSequence": bson.M{"$gt": after}},
		options.Find().SetSort(bson.D{{Key: "eventLogSequence", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var documents []struct {
		EventID          string    `bson:"eventId"`
		EventType        string    `bson:"eventType"`
		AggregateID      string    `bson:"aggregateId"`
		AggregateVersion int64     `bson:"aggregateVersion"`
		PayloadJSON      string    `bson:"payloadJson"`
		OccurredAt       time.Time `bson:"occurredAt"`
		Sequence         int64     `bson:"eventLogSequence"`
	}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	values := make([]ports.EventLogRecord, 0, len(documents))
	for _, document := range documents {
		values = append(values, ports.EventLogRecord{
			EventID: document.EventID, EventType: document.EventType,
			AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
			Payload: json.RawMessage(document.PayloadJSON), OccurredAt: document.OccurredAt.UTC(),
			Sequence: document.Sequence,
		})
	}
	return values, nil
}

func mapPlanWriteError(err error) error {
	if !mongo.IsDuplicateKeyError(err) {
		return err
	}
	message := err.Error()
	if strings.Contains(message, "uq_gathering_plan_gathering") || strings.Contains(message, "index: _id_") {
		return model.ErrAlreadyExists
	}
	return err
}

func mapReceiptWriteError(err error) error {
	if mongo.IsDuplicateKeyError(err) {
		return model.ErrIdempotencyConflict
	}
	return err
}

func mapEventLogWriteError(err error) error {
	if mongo.IsDuplicateKeyError(err) {
		return model.ErrVersionConflict
	}
	return err
}

var (
	_ ports.AggregateStore = (*MongoAggregateStore)(nil)
	_ ports.EventLogReader = (*MongoAggregateStore)(nil)
)
