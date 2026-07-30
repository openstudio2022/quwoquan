// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001

package api_integration

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	assetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	sessionmodel "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/model"
	sessionports "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
	sessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"
)

func TestMediaUploadCompletionRollsBackSessionWhenAssetCreationFails(t *testing.T) {
	ctx := context.Background()
	database := mongoDB.Client().Database(
		fmt.Sprintf("media_upload_atomic_%d", time.Now().UnixNano()),
	)
	t.Cleanup(func() { _ = database.Drop(context.Background()) })
	store := sessionpersistence.NewMongoStore(
		database.Collection("media_upload_sessions"),
		failingAssetCreationAppender{},
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure upload session indexes: %v", err)
	}
	now := time.Date(2030, time.January, 2, 3, 4, 5, 0, time.UTC)
	session, err := sessionmodel.Create(sessionmodel.CreateParams{
		ID: "mus-atomic", OwnerID: "persona-atomic",
		ObjectKey: "uploads/persona-atomic/mus-atomic.jpg",
		MediaType: "image", MimeType: "image/jpeg", FileSize: 128,
		ExpectedSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ExpiresAt:      now.Add(15 * time.Minute), Now: now,
	})
	if err != nil {
		t.Fatalf("create upload session: %v", err)
	}
	if _, err := store.Commit(ctx, sessionports.Commit{
		Session: session, ExpectedVersion: 0,
		IdempotencyKey: "init-atomic", CommandName: "InitMediaUpload",
		CommandDigest: "digest-init-atomic", ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []sessionports.Event{{
			ID: "evt-init-atomic", Type: "content.media_upload.initialized",
			AggregateType: "MediaUploadSession", AggregateID: session.ID(),
			AggregateVersion: session.Version(), Payload: []byte(`{}`), OccurredAt: now,
		}},
	}); err != nil {
		t.Fatalf("commit initial upload session: %v", err)
	}
	if err := session.Complete(
		"persona-atomic",
		session.ExpectedSHA256(),
		"mas-atomic",
		now.Add(time.Minute),
	); err != nil {
		t.Fatalf("complete upload aggregate: %v", err)
	}
	_, err = store.Complete(ctx, sessionports.CompleteCommit{
		Session: session, ExpectedVersion: 1,
		Asset: assetports.Creation{
			ID: "mas-atomic", Version: 1, OwnerID: "persona-atomic",
			SourceSessionID: "mus-atomic",
			ObjectKey:       "media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpe",
			SHA256:          "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			MediaType:       "image", MimeType: "image/jpeg", FileSize: 128,
			AccessPolicy: "owner_only", ProcessingStatus: "processing",
			CoverStrategy: "first_frame", CreatedAt: now.Add(time.Minute),
			UpdatedAt: now.Add(time.Minute),
		},
		IdempotencyKey: "complete-atomic", CommandName: "CompleteMediaUpload",
		CommandDigest:    "digest-complete-atomic",
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []sessionports.Event{
			{
				ID: "evt-complete-atomic", Type: "content.media_upload.completed",
				AggregateType: "MediaUploadSession", AggregateID: "mus-atomic",
				AggregateVersion: 2, Payload: []byte(`{}`), OccurredAt: now.Add(time.Minute),
			},
			{
				ID: "evt-asset-atomic", Type: "content.media_asset.created",
				AggregateType: "MediaAsset", AggregateID: "mas-atomic",
				AggregateVersion: 1, Payload: []byte(`{}`), OccurredAt: now.Add(time.Minute),
			},
		},
	})
	if !errors.Is(err, errInjectedAssetCreation) {
		t.Fatalf("complete error=%v want injected asset creation failure", err)
	}

	var persisted struct {
		Version int64               `bson:"version"`
		Status  sessionmodel.Status `bson:"status"`
		AssetID string              `bson:"assetId"`
	}
	if err := database.Collection("media_upload_sessions").FindOne(
		ctx,
		bson.M{"_id": "mus-atomic"},
	).Decode(&persisted); err != nil {
		t.Fatalf("reload upload session after rollback: %v", err)
	}
	if persisted.Version != 1 ||
		persisted.Status != sessionmodel.StatusPending ||
		persisted.AssetID != "" {
		t.Fatalf("failed asset creation leaked completed session state: %+v", persisted)
	}
	for collection, filter := range map[string]bson.M{
		"media_upload_session_outbox": {
			"eventType":   "content.media_upload.completed",
			"aggregateId": "mus-atomic",
		},
		"media_upload_session_command_receipts": {"_id": "complete-atomic"},
	} {
		count, err := database.Collection(collection).CountDocuments(ctx, filter)
		if err != nil {
			t.Fatalf("count %s rollback residue: %v", collection, err)
		}
		if count != 0 {
			t.Fatalf("failed completion left %d document(s) in %s", count, collection)
		}
	}
}

var errInjectedAssetCreation = errors.New("injected MediaAsset creation failure")

type failingAssetCreationAppender struct{}

func (failingAssetCreationAppender) AppendCreated(
	context.Context,
	assetports.CreateCommit,
) error {
	return errInjectedAssetCreation
}
