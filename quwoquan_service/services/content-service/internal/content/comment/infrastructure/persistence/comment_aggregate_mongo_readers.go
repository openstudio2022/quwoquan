package persistence

// Comment readers are object-local projections over Comment-owned storage.

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
)

var (
	_ commentports.OutboxReader              = (*MongoCommentDataAdapter)(nil)
	_ commentports.CommentPageReader         = (*MongoCommentDataAdapter)(nil)
	_ commentports.ReplyPageReader           = (*MongoCommentDataAdapter)(nil)
	_ commentports.ReplySummaryReader        = (*MongoCommentDataAdapter)(nil)
	_ commentports.AuthorCommentPageReader   = (*MongoCommentDataAdapter)(nil)
	_ commentports.ReceivedCommentPageReader = (*MongoCommentDataAdapter)(nil)
	_ commentports.CountReader               = (*MongoCommentDataAdapter)(nil)
	_ commentports.CommentRelationReader     = (*MongoCommentDataAdapter)(nil)
	_ commentports.PostOwnershipReader       = (*MongoCommentDataAdapter)(nil)
)

func (s *MongoCommentDataAdapter) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]commentports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		occurredAt, eventID, err := parseCommentOutboxCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$gt": occurredAt}},
			bson.M{"occurredAt": occurredAt, "_id": bson.M{"$gt": eventID}},
		}
	}
	cursor, err := s.outbox.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read comment outbox: %w", err)
	}
	defer cursor.Close(ctx)

	events := make([]commentports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document commentOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode comment outbox: %w", err)
		}
		events = append(events, commentports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt.UTC(),
			Checkpoint:       commentOutboxCheckpoint(document.OccurredAt, document.ID),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate comment outbox: %w", err)
	}
	return events, nil
}

func (s *MongoCommentDataAdapter) ListByPost(
	ctx context.Context,
	postID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	sortMode := request.Sort
	if sortMode == "" {
		sortMode = commentmodel.SortHot
	}
	filter := bson.M{
		"postId":          strings.TrimSpace(postID),
		"parentCommentId": "",
		"status":          string(commentmodel.StatusActive),
	}
	applyCommentAccountRestrictionVisibility(filter)
	applyCommentAuthorExclusions(filter, request.ExcludedAuthorIDs)
	cursor, hasCursor := commentmodel.DecodeCursor(request.Cursor)
	if hasCursor {
		if sortMode == commentmodel.SortHot {
			filter["$or"] = topLevelHotAfter(cursor)
		} else {
			filter["$or"] = topLevelAfter(cursor)
		}
	}
	sortSpec := bson.D{
		{Key: "isPinned", Value: -1},
		{Key: "pinnedAt", Value: -1},
		{Key: "createdAt", Value: -1},
		{Key: "_id", Value: -1},
	}
	if sortMode == commentmodel.SortHot {
		sortSpec = bson.D{
			{Key: "isPinned", Value: -1},
			{Key: "pinnedAt", Value: -1},
			{Key: "hotScore", Value: -1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
		}
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		sortSpec,
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) ListReplies(
	ctx context.Context,
	postID string,
	parentCommentID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	filter := bson.M{
		"postId":          strings.TrimSpace(postID),
		"parentCommentId": strings.TrimSpace(parentCommentID),
		"status":          string(commentmodel.StatusActive),
	}
	applyCommentAccountRestrictionVisibility(filter)
	applyCommentAuthorExclusions(filter, request.ExcludedAuthorIDs)
	if cursor, ok := commentmodel.DecodeCursor(request.Cursor); ok {
		filter["$or"] = flatAfter(cursor)
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) ReadReplySummaries(
	ctx context.Context,
	parentCommentIDs []string,
	previewLimit int,
	excludedAuthorIDs []string,
) (map[string]commentmodel.ReplySummary, error) {
	parentCommentIDs = uniqueNonEmptyStrings(parentCommentIDs)
	summaries := make(map[string]commentmodel.ReplySummary, len(parentCommentIDs))
	if len(parentCommentIDs) == 0 {
		return summaries, nil
	}
	if previewLimit <= 0 {
		previewLimit = 1
	}
	if previewLimit > 10 {
		previewLimit = 10
	}
	match := bson.M{
		"parentCommentId": bson.M{"$in": parentCommentIDs},
		"status":          string(commentmodel.StatusActive),
	}
	applyCommentAccountRestrictionVisibility(match)
	applyCommentAuthorExclusions(match, excludedAuthorIDs)
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: match}},
		{{Key: "$sort", Value: bson.D{
			{Key: "parentCommentId", Value: 1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
		}}},
		{{Key: "$group", Value: bson.M{
			"_id":   "$parentCommentId",
			"count": bson.M{"$sum": 1},
			"items": bson.M{"$push": "$$ROOT"},
		}}},
		{{Key: "$project", Value: bson.M{
			"count": 1,
			"items": bson.M{"$slice": []any{"$items", previewLimit}},
		}}},
	}
	cursor, err := s.comments.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var row struct {
			ParentCommentID string                `bson:"_id"`
			Count           int64                 `bson:"count"`
			Items           []commentReadDocument `bson:"items"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		preview := make([]commentmodel.ReadModel, 0, len(row.Items))
		for _, document := range row.Items {
			preview = append(preview, document.readModel())
		}
		nextCursor := ""
		if row.Count > int64(len(preview)) && len(preview) > 0 {
			nextCursor = commentmodel.EncodeCursor(commentmodel.CursorFor(preview[len(preview)-1]))
		}
		summaries[row.ParentCommentID] = commentmodel.ReplySummary{
			Count:      row.Count,
			Preview:    preview,
			NextCursor: nextCursor,
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return summaries, nil
}

func (s *MongoCommentDataAdapter) ListByAuthor(
	ctx context.Context,
	authorID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	filter := bson.M{
		"authorId": strings.TrimSpace(authorID),
		"status": bson.M{
			"$in": []string{
				string(commentmodel.StatusActive),
				string(commentmodel.StatusHidden),
			},
		},
	}
	applyCommentAccountRestrictionVisibility(filter)
	if cursor, ok := commentmodel.DecodeCursor(request.Cursor); ok {
		filter["$or"] = flatAfter(cursor)
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) ListReceivedByPostAuthor(
	ctx context.Context,
	postAuthorID string,
	postIDs []string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	if len(postIDs) == 0 {
		return commentmodel.Page{Items: []commentmodel.ReadModel{}}, nil
	}
	filter := bson.M{
		"postId": bson.M{"$in": cloneStrings(postIDs)},
		"authorId": bson.M{"$nin": uniqueNonEmptyStrings(append(
			[]string{postAuthorID},
			request.ExcludedAuthorIDs...,
		))},
		"status": string(commentmodel.StatusActive),
	}
	applyCommentAccountRestrictionVisibility(filter)
	if cursor, ok := commentmodel.DecodeCursor(request.Cursor); ok {
		filter["$or"] = flatAfter(cursor)
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) CountByPost(ctx context.Context, postID string) (int64, error) {
	return s.comments.CountDocuments(ctx, bson.M{
		"postId":            strings.TrimSpace(postID),
		"status":            string(commentmodel.StatusActive),
		"accountRestricted": bson.M{"$ne": true},
	})
}

func (s *MongoCommentDataAdapter) FindReplyTarget(
	ctx context.Context,
	commentID string,
) (commentmodel.ReplyTarget, bool, error) {
	var document commentRelationDocument
	err := s.comments.FindOne(
		ctx,
		bson.M{
			"_id":               strings.TrimSpace(commentID),
			"accountRestricted": bson.M{"$ne": true},
		},
		options.FindOne().SetProjection(CommentRelationProjection()),
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return commentmodel.ReplyTarget{}, false, nil
	}
	if err != nil {
		return commentmodel.ReplyTarget{}, false, err
	}
	return commentmodel.ReplyTarget{
		ID:              document.ID,
		PostID:          document.PostID,
		AuthorID:        document.AuthorID,
		ParentCommentID: document.ParentCommentID,
		Status:          commentmodel.Status(document.Status),
	}, true, nil
}

func (s *MongoCommentDataAdapter) FindPostOwnership(
	ctx context.Context,
	postID string,
) (commentmodel.PostOwnership, bool, error) {
	var document postOwnershipDocument
	err := s.posts.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(postID)},
		options.FindOne().SetProjection(bson.D{
			{Key: "_id", Value: 1},
			{Key: "authorId", Value: 1},
			{Key: "status", Value: 1},
		}),
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return commentmodel.PostOwnership{}, false, nil
	}
	if err != nil {
		return commentmodel.PostOwnership{}, false, err
	}
	return commentmodel.PostOwnership{
		PostID:   document.ID,
		AuthorID: document.AuthorID,
		Active:   strings.TrimSpace(document.Status) != "deleted",
	}, true, nil
}

func (s *MongoCommentDataAdapter) ListOwnedPostIDs(
	ctx context.Context,
	postAuthorID string,
) ([]string, error) {
	cursor, err := s.posts.Find(
		ctx,
		bson.M{
			"authorId": strings.TrimSpace(postAuthorID),
			"status":   bson.M{"$ne": "deleted"},
		},
		options.Find().SetProjection(bson.D{{Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	postIDs := []string{}
	for cursor.Next(ctx) {
		var document postIDDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		if id := strings.TrimSpace(document.ID); id != "" {
			postIDs = append(postIDs, id)
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return postIDs, nil
}

func (s *MongoCommentDataAdapter) FindPostOwnerships(
	ctx context.Context,
	postIDs []string,
) (map[string]commentmodel.PostOwnership, error) {
	postIDs = uniqueNonEmptyStrings(postIDs)
	ownerships := make(map[string]commentmodel.PostOwnership, len(postIDs))
	if len(postIDs) == 0 {
		return ownerships, nil
	}
	cursor, err := s.posts.Find(
		ctx,
		bson.M{"_id": bson.M{"$in": postIDs}},
		options.Find().SetProjection(bson.D{
			{Key: "_id", Value: 1},
			{Key: "authorId", Value: 1},
			{Key: "status", Value: 1},
		}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var document postOwnershipDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		ownerships[document.ID] = commentmodel.PostOwnership{
			PostID:   document.ID,
			AuthorID: document.AuthorID,
			Active:   strings.TrimSpace(document.Status) != "deleted",
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return ownerships, nil
}

func (s *MongoCommentDataAdapter) findPage(
	ctx context.Context,
	filter bson.M,
	sortSpec bson.D,
	limit int,
	total int64,
) (commentmodel.Page, error) {
	limit = normalizeCommentPageLimit(limit)
	cursor, err := s.comments.Find(
		ctx,
		filter,
		options.Find().
			SetProjection(CommentReadProjection()).
			SetSort(sortSpec).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return commentmodel.Page{}, err
	}
	defer cursor.Close(ctx)

	items := make([]commentmodel.ReadModel, 0, limit+1)
	for cursor.Next(ctx) {
		var document commentReadDocument
		if err := cursor.Decode(&document); err != nil {
			return commentmodel.Page{}, err
		}
		items = append(items, document.readModel())
	}
	if err := cursor.Err(); err != nil {
		return commentmodel.Page{}, err
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		nextCursor = commentmodel.EncodeCursor(commentmodel.CursorFor(items[len(items)-1]))
	}
	return commentmodel.Page{
		Items:      cloneReadModels(items),
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}

func CommentReadProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "version", Value: 1},
		{Key: "postId", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "authorDisplayNameSnapshot", Value: 1},
		{Key: "authorAvatarUrlSnapshot", Value: 1},
		{Key: "personaContextVersion", Value: 1},
		{Key: "content", Value: 1},
		{Key: "replyToCommentId", Value: 1},
		{Key: "replyToUserId", Value: 1},
		{Key: "parentCommentId", Value: 1},
		{Key: "attachmentMediaIds", Value: 1},
		{Key: "mentions", Value: 1},
		{Key: "assistantMentioned", Value: 1},
		{Key: "assistantReplySource", Value: 1},
		{Key: "assistantCorrectionStatus", Value: 1},
		{Key: "status", Value: 1},
		{Key: "isPinned", Value: 1},
		{Key: "pinnedAt", Value: 1},
		{Key: "createdAt", Value: 1},
		{Key: "updatedAt", Value: 1},
		{Key: "deletedAt", Value: 1},
	}
}

func CommentRelationProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "postId", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "parentCommentId", Value: 1},
		{Key: "status", Value: 1},
	}
}
