package releaseimport

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
)

type CommitReceiptReader struct {
	db          *mongo.Database
	environment string
}

func NewCommitReceiptReader(db *mongo.Database, environment string) *CommitReceiptReader {
	return &CommitReceiptReader{db, environment}
}
func (r *CommitReceiptReader) ReadContentReleaseCommitReceipt(ctx context.Context, q wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error) {
	if r == nil || r.db == nil {
		return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryNotReady
	}
	if q.Release.Environment != r.environment || q.Release.SourceOwner != "qwq_data" || q.Expected.Environment != r.environment || q.Expected.SourceOwner != q.Release.SourceOwner || app.ValidateReleaseWireFence(q.Expected) != nil {
		return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryInvalid
	}
	expected := ExpectedActiveRelease{Empty: !q.Expected.Found, SourceOwner: q.Expected.SourceOwner, ReleaseID: q.Expected.ReleaseId, ManifestDigest: q.Expected.ManifestDigest, Revision: q.Expected.Revision}
	target := ImportedReleaseBinding{SourceOwner: q.Release.SourceOwner, ReleaseID: q.Release.ReleaseId, ManifestDigest: q.Release.ManifestDigest}
	return readExactReleaseCommit(ctx, r.db.Collection("data_release_stage_receipts"), r.db.Collection("content_outbox"), q.Release.Environment, target, expected, &q.Expected)
}
func readExactReleaseCommit(ctx context.Context, receipts, outbox *mongo.Collection, environment string, target ImportedReleaseBinding, expected ExpectedActiveRelease, expectedWire *wire.ContentActiveReleaseFence) (wire.ContentReleaseCommitReceipt, error) {
	var stored releaseStageReceipt
	err := receipts.FindOne(ctx, bson.M{"environment": environment, "sourceOwner": target.SourceOwner, "releaseId": target.ReleaseID, "manifestDigest": target.ManifestDigest, "stage": "active", "attemptId": releaseActivationAttemptID(environment, target.SourceOwner, target, expected)}).Decode(&stored)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryNotReady
	}
	if err != nil {
		return wire.ContentReleaseCommitReceipt{}, fmt.Errorf("read Content commit receipt storage: %w", err)
	}
	if stored.Status != "passed" || stored.Checkpoint != "live-closure-and-active-pointer-cas-committed" || stored.Transition == nil || stored.EventID == "" || stored.PayloadDigest == "" {
		return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryNotReady
	}
	if stored.ExpectedEmpty != expected.Empty || stored.ExpectedSourceOwner != expected.SourceOwner || stored.ExpectedReleaseID != expected.ReleaseID || stored.ExpectedManifestDigest != expected.ManifestDigest || stored.ExpectedRevision != expected.Revision {
		return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryInvalid
	}
	result := wire.ContentReleaseCommitReceipt{EventId: stored.EventID, Transition: *stored.Transition, PayloadDigest: stored.PayloadDigest}
	before := result.Transition.Before
	if expectedWire != nil {
		before = *expectedWire
	}
	if before.Found == expected.Empty || before.ReleaseId != expected.ReleaseID || before.ManifestDigest != expected.ManifestDigest || before.Revision != expected.Revision {
		return result, app.ErrReleaseQueryInvalid
	}
	q := wire.ReadContentReleaseCommitReceiptQuery{Release: wire.ReleaseCandidateBinding{Environment: environment, SourceOwner: target.SourceOwner, ReleaseId: target.ReleaseID, ManifestDigest: target.ManifestDigest}, Expected: before}
	if err = app.ValidateReleaseCommitReceipt(q, result); err != nil {
		return wire.ContentReleaseCommitReceipt{}, err
	}
	var event importedOutboxDocument
	if err = outbox.FindOne(ctx, bson.M{"_id": result.EventId}).Decode(&event); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryNotReady
		}
		return wire.ContentReleaseCommitReceipt{}, fmt.Errorf("read Content commit outbox: %w", err)
	}
	raw, _ := json.Marshal(result.Transition)
	a := result.Transition.After
	if !bytes.Equal(raw, event.PayloadJSON) || event.EventType != "ContentReleaseFenceChanged" || event.AggregateType != "Post" || event.AggregateID != environment+"/"+target.SourceOwner || event.AggregateVersion != a.Revision || event.ActivationRevision != a.Revision || event.ReleaseID != target.ReleaseID || event.ManifestDigest != target.ManifestDigest || event.SourceOwner != target.SourceOwner || a.ActivatedAt == nil || !event.OccurredAt.Equal(*a.ActivatedAt) {
		return wire.ContentReleaseCommitReceipt{}, app.ErrReleaseQueryInvalid
	}
	return result, nil
}
