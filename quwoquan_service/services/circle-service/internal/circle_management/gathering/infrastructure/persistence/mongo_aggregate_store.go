package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const (
	gatheringCollection                = "gatherings"
	receiptCollection                  = "gathering_command_receipts"
	outboxCollection                   = "gathering_outbox"
	sequenceCollection                 = "gathering_outbox_sequences"
	publicationCheckpointCollection    = "gathering_publication_checkpoints"
	reconciliationCheckpointCollection = "gathering_reconciliation_checkpoints"

	gatheringConversationIndex   = "uq_gathering_conversation"
	gatheringReceiptIndex        = "uq_gathering_command_receipt"
	gatheringOutboxSequenceIndex = "uq_gathering_outbox_sequence"

	invitationStatusPending   = "pending"
	invitationStatusAccepted  = "accepted"
	invitationStatusDeclined  = "declined"
	invitationStatusRevoked   = "revoked"
	invitationStatusCancelled = "cancelled"
	invitationStatusExpired   = "expired"
)

type MongoAggregateStore struct {
	gatherings             *mongo.Collection
	receipts               *mongo.Collection
	outbox                 *mongo.Collection
	sequences              *mongo.Collection
	publicationCheckpoints *mongo.Collection
	checkpoints            *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("Gathering MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		gatherings:             database.Collection(gatheringCollection),
		receipts:               database.Collection(receiptCollection),
		outbox:                 database.Collection(outboxCollection),
		sequences:              database.Collection(sequenceCollection),
		publicationCheckpoints: database.Collection(publicationCheckpointCollection),
		checkpoints:            database.Collection(reconciliationCheckpointCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.gatherings.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "conversationId", Value: 1}}, Options: options.Index().SetName(gatheringConversationIndex).SetSparse(true).SetUnique(true)},
		{Keys: bson.D{{Key: "lifecycleStatus", Value: 1}, {Key: "schedule.startAt", Value: 1}, {Key: "schedule.endAt", Value: 1}}, Options: options.Index().SetName("idx_gathering_lifecycle_schedule")},
		{Keys: bson.D{{Key: "hostBinding.hostSubjectKind", Value: 1}, {Key: "hostBinding.hostSubjectId", Value: 1}, {Key: "lifecycleStatus", Value: 1}, {Key: "schedule.startAt", Value: 1}}, Options: options.Index().SetName("idx_gathering_host_page")},
		{Keys: bson.D{{Key: "purpose.sourceObjectRefs.objectRef.objectTypeRef", Value: 1}, {Key: "purpose.sourceObjectRefs.objectRef.objectId", Value: 1}, {Key: "lifecycleStatus", Value: 1}, {Key: "schedule.startAt", Value: 1}}, Options: options.Index().SetName("idx_gathering_source_page")},
		{Keys: bson.D{{Key: "participations.personaId", Value: 1}, {Key: "participations.state", Value: 1}}, Options: options.Index().SetName("idx_gathering_participation_identity")},
		{Keys: bson.D{{Key: "availabilityWatches.personaId", Value: 1}, {Key: "availabilityWatches.status", Value: 1}, {Key: "schedule.startAt", Value: 1}}, Options: options.Index().SetName("idx_gathering_availability_watch")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_gathering_command_receipt").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName(gatheringOutboxSequenceIndex).SetUnique(true)},
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_gathering_outbox_aggregate")},
	})
	return err
}

// EncodeGatheringDocument applies canonical BSON nullability. In particular,
// pending drafts omit conversationId so the sparse unique index does not treat
// every draft as the same empty-string binding.
func EncodeGatheringDocument(value model.Gathering) (bson.M, error) {
	encoded, err := bson.Marshal(value)
	if err != nil {
		return nil, err
	}
	var document bson.M
	if err := bson.Unmarshal(encoded, &document); err != nil {
		return nil, err
	}
	if strings.TrimSpace(value.ConversationID) == "" {
		delete(document, "conversationId")
	}
	if value.Outcome.Status == "" {
		delete(document, "outcome")
	}
	if strings.TrimSpace(value.CurrentGatheringRevisionID) == "" {
		delete(document, "currentGatheringRevisionId")
	}
	if value.CancelledAt.IsZero() {
		delete(document, "cancelledAt")
	}
	if value.CompletedAt.IsZero() {
		delete(document, "completedAt")
	}
	if value.OrganizerAssignments == nil {
		document["organizerAssignments"] = bson.A{}
	}
	if value.Participations == nil {
		document["participations"] = bson.A{}
	}
	if value.Revisions == nil {
		document["revisions"] = bson.A{}
	}
	if value.AvailabilityWatches == nil {
		document["availabilityWatches"] = bson.A{}
	}
	return document, nil
}

// DuplicateIndexName returns only a known canonical index name. Callers map
// duplicates by collection plus this name instead of collapsing every E11000
// into a version or idempotency conflict.
func DuplicateIndexName(err error) string {
	if err == nil || !mongo.IsDuplicateKeyError(err) {
		return ""
	}
	message := err.Error()
	for _, name := range []string{
		gatheringConversationIndex,
		gatheringReceiptIndex,
		gatheringOutboxSequenceIndex,
		"_id_",
	} {
		if strings.Contains(message, "index: "+name+" ") ||
			strings.Contains(message, "index: "+name+" dup key") {
			return name
		}
	}
	return ""
}

func mapGatheringDuplicateWrite(err error) error {
	if !mongo.IsDuplicateKeyError(err) {
		return err
	}
	switch DuplicateIndexName(err) {
	case gatheringConversationIndex:
		return gatheringerrors.ErrGatheringRoomProvisionFailed
	case "_id_":
		return ports.ErrVersionConflict
	default:
		return err
	}
}

func mapReceiptDuplicateWrite(err error) error {
	if !mongo.IsDuplicateKeyError(err) {
		return err
	}
	switch DuplicateIndexName(err) {
	case gatheringReceiptIndex, "_id_":
		return gatheringerrors.ErrGatheringIdempotencyConflict
	default:
		return err
	}
}

func (store *MongoAggregateStore) Load(ctx context.Context, gatheringID string) (model.Gathering, bool, error) {
	var value model.Gathering
	err := store.gatherings.FindOne(ctx, bson.M{"_id": strings.TrimSpace(gatheringID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Gathering{}, false, nil
	}
	if err != nil {
		return model.Gathering{}, false, err
	}
	return value, true, nil
}

func (store *MongoAggregateStore) ListReconciliationCandidates(
	ctx context.Context,
	limit int,
) ([]model.Gathering, error) {
	if limit <= 0 {
		limit = 100
	}
	cursor, err := store.gatherings.Aggregate(ctx, mongo.Pipeline{
		bson.D{{Key: "$lookup", Value: bson.D{
			{Key: "from", Value: reconciliationCheckpointCollection},
			{Key: "localField", Value: "_id"},
			{Key: "foreignField", Value: "_id"},
			{Key: "as", Value: "reconciliationCheckpoint"},
		}}},
		bson.D{{Key: "$set", Value: bson.D{{Key: "reconciliationCheckpointVersion", Value: bson.D{
			{Key: "$ifNull", Value: bson.A{
				bson.D{{Key: "$arrayElemAt", Value: bson.A{"$reconciliationCheckpoint.version", 0}}},
				int64(0),
			}},
		}}}}},
		bson.D{{Key: "$match", Value: bson.D{{Key: "$expr", Value: bson.D{
			{Key: "$lt", Value: bson.A{"$reconciliationCheckpointVersion", "$version"}},
		}}}}},
		bson.D{{Key: "$sort", Value: bson.D{{Key: "updatedAt", Value: 1}, {Key: "_id", Value: 1}}}},
		bson.D{{Key: "$limit", Value: int64(limit)}},
		bson.D{{Key: "$unset", Value: bson.A{"reconciliationCheckpoint", "reconciliationCheckpointVersion"}}},
	})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var values []model.Gathering
	if err := cursor.All(ctx, &values); err != nil {
		return nil, err
	}
	return values, nil
}

func (store *MongoAggregateStore) SaveReconciliationCheckpoint(
	ctx context.Context,
	gatheringID string,
	version int64,
	updatedAt time.Time,
) error {
	gatheringID = strings.TrimSpace(gatheringID)
	if gatheringID == "" || version <= 0 || updatedAt.IsZero() {
		return model.ErrInvalidLifecycleArgument
	}
	_, err := store.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": gatheringID},
		bson.M{
			"$max": bson.M{"version": version},
			"$set": bson.M{"updatedAt": updatedAt.UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	if strings.TrimSpace(request.GatheringID) == "" || strings.TrimSpace(request.ReceiptKey) == "" ||
		strings.TrimSpace(request.CommandDigest) == "" || request.ReceiptExpiresAt.IsZero() ||
		strings.TrimSpace(request.EventType) == "" || request.Mutate == nil {
		return ports.CommitReceipt{}, model.ErrInvalidLifecycleArgument
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.gatherings.Database().Client().StartSession()
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed ports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.Load(txCtx, request.GatheringID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *model.Gathering
		if found {
			copy := current
			currentPointer = &copy
		}
		next, mutateErr := request.Mutate(currentPointer)
		if mutateErr != nil {
			return nil, mutateErr
		}
		if next.ID != request.GatheringID {
			return nil, model.ErrInvalidLifecycleArgument
		}
		changed := !found || next.Version != current.Version
		if (!found && next.Version != 1) ||
			(found && changed && next.Version != current.Version+1) {
			return nil, ports.ErrVersionConflict
		}
		document, encodeErr := EncodeGatheringDocument(next)
		if encodeErr != nil {
			return nil, encodeErr
		}
		if !found {
			if _, insertErr := store.gatherings.InsertOne(txCtx, document); insertErr != nil {
				return nil, mapGatheringDuplicateWrite(insertErr)
			}
		} else if changed {
			result, replaceErr := store.gatherings.ReplaceOne(
				txCtx,
				bson.M{"_id": next.ID, "version": current.Version},
				document,
			)
			if replaceErr != nil {
				return nil, mapGatheringDuplicateWrite(replaceErr)
			}
			if result.MatchedCount != 1 {
				return nil, ports.ErrVersionConflict
			}
		}
		if changed {
			eventTypes := append(
				[]string{request.EventType},
				request.AdditionalEventTypes...,
			)
			for _, eventType := range eventTypes {
				if outboxErr := store.appendOutbox(
					txCtx,
					eventType,
					lifecycleActorFromReceiptKey(request.ReceiptKey),
					currentPointer,
					next,
				); outboxErr != nil {
					return nil, outboxErr
				}
			}
		}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"operationId": request.EventType, "gatheringId": next.ID,
			"aggregateVersion": next.Version, "lifecycleStatus": next.LifecycleStatus,
			"aggregateSnapshot": next, "expiresAt": request.ReceiptExpiresAt.UTC(),
		})
		if insertErr != nil {
			return nil, mapReceiptDuplicateWrite(insertErr)
		}
		committed = ports.CommitReceipt{Gathering: next}
		return nil, nil
	})
	if err == nil {
		return committed, nil
	}
	// A concurrent first execution can commit after the preflight read while
	// this transaction observes duplicate _id. Re-read the durable receipt so
	// Create replay returns its original draft result instead of a false CAS.
	if replay, found, replayErr := store.findReceipt(
		ctx,
		request.ReceiptKey,
		request.CommandDigest,
	); replayErr == nil && found {
		return replay, nil
	}
	return ports.CommitReceipt{}, err
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, key, digest string) (ports.CommitReceipt, bool, error) {
	var receipt struct {
		CommandDigest     string          `bson:"commandDigest"`
		AggregateSnapshot model.Gathering `bson:"aggregateSnapshot"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": key}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return ports.CommitReceipt{}, false, err
	}
	if receipt.CommandDigest != digest {
		return ports.CommitReceipt{}, false, gatheringerrors.ErrGatheringIdempotencyConflict
	}
	return ports.CommitReceipt{Gathering: receipt.AggregateSnapshot, Replayed: true}, true, nil
}

func (store *MongoAggregateStore) appendOutbox(
	ctx context.Context,
	eventType string,
	actorPersonaID string,
	previous *model.Gathering,
	value model.Gathering,
) error {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	if err := store.sequences.FindOneAndUpdate(
		ctx, bson.M{"_id": "Gathering"}, bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequence); err != nil {
		return err
	}
	payload, err := json.Marshal(
		GatheringEventPayloadFor(eventType, actorPersonaID, previous, value),
	)
	if err != nil {
		return err
	}
	eventID := value.ID + ":" + eventType + ":" + strconv.FormatInt(value.Version, 10)
	_, err = store.outbox.InsertOne(ctx, bson.M{
		"_id": eventID, "outboxSequence": sequence.Value, "eventType": eventType,
		"aggregateId": value.ID, "aggregateVersion": value.Version,
		"payloadJson": string(payload), "occurredAt": value.UpdatedAt.UTC(),
	})
	return err
}

// GatheringEventPayloadFor builds the canonical typed outbox payload from the
// committed aggregate transition. The persistence package is service-internal;
// exporting this pure constructor lets object-local contract tests validate the
// exact event fields without requiring a Mongo process.
func GatheringEventPayloadFor(
	eventType string,
	actorPersonaID string,
	previous *model.Gathering,
	gathering model.Gathering,
) map[string]any {
	payload := map[string]any{
		"gatheringId":      gathering.ID,
		"aggregateVersion": gathering.Version,
		"lifecycleStatus":  gathering.LifecycleStatus,
		"occurredAt":       gathering.UpdatedAt.UTC(),
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	switch eventType {
	case gatheringevent.GatheringDraftCreated:
		payload["actorPersonaId"] = actorPersonaID
		addRevisionPayload(payload, gathering)
		payload["roomBindingStatus"] = gathering.RoomBindingStatus
	case gatheringevent.GatheringRoomBindingChanged:
		payload["roomBindingStatus"] = gathering.RoomBindingStatus
		addConversationPayload(payload, gathering)
	case gatheringevent.GatheringPublished:
		payload["actorPersonaId"] = actorPersonaID
		addRevisionPayload(payload, gathering)
		payload["roomBindingStatus"] = gathering.RoomBindingStatus
		addConversationPayload(payload, gathering)
	case gatheringevent.GatheringRevisionAppended:
		payload["actorPersonaId"] = actorPersonaID
		addRevisionPayload(payload, gathering)
	case gatheringevent.GatheringParticipationChanged:
		payload["actorPersonaId"] = actorPersonaID
		addParticipationPayload(payload, previous, gathering)
		addRevisionPayload(payload, gathering)
	case gatheringevent.GatheringInvitationChanged:
		return gatheringInvitationEventPayload(previous, gathering)
	case gatheringevent.GatheringAdmissionControlChanged:
		payload["actorPersonaId"] = actorPersonaID
		payload["admissionControlStatus"] = gathering.AdmissionControl.Status
	case gatheringevent.GatheringCancelled:
		payload["actorPersonaId"] = actorPersonaID
		payload["roomBindingStatus"] = gathering.RoomBindingStatus
		addConversationPayload(payload, gathering)
	case gatheringevent.GatheringEndedEarly,
		gatheringevent.GatheringSafetyTerminated,
		gatheringevent.GatheringCompleted:
		payload["actorPersonaId"] = actorPersonaID
		payload["outcomeStatus"] = gathering.Outcome.Status
		payload["roomBindingStatus"] = gathering.RoomBindingStatus
		addConversationPayload(payload, gathering)
	case gatheringevent.GatheringOutcomeCalculated:
		payload["outcomeStatus"] = gathering.Outcome.Status
	case gatheringevent.GatheringAvailabilityWatchChanged:
		payload["actorPersonaId"] = actorPersonaID
		addAvailabilityWatchPayload(payload, previous, gathering)
	}
	return payload
}

func gatheringInvitationEventPayload(
	previous *model.Gathering,
	gathering model.Gathering,
) map[string]any {
	participation, found := changedParticipation(previous, gathering)
	if !found || participation.AdmissionSource != model.AdmissionSourceInvitation {
		return map[string]any{}
	}
	schedule := model.ProjectDisclosureSchedule(
		gathering.Schedule,
		gathering.PolicySet.DisclosurePolicy,
		false,
	)
	place := model.ProjectDisclosurePlace(
		gathering.Place,
		gathering.PolicySet.DisclosurePolicy,
		false,
	)
	status := invitationStatus(gathering, participation)
	schedulePayload := map[string]any{"timezone": schedule.Timezone}
	if !schedule.StartAt.IsZero() {
		schedulePayload["startAt"] = schedule.StartAt
	}
	if !schedule.EndAt.IsZero() {
		schedulePayload["endAt"] = schedule.EndAt
	}
	if schedule.DateLabel != "" {
		schedulePayload["dateLabel"] = schedule.DateLabel
	}
	placePayload := map[string]any{"mode": place.Mode}
	if place.CoarsePlaceLabel != "" {
		placePayload["coarsePlaceLabel"] = place.CoarsePlaceLabel
	}
	if place.ExactMeetingPoint != "" {
		placePayload["exactMeetingPoint"] = place.ExactMeetingPoint
	}
	payload := map[string]any{
		"gatheringId":          gathering.ID,
		"inviterPersonaId":     participation.InvitedByPersonaID,
		"recipientPersonaId":   participation.PersonaID,
		"purposeSummary":       strings.TrimSpace(gathering.Purpose.Summary),
		"schedule":             schedulePayload,
		"place":                placePayload,
		"participationVersion": participation.Version,
		"status":               status,
		"actionIntents":        []map[string]any{},
		"occurredAt":           gathering.UpdatedAt.UTC(),
	}
	if !participation.SeatHoldUntil.IsZero() {
		payload["expiresAt"] = participation.SeatHoldUntil.UTC()
	}
	if status == invitationStatusPending &&
		participation.SeatHoldUntil.After(gathering.UpdatedAt) {
		payload["actionIntents"] = []map[string]any{
			{
				"action":                       "accept",
				"expectedGatheringVersion":     gathering.Version,
				"expectedParticipationVersion": participation.Version,
			},
			{
				"action":                       "decline",
				"expectedGatheringVersion":     gathering.Version,
				"expectedParticipationVersion": participation.Version,
			},
		}
	}
	return payload
}

func changedParticipation(
	previous *model.Gathering,
	gathering model.Gathering,
) (model.GatheringParticipation, bool) {
	previousVersions := make(map[string]int64)
	if previous != nil {
		for _, participation := range previous.Participations {
			previousVersions[participation.PersonaID] = participation.Version
		}
	}
	for _, participation := range gathering.Participations {
		if previousVersions[participation.PersonaID] != participation.Version {
			return participation, true
		}
	}
	return model.GatheringParticipation{}, false
}

func invitationStatus(
	gathering model.Gathering,
	participation model.GatheringParticipation,
) string {
	if gathering.LifecycleStatus == contract.GatheringLifecycleStatusCancelled {
		return invitationStatusCancelled
	}
	switch participation.State {
	case model.ParticipationStateInvitedPending:
		if !participation.SeatHoldUntil.IsZero() &&
			!participation.SeatHoldUntil.After(gathering.UpdatedAt) {
			return invitationStatusExpired
		}
		return invitationStatusPending
	case model.ParticipationStateActive:
		return invitationStatusAccepted
	case model.ParticipationStateClosed:
		switch participation.ClosedReason {
		case contract.GatheringParticipationClosedReasonDeclined:
			return invitationStatusDeclined
		case contract.GatheringParticipationClosedReasonRevoked:
			return invitationStatusRevoked
		case contract.GatheringParticipationClosedReasonExpired:
			return invitationStatusExpired
		}
	}
	return invitationStatusRevoked
}

func addConversationPayload(payload map[string]any, gathering model.Gathering) {
	if conversationID := strings.TrimSpace(gathering.ConversationID); conversationID != "" {
		payload["conversationId"] = conversationID
	}
}

func addRevisionPayload(payload map[string]any, gathering model.Gathering) {
	revisionID := strings.TrimSpace(gathering.CurrentGatheringRevisionID)
	if revisionID == "" {
		return
	}
	payload["revisionId"] = revisionID
	payload["revisionNumber"] = gathering.CurrentGatheringRevisionNumber
	for _, revision := range gathering.Revisions {
		if revision.RevisionID == revisionID {
			payload["revisionDigest"] = revision.Digest
			return
		}
	}
}

func addParticipationPayload(
	payload map[string]any,
	previous *model.Gathering,
	gathering model.Gathering,
) {
	previousVersions := make(map[string]int64)
	if previous != nil {
		for _, participation := range previous.Participations {
			previousVersions[participation.PersonaID] = participation.Version
		}
	}
	for _, participation := range gathering.Participations {
		if previousVersions[participation.PersonaID] != participation.Version {
			payload["participantPersonaId"] = participation.PersonaID
			payload["participationState"] = participation.State
			return
		}
	}
}

func addAvailabilityWatchPayload(
	payload map[string]any,
	previous *model.Gathering,
	gathering model.Gathering,
) {
	previousVersions := make(map[string]int64)
	if previous != nil {
		for _, watch := range previous.AvailabilityWatches {
			previousVersions[watch.PersonaID] = watch.Version
		}
	}
	for _, watch := range gathering.AvailabilityWatches {
		if previousVersions[watch.PersonaID] != watch.Version {
			payload["watchStatus"] = watch.Status
			return
		}
	}
}

func lifecycleActorFromReceiptKey(receiptKey string) string {
	actor, _, found := strings.Cut(strings.TrimSpace(receiptKey), ":")
	if !found || actor == "" || actor == "system" {
		return ""
	}
	return actor
}

var _ ports.AggregateStore = (*MongoAggregateStore)(nil)
var _ ports.ReconciliationStore = (*MongoAggregateStore)(nil)
var _ ports.PublicationOutbox = (*MongoAggregateStore)(nil)
