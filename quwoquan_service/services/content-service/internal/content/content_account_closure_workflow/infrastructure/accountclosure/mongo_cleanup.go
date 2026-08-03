package accountclosure

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	deletedPostTombstoneRetention = 30 * 24 * time.Hour
	closedAccountAnonymousID      = "closed_account"
)

type postClosureRow struct {
	ID       string `bson:"_id"`
	AuthorID string `bson:"authorId"`
}

type cleanupInventory struct {
	postRows          []postClosureRow
	postIDs           []string
	commentRows       []commentClosureRow
	commentIDs        []string
	commentRefIDs     []string
	reactionRows      []reactionClosureRow
	reactionIDs       []string
	activityRows      []activityClosureRow
	activityDocIDs    []string
	activityIDs       []string
	readFactIDs       []string
	shareRows         []shareClosureRow
	shareFactIDs      []string
	moderationCaseIDs []string
	mediaSessionIDs   []string
	mediaAssetIDs     []string
	mediaArtifactRows []MediaArtifactClosureRow
	affectedPostIDs   []string
}

func (store *MongoStore) applyContentCleanup(
	ctx context.Context,
	event UserAccountClosedEvent,
) error {
	subjectIDs := event.SubjectIDs()
	inventory, err := store.collectCleanupInventory(ctx, subjectIDs)
	if err != nil {
		return err
	}
	if err := store.stageSearchDeletion(ctx, event, inventory.postIDs); err != nil {
		return err
	}
	if err := store.writeAnonymousClosureAudit(ctx, event, len(subjectIDs)); err != nil {
		return err
	}
	if err := store.writePostTombstones(ctx, event, inventory.postRows); err != nil {
		return err
	}
	if err := store.stageMediaArtifactCleanup(
		ctx,
		event,
		inventory.mediaArtifactRows,
	); err != nil {
		return err
	}
	if err := store.deleteAggregateData(ctx, subjectIDs, inventory); err != nil {
		return err
	}
	if err := store.deleteDerivedData(ctx, subjectIDs, inventory); err != nil {
		return err
	}
	if err := store.anonymizeRetainedAudit(ctx, event, subjectIDs); err != nil {
		return err
	}
	if err := store.recomputePostCounters(ctx, inventory.affectedPostIDs); err != nil {
		return err
	}
	if err := finalizeContentAccountRestrictionClosure(ctx, store.db, event); err != nil {
		return err
	}
	return nil
}

func (store *MongoStore) collectCleanupInventory(
	ctx context.Context,
	subjectIDs []string,
) (cleanupInventory, error) {
	postRows, err := findPostClosureRows(
		ctx,
		store.db.Collection("posts"),
		bson.M{"authorId": bson.M{"$in": subjectIDs}},
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account Posts: %w", err)
	}
	postIDs := postClosureIDs(postRows)
	commentRows, err := collectCommentClosureRows(
		ctx,
		store.db.Collection("comments"),
		subjectIDs,
		postIDs,
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account Comments: %w", err)
	}
	commentIDs := rowIDs(commentRows)
	commentReferenceRows, err := collectCommentReferenceRows(
		ctx,
		store.db.Collection("comments"),
		subjectIDs,
		commentIDs,
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf(
			"collect closed-account Comment references: %w",
			err,
		)
	}
	commentReferenceIDs := rowIDs(commentReferenceRows)
	reactionRows, err := collectReactionClosureRows(
		ctx,
		store.db.Collection("content_reaction_aggregates"),
		subjectIDs,
		uniqueStrings(postIDs, commentIDs),
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account ContentReactions: %w", err)
	}
	activityRows, err := collectActivityClosureRows(
		ctx,
		store.db.Collection("profile_interaction_activity_views"),
		subjectIDs,
		postIDs,
		commentIDs,
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account interaction activities: %w", err)
	}
	activityIDs := make([]string, 0, len(activityRows))
	for _, row := range activityRows {
		activityIDs = append(activityIDs, row.ActivityID)
	}
	readFactIDs, err := collectStringField(
		ctx,
		store.db.Collection("profile_interaction_read_facts"),
		bson.M{"$or": bson.A{
			bson.M{"ownerPersonaId": bson.M{"$in": subjectIDs}},
			bson.M{"activityId": bson.M{"$in": activityIDs}},
		}},
		"_id",
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account interaction read facts: %w", err)
	}
	shareRows, err := collectShareClosureRows(
		ctx,
		store.db.Collection("outbound_share_facts"),
		subjectIDs,
		postIDs,
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account outbound shares: %w", err)
	}
	shareFactIDs := rowIDs(shareRows)
	moderationCaseIDs, err := collectStringField(
		ctx,
		store.db.Collection("post_moderation_cases"),
		bson.M{"postId": bson.M{"$in": postIDs}},
		"_id",
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account moderation cases: %w", err)
	}
	mediaSessionIDs, err := collectStringField(
		ctx,
		store.db.Collection("media_upload_sessions"),
		bson.M{"ownerId": bson.M{"$in": subjectIDs}},
		"_id",
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf("collect closed-account media sessions: %w", err)
	}
	mediaArtifactRows, err := collectMediaArtifactClosureRows(
		ctx,
		store.db.Collection("media_assets"),
		subjectIDs,
	)
	if err != nil {
		return cleanupInventory{}, fmt.Errorf(
			"collect closed-account media artifacts: %w",
			err,
		)
	}
	mediaAssetIDs := make([]string, 0, len(mediaArtifactRows))
	for _, row := range mediaArtifactRows {
		mediaAssetIDs = append(mediaAssetIDs, row.ID)
	}
	affectedPostIDs := append([]string(nil), postIDs...)
	for _, row := range commentRows {
		affectedPostIDs = append(affectedPostIDs, row.PostID)
	}
	for _, row := range reactionRows {
		if row.TargetKind == "post" {
			affectedPostIDs = append(affectedPostIDs, row.TargetID)
		}
	}
	for _, row := range shareRows {
		affectedPostIDs = append(affectedPostIDs, row.PostID)
	}
	return cleanupInventory{
		postRows:          postRows,
		postIDs:           postIDs,
		commentRows:       commentRows,
		commentIDs:        commentIDs,
		commentRefIDs:     commentReferenceIDs,
		reactionRows:      reactionRows,
		reactionIDs:       rowIDs(reactionRows),
		activityRows:      activityRows,
		activityDocIDs:    rowIDs(activityRows),
		activityIDs:       uniqueStrings(activityIDs),
		readFactIDs:       readFactIDs,
		shareRows:         shareRows,
		shareFactIDs:      shareFactIDs,
		moderationCaseIDs: moderationCaseIDs,
		mediaSessionIDs:   mediaSessionIDs,
		mediaAssetIDs:     mediaAssetIDs,
		mediaArtifactRows: mediaArtifactRows,
		affectedPostIDs:   uniqueStrings(affectedPostIDs),
	}, nil
}

func findPostClosureRows(
	ctx context.Context,
	collection *mongo.Collection,
	filter any,
) ([]postClosureRow, error) {
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"_id": 1, "authorId": 1}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []postClosureRow
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func postClosureIDs(rows []postClosureRow) []string {
	ids := make([]string, 0, len(rows))
	for _, row := range rows {
		ids = append(ids, row.ID)
	}
	return uniqueStrings(ids)
}

func (store *MongoStore) stageSearchDeletion(
	ctx context.Context,
	event UserAccountClosedEvent,
	postIDs []string,
) error {
	if len(postIDs) == 0 {
		return nil
	}
	now := time.Now().UTC()
	models := make([]mongo.WriteModel, 0, len(postIDs))
	for _, postID := range postIDs {
		document := SearchDocumentID{
			ObjectType: ContentPostSearchObjectType,
			ObjectID:   postID,
		}
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(bson.M{"_id": searchWorkID(event.EventID, document.CanonicalID())}).
			SetUpdate(bson.M{"$setOnInsert": bson.M{
				"eventId":     event.EventID,
				"canonicalId": document.CanonicalID(),
				"objectType":  document.ObjectType,
				"objectId":    document.ObjectID,
				"createdAt":   now,
			}}).
			SetUpsert(true))
	}
	if _, err := store.searchWork.BulkWrite(
		ctx,
		models,
		options.BulkWrite().SetOrdered(false),
	); err != nil {
		return fmt.Errorf("stage closed-account search deletion: %w", err)
	}
	return nil
}

func (store *MongoStore) writeAnonymousClosureAudit(
	ctx context.Context,
	event UserAccountClosedEvent,
	subjectCount int,
) error {
	_, err := store.closedSubjects.UpdateOne(
		ctx,
		bson.M{"_id": event.Digest()},
		bson.M{"$setOnInsert": bson.M{
			"eventDigest":    event.Digest(),
			"accountVersion": event.AccountVersion,
			"subjectCount":   subjectCount,
			"closedAt":       event.Payload.UpdatedAt.UTC(),
			"recordedAt":     time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("write anonymous closed-account audit: %w", err)
	}
	return nil
}

func (store *MongoStore) writePostTombstones(
	ctx context.Context,
	event UserAccountClosedEvent,
	rows []postClosureRow,
) error {
	if len(rows) == 0 {
		return nil
	}
	deletedAt := event.Payload.UpdatedAt.UTC()
	models := make([]mongo.WriteModel, 0, len(rows))
	for _, row := range rows {
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(bson.M{"_id": row.ID}).
			SetUpdate(bson.M{"$set": bson.M{
				"postId":    row.ID,
				"authorId":  closedAccountAnonymousID,
				"reason":    "account_closed",
				"deletedAt": deletedAt,
				"expireAt":  deletedAt.Add(deletedPostTombstoneRetention),
			}}).
			SetUpsert(true))
	}
	if _, err := store.db.Collection("deleted_post_tombstones").BulkWrite(
		ctx,
		models,
		options.BulkWrite().SetOrdered(false),
	); err != nil {
		return fmt.Errorf("write closed-account Post tombstones: %w", err)
	}
	return nil
}

func (store *MongoStore) deleteAggregateData(
	ctx context.Context,
	subjectIDs []string,
	inventory cleanupInventory,
) error {
	commentWorkIDs := uniqueStrings(
		inventory.commentIDs,
		inventory.commentRefIDs,
	)
	operations := []mongoDeleteOperation{
		{"post receipts", "post_command_receipts", bson.M{"aggregateId": bson.M{"$in": inventory.postIDs}}},
		{"post outbox", "content_outbox", bson.M{"aggregateId": bson.M{"$in": inventory.postIDs}}},
		{"Posts", "posts", bson.M{"_id": bson.M{"$in": inventory.postIDs}}},
		{"comment receipts", "comment_command_receipts", bson.M{"aggregateId": bson.M{"$in": commentWorkIDs}}},
		{"comment outbox", "comment_outbox", bson.M{"aggregateId": bson.M{"$in": commentWorkIDs}}},
		{"comment rate locks", "comment_author_rate_limit_locks", bson.M{"_id": bson.M{"$in": subjectIDs}}},
		{"Comments", "comments", bson.M{"_id": bson.M{"$in": inventory.commentIDs}}},
		{"ContentReaction receipts", "content_reaction_command_receipts", bson.M{"aggregateId": bson.M{"$in": inventory.reactionIDs}}},
		{"ContentReaction outbox", "content_reaction_outbox", bson.M{"aggregateId": bson.M{"$in": inventory.reactionIDs}}},
		{"ContentReactions", "content_reaction_aggregates", bson.M{"_id": bson.M{"$in": inventory.reactionIDs}}},
		{"interaction read-fact outbox", "profile_interaction_read_fact_outbox", bson.M{"eventId": bson.M{"$in": inventory.readFactIDs}}},
		{"interaction read facts", "profile_interaction_read_facts", bson.M{"_id": bson.M{"$in": inventory.readFactIDs}}},
		{"outbound-share receipts", "outbound_share_receipts", bson.M{"fact._id": bson.M{"$in": inventory.shareFactIDs}}},
		{"outbound-share outbox", "outbound_share_outbox", bson.M{"eventId": bson.M{"$in": inventory.shareFactIDs}}},
		{"outbound-share facts", "outbound_share_facts", bson.M{"_id": bson.M{"$in": inventory.shareFactIDs}}},
		{"moderation receipts", "post_moderation_case_command_receipts", bson.M{"aggregateId": bson.M{"$in": inventory.moderationCaseIDs}}},
		{"moderation outbox", "post_moderation_case_outbox", bson.M{"aggregateId": bson.M{"$in": inventory.moderationCaseIDs}}},
		{"moderation cases", "post_moderation_cases", bson.M{"_id": bson.M{"$in": inventory.moderationCaseIDs}}},
		{"media session receipts", "media_upload_session_command_receipts", bson.M{"aggregateId": bson.M{"$in": inventory.mediaSessionIDs}}},
		{"media session outbox", "media_upload_session_outbox", bson.M{"aggregateId": bson.M{"$in": inventory.mediaSessionIDs}}},
		{"media upload sessions", "media_upload_sessions", bson.M{"_id": bson.M{"$in": inventory.mediaSessionIDs}}},
		{"media asset receipts", "media_asset_command_receipts", bson.M{"aggregateId": bson.M{"$in": inventory.mediaAssetIDs}}},
		{"media asset outbox", "media_asset_outbox", bson.M{"aggregateId": bson.M{"$in": inventory.mediaAssetIDs}}},
		{"media assets", "media_assets", bson.M{"_id": bson.M{"$in": inventory.mediaAssetIDs}}},
	}
	if err := store.runDeleteOperations(ctx, operations); err != nil {
		return err
	}
	return store.scrubRetainedCommentReferences(
		ctx,
		subjectIDs,
		inventory.commentIDs,
	)
}

func (store *MongoStore) scrubRetainedCommentReferences(
	ctx context.Context,
	subjectIDs []string,
	deletedCommentIDs []string,
) error {
	comments := store.db.Collection("comments")
	if _, err := comments.UpdateMany(
		ctx,
		bson.M{"replyToUserId": bson.M{"$in": subjectIDs}},
		bson.M{"$unset": bson.M{"replyToUserId": ""}},
	); err != nil {
		return fmt.Errorf(
			"anonymize retained Comment reply subjects: %w",
			err,
		)
	}
	for _, field := range []string{"parentCommentId", "replyToCommentId"} {
		if _, err := comments.UpdateMany(
			ctx,
			bson.M{field: bson.M{"$in": deletedCommentIDs}},
			bson.M{"$unset": bson.M{field: ""}},
		); err != nil {
			return fmt.Errorf(
				"unlink retained Comment references: %w",
				err,
			)
		}
	}
	_, err := comments.UpdateMany(
		ctx,
		bson.M{"mentions.subjectId": bson.M{"$in": subjectIDs}},
		mongo.Pipeline{bson.D{{Key: "$set", Value: bson.M{
			"mentions": bson.M{
				"$filter": bson.M{
					"input": bson.M{
						"$ifNull": bson.A{"$mentions", bson.A{}},
					},
					"as": "mention",
					"cond": bson.M{
						"$not": bson.A{
							bson.M{
								"$in": bson.A{
									"$$mention.subjectId",
									subjectIDs,
								},
							},
						},
					},
				},
			},
		}}}},
	)
	if err != nil {
		return fmt.Errorf(
			"anonymize retained Comment mentions: %w",
			err,
		)
	}
	return nil
}

type mongoDeleteOperation struct {
	name       string
	collection string
	filter     bson.M
}

func (store *MongoStore) runDeleteOperations(
	ctx context.Context,
	operations []mongoDeleteOperation,
) error {
	for _, operation := range operations {
		if _, err := store.db.Collection(operation.collection).DeleteMany(
			ctx,
			operation.filter,
		); err != nil {
			return fmt.Errorf("delete closed-account %s: %w", operation.name, err)
		}
	}
	return nil
}

func (store *MongoStore) deleteDerivedData(
	ctx context.Context,
	subjectIDs []string,
	inventory cleanupInventory,
) error {
	subjectOrPost := bson.A{
		bson.M{"userId": bson.M{"$in": subjectIDs}},
		bson.M{"authorId": bson.M{"$in": subjectIDs}},
		bson.M{"contentId": bson.M{"$in": inventory.postIDs}},
	}
	operations := []mongoDeleteOperation{
		{"profile interaction activities", "profile_interaction_activity_views", bson.M{"_id": bson.M{"$in": inventory.activityDocIDs}}},
		{"behavior events", "rm_behavior_events", bson.M{"$or": subjectOrPost}},
		{"wishlist events", "entity_wishlist_events", bson.M{"userId": bson.M{"$in": subjectIDs}}},
		{"persona access projection", "content_persona_access_projection", bson.M{"$or": bson.A{
			bson.M{"sourcePersonaId": bson.M{"$in": subjectIDs}},
			bson.M{"targetPersonaId": bson.M{"$in": subjectIDs}},
		}}},
		{"persona access projection inbox", "content_persona_access_projection_inbox", bson.M{"$or": bson.A{
			bson.M{"sourcePersonaId": bson.M{"$in": subjectIDs}},
			bson.M{"targetPersonaId": bson.M{"$in": subjectIDs}},
		}}},
	}
	if err := store.runDeleteOperations(ctx, operations); err != nil {
		return err
	}
	return nil
}

func (store *MongoStore) anonymizeRetainedAudit(
	ctx context.Context,
	event UserAccountClosedEvent,
	subjectIDs []string,
) error {
	anonymousID := "closed_" + event.Digest()[:24]
	if _, err := store.db.Collection("post_moderation_case_audit").UpdateMany(
		ctx,
		bson.M{"reviewerId": bson.M{"$in": subjectIDs}},
		bson.M{"$set": bson.M{"reviewerId": anonymousID}},
	); err != nil {
		return fmt.Errorf("anonymize closed-account moderation audit: %w", err)
	}
	if _, err := store.db.Collection("media_original_access_facts").UpdateMany(
		ctx,
		bson.M{"viewerId": bson.M{"$in": subjectIDs}},
		bson.M{"$set": bson.M{"viewerId": anonymousID}},
	); err != nil {
		return fmt.Errorf("anonymize closed-account media audit: %w", err)
	}
	if _, err := store.db.Collection("media_original_access_receipts").DeleteMany(
		ctx,
		bson.M{"fact.viewerId": bson.M{"$in": subjectIDs}},
	); err != nil {
		return fmt.Errorf("delete closed-account media audit receipts: %w", err)
	}
	return nil
}

func (store *MongoStore) recomputePostCounters(
	ctx context.Context,
	postIDs []string,
) error {
	if len(postIDs) == 0 {
		return nil
	}
	commentCounts, err := groupedCount(
		ctx,
		store.db.Collection("comments"),
		bson.M{
			"postId": bson.M{"$in": postIDs},
			"status": "active",
		},
		"postId",
	)
	if err != nil {
		return fmt.Errorf("recompute closed-account comment counts: %w", err)
	}
	likeCounts, err := groupedCount(
		ctx,
		store.db.Collection("content_reaction_aggregates"),
		bson.M{
			"targetKind": "post",
			"targetId":   bson.M{"$in": postIDs},
			"reaction":   "like",
		},
		"targetId",
	)
	if err != nil {
		return fmt.Errorf("recompute closed-account like counts: %w", err)
	}
	shareCounts, err := groupedCount(
		ctx,
		store.db.Collection("outbound_share_facts"),
		bson.M{"postId": bson.M{"$in": postIDs}},
		"postId",
	)
	if err != nil {
		return fmt.Errorf("recompute closed-account share counts: %w", err)
	}
	now := time.Now().UTC()
	postModels := make([]mongo.WriteModel, 0, len(postIDs))
	for _, postID := range postIDs {
		update := bson.M{"$set": bson.M{
			"commentCount": commentCounts[postID],
			"likeCount":    likeCounts[postID],
			"shareCount":   shareCounts[postID],
			"updatedAt":    now,
		}}
		postModels = append(postModels, mongo.NewUpdateOneModel().
			SetFilter(bson.M{"_id": postID}).
			SetUpdate(update))
	}
	if _, err := store.db.Collection("posts").BulkWrite(
		ctx,
		postModels,
		options.BulkWrite().SetOrdered(false),
	); err != nil {
		return fmt.Errorf("update closed-account Post counters: %w", err)
	}
	return nil
}

func groupedCount(
	ctx context.Context,
	collection *mongo.Collection,
	filter bson.M,
	field string,
) (map[string]int64, error) {
	cursor, err := collection.Aggregate(ctx, mongo.Pipeline{
		{{Key: "$match", Value: filter}},
		{{Key: "$group", Value: bson.M{
			"_id":   "$" + strings.TrimSpace(field),
			"count": bson.M{"$sum": 1},
		}}},
	})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []struct {
		ID    string `bson:"_id"`
		Count int64  `bson:"count"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	counts := make(map[string]int64, len(rows))
	for _, row := range rows {
		counts[row.ID] = row.Count
	}
	return counts, nil
}
