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

	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
)

const (
	groupCollection               = "circle_groups"
	groupReceiptCollection        = "circle_group_command_receipts"
	groupOutboxCollection         = "circle_group_outbox"
	groupSequenceCollection       = "circle_group_outbox_sequences"
	groupCheckpointCollection     = "circle_group_projection_checkpoints"
	groupBindingReceiptCollection = "circle_group_conversation_binding_receipts"
)

type MongoAggregateStore struct {
	groups          *mongo.Collection
	receipts        *mongo.Collection
	outbox          *mongo.Collection
	sequences       *mongo.Collection
	checkpoints     *mongo.Collection
	bindingReceipts *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("CircleGroup MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		groups: database.Collection(groupCollection), receipts: database.Collection(groupReceiptCollection),
		outbox: database.Collection(groupOutboxCollection), sequences: database.Collection(groupSequenceCollection),
		checkpoints:     database.Collection(groupCheckpointCollection),
		bindingReceipts: database.Collection(groupBindingReceiptCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.groups.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "status", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_circle_group_list")},
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "name", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_circle_group_search")},
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "isDefaultPublicGroup", Value: 1}}, Options: options.Index().SetName("idx_circle_group_default").SetUnique(true).SetPartialFilterExpression(bson.M{"isDefaultPublicGroup": true, "status": groupmodel.CircleGroupStatusActive})},
		{Keys: bson.D{{Key: "conversationId", Value: 1}}, Options: options.Index().SetName("uq_circle_group_conversation").SetSparse(true).SetUnique(true)},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_circle_group_receipt_expiry").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	if _, err := store.bindingReceipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "eventId", Value: 1}}, Options: options.Index().SetName("uq_circle_group_conversation_binding_event").SetUnique(true)},
		{Keys: bson.D{{Key: "conversationId", Value: 1}}, Options: options.Index().SetName("uq_circle_group_conversation_binding_conversation").SetUnique(true)},
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_circle_group_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_group_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, groupID string) (groupmodel.CircleGroup, bool, error) {
	var value groupmodel.CircleGroup
	err := store.groups.FindOne(ctx, bson.M{"_id": strings.TrimSpace(groupID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupmodel.CircleGroup{}, false, nil
	}
	if err != nil {
		return groupmodel.CircleGroup{}, false, err
	}
	return value, true, nil
}

// BindConversation consumes the Chat-produced durable binding fact. The
// receipt and CircleGroup.conversationId write share one Mongo transaction:
// duplicate/reclaimed events are no-ops, while a second different conversation
// for the same CircleGroup is a hard consistency conflict.
func (store *MongoAggregateStore) BindConversation(
	ctx context.Context,
	eventID string,
	circleID string,
	groupID string,
	conversationID string,
) error {
	eventID = strings.TrimSpace(eventID)
	circleID = strings.TrimSpace(circleID)
	groupID = strings.TrimSpace(groupID)
	conversationID = strings.TrimSpace(conversationID)
	if eventID == "" || circleID == "" || groupID == "" || conversationID == "" {
		return groupmodel.ErrInvalidChange
	}
	session, err := store.groups.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var receipt struct {
			CircleID       string `bson:"circleId"`
			GroupID        string `bson:"groupId"`
			ConversationID string `bson:"conversationId"`
		}
		receiptErr := store.bindingReceipts.FindOne(
			txCtx,
			bson.M{"eventId": eventID},
		).Decode(&receipt)
		if receiptErr == nil {
			if receipt.CircleID == circleID && receipt.GroupID == groupID &&
				receipt.ConversationID == conversationID {
				return nil, nil
			}
			return nil, groupmodel.ErrVersionConflict
		}
		if !errors.Is(receiptErr, mongo.ErrNoDocuments) {
			return nil, receiptErr
		}
		group, found, loadErr := store.Load(txCtx, groupID)
		if loadErr != nil {
			return nil, loadErr
		}
		if !found || group.CircleID != circleID {
			return nil, groupmodel.ErrInvalidChange
		}
		if existing := strings.TrimSpace(group.ConversationID); existing != "" {
			if existing != conversationID {
				return nil, groupmodel.ErrVersionConflict
			}
		} else {
			result, updateErr := store.groups.UpdateOne(
				txCtx,
				bson.M{
					"_id":      groupID,
					"circleId": circleID,
					"$or": bson.A{
						bson.M{"conversationId": ""},
						bson.M{"conversationId": bson.M{"$exists": false}},
					},
				},
				bson.M{"$set": bson.M{
					"conversationId": conversationID,
					"updatedAt":      time.Now().UTC(),
				}},
			)
			if updateErr != nil {
				return nil, updateErr
			}
			if result.MatchedCount != 1 {
				return nil, groupmodel.ErrVersionConflict
			}
		}
		_, insertErr := store.bindingReceipts.InsertOne(txCtx, bson.M{
			"eventId": eventID, "circleId": circleID, "groupId": groupID,
			"conversationId": conversationID, "createdAt": time.Now().UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, groupmodel.ErrVersionConflict
		}
		return nil, insertErr
	})
	return err
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request groupports.CommitRequest) (groupports.CommitReceipt, error) {
	if strings.TrimSpace(request.Change.GroupID) == "" || strings.TrimSpace(request.Change.CircleID) == "" ||
		strings.TrimSpace(request.ReceiptKey) == "" || strings.TrimSpace(request.CommandDigest) == "" || request.ReceiptExpiresAt.IsZero() {
		return groupports.CommitReceipt{}, groupmodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.groups.Database().Client().StartSession()
	if err != nil {
		return groupports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed groupports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.Load(txCtx, request.Change.GroupID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *groupmodel.CircleGroup
		if found {
			currentPointer = &current
		}
		if err := store.validateParentChain(txCtx, request.Change, currentPointer); err != nil {
			return nil, err
		}
		next, applyErr := groupmodel.Apply(currentPointer, request.Change)
		if applyErr != nil {
			return nil, applyErr
		}
		if !found {
			if _, insertErr := store.groups.InsertOne(txCtx, next); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, groupmodel.ErrDefaultConflict
				}
				return nil, insertErr
			}
		} else {
			result, replaceErr := store.groups.ReplaceOne(txCtx,
				bson.M{"_id": next.ID, "version": request.Change.ExpectedVersion}, next)
			if replaceErr != nil {
				if mongo.IsDuplicateKeyError(replaceErr) {
					return nil, groupmodel.ErrDefaultConflict
				}
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, groupmodel.ErrVersionConflict
			}
		}
		var sequence struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := store.sequences.FindOneAndUpdate(txCtx,
			bson.M{"_id": "CircleGroup"}, bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); sequenceErr != nil {
			return nil, sequenceErr
		}
		eventType := groupEventType(request.Change.Kind)
		payloadJSON, marshalErr := json.Marshal(groupEventPayload{
			GroupID: next.ID, Version: next.Version, CircleID: next.CircleID,
			GroupType: next.GroupType, Name: next.Name, CreatedByPersonaID: next.CreatedByPersonaID,
			Status: next.Status, CreatedAt: next.CreatedAt.UTC(), UpdatedAt: next.UpdatedAt.UTC(),
		})
		if marshalErr != nil {
			return nil, marshalErr
		}
		eventID := next.ID + ":" + eventType + ":" + strconv.FormatInt(next.Version, 10)
		if _, insertErr := store.outbox.InsertOne(txCtx, bson.M{
			"_id": eventID, "outboxSequence": sequence.Value, "eventType": eventType,
			"aggregateId": next.ID, "aggregateVersion": next.Version,
			"payloadJson": string(payloadJSON), "occurredAt": next.UpdatedAt.UTC(),
		}); insertErr != nil {
			return nil, insertErr
		}
		committed = groupports.CommitReceipt{GroupID: next.ID, Version: next.Version, Status: next.Status}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"groupId": next.ID, "version": next.Version, "status": next.Status,
			"expiresAt": request.ReceiptExpiresAt.UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if replay, found, replayErr := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); replayErr == nil && found {
			return replay, nil
		}
		return groupports.CommitReceipt{}, err
	}
	return committed, nil
}

// RecordNoopReceipt 落"目标状态已满足"回执：不递增 version、不写 outbox。
func (store *MongoAggregateStore) RecordNoopReceipt(ctx context.Context, noop groupports.NoopReceipt) (groupports.CommitReceipt, error) {
	if strings.TrimSpace(noop.GroupID) == "" ||
		strings.TrimSpace(noop.ReceiptKey) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return groupports.CommitReceipt{}, groupmodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); err != nil || found {
		return replay, err
	}
	expiresAt := noop.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err := store.receipts.InsertOne(ctx, bson.M{
		"_id": noop.ReceiptKey, "commandDigest": noop.CommandDigest,
		"groupId": noop.GroupID, "version": noop.Version, "status": noop.Status,
		"expiresAt": expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			if replay, found, replayErr := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); replayErr == nil && found {
				return replay, nil
			}
		}
		return groupports.CommitReceipt{}, err
	}
	return groupports.CommitReceipt{
		GroupID: noop.GroupID, Version: noop.Version, Status: noop.Status,
	}, nil
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, receiptKey, commandDigest string) (groupports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string                       `bson:"commandDigest"`
		GroupID       string                       `bson:"groupId"`
		Version       int64                        `bson:"version"`
		Status        groupmodel.CircleGroupStatus `bson:"status"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": receiptKey}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return groupports.CommitReceipt{}, false, err
	}
	if document.CommandDigest != commandDigest {
		return groupports.CommitReceipt{}, false, groupmodel.ErrIdempotencyConflict
	}
	return groupports.CommitReceipt{
		GroupID: document.GroupID, Version: document.Version, Status: document.Status, Replayed: true,
	}, true, nil
}

func (store *MongoAggregateStore) validateParentChain(ctx context.Context, change groupmodel.ChangeSet, current *groupmodel.CircleGroup) error {
	if change.ParentGroupID == nil {
		return nil
	}
	parentID := strings.TrimSpace(*change.ParentGroupID)
	if parentID == "" {
		return nil
	}
	seen := map[string]struct{}{change.GroupID: {}}
	for depth := 0; depth < 64 && parentID != ""; depth++ {
		if _, exists := seen[parentID]; exists {
			return groupmodel.ErrParentInvalid
		}
		seen[parentID] = struct{}{}
		var parent groupmodel.CircleGroup
		err := store.groups.FindOne(ctx, bson.M{
			"_id": parentID, "circleId": change.CircleID, "status": groupmodel.CircleGroupStatusActive,
		}).Decode(&parent)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return groupmodel.ErrParentInvalid
		}
		if err != nil {
			return err
		}
		parentID = strings.TrimSpace(parent.ParentGroupID)
	}
	if parentID != "" {
		return groupmodel.ErrParentInvalid
	}
	_ = current
	return nil
}

func groupEventType(kind groupmodel.ChangeKind) string {
	switch kind {
	case groupmodel.ChangeCreate:
		return "CircleGroupCreated"
	case groupmodel.ChangeArchive:
		return "CircleGroupArchived"
	default:
		return "CircleGroupUpdated"
	}
}

type groupEventPayload struct {
	GroupID            string                       `json:"groupId"`
	Version            int64                        `json:"version"`
	CircleID           string                       `json:"circleId"`
	GroupType          groupmodel.CircleGroupType   `json:"groupType"`
	Name               string                       `json:"name"`
	CreatedByPersonaID string                       `json:"createdByPersonaId"`
	Status             groupmodel.CircleGroupStatus `json:"status"`
	CreatedAt          time.Time                    `json:"createdAt"`
	UpdatedAt          time.Time                    `json:"updatedAt"`
}

var _ groupports.AggregateStore = (*MongoAggregateStore)(nil)
var _ groupports.ConversationBindingWriter = (*MongoAggregateStore)(nil)
