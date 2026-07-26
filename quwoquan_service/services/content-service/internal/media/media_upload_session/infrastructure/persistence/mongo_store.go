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

	contenterrors "quwoquan_service/services/content-service/generated/content/post"
	assetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	sessionmodel "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/model"
	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

// MongoStore is the MediaUploadSession aggregate's durable adapter. Completion
// invokes the MediaAsset-owned append port in the same Mongo transaction,
// preserving session-to-asset atomicity without a Post write path.
type MongoStore struct {
	sessions     *mongo.Collection
	receipts     *mongo.Collection
	outbox       *mongo.Collection
	assetCreator assetports.CreationAppender
}

func NewMongoStore(
	sessions *mongo.Collection,
	assetCreator assetports.CreationAppender,
) *MongoStore {
	if sessions == nil {
		panic("media upload session Mongo store requires media_upload_sessions")
	}
	if assetCreator == nil {
		panic("media upload session Mongo store requires MediaAsset creation appender")
	}
	db := sessions.Database()
	return &MongoStore{
		sessions:     sessions,
		receipts:     db.Collection("media_upload_session_command_receipts"),
		outbox:       db.Collection("media_upload_session_outbox"),
		assetCreator: assetCreator,
	}
}

func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.sessions.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "ownerId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_media_upload_sessions_owner_status"),
		},
		{
			Keys:    bson.D{{Key: "objectKey", Value: 1}},
			Options: options.Index().SetName("idx_media_upload_sessions_object_key").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_media_upload_sessions_expire").SetExpireAfterSeconds(0),
		},
		{
			Keys: bson.D{
				{Key: "_id", Value: 1},
				{Key: "version", Value: 1},
			},
			Options: options.Index().SetName("idx_media_upload_sessions_version").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("create media upload session indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: -1},
			},
			Options: options.Index().SetName("idx_media_upload_session_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_media_upload_session_receipts_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("create media upload session receipt indexes: %w", err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().SetName("idx_media_upload_session_outbox_aggregate_version").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "occurredAt", Value: 1},
				{Key: "_id", Value: 1},
			},
			Options: options.Index().SetName("idx_media_upload_session_outbox_replay"),
		},
	}); err != nil {
		return fmt.Errorf("create media upload session outbox indexes: %w", err)
	}
	return nil
}

type sessionDocument struct {
	ID             string              `bson:"_id"`
	Version        int64               `bson:"version"`
	OwnerID        string              `bson:"ownerId"`
	ObjectKey      string              `bson:"objectKey"`
	MediaType      string              `bson:"mediaType"`
	ContentType    string              `bson:"contentType"`
	FileSize       int64               `bson:"fileSize"`
	ExpectedSHA256 string              `bson:"expectedSha256"`
	AssetID        string              `bson:"assetId,omitempty"`
	Status         sessionmodel.Status `bson:"status"`
	CreatedAt      time.Time           `bson:"createdAt"`
	UpdatedAt      time.Time           `bson:"updatedAt"`
	ExpiresAt      time.Time           `bson:"expiresAt"`
	CompletedAt    *time.Time          `bson:"completedAt,omitempty"`
	AbortedAt      *time.Time          `bson:"abortedAt,omitempty"`
}

type receiptDocument struct {
	ID                    string          `bson:"_id"`
	AggregateID           string          `bson:"aggregateId"`
	AggregateVersion      int64           `bson:"aggregateVersion"`
	CommandName           string          `bson:"commandName"`
	CommandDigest         string          `bson:"commandDigest"`
	Result                sessionDocument `bson:"result"`
	AssetID               string          `bson:"assetId,omitempty"`
	AssetProcessingStatus string          `bson:"assetProcessingStatus,omitempty"`
	AssetObjectKey        string          `bson:"assetObjectKey,omitempty"`
	CreatedAt             time.Time       `bson:"createdAt"`
	ExpiresAt             time.Time       `bson:"expiresAt"`
}

type outboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateType    string    `bson:"aggregateType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

func (s *MongoStore) Load(ctx context.Context, id string) (*sessionmodel.Session, bool, error) {
	var document sessionDocument
	err := s.sessions.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(id)}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load media upload session: %w", err)
	}
	session, err := sessionFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return session, true, nil
}

func (s *MongoStore) FindForOwner(ctx context.Context, id, ownerID string) (sessionmodel.Snapshot, bool, error) {
	var document sessionDocument
	err := s.sessions.FindOne(ctx, bson.D{
		{Key: "_id", Value: strings.TrimSpace(id)},
		{Key: "ownerId", Value: strings.TrimSpace(ownerID)},
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return sessionmodel.Snapshot{}, false, nil
	}
	if err != nil {
		return sessionmodel.Snapshot{}, false, fmt.Errorf("find media upload session: %w", err)
	}
	session, err := sessionFromDocument(document)
	if err != nil {
		return sessionmodel.Snapshot{}, false, err
	}
	return session.Snapshot(), true, nil
}

func (s *MongoStore) FindReceipt(ctx context.Context, key, name, digest string) (ports.Receipt, bool, error) {
	var document receiptDocument
	err := s.receipts.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(key)}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) || (!document.ExpiresAt.IsZero() && !document.ExpiresAt.After(time.Now().UTC())) {
		return ports.Receipt{}, false, nil
	}
	if err != nil {
		return ports.Receipt{}, false, fmt.Errorf("find media upload receipt: %w", err)
	}
	if err := validateReceipt(document.CommandName, document.CommandDigest, name, digest); err != nil {
		return ports.Receipt{}, false, err
	}
	session, err := sessionFromDocument(document.Result)
	if err != nil {
		return ports.Receipt{}, false, err
	}
	return ports.Receipt{
		Session:               session,
		AssetID:               document.AssetID,
		AssetProcessingStatus: document.AssetProcessingStatus,
		ObjectKey:             document.AssetObjectKey,
		Replayed:              true,
	}, true, nil
}

func (s *MongoStore) Commit(ctx context.Context, commit ports.Commit) (ports.Receipt, error) {
	if err := validateCommit(commit); err != nil {
		return ports.Receipt{}, err
	}
	clientSession, err := s.sessions.Database().Client().StartSession()
	if err != nil {
		return ports.Receipt{}, fmt.Errorf("start media upload transaction: %w", err)
	}
	defer clientSession.EndSession(ctx)
	var result ports.Receipt
	_, err = clientSession.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replayed, found, err := s.findReceiptTx(txCtx, commit.IdempotencyKey, commit.CommandName, commit.CommandDigest); err != nil || found {
			result = replayed
			return nil, err
		}
		document := sessionDocumentFromModel(commit.Session)
		if err := s.writeSession(txCtx, document, commit.ExpectedVersion); err != nil {
			return nil, err
		}
		if err := writeOutbox(txCtx, s.outbox, commit.Events); err != nil {
			return nil, err
		}
		if _, err := s.receipts.InsertOne(txCtx, receiptDocument{
			ID: commit.IdempotencyKey, AggregateID: document.ID, AggregateVersion: document.Version,
			CommandName: commit.CommandName, CommandDigest: commit.CommandDigest, Result: document,
			CreatedAt: time.Now().UTC(), ExpiresAt: receiptExpiry(commit.ReceiptExpiresAt),
		}); err != nil {
			return nil, err
		}
		persisted, err := sessionFromDocument(document)
		result = ports.Receipt{Session: persisted}
		return nil, err
	})
	return result, err
}

func (s *MongoStore) Complete(ctx context.Context, commit ports.CompleteCommit) (ports.Receipt, error) {
	if err := validateCompleteCommit(commit); err != nil {
		return ports.Receipt{}, err
	}
	clientSession, err := s.sessions.Database().Client().StartSession()
	if err != nil {
		return ports.Receipt{}, fmt.Errorf("start media completion transaction: %w", err)
	}
	defer clientSession.EndSession(ctx)
	var result ports.Receipt
	_, err = clientSession.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replayed, found, err := s.findReceiptTx(txCtx, commit.IdempotencyKey, commit.CommandName, commit.CommandDigest); err != nil || found {
			result = replayed
			return nil, err
		}
		sessionDocument := sessionDocumentFromModel(commit.Session)
		if err := s.writeSession(txCtx, sessionDocument, commit.ExpectedVersion); err != nil {
			return nil, err
		}
		if err := writeOutbox(txCtx, s.outbox, commit.Events[:1]); err != nil {
			return nil, err
		}
		assetEvent := commit.Events[1]
		if err := s.assetCreator.AppendCreated(txCtx, assetports.CreateCommit{
			Asset:            commit.Asset,
			IdempotencyKey:   commit.IdempotencyKey,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			ReceiptExpiresAt: commit.ReceiptExpiresAt,
			Event: assetports.CreatedEvent{
				ID:               assetEvent.ID,
				Type:             assetEvent.Type,
				AggregateID:      assetEvent.AggregateID,
				AggregateVersion: assetEvent.AggregateVersion,
				Payload:          append([]byte(nil), assetEvent.Payload...),
				OccurredAt:       assetEvent.OccurredAt,
			},
		}); err != nil {
			return nil, err
		}
		expiresAt := receiptExpiry(commit.ReceiptExpiresAt)
		if _, err := s.receipts.InsertOne(txCtx, receiptDocument{
			ID: commit.IdempotencyKey, AggregateID: sessionDocument.ID, AggregateVersion: sessionDocument.Version,
			CommandName: commit.CommandName, CommandDigest: commit.CommandDigest, Result: sessionDocument,
			AssetID: commit.Asset.ID, AssetProcessingStatus: commit.Asset.ProcessingStatus,
			AssetObjectKey: commit.Asset.ObjectKey,
			CreatedAt:      time.Now().UTC(), ExpiresAt: expiresAt,
		}); err != nil {
			return nil, err
		}
		result = ports.Receipt{
			Session:               commit.Session,
			AssetID:               commit.Asset.ID,
			AssetProcessingStatus: commit.Asset.ProcessingStatus,
			ObjectKey:             commit.Asset.ObjectKey,
		}
		return nil, nil
	})
	return result, err
}

func (s *MongoStore) findReceiptTx(ctx context.Context, key, name, digest string) (ports.Receipt, bool, error) {
	return s.FindReceipt(ctx, key, name, digest)
}

func (s *MongoStore) writeSession(ctx context.Context, document sessionDocument, expectedVersion int64) error {
	if expectedVersion == 0 {
		_, err := s.sessions.InsertOne(ctx, document)
		return err
	}
	result, err := s.sessions.ReplaceOne(ctx, bson.D{{Key: "_id", Value: document.ID}, {Key: "version", Value: expectedVersion}}, document)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return contenterrors.AppErrorFromVersionConflict("media upload session version changed before commit")
	}
	return nil
}

func writeOutbox(ctx context.Context, collection *mongo.Collection, events []ports.Event) error {
	for _, event := range events {
		if _, err := collection.InsertOne(ctx, outboxDocument{
			ID: event.ID, EventType: event.Type, AggregateType: event.AggregateType, AggregateID: event.AggregateID,
			AggregateVersion: event.AggregateVersion, Payload: append([]byte(nil), event.Payload...), OccurredAt: event.OccurredAt.UTC(),
		}); err != nil {
			return err
		}
	}
	return nil
}

func sessionDocumentFromModel(session *sessionmodel.Session) sessionDocument {
	snapshot := session.Snapshot()
	return sessionDocument{
		ID: snapshot.ID, Version: snapshot.Version, OwnerID: snapshot.OwnerID, ObjectKey: snapshot.ObjectKey,
		MediaType: snapshot.MediaType, ContentType: snapshot.ContentType, FileSize: snapshot.FileSize,
		ExpectedSHA256: snapshot.ExpectedSHA256, AssetID: snapshot.AssetID, Status: snapshot.Status,
		CreatedAt: snapshot.CreatedAt, UpdatedAt: snapshot.UpdatedAt, ExpiresAt: snapshot.ExpiresAt,
		CompletedAt: snapshot.CompletedAt, AbortedAt: snapshot.AbortedAt,
	}
}

func sessionFromDocument(document sessionDocument) (*sessionmodel.Session, error) {
	session, err := sessionmodel.Restore(sessionmodel.Snapshot{
		ID: document.ID, Version: document.Version, OwnerID: document.OwnerID, ObjectKey: document.ObjectKey,
		MediaType: document.MediaType, ContentType: document.ContentType, FileSize: document.FileSize,
		ExpectedSHA256: document.ExpectedSHA256, AssetID: document.AssetID, Status: document.Status,
		CreatedAt: document.CreatedAt, UpdatedAt: document.UpdatedAt, ExpiresAt: document.ExpiresAt,
		CompletedAt: document.CompletedAt, AbortedAt: document.AbortedAt,
	})
	if err != nil {
		return nil, fmt.Errorf("restore media upload session: %w", err)
	}
	return session, nil
}

func validateCommit(commit ports.Commit) error {
	if commit.Session == nil || commit.ExpectedVersion < 0 || commit.Session.Version() != commit.ExpectedVersion+1 ||
		strings.TrimSpace(commit.IdempotencyKey) == "" || strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" || len(commit.Events) != 1 {
		return contenterrors.AppErrorFromVersionConflict("invalid media upload session commit")
	}
	return validateEvent(commit.Events[0], "MediaUploadSession", commit.Session.ID(), commit.Session.Version())
}

func validateCompleteCommit(commit ports.CompleteCommit) error {
	if commit.Session == nil || commit.ExpectedVersion < 1 || commit.Session.Version() != commit.ExpectedVersion+1 ||
		strings.TrimSpace(commit.Asset.ID) == "" || commit.Asset.Version != 1 ||
		strings.TrimSpace(commit.Asset.ObjectKey) == "" || strings.TrimSpace(commit.Asset.SHA256) == "" ||
		commit.Asset.SourceSessionID != commit.Session.ID() ||
		commit.Asset.OwnerID != commit.Session.OwnerID() ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" || strings.TrimSpace(commit.CommandDigest) == "" || len(commit.Events) != 2 {
		return contenterrors.AppErrorFromVersionConflict("invalid complete media upload commit")
	}
	if err := validateEvent(commit.Events[0], "MediaUploadSession", commit.Session.ID(), commit.Session.Version()); err != nil {
		return err
	}
	return validateEvent(
		commit.Events[1],
		"MediaAsset",
		commit.Asset.ID,
		commit.Asset.Version,
	)
}

func validateEvent(event ports.Event, aggregateType, aggregateID string, version int64) error {
	if strings.TrimSpace(event.ID) == "" || strings.TrimSpace(event.Type) == "" || event.OccurredAt.IsZero() ||
		event.AggregateType != aggregateType || event.AggregateID != aggregateID || event.AggregateVersion != version {
		return contenterrors.AppErrorFromVersionConflict("media upload outbox does not match aggregate commit")
	}
	return nil
}

func validateReceipt(actualName, actualDigest, expectedName, expectedDigest string) error {
	if actualName != expectedName || actualDigest != expectedDigest {
		return contenterrors.AppErrorFromIdempotencyConflict("idempotency key was reused with a different media command")
	}
	return nil
}

func receiptExpiry(value time.Time) time.Time {
	if value.IsZero() {
		return time.Now().UTC().Add(24 * time.Hour)
	}
	return value.UTC()
}

var _ ports.Store = (*MongoStore)(nil)
