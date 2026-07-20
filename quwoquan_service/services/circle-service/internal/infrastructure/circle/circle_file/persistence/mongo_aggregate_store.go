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

	filemodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/model"
	fileports "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/ports"
)

const (
	fileCollection           = "circle_files"
	fileReceiptCollection    = "circle_files_command_receipts"
	fileOutboxCollection     = "circle_files_outbox"
	fileSequenceCollection   = "circle_files_outbox_sequences"
	fileCheckpointCollection = "circle_files_projection_checkpoints"
	fileQuotaLockCollection  = "circle_files_quota_locks"
)

type MongoAggregateStore struct {
	files       *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
	quotaLocks  *mongo.Collection
}

func NewMongoAggregateStore(database *mongo.Database) *MongoAggregateStore {
	if database == nil {
		panic("CircleFile MongoAggregateStore requires database")
	}
	return &MongoAggregateStore{
		files: database.Collection(fileCollection), receipts: database.Collection(fileReceiptCollection),
		outbox: database.Collection(fileOutboxCollection), sequences: database.Collection(fileSequenceCollection),
		checkpoints: database.Collection(fileCheckpointCollection), quotaLocks: database.Collection(fileQuotaLockCollection),
	}
}

func (store *MongoAggregateStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.files.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "circleId", Value: 1}, {Key: "groupId", Value: 1}, {Key: "parentFolderId", Value: 1}, {Key: "status", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_circle_file_list")},
		{Keys: bson.D{{Key: "assetId", Value: 1}, {Key: "status", Value: 1}}, Options: options.Index().SetName("idx_circle_file_asset")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("idx_circle_file_receipt_expiry").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_circle_file_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_circle_file_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoAggregateStore) Load(ctx context.Context, fileID string) (filemodel.CircleFile, bool, error) {
	var value filemodel.CircleFile
	err := store.files.FindOne(ctx, bson.M{"_id": strings.TrimSpace(fileID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return filemodel.CircleFile{}, false, nil
	}
	if err != nil {
		return filemodel.CircleFile{}, false, err
	}
	return value, true, nil
}

func (store *MongoAggregateStore) Commit(ctx context.Context, request fileports.CommitRequest) (fileports.CommitReceipt, error) {
	if strings.TrimSpace(request.Change.FileID) == "" || strings.TrimSpace(request.Change.CircleID) == "" ||
		strings.TrimSpace(request.ReceiptKey) == "" || strings.TrimSpace(request.CommandDigest) == "" ||
		request.ReceiptExpiresAt.IsZero() || request.StorageQuota <= 0 {
		return fileports.CommitReceipt{}, filemodel.ErrInvalidChange
	}
	if replay, found, err := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); err != nil || found {
		return replay, err
	}
	session, err := store.files.Database().Client().StartSession()
	if err != nil {
		return fileports.CommitReceipt{}, err
	}
	defer session.EndSession(ctx)
	var committed fileports.CommitReceipt
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, findErr := store.findReceipt(txCtx, request.ReceiptKey, request.CommandDigest); findErr != nil {
			return nil, findErr
		} else if found {
			committed = replay
			return nil, nil
		}
		current, found, loadErr := store.Load(txCtx, request.Change.FileID)
		if loadErr != nil {
			return nil, loadErr
		}
		var currentPointer *filemodel.CircleFile
		if found {
			currentPointer = &current
		}
		if err := store.validateParentChain(txCtx, request.Change); err != nil {
			return nil, err
		}
		if request.Change.Kind == filemodel.ChangeCreate && request.Change.SizeBytes > 0 {
			if err := store.validateQuota(txCtx, request.Change.CircleID, request.Change.SizeBytes, request.StorageQuota); err != nil {
				return nil, err
			}
		}
		next, applyErr := filemodel.Apply(currentPointer, request.Change)
		if applyErr != nil {
			return nil, applyErr
		}
		if !found {
			if _, insertErr := store.files.InsertOne(txCtx, next); insertErr != nil {
				return nil, insertErr
			}
		} else {
			result, replaceErr := store.files.ReplaceOne(txCtx,
				bson.M{"_id": next.ID, "version": request.Change.ExpectedVersion}, next)
			if replaceErr != nil {
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, filemodel.ErrVersionConflict
			}
		}
		var sequence struct {
			Value int64 `bson:"value"`
		}
		if sequenceErr := store.sequences.FindOneAndUpdate(txCtx,
			bson.M{"_id": "CircleFile"}, bson.M{"$inc": bson.M{"value": int64(1)}},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); sequenceErr != nil {
			return nil, sequenceErr
		}
		eventType := fileEventType(request.Change.Kind)
		payloadJSON, marshalErr := json.Marshal(fileEventPayload{
			FileID: next.ID, Version: next.Version, CircleID: next.CircleID, GroupID: next.GroupID,
			ParentFolderID: next.ParentFolderID, Name: next.Name, FileType: next.FileType,
			AssetID: next.AssetID, UploaderPersonaID: next.UploaderPersonaID,
			Status: next.Status, OccurredAt: next.UpdatedAt.UTC(),
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
		committed = fileports.CommitReceipt{FileID: next.ID, Version: next.Version, Status: next.Status}
		_, insertErr := store.receipts.InsertOne(txCtx, bson.M{
			"_id": request.ReceiptKey, "commandDigest": request.CommandDigest,
			"fileId": next.ID, "version": next.Version, "status": next.Status,
			"expiresAt": request.ReceiptExpiresAt.UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if replay, found, replayErr := store.findReceipt(ctx, request.ReceiptKey, request.CommandDigest); replayErr == nil && found {
			return replay, nil
		}
		return fileports.CommitReceipt{}, err
	}
	return committed, nil
}

func (store *MongoAggregateStore) validateQuota(ctx context.Context, circleID string, added, quota int64) error {
	if _, err := store.quotaLocks.UpdateOne(ctx, bson.M{"_id": strings.TrimSpace(circleID)},
		bson.M{"$inc": bson.M{"revision": int64(1)}, "$set": bson.M{"updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true)); err != nil {
		return err
	}
	rows, err := store.files.Aggregate(ctx, mongo.Pipeline{
		{{Key: "$match", Value: bson.M{"circleId": strings.TrimSpace(circleID), "fileType": filemodel.CircleFileTypeFile, "status": filemodel.CircleFileStatusActive}}},
		{{Key: "$group", Value: bson.M{"_id": nil, "used": bson.M{"$sum": "$sizeBytes"}}}},
	})
	if err != nil {
		return err
	}
	defer rows.Close(ctx)
	var used int64
	if rows.Next(ctx) {
		var result struct {
			Used int64 `bson:"used"`
		}
		if err := rows.Decode(&result); err != nil {
			return err
		}
		used = result.Used
	}
	if err := rows.Err(); err != nil {
		return err
	}
	if added > quota || used > quota-added {
		return filemodel.ErrQuotaExceeded
	}
	return nil
}

func (store *MongoAggregateStore) validateParentChain(ctx context.Context, change filemodel.ChangeSet) error {
	if change.ParentFolderID == nil || strings.TrimSpace(*change.ParentFolderID) == "" {
		return nil
	}
	parentID := strings.TrimSpace(*change.ParentFolderID)
	seen := map[string]struct{}{change.FileID: {}}
	for depth := 0; depth < 64 && parentID != ""; depth++ {
		if _, exists := seen[parentID]; exists {
			return filemodel.ErrParentInvalid
		}
		seen[parentID] = struct{}{}
		var parent filemodel.CircleFile
		err := store.files.FindOne(ctx, bson.M{
			"_id": parentID, "circleId": change.CircleID, "groupId": change.GroupID,
			"fileType": filemodel.CircleFileTypeFolder, "status": filemodel.CircleFileStatusActive,
		}).Decode(&parent)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return filemodel.ErrParentInvalid
		}
		if err != nil {
			return err
		}
		parentID = strings.TrimSpace(parent.ParentFolderID)
	}
	if parentID != "" {
		return filemodel.ErrParentInvalid
	}
	return nil
}

// RecordNoopReceipt 落"目标状态已满足"回执：不递增 version、不写 outbox。
func (store *MongoAggregateStore) RecordNoopReceipt(ctx context.Context, noop fileports.NoopReceipt) (fileports.CommitReceipt, error) {
	if strings.TrimSpace(noop.FileID) == "" ||
		strings.TrimSpace(noop.ReceiptKey) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return fileports.CommitReceipt{}, filemodel.ErrInvalidChange
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
		"fileId": noop.FileID, "version": noop.Version, "status": noop.Status,
		"expiresAt": expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			if replay, found, replayErr := store.findReceipt(ctx, noop.ReceiptKey, noop.CommandDigest); replayErr == nil && found {
				return replay, nil
			}
		}
		return fileports.CommitReceipt{}, err
	}
	return fileports.CommitReceipt{
		FileID: noop.FileID, Version: noop.Version, Status: noop.Status,
	}, nil
}

func (store *MongoAggregateStore) findReceipt(ctx context.Context, key, digest string) (fileports.CommitReceipt, bool, error) {
	var document struct {
		CommandDigest string                     `bson:"commandDigest"`
		FileID        string                     `bson:"fileId"`
		Version       int64                      `bson:"version"`
		Status        filemodel.CircleFileStatus `bson:"status"`
	}
	err := store.receipts.FindOne(ctx, bson.M{"_id": key}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return fileports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return fileports.CommitReceipt{}, false, err
	}
	if document.CommandDigest != digest {
		return fileports.CommitReceipt{}, false, filemodel.ErrIdempotencyConflict
	}
	return fileports.CommitReceipt{FileID: document.FileID, Version: document.Version, Status: document.Status, Replayed: true}, true, nil
}

func fileEventType(kind filemodel.ChangeKind) string {
	switch kind {
	case filemodel.ChangeCreate:
		return "CircleFileCreated"
	case filemodel.ChangeDelete:
		return "CircleFileDeleted"
	default:
		return "CircleFileUpdated"
	}
}

type fileEventPayload struct {
	FileID            string                     `json:"id"`
	Version           int64                      `json:"version"`
	CircleID          string                     `json:"circleId"`
	GroupID           string                     `json:"groupId,omitempty"`
	ParentFolderID    string                     `json:"parentFolderId,omitempty"`
	Name              string                     `json:"name"`
	FileType          filemodel.CircleFileType   `json:"fileType"`
	AssetID           string                     `json:"assetId,omitempty"`
	UploaderPersonaID string                     `json:"uploaderPersonaId"`
	Status            filemodel.CircleFileStatus `json:"status"`
	OccurredAt        time.Time                  `json:"occurredAt"`
}

var _ fileports.AggregateStore = (*MongoAggregateStore)(nil)
