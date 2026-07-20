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

	membershipmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/model"
	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
)

const (
	membershipCollection           = "circle_memberships"
	membershipReceiptCollection    = "circle_membership_command_receipts"
	membershipOutboxCollection     = "circle_membership_outbox"
	membershipSequenceCollection   = "circle_membership_outbox_sequences"
	membershipCheckpointCollection = "circle_membership_projection_checkpoints"
)

type MongoAggregateStore struct {
	memberships *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
	circles     *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("CircleMembership MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		memberships: database.Collection(membershipCollection),
		receipts:    database.Collection(membershipReceiptCollection),
		outbox:      database.Collection(membershipOutboxCollection),
		sequences:   database.Collection(membershipSequenceCollection),
		checkpoints: database.Collection(membershipCheckpointCollection),
		circles:     database.Collection("circles"),
	}
}

// circleOwnerPersonaID 在提交事务内读取圈主，用于事件 payload 自包含通知
// 接收者；圈子缺失时返回空串，由通知投影按无接收者跳过。
func (store *MongoAggregateStore) circleOwnerPersonaID(ctx context.Context, circleID string) (string, error) {
	var document struct {
		OwnerID string `bson:"ownerId"`
	}
	err := store.circles.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(circleID)},
		options.FindOne().SetProjection(bson.D{{Key: "ownerId", Value: 1}}),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(document.OwnerID), nil
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.memberships.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "personaId", Value: 1}}, Options: options.Index().SetName("idx_circle_membership_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "state", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_circle_membership_roster")},
		{Keys: bson.D{{Key: "personaId", Value: 1}, {Key: "state", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_circle_membership_persona")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_circle_membership_receipt_expiry").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_circle_membership_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_membership_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, membershipID string) (membershipmodel.CircleMembership, bool, error) {
	return store.load(ctx, bson.M{"_id": strings.TrimSpace(membershipID)})
}

func (store *MongoAggregateStore) LoadByIdentity(ctx context.Context, circleID, personaID string) (membershipmodel.CircleMembership, bool, error) {
	return store.load(ctx, bson.M{"circleId": strings.TrimSpace(circleID), "personaId": strings.TrimSpace(personaID)})
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request membershipports.CommitRequest) (membershipports.CommitReceipt, error) {
	if err := request.Change.Validate(); err != nil || strings.TrimSpace(request.ReceiptKey) == "" ||
		strings.TrimSpace(request.CommandDigest) == "" || request.ReceiptExpiresAt.IsZero() {
		return membershipports.CommitReceipt{}, membershipmodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.memberships.Database().Client().StartSession()
	if err != nil {
		return membershipports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed membershipports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.LoadByIdentity(txCtx, request.Change.CircleID, request.Change.PersonaID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *membershipmodel.CircleMembership
		if found {
			currentPointer = &current
		}
		next, eventType, applyErr := request.Change.Apply(currentPointer)
		if applyErr != nil {
			return nil, applyErr
		}
		if !found {
			if _, insertErr := store.memberships.InsertOne(txCtx, membershipDocumentFrom(next)); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, membershipmodel.ErrVersionConflict
				}
				return nil, insertErr
			}
		} else {
			result, replaceErr := store.memberships.ReplaceOne(txCtx,
				bson.M{"_id": next.ID, "version": request.Change.ExpectedVersion},
				membershipDocumentFrom(next))
			if replaceErr != nil {
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, membershipmodel.ErrVersionConflict
			}
		}
		var sequence struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := store.sequences.FindOneAndUpdate(txCtx,
			bson.M{"_id": "CircleMembership"}, bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); sequenceErr != nil {
			return nil, sequenceErr
		}
		circleOwnerID, ownerErr := store.circleOwnerPersonaID(txCtx, next.CircleID)
		if ownerErr != nil {
			return nil, ownerErr
		}
		payloadJSON, marshalErr := json.Marshal(membershipEventPayload(next, circleOwnerID))
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
		committed = membershipports.CommitReceipt{
			MembershipID: next.ID, Version: next.Version, State: next.State, Role: next.Role,
		}
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
		return membershipports.CommitReceipt{}, err
	}
	return committed, nil
}

func (store *MongoAggregateStore) load(ctx context.Context, filter any) (membershipmodel.CircleMembership, bool, error) {
	var document membershipDocument
	err := store.memberships.FindOne(ctx, filter).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return membershipmodel.CircleMembership{}, false, nil
	}
	if err != nil {
		return membershipmodel.CircleMembership{}, false, err
	}
	return document.toModel(), true, nil
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, receiptKey, commandDigest string) (membershipports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string                                `bson:"commandDigest"`
		MembershipID  string                                `bson:"membershipId"`
		Version       int64                                 `bson:"version"`
		State         membershipmodel.CircleMembershipState `bson:"state"`
		Role          membershipmodel.CircleMemberRole      `bson:"role"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": receiptKey}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return membershipports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return membershipports.CommitReceipt{}, false, err
	}
	if document.CommandDigest != commandDigest {
		return membershipports.CommitReceipt{}, false, membershipmodel.ErrIdempotencyConflict
	}
	return membershipports.CommitReceipt{
		MembershipID: document.MembershipID, Version: document.Version,
		State: document.State, Role: document.Role, Replayed: true,
	}, true, nil
}

type membershipDocument struct {
	ID           string                                `bson:"_id"`
	Version      int64                                 `bson:"version"`
	CircleID     string                                `bson:"circleId"`
	PersonaID    string                                `bson:"personaId"`
	Role         membershipmodel.CircleMemberRole      `bson:"role"`
	State        membershipmodel.CircleMembershipState `bson:"state"`
	JoinedAt     time.Time                             `bson:"joinedAt"`
	LeftAt       *time.Time                            `bson:"leftAt,omitempty"`
	LastActiveAt *time.Time                            `bson:"lastActiveAt,omitempty"`
	Contribution int64                                 `bson:"contribution"`
	CreatedAt    time.Time                             `bson:"createdAt"`
	UpdatedAt    time.Time                             `bson:"updatedAt"`
}

func membershipDocumentFrom(value membershipmodel.CircleMembership) membershipDocument {
	document := membershipDocument{
		ID: value.ID, Version: value.Version, CircleID: value.CircleID, PersonaID: value.PersonaID,
		Role: value.Role, State: value.State, JoinedAt: value.JoinedAt.UTC(),
		Contribution: value.Contribution, CreatedAt: value.CreatedAt.UTC(), UpdatedAt: value.UpdatedAt.UTC(),
	}
	if !value.LeftAt.IsZero() {
		leftAt := value.LeftAt.UTC()
		document.LeftAt = &leftAt
	}
	if !value.LastActiveAt.IsZero() {
		lastActiveAt := value.LastActiveAt.UTC()
		document.LastActiveAt = &lastActiveAt
	}
	return document
}

func (document membershipDocument) toModel() membershipmodel.CircleMembership {
	value := membershipmodel.CircleMembership{
		ID: document.ID, Version: document.Version, CircleID: document.CircleID, PersonaID: document.PersonaID,
		Role: document.Role, State: document.State, JoinedAt: document.JoinedAt.UTC(),
		Contribution: document.Contribution, CreatedAt: document.CreatedAt.UTC(), UpdatedAt: document.UpdatedAt.UTC(),
	}
	if document.LeftAt != nil {
		value.LeftAt = document.LeftAt.UTC()
	}
	if document.LastActiveAt != nil {
		value.LastActiveAt = document.LastActiveAt.UTC()
	}
	return value
}

func membershipEventPayload(value membershipmodel.CircleMembership, circleOwnerPersonaID string) map[string]any {
	payload := map[string]any{
		"id": value.ID, "version": value.Version, "circleId": value.CircleID,
		"personaId": value.PersonaID, "role": value.Role, "state": value.State,
		"joinedAt": value.JoinedAt.UTC(), "createdAt": value.CreatedAt.UTC(), "updatedAt": value.UpdatedAt.UTC(),
	}
	if !value.LeftAt.IsZero() {
		payload["leftAt"] = value.LeftAt.UTC()
	}
	if circleOwnerPersonaID != "" {
		payload["circleOwnerPersonaId"] = circleOwnerPersonaID
	}
	return payload
}

var _ membershipports.AggregateStore = (*MongoAggregateStore)(nil)
