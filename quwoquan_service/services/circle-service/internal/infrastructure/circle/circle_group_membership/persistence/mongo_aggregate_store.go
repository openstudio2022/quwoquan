package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/domain/circle/circle_group_membership/model"
	ports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group_membership/ports"
)

const (
	membershipCollection = "circle_group_memberships"
	receiptCollection    = "circle_group_membership_command_receipts"
	outboxCollection     = "circle_group_membership_outbox"
	sequenceCollection   = "circle_group_membership_outbox_sequences"
	checkpointCollection = "circle_group_membership_projection_checkpoints"
	capacityCollection   = "circle_group_membership_capacity_counters"
)

type MongoAggregateStore struct {
	memberships      *mongo.Collection
	receipts         *mongo.Collection
	outbox           *mongo.Collection
	sequences        *mongo.Collection
	checkpoints      *mongo.Collection
	capacityCounters *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("CircleGroupMembership MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		memberships: database.Collection(membershipCollection), receipts: database.Collection(receiptCollection),
		outbox: database.Collection(outboxCollection), sequences: database.Collection(sequenceCollection),
		checkpoints: database.Collection(checkpointCollection), capacityCounters: database.Collection(capacityCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.memberships.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "groupId", Value: 1}, {Key: "personaId", Value: 1}}, Options: options.Index().SetName("idx_circle_group_membership_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "groupId", Value: 1}, {Key: "state", Value: 1}, {Key: "joinedAt", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_circle_group_membership_roster")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("idx_circle_group_membership_receipt_expiry").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_circle_group_membership_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_group_membership_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, membershipID string) (model.CircleGroupMembership, bool, error) {
	return store.load(ctx, bson.M{"_id": strings.TrimSpace(membershipID)})
}

func (store *MongoAggregateStore) LoadByIdentity(ctx context.Context, groupID, personaID string) (model.CircleGroupMembership, bool, error) {
	return store.load(ctx, bson.M{"groupId": strings.TrimSpace(groupID), "personaId": strings.TrimSpace(personaID)})
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	if err := request.Change.Validate(); err != nil || strings.TrimSpace(request.ReceiptKey) == "" ||
		strings.TrimSpace(request.CommandDigest) == "" || request.ReceiptExpiresAt.IsZero() {
		return ports.CommitReceipt{}, model.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.memberships.Database().Client().StartSession()
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
		current, found, loadErr := store.LoadByIdentity(txCtx, request.Change.GroupID, request.Change.PersonaID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *model.CircleGroupMembership
		if found {
			currentPointer = &current
		}
		next, eventType, applyErr := request.Change.Apply(currentPointer)
		if applyErr != nil {
			return nil, applyErr
		}
		if capacityErr := store.adjustActiveMemberCapacity(txCtx, currentPointer, next); capacityErr != nil {
			return nil, capacityErr
		}
		if !found {
			if _, insertErr := store.memberships.InsertOne(txCtx, documentFrom(next)); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, model.ErrVersionConflict
				}
				return nil, insertErr
			}
		} else {
			result, replaceErr := store.memberships.ReplaceOne(txCtx,
				bson.M{"_id": next.ID, "version": request.Change.ExpectedVersion}, documentFrom(next))
			if replaceErr != nil {
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, model.ErrVersionConflict
			}
		}
		var sequence struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := store.sequences.FindOneAndUpdate(txCtx,
			bson.M{"_id": "CircleGroupMembership"}, bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); sequenceErr != nil {
			return nil, sequenceErr
		}
		groupOwnerID, ownerErr := store.groupOwnerPersonaID(txCtx, next.GroupID)
		if ownerErr != nil {
			return nil, ownerErr
		}
		payloadJSON, marshalErr := json.Marshal(eventPayload(next, groupOwnerID))
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
		committed = ports.CommitReceipt{MembershipID: next.ID, Version: next.Version, State: next.State, Role: next.Role}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"membershipId": next.ID, "version": next.Version, "state": next.State, "role": next.Role,
			"expiresAt": request.ReceiptExpiresAt.UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if replay, found, replayErr := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); replayErr == nil && found {
			return replay, nil
		}
		return ports.CommitReceipt{}, err
	}
	return committed, nil
}

// adjustActiveMemberCapacity maintains a single per-group ledger in the same
// Mongo transaction as the authoritative membership document and its outbox.
// The ledger is an invariant lock, not a read model: it serializes concurrent
// active-state transitions so two snapshots cannot admit a 1001st member.
func (store *MongoAggregateStore) adjustActiveMemberCapacity(
	ctx context.Context,
	current *model.CircleGroupMembership,
	next model.CircleGroupMembership,
) error {
	delta := model.ActiveMembershipDelta(current, next)
	if delta == 0 {
		return nil
	}
	groupID := strings.TrimSpace(next.GroupID)
	if groupID == "" {
		return model.ErrInvalidChange
	}

	var counter struct {
		ActiveMemberCount int64 `bson:"activeMemberCount"`
	}
	err := store.capacityCounters.FindOne(ctx, bson.M{"_id": groupID}).Decode(&counter)
	if errors.Is(err, mongo.ErrNoDocuments) {
		activeCount, countErr := store.memberships.CountDocuments(ctx, bson.M{
			"groupId": groupID, "state": model.CircleGroupMembershipStateActive,
		})
		if countErr != nil {
			return countErr
		}
		nextCount := activeCount + delta
		if nextCount > model.MaxActiveMembersPerGroup {
			return model.ErrGroupFull
		}
		if nextCount < 0 {
			return fmt.Errorf("CircleGroupMembership capacity ledger underflow for group %q", groupID)
		}
		_, insertErr := store.capacityCounters.InsertOne(ctx, bson.M{
			"_id": groupID, "activeMemberCount": nextCount, "updatedAt": next.UpdatedAt.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return model.ErrVersionConflict
		}
		return insertErr
	}
	if err != nil {
		return err
	}

	nextCount := counter.ActiveMemberCount + delta
	if nextCount > model.MaxActiveMembersPerGroup {
		return model.ErrGroupFull
	}
	if nextCount < 0 {
		return fmt.Errorf("CircleGroupMembership capacity ledger underflow for group %q", groupID)
	}
	result, updateErr := store.capacityCounters.UpdateOne(ctx, bson.M{
		"_id": groupID, "activeMemberCount": counter.ActiveMemberCount,
	}, bson.M{
		"$set": bson.M{"activeMemberCount": nextCount, "updatedAt": next.UpdatedAt.UTC()},
	})
	if updateErr != nil {
		return updateErr
	}
	if result.MatchedCount != 1 {
		return model.ErrVersionConflict
	}
	return nil
}

func (store *MongoAggregateStore) load(ctx context.Context, filter any) (model.CircleGroupMembership, bool, error) {
	var document membershipDocument
	err := store.memberships.FindOne(ctx, filter).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.CircleGroupMembership{}, false, nil
	}
	if err != nil {
		return model.CircleGroupMembership{}, false, err
	}
	return document.toModel(), true, nil
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, key, digest string) (ports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string                           `bson:"commandDigest"`
		MembershipID  string                           `bson:"membershipId"`
		Version       int64                            `bson:"version"`
		State         model.CircleGroupMembershipState `bson:"state"`
		Role          model.CircleGroupMembershipRole  `bson:"role"`
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
	return ports.CommitReceipt{
		MembershipID: document.MembershipID, Version: document.Version,
		State: document.State, Role: document.Role, Replayed: true,
	}, true, nil
}

type membershipDocument struct {
	ID                 string                           `bson:"_id"`
	Version            int64                            `bson:"version"`
	GroupID            string                           `bson:"groupId"`
	CircleID           string                           `bson:"circleId"`
	PersonaID          string                           `bson:"personaId"`
	Role               model.CircleGroupMembershipRole  `bson:"role"`
	State              model.CircleGroupMembershipState `bson:"state"`
	JoinedAt           *time.Time                       `bson:"joinedAt,omitempty"`
	LeftAt             *time.Time                       `bson:"leftAt,omitempty"`
	DecidedAt          *time.Time                       `bson:"decidedAt,omitempty"`
	DecidedByPersonaID string                           `bson:"decidedByPersonaId,omitempty"`
	CreatedAt          time.Time                        `bson:"createdAt"`
	UpdatedAt          time.Time                        `bson:"updatedAt"`
}

func documentFrom(value model.CircleGroupMembership) membershipDocument {
	document := membershipDocument{
		ID: value.ID, Version: value.Version, GroupID: value.GroupID, CircleID: value.CircleID,
		PersonaID: value.PersonaID, Role: value.Role, State: value.State,
		DecidedByPersonaID: value.DecidedByPersonaID, CreatedAt: value.CreatedAt.UTC(), UpdatedAt: value.UpdatedAt.UTC(),
	}
	document.JoinedAt = optionalTime(value.JoinedAt)
	document.LeftAt = optionalTime(value.LeftAt)
	document.DecidedAt = optionalTime(value.DecidedAt)
	return document
}

func (document membershipDocument) toModel() model.CircleGroupMembership {
	value := model.CircleGroupMembership{
		ID: document.ID, Version: document.Version, GroupID: document.GroupID, CircleID: document.CircleID,
		PersonaID: document.PersonaID, Role: document.Role, State: document.State,
		DecidedByPersonaID: document.DecidedByPersonaID, CreatedAt: document.CreatedAt.UTC(), UpdatedAt: document.UpdatedAt.UTC(),
	}
	if document.JoinedAt != nil {
		value.JoinedAt = document.JoinedAt.UTC()
	}
	if document.LeftAt != nil {
		value.LeftAt = document.LeftAt.UTC()
	}
	if document.DecidedAt != nil {
		value.DecidedAt = document.DecidedAt.UTC()
	}
	return value
}

func optionalTime(value time.Time) *time.Time {
	if value.IsZero() {
		return nil
	}
	result := value.UTC()
	return &result
}

// groupOwnerPersonaID 在提交事务内读取群主，用于事件 payload 自包含通知
// 接收者；群主缺失（如群主自建事件本身）时返回空串，由通知投影按无接收者跳过。
func (store *MongoAggregateStore) groupOwnerPersonaID(ctx context.Context, groupID string) (string, error) {
	var document struct {
		PersonaID string `bson:"personaId"`
	}
	err := store.memberships.FindOne(
		ctx,
		bson.M{
			"groupId": strings.TrimSpace(groupID),
			"role":    model.CircleGroupMembershipRoleOwner,
			"state":   model.CircleGroupMembershipStateActive,
		},
		options.FindOne().SetProjection(bson.D{{Key: "personaId", Value: 1}}),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(document.PersonaID), nil
}

func eventPayload(value model.CircleGroupMembership, groupOwnerPersonaID string) map[string]any {
	payload := map[string]any{
		"id": value.ID, "version": value.Version, "groupId": value.GroupID, "circleId": value.CircleID,
		"personaId": value.PersonaID, "role": value.Role, "state": value.State,
		"createdAt": value.CreatedAt.UTC(), "updatedAt": value.UpdatedAt.UTC(),
	}
	if !value.JoinedAt.IsZero() {
		payload["joinedAt"] = value.JoinedAt.UTC()
	}
	if !value.LeftAt.IsZero() {
		payload["leftAt"] = value.LeftAt.UTC()
	}
	if !value.DecidedAt.IsZero() {
		payload["decidedAt"] = value.DecidedAt.UTC()
	}
	if groupOwnerPersonaID != "" {
		payload["groupOwnerPersonaId"] = groupOwnerPersonaID
	}
	return payload
}

var _ ports.AggregateStore = (*MongoAggregateStore)(nil)
