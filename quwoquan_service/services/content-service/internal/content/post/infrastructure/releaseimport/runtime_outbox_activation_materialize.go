package releaseimport

import (
	"bytes"
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// 本文件承载 ActivateImportedPostRelease 的事务内物化与 CAS 内部步骤：候选闭包校验、
// posts/media 原子物化与 tombstone、outbox/live 闭包校验、active pointer 读取与 CAS。
// 与 runtime_outbox.go 同包同语义，仅按体积拆分。

func ensureReleaseActivationIndexes(
	ctx context.Context,
	candidatePosts *mongo.Collection,
	candidateOutbox *mongo.Collection,
	candidateMedia *mongo.Collection,
	livePosts *mongo.Collection,
	liveOutbox *mongo.Collection,
	liveMedia *mongo.Collection,
	state *mongo.Collection,
	receipts *mongo.Collection,
) error {
	if err := ensureImportedReleaseIndexes(
		ctx, candidatePosts, candidateOutbox, candidateMedia, state, receipts,
	); err != nil {
		return err
	}
	if _, err := livePosts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "postRef", Value: 1}},
		Options: options.Index().SetName("idx_post_ref").SetUnique(true).SetSparse(true),
	}); err != nil {
		return fmt.Errorf("ensure live imported Post identity index: %w", err)
	}
	if _, err := liveOutbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_content_outbox_sequence").SetUnique(true)},
		{Keys: bson.D{{Key: "aggregateType", Value: 1}, {Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_content_outbox_aggregate_version").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("ensure live imported Post outbox indexes: %w", err)
	}
	if _, err := liveMedia.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "sourceSessionId", Value: 1}},
		Options: options.Index().SetName("idx_media_assets_source_session").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure live release MediaAsset source session index: %w", err)
	}
	return nil
}

func validateStoredCandidateClosure(
	ctx context.Context,
	candidatePosts *mongo.Collection,
	candidateFacts *mongo.Collection,
	candidateMedia *mongo.Collection,
	candidate importedReleaseCandidateState,
) error {
	checks := []struct {
		collection    *mongo.Collection
		expected      string
		expectedCount int
		label         string
	}{
		{candidatePosts, candidate.PostClosureDigest, candidate.Counts.PostsProjected, "Post"},
		{candidateFacts, candidate.FactClosureDigest, candidate.Counts.OutboxProjected, "fact"},
		{candidateMedia, candidate.MediaClosureDigest, candidate.Counts.MediaProjected, "media"},
	}
	for _, check := range checks {
		if !sha256Pattern.MatchString(check.expected) {
			return fmt.Errorf("GATE_BLOCK: candidate %s closure digest is invalid", check.label)
		}
		cursor, err := check.collection.Find(ctx, releaseCandidateFilter(candidate))
		if err != nil {
			return err
		}
		actualCount := 0
		for cursor.Next(ctx) {
			var document bson.M
			if err := cursor.Decode(&document); err != nil {
				_ = cursor.Close(ctx)
				return err
			}
			stored, _ := document["documentDigest"].(string)
			actual, err := canonicalDocumentDigest(document, "documentDigest")
			if err != nil || !sha256Pattern.MatchString(stored) || actual != stored {
				_ = cursor.Close(ctx)
				return fmt.Errorf("GATE_BLOCK: candidate %s document digest drift", check.label)
			}
			actualCount++
		}
		if err := cursor.Err(); err != nil {
			_ = cursor.Close(ctx)
			return err
		}
		if err := cursor.Close(ctx); err != nil {
			return err
		}
		if actualCount != check.expectedCount {
			return fmt.Errorf("GATE_BLOCK: candidate %s closure count mismatch", check.label)
		}
		actualClosure, err := collectionClosureDigest(ctx, check.collection, releaseCandidateFilter(candidate))
		if err != nil || actualClosure != check.expected {
			return fmt.Errorf("GATE_BLOCK: candidate %s closure digest drift", check.label)
		}
	}
	return nil
}

func materializeCandidatePosts(
	ctx context.Context,
	candidates *mongo.Collection,
	live *mongo.Collection,
	candidate importedReleaseCandidateState,
	activationVersion int64,
) (int, []PostDoc, error) {
	cursor, err := candidates.Find(
		ctx, releaseCandidateFilter(candidate), options.Find().SetSort(bson.D{{Key: "postId", Value: 1}}),
	)
	if err != nil {
		return 0, nil, fmt.Errorf("read candidate Posts for activation: %w", err)
	}
	defer cursor.Close(ctx)
	materialized := 0
	posts := make([]PostDoc, 0, candidate.Counts.PostsProjected)
	for cursor.Next(ctx) {
		var candidateDocument bson.M
		if err := cursor.Decode(&candidateDocument); err != nil {
			return materialized, nil, fmt.Errorf("decode candidate Post for activation: %w", err)
		}
		storedDigest, _ := candidateDocument["documentDigest"].(string)
		actualDigest, err := canonicalDocumentDigest(candidateDocument, "documentDigest")
		if err != nil || storedDigest == "" || storedDigest != actualDigest {
			return materialized, nil, fmt.Errorf("GATE_BLOCK: candidate Post document digest drift")
		}
		postID, _ := candidateDocument["postId"].(string)
		postID = strings.TrimSpace(postID)
		if postID == "" {
			return materialized, nil, fmt.Errorf("GATE_BLOCK: candidate Post has no stable runtime postId")
		}
		var post PostDoc
		raw, err := bson.Marshal(candidateDocument)
		if err != nil || bson.Unmarshal(raw, &post) != nil {
			return materialized, nil, fmt.Errorf("decode candidate Post %q transition facts", postID)
		}
		posts = append(posts, post)
		liveDocument := bson.M{}
		for key, value := range candidateDocument {
			if key == "environment" || key == "documentDigest" {
				continue
			}
			liveDocument[key] = value
		}
		liveDocument["_id"] = postID
		liveDocument["lifecycleStatus"] = "active"
		liveDocument["version"] = activationVersion
		var existing struct {
			SourceOwner string `bson:"sourceOwner"`
		}
		err = live.FindOne(ctx, bson.M{"_id": postID}, options.FindOne().SetProjection(bson.M{"sourceOwner": 1})).Decode(&existing)
		switch {
		case err == mongo.ErrNoDocuments:
			if _, err := live.InsertOne(ctx, liveDocument); err != nil {
				return materialized, nil, fmt.Errorf("insert candidate Post %q into live: %w", postID, err)
			}
		case err != nil:
			return materialized, nil, fmt.Errorf("read live Post %q owner: %w", postID, err)
		case existing.SourceOwner != candidate.SourceOwner:
			return materialized, nil, fmt.Errorf("GATE_BLOCK: live Post %q is not Data-owned", postID)
		default:
			if _, err := live.ReplaceOne(ctx, bson.M{"_id": postID, "sourceOwner": candidate.SourceOwner}, liveDocument); err != nil {
				return materialized, nil, fmt.Errorf("replace Data-owned live Post %q: %w", postID, err)
			}
		}
		materialized++
	}
	if err := cursor.Err(); err != nil {
		return materialized, nil, fmt.Errorf("scan candidate Posts for activation: %w", err)
	}
	if materialized != candidate.Counts.PostsProjected {
		return materialized, nil, fmt.Errorf("GATE_BLOCK: candidate Post materialization count mismatch")
	}
	return materialized, posts, nil
}

func detectLivePostIdentityConflicts(
	ctx context.Context,
	candidates *mongo.Collection,
	live *mongo.Collection,
	candidate importedReleaseCandidateState,
) error {
	cursor, err := candidates.Find(
		ctx, releaseCandidateFilter(candidate),
		options.Find().SetProjection(bson.M{"postId": 1, "postRef": 1}),
	)
	if err != nil {
		return fmt.Errorf("read candidate Post identities: %w", err)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var identity struct {
			PostID  string `bson:"postId"`
			PostRef string `bson:"postRef"`
		}
		if err := cursor.Decode(&identity); err != nil {
			return fmt.Errorf("decode candidate Post identity: %w", err)
		}
		var existing struct {
			ID          string `bson:"_id"`
			SourceOwner string `bson:"sourceOwner"`
			ContentID   string `bson:"contentId"`
		}
		err := live.FindOne(ctx, bson.M{
			"$or": bson.A{bson.M{"_id": identity.PostID}, bson.M{"postRef": identity.PostRef}},
		}, options.FindOne().SetProjection(bson.M{"_id": 1, "sourceOwner": 1, "contentId": 1})).Decode(&existing)
		if err == mongo.ErrNoDocuments {
			continue
		}
		if err != nil {
			return fmt.Errorf("read live Post identity conflict: %w", err)
		}
		if existing.ID != identity.PostID ||
			(strings.TrimSpace(existing.SourceOwner) != "" && existing.SourceOwner != candidate.SourceOwner) {
			return fmt.Errorf(
				"GATE_BLOCK: candidate Post identity conflicts with live Post %q",
				existing.ID,
			)
		}
	}
	if err := cursor.Err(); err != nil {
		return fmt.Errorf("scan candidate Post identities: %w", err)
	}
	return nil
}

func tombstoneMissingLivePosts(
	ctx context.Context,
	live *mongo.Collection,
	candidate importedReleaseCandidateState,
	activatedAt time.Time,
) ([]ImportedPostDeletionSnapshot, error) {
	var targetIDs []string
	cursor, err := live.Find(ctx, bson.M{
		"sourceOwner": candidate.SourceOwner, "releaseId": candidate.ReleaseID,
		"manifestDigest": candidate.ManifestDigest, "lifecycleStatus": "active",
	}, options.Find().SetProjection(bson.M{"_id": 1}))
	if err != nil {
		return nil, fmt.Errorf("read materialized target Post identities: %w", err)
	}
	for cursor.Next(ctx) {
		var row struct {
			ID string `bson:"_id"`
		}
		if err := cursor.Decode(&row); err != nil {
			_ = cursor.Close(ctx)
			return nil, err
		}
		targetIDs = append(targetIDs, row.ID)
	}
	if err := cursor.Close(ctx); err != nil {
		return nil, err
	}
	filter := bson.M{
		"sourceOwner":     candidate.SourceOwner,
		"releaseId":       bson.M{"$ne": candidate.ReleaseID},
		"lifecycleStatus": "active",
		"_id":             bson.M{"$nin": targetIDs},
	}
	cursor, err = live.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return nil, fmt.Errorf("read previous active Posts for tombstone: %w", err)
	}
	defer cursor.Close(ctx)
	snapshots := make([]ImportedPostDeletionSnapshot, 0)
	for cursor.Next(ctx) {
		var row struct {
			ID              string `bson:"_id"`
			AuthorID        string `bson:"authorId"`
			ContentType     string `bson:"contentType"`
			ContentIdentity string `bson:"contentIdentity"`
			Status          string `bson:"status"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, fmt.Errorf("decode previous active Post for tombstone: %w", err)
		}
		identity, err := canonicalImportedContentIdentity(row.ContentIdentity)
		if err != nil {
			return nil, fmt.Errorf("previous active Post %q: %w", row.ID, err)
		}
		if strings.TrimSpace(row.ID) == "" || strings.TrimSpace(row.AuthorID) == "" ||
			strings.TrimSpace(row.ContentType) == "" || strings.TrimSpace(row.Status) == "" {
			return nil, fmt.Errorf("GATE_BLOCK: previous active Post lacks deletion lifecycle fields")
		}
		snapshots = append(snapshots, ImportedPostDeletionSnapshot{
			PostID: row.ID, AuthorID: row.AuthorID, ContentType: row.ContentType,
			ContentIdentity: identity, Status: "published",
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("scan previous active Posts for tombstone: %w", err)
	}
	if len(snapshots) == 0 {
		return snapshots, nil
	}
	ids := make([]string, 0, len(snapshots))
	for _, snapshot := range snapshots {
		ids = append(ids, snapshot.PostID)
	}
	update, err := live.UpdateMany(ctx, bson.M{"_id": bson.M{"$in": ids}}, bson.M{"$set": bson.M{
		"status": "deleted", "visibility": "hidden", "lifecycleStatus": "tombstone",
		"deletedAt": activatedAt, "deletedByReleaseId": candidate.ReleaseID,
		"updatedAt": activatedAt,
	}})
	if err != nil {
		return nil, fmt.Errorf("tombstone previous active Posts: %w", err)
	}
	if update.ModifiedCount != int64(len(snapshots)) {
		return nil, fmt.Errorf(
			"GATE_BLOCK: previous Post tombstone count mismatch: expected=%d modified=%d",
			len(snapshots), update.ModifiedCount,
		)
	}
	return snapshots, nil
}

func materializeCandidateMedia(
	ctx context.Context,
	candidates *mongo.Collection,
	live *mongo.Collection,
	candidate importedReleaseCandidateState,
) (int, error) {
	cursor, err := candidates.Find(
		ctx, releaseCandidateFilter(candidate), options.Find().SetSort(bson.D{{Key: "assetId", Value: 1}}),
	)
	if err != nil {
		return 0, fmt.Errorf("read candidate media for activation: %w", err)
	}
	defer cursor.Close(ctx)
	materialized := 0
	for cursor.Next(ctx) {
		var document bson.M
		if err := cursor.Decode(&document); err != nil {
			return materialized, fmt.Errorf("decode candidate media for activation: %w", err)
		}
		storedDigest, _ := document["documentDigest"].(string)
		actualDigest, err := canonicalDocumentDigest(document, "documentDigest")
		if err != nil || storedDigest == "" || storedDigest != actualDigest {
			return materialized, fmt.Errorf("GATE_BLOCK: candidate media document digest drift")
		}
		assetID, _ := document["assetId"].(string)
		ownerID, _ := document["ownerId"].(string)
		sessionID, _ := document["sourceSessionId"].(string)
		sha256Value, _ := document["sha256"].(string)
		assetID, ownerID = strings.TrimSpace(assetID), strings.TrimSpace(ownerID)
		if assetID == "" || ownerID != candidate.SourceOwner {
			return materialized, fmt.Errorf("GATE_BLOCK: candidate media owner binding is incomplete")
		}
		var existing struct {
			ID              string `bson:"_id"`
			OwnerID         string `bson:"ownerId"`
			SourceSessionID string `bson:"sourceSessionId"`
			SHA256          string `bson:"sha256"`
		}
		err = live.FindOne(ctx, bson.M{
			"$or": bson.A{bson.M{"_id": assetID}, bson.M{"sourceSessionId": sessionID}},
		}, options.FindOne().SetProjection(bson.M{"_id": 1, "ownerId": 1, "sourceSessionId": 1, "sha256": 1})).Decode(&existing)
		if err != nil && err != mongo.ErrNoDocuments {
			return materialized, fmt.Errorf("inspect live media ownership: %w", err)
		}
		if err == nil && (existing.ID != assetID || existing.OwnerID != candidate.SourceOwner ||
			existing.SourceSessionID != sessionID || existing.SHA256 != sha256Value) {
			return materialized, fmt.Errorf("GATE_BLOCK: live MediaAsset %q ownership or digest conflicts", assetID)
		}
		ownedSet := bson.M{
			"ownerId": candidate.SourceOwner, "sourceSessionId": sessionID,
			"objectKey": document["objectKey"], "sha256": sha256Value,
			"mediaType": document["mediaType"], "mimeType": document["mimeType"],
			"fileSize": document["fileSize"], "accessPolicy": document["accessPolicy"],
			"processingStatus": "ready", "sourceReleaseId": candidate.ReleaseID,
			"sourceManifestDigest": candidate.ManifestDigest, "updatedAt": document["updatedAt"],
		}
		if err == mongo.ErrNoDocuments {
			ownedSet["_id"] = assetID
			ownedSet["version"] = document["version"]
			ownedSet["createdAt"] = document["createdAt"]
			if _, err := live.InsertOne(ctx, ownedSet); err != nil {
				return materialized, fmt.Errorf("insert Data MediaAsset %q: %w", assetID, err)
			}
		} else {
			result, err := live.UpdateOne(ctx, bson.M{
				"_id": assetID, "ownerId": candidate.SourceOwner,
				"sourceSessionId": sessionID, "sha256": sha256Value,
			}, bson.M{"$set": ownedSet})
			if err != nil {
				return materialized, fmt.Errorf("update Data MediaAsset %q: %w", assetID, err)
			}
			if result.MatchedCount != 1 {
				return materialized, fmt.Errorf("GATE_BLOCK: Data MediaAsset owner-bound update lost")
			}
		}
		materialized++
	}
	if err := cursor.Err(); err != nil {
		return materialized, fmt.Errorf("scan candidate media for activation: %w", err)
	}
	if materialized != candidate.Counts.MediaProjected {
		return materialized, fmt.Errorf("GATE_BLOCK: candidate media materialization count mismatch")
	}
	return materialized, nil
}

func tombstoneMissingLiveMedia(
	ctx context.Context,
	live *mongo.Collection,
	candidate importedReleaseCandidateState,
	tombstonedAt time.Time,
) (int64, error) {
	targetIDs := make([]string, 0)
	cursor, err := live.Find(ctx, bson.M{
		"ownerId": candidate.SourceOwner, "sourceReleaseId": candidate.ReleaseID,
		"sourceManifestDigest": candidate.ManifestDigest, "processingStatus": "ready",
	}, options.Find().SetProjection(bson.M{"_id": 1}))
	if err != nil {
		return 0, fmt.Errorf("read materialized target media identities: %w", err)
	}
	for cursor.Next(ctx) {
		var row struct {
			ID string `bson:"_id"`
		}
		if err := cursor.Decode(&row); err != nil {
			_ = cursor.Close(ctx)
			return 0, err
		}
		targetIDs = append(targetIDs, row.ID)
	}
	if err := cursor.Close(ctx); err != nil {
		return 0, err
	}
	result, err := live.UpdateMany(ctx, bson.M{
		"ownerId":          candidate.SourceOwner,
		"sourceReleaseId":  bson.M{"$ne": candidate.ReleaseID},
		"processingStatus": "ready", "_id": bson.M{"$nin": targetIDs},
	}, bson.M{"$set": bson.M{
		"processingStatus": "deleted", "deletedAt": tombstonedAt,
		"deletedByReleaseId": candidate.ReleaseID,
	}})
	if err != nil {
		return 0, fmt.Errorf("tombstone previous live release media: %w", err)
	}
	return result.ModifiedCount, nil
}

func validateActivationOutboxClosure(
	ctx context.Context,
	live *mongo.Collection,
	candidate importedReleaseCandidateState,
	events []postports.OutboxEvent,
) error {
	for _, event := range events {
		var existing importedOutboxDocument
		err := live.FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&existing)
		if err == mongo.ErrNoDocuments {
			continue
		}
		if err != nil {
			return fmt.Errorf("read live activation outbox event %q: %w", event.EventID, err)
		}
		if existing.SourceOwner != candidate.SourceOwner || existing.ReleaseID != candidate.ReleaseID ||
			existing.ManifestDigest != candidate.ManifestDigest ||
			existing.EventType != event.EventType || existing.AggregateType != event.AggregateType ||
			existing.AggregateID != event.AggregateID || existing.AggregateVersion != event.AggregateVersion ||
			!existing.OccurredAt.Equal(event.OccurredAt) || !bytes.Equal(existing.PayloadJSON, event.Payload) {
			return fmt.Errorf(
				"GATE_BLOCK CONTENT.CONFLICT.DATA_RELEASE_EVENT_DIGEST: event %q differs from activation closure",
				event.EventID,
			)
		}
	}
	if len(events) > 0 {
		count, err := live.CountDocuments(ctx, bson.M{
			"releaseId":        candidate.ReleaseID,
			"aggregateVersion": events[0].AggregateVersion,
		})
		if err != nil {
			return fmt.Errorf("count activation outbox closure: %w", err)
		}
		if count != 0 && count != int64(len(events)) {
			return fmt.Errorf("GATE_BLOCK: partial activation outbox closure exists")
		}
	}
	return nil
}

func validateLiveReleaseClosure(
	ctx context.Context,
	posts *mongo.Collection,
	outbox *mongo.Collection,
	media *mongo.Collection,
	candidate importedReleaseCandidateState,
	activationVersion int64,
	requireExactActiveClosure bool,
) error {
	postCount, err := posts.CountDocuments(ctx, bson.M{
		"sourceOwner": candidate.SourceOwner, "releaseId": candidate.ReleaseID,
		"manifestDigest": candidate.ManifestDigest, "lifecycleStatus": "active",
	})
	if err != nil {
		return fmt.Errorf("count live release Posts: %w", err)
	}
	totalActivePosts, err := posts.CountDocuments(ctx, bson.M{
		"sourceOwner": candidate.SourceOwner, "lifecycleStatus": "active",
	})
	if err != nil {
		return fmt.Errorf("count all Content-owned active Posts: %w", err)
	}
	publishedCount, err := outbox.CountDocuments(ctx, bson.M{
		"aggregateVersion": activationVersion,
		"eventType":        "PostPublished",
		"releaseId":        candidate.ReleaseID,
	})
	if err != nil {
		return fmt.Errorf("count live release outbox: %w", err)
	}
	mediaCount, err := media.CountDocuments(ctx, bson.M{
		"ownerId": candidate.SourceOwner, "sourceReleaseId": candidate.ReleaseID,
		"sourceManifestDigest": candidate.ManifestDigest, "processingStatus": "ready",
	})
	if err != nil {
		return fmt.Errorf("count live release media: %w", err)
	}
	if postCount != int64(candidate.Counts.PostsProjected) ||
		(requireExactActiveClosure && totalActivePosts != int64(candidate.Counts.PostsProjected)) ||
		publishedCount != int64(candidate.Counts.PostsProjected) ||
		mediaCount != int64(candidate.Counts.MediaProjected) {
		return fmt.Errorf(
			"GATE_BLOCK: live release closure mismatch: posts=%d/%d totalActive=%d publishedEvents=%d/%d media=%d/%d",
			postCount, candidate.Counts.PostsProjected, totalActivePosts,
			publishedCount, candidate.Counts.PostsProjected,
			mediaCount, candidate.Counts.MediaProjected,
		)
	}
	return nil
}

func releaseCandidateFilter(candidate importedReleaseCandidateState) bson.M {
	return bson.M{
		"environment": candidate.Environment, "sourceOwner": candidate.SourceOwner,
		"releaseId": candidate.ReleaseID, "manifestDigest": candidate.ManifestDigest,
	}
}

func validateExpectedActiveRelease(expected ExpectedActiveRelease) error {
	if expected.Empty {
		if expected.SourceOwner == "" || expected.Revision != 0 || expected.ReleaseID != "" || expected.ManifestDigest != "" {
			return fmt.Errorf("expected empty active release requires empty tuple and revision 0")
		}
		return nil
	}
	if expected.SourceOwner == "" || expected.ReleaseID == "" || expected.ManifestDigest == "" || expected.Revision <= 0 {
		return fmt.Errorf("expected active release requires exact tuple and positive revision")
	}
	return nil
}

func expectedActiveMatches(actual ActiveReleaseBinding, expected ExpectedActiveRelease) bool {
	if expected.Empty {
		return !actual.Found && actual.Revision == 0
	}
	return actual.Found && actual.SourceOwner == expected.SourceOwner && actual.ReleaseID == expected.ReleaseID &&
		actual.ManifestDigest == expected.ManifestDigest && actual.Revision == expected.Revision
}

func activeBindingMatches(actual ActiveReleaseBinding, target ImportedReleaseBinding) bool {
	return actual.Found && actual.SourceOwner == target.SourceOwner && actual.ReleaseID == target.ReleaseID &&
		actual.ManifestDigest == target.ManifestDigest
}

func sameActivationReplayExpectation(actual ActiveReleaseBinding, expected ExpectedActiveRelease) bool {
	if expected.Empty {
		return actual.Revision == 1
	}
	return actual.Revision == expected.Revision+1
}

func readActivePointerInTransaction(
	ctx context.Context,
	state *mongo.Collection,
	environment string,
	sourceOwner string,
) (ActiveReleaseBinding, error) {
	var pointer importedReleasePointerDocument
	err := state.FindOne(ctx, bson.M{
		"kind": releaseActivePointerKind, "status": "active", "environment": environment,
		"sourceOwner": sourceOwner,
	}).Decode(&pointer)
	if err == mongo.ErrNoDocuments {
		return ActiveReleaseBinding{Environment: environment, SourceOwner: sourceOwner}, nil
	}
	if err != nil {
		return ActiveReleaseBinding{}, fmt.Errorf("read active Content release pointer: %w", err)
	}
	if err := validateStoredActivePointer(pointer, environment, sourceOwner); err != nil {
		return ActiveReleaseBinding{}, err
	}
	return activeReleaseBindingFromPointer(pointer), nil
}

func activeReleaseBindingFromPointer(pointer importedReleasePointerDocument) ActiveReleaseBinding {
	return ActiveReleaseBinding{
		Environment: pointer.Environment, SourceOwner: pointer.SourceOwner,
		ReleaseID: pointer.ActiveReleaseID, ManifestDigest: pointer.ManifestDigest,
		ReleaseClass: pointer.ReleaseClass, ProjectionVersion: pointer.ProjectionVersion,
		Revision: pointer.Revision, ActivatedAt: pointer.ActivatedAt, Found: true,
	}
}

func compareAndSwapActivePointer(
	ctx context.Context,
	state *mongo.Collection,
	pointer importedReleasePointerDocument,
	expected ExpectedActiveRelease,
) (bool, error) {
	if expected.Empty {
		result, err := state.UpdateOne(ctx, bson.M{
			"kind": releaseActivePointerKind, "environment": pointer.Environment,
			"sourceOwner": pointer.SourceOwner,
		}, bson.M{"$setOnInsert": pointer}, options.UpdateOne().SetUpsert(true))
		if err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return false, nil
			}
			return false, fmt.Errorf("create active Content release pointer: %w", err)
		}
		return result.UpsertedCount == 1, nil
	}
	update := bson.M{"$set": bson.M{
		"status": "active", "activeReleaseId": pointer.ActiveReleaseID, "manifestDigest": pointer.ManifestDigest,
		"releaseClass": pointer.ReleaseClass, "projectionVersion": pointer.ProjectionVersion,
		"revision": pointer.Revision, "activatedAt": pointer.ActivatedAt,
	}}
	result, err := state.UpdateOne(ctx, bson.M{
		"kind": releaseActivePointerKind, "environment": pointer.Environment,
		"sourceOwner": pointer.SourceOwner, "activeReleaseId": expected.ReleaseID,
		"manifestDigest": expected.ManifestDigest, "revision": expected.Revision,
	}, update)
	if err != nil {
		return false, fmt.Errorf("compare-and-swap active Content release pointer: %w", err)
	}
	return result.MatchedCount == 1 && result.ModifiedCount == 1, nil
}

func rejectPriorReleaseStateShape(
	ctx context.Context,
	state *mongo.Collection,
	environment string,
	sourceOwner string,
) error {
	count, err := state.CountDocuments(ctx, bson.M{
		"environment": environment, "sourceOwner": sourceOwner,
		"$or": bson.A{
			bson.M{"kind": bson.M{"$exists": false}},
			bson.M{"kind": releaseActivePointerKind, "status": bson.M{"$ne": "active"}},
		},
	}, options.Count().SetLimit(1))
	if err != nil {
		return fmt.Errorf("inspect Content release state shape: %w", err)
	}
	if count != 0 {
		return fmt.Errorf("%s: prior data_release_state shape requires explicit migration", ReleasePriorStateMigrationRequiredCode)
	}
	return nil
}

func readVerifiedCandidateState(
	ctx context.Context,
	state *mongo.Collection,
	environment string,
	opts ImportOptions,
) (importedReleaseCandidateState, bool, error) {
	var candidate importedReleaseCandidateState
	err := state.FindOne(ctx, bson.M{
		"kind": releaseCandidateKind, "environment": environment,
		"sourceOwner": opts.SourceOwner, "releaseId": opts.ReleaseID,
		"manifestDigest": opts.ManifestDigest,
	}).Decode(&candidate)
	if err == mongo.ErrNoDocuments {
		return importedReleaseCandidateState{}, false, nil
	}
	if err != nil {
		return importedReleaseCandidateState{}, false, fmt.Errorf("read release candidate state: %w", err)
	}
	if candidate.Status != "verified" || candidate.ProjectionVersion <= 0 {
		return importedReleaseCandidateState{}, false, fmt.Errorf("GATE_BLOCK: candidate state is not verified")
	}
	if candidate.ReleaseClass != opts.ReleaseClass || candidate.ReleaseKind != opts.ReleaseKind ||
		candidate.Mode != opts.Mode || candidate.DeletePolicy != opts.DeletePolicy {
		return importedReleaseCandidateState{}, false, fmt.Errorf("GATE_BLOCK: verified candidate policy binding differs")
	}
	return candidate, true, nil
}

func allocateReleaseProjectionVersion(ctx context.Context, sequences *mongo.Collection) (int64, error) {
	var counter struct {
		Value int64 `bson:"value"`
	}
	if err := sequences.FindOneAndUpdate(
		ctx, bson.M{"_id": "content-release-projection"},
		bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&counter); err != nil {
		return 0, fmt.Errorf("allocate Data release projection version: %w", err)
	}
	if counter.Value <= 0 {
		return 0, fmt.Errorf("GATE_BLOCK: allocated Data release projection version is invalid")
	}
	return counter.Value, nil
}
