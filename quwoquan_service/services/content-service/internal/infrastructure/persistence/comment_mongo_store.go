package persistence

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

const commentsCollection = "comments"

// MongoCommentStore implements commentdomain.Store backed by MongoDB. Ordering,
// cursor and count semantics mirror MemoryCommentStore exactly. The collection
// is opened with DefaultDocumentMap so `any` fields (attachments / mentions)
// decode into map[string]any (JSON object shape) instead of bson.D.
type MongoCommentStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewMongoCommentStore opens the comments collection (with map-document decoding)
// and ensures the indexes declared in storage.yaml exist.
func NewMongoCommentStore(db *mongo.Database, logger *slog.Logger) *MongoCommentStore {
	if logger == nil {
		logger = slog.Default()
	}
	coll := db.Collection(
		commentsCollection,
		options.Collection().SetBSONOptions(&options.BSONOptions{DefaultDocumentMap: true}),
	)
	s := &MongoCommentStore{coll: coll, logger: logger}
	s.ensureIndexes()
	return s
}

var _ commentdomain.Store = (*MongoCommentStore)(nil)

// ensureIndexes creates the indexes declared in
// contracts/metadata/content/post/storage.yaml#collections.comments. The pinned
// and deleted partial indexes back, respectively, the two-phase keyset listing
// (pinned segment) and GetCommentCountsDelta (deleted-since window).
func (s *MongoCommentStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	indexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}, Options: options.Index().SetName("idx_comments_post_created")},
		{Keys: bson.D{{Key: "authorId", Value: 1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}, Options: options.Index().SetName("idx_comments_author")},
		{Keys: bson.D{{Key: "replyToCommentId", Value: 1}}, Options: options.Index().SetName("idx_comments_reply").SetSparse(true)},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "parentCommentId", Value: 1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}, Options: options.Index().SetName("idx_comments_parent_created")},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "likeCount", Value: -1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}, Options: options.Index().SetName("idx_comments_hot")},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "recommendedScore", Value: -1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}, Options: options.Index().SetName("idx_comments_recommended")},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "pinnedAt", Value: -1}, {Key: "_id", Value: -1}}, Options: options.Index().SetName("idx_comments_pinned").SetPartialFilterExpression(bson.M{"isPinned": true})},
		{Keys: bson.D{{Key: "postId", Value: 1}, {Key: "deletedAt", Value: -1}}, Options: options.Index().SetName("idx_comments_deleted").SetPartialFilterExpression(bson.M{"status": "deleted"})},
		{Keys: bson.D{{Key: "primaryHomepageId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_comments_homepage_created").SetSparse(true)},
		{Keys: bson.D{{Key: "canonicalEntityId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_comments_canonical_entity").SetSparse(true)},
	}
	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("comment_mongo_store: index creation failed", slog.String("error", err.Error()))
		}
	}
}

func (s *MongoCommentStore) Create(ctx context.Context, c *postmodel.Comment) error {
	_, err := s.coll.InsertOne(ctx, c)
	return err
}

func (s *MongoCommentStore) FindByID(ctx context.Context, id string) (*postmodel.Comment, bool) {
	var c postmodel.Comment
	if err := s.coll.FindOne(ctx, bson.M{"_id": id}).Decode(&c); err != nil {
		return nil, false
	}
	return &c, true
}

func notDeleted() bson.M { return bson.M{"$ne": "deleted"} }

func normalizeLimit(limit, fallback int) int {
	if limit <= 0 {
		return fallback
	}
	return limit
}

// mainSortSpec is the index-backed sort for the non-pinned (ranked) segment. It
// must stay in lockstep with MemoryCommentStore.lessComment's mode branch. _id
// is the deterministic final tiebreak. createdAt+_id make the order total even
// when the mutable score key is unchanged (no drift within a session).
func mainSortSpec(mode commentdomain.SortMode) bson.D {
	switch mode {
	case commentdomain.SortMostLiked:
		return bson.D{{Key: "likeCount", Value: -1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}
	case commentdomain.SortLatest:
		return bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}
	default:
		return bson.D{{Key: "recommendedScore", Value: -1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}
	}
}

var pinnedSortSpec = bson.D{{Key: "pinnedAt", Value: -1}, {Key: "_id", Value: -1}}

var flatSortSpec = bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}

// scoreFieldForMode returns the score field name for score-ordered modes, or ""
// for latest (createdAt-only).
func scoreFieldForMode(mode commentdomain.SortMode) string {
	switch mode {
	case commentdomain.SortMostLiked:
		return "likeCount"
	case commentdomain.SortRecommended:
		return "recommendedScore"
	default:
		return ""
	}
}

// keysetAfter builds the strict "after cursor" predicate for a DESC keyset on
// (scoreField?, createdAt, _id). When scoreField is empty the keyset is
// (createdAt, _id) only. This index-seeks the next page with no offset/scan.
func keysetAfter(scoreField string, cur commentdomain.Cursor) bson.M {
	createdAt := cur.KeyTime()
	if scoreField == "" || !cur.HasScore {
		return bson.M{"$or": bson.A{
			bson.M{"createdAt": bson.M{"$lt": createdAt}},
			bson.M{"createdAt": createdAt, "_id": bson.M{"$lt": cur.ID}},
		}}
	}
	return bson.M{"$or": bson.A{
		bson.M{scoreField: bson.M{"$lt": cur.Score}},
		bson.M{scoreField: cur.Score, "createdAt": bson.M{"$lt": createdAt}},
		bson.M{scoreField: cur.Score, "createdAt": createdAt, "_id": bson.M{"$lt": cur.ID}},
	}}
}

// pinnedKeysetAfter builds the strict "after cursor" predicate for the pinned
// segment DESC keyset on (pinnedAt, _id).
func pinnedKeysetAfter(cur commentdomain.Cursor) bson.M {
	pinnedAt := cur.KeyTime()
	return bson.M{"$or": bson.A{
		bson.M{"pinnedAt": bson.M{"$lt": pinnedAt}},
		bson.M{"pinnedAt": pinnedAt, "_id": bson.M{"$lt": cur.ID}},
	}}
}

func mainCursorFor(c postmodel.Comment, mode commentdomain.SortMode) commentdomain.Cursor {
	cur := commentdomain.Cursor{Phase: commentdomain.PhaseMain, TimeUnixNano: c.CreatedAt.UnixNano(), ID: c.ID}
	switch mode {
	case commentdomain.SortMostLiked:
		cur.HasScore = true
		cur.Score = float64(c.LikeCount)
	case commentdomain.SortRecommended:
		cur.HasScore = true
		cur.Score = c.RecommendedScore
	}
	return cur
}

func flatCursorFor(c postmodel.Comment) commentdomain.Cursor {
	return commentdomain.Cursor{Phase: commentdomain.PhaseFlat, TimeUnixNano: c.CreatedAt.UnixNano(), ID: c.ID}
}

func pinnedCursorFor(c postmodel.Comment) commentdomain.Cursor {
	return commentdomain.Cursor{Phase: commentdomain.PhasePinned, TimeUnixNano: c.PinnedAt.UnixNano(), ID: c.ID}
}

func (s *MongoCommentStore) fetchPage(ctx context.Context, filter bson.M, sort bson.D, limit int) ([]postmodel.Comment, error) {
	cur, err := s.coll.Find(ctx, filter, options.Find().SetSort(sort).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	var docs []postmodel.Comment
	if err := cur.All(ctx, &docs); err != nil {
		return nil, err
	}
	return docs, nil
}

// ListTopLevel returns one keyset page: pinned segment first (by pinnedAt desc),
// then the non-pinned ranked segment (by the mode key). The cursor records which
// segment to resume in so transitions never re-scan or drop rows.
func (s *MongoCommentStore) ListTopLevel(
	ctx context.Context, postID string, mode commentdomain.SortMode, cursor string, limit int,
) (commentdomain.Page, error) {
	limit = normalizeLimit(limit, 20)
	cur, hasCursor := commentdomain.DecodeCursor(cursor)

	result := make([]postmodel.Comment, 0, limit)

	// Phase 1: pinned segment (skip when the cursor already advanced to main).
	if !hasCursor || cur.Phase == commentdomain.PhasePinned {
		pinnedFilter := bson.M{"postId": postID, "parentCommentId": "", "status": notDeleted(), "isPinned": true}
		if hasCursor && cur.Phase == commentdomain.PhasePinned {
			pinnedFilter["$and"] = bson.A{pinnedKeysetAfter(cur)}
		}
		pinned, err := s.fetchPage(ctx, pinnedFilter, pinnedSortSpec, limit+1)
		if err != nil {
			return commentdomain.Page{}, err
		}
		if len(pinned) > limit {
			page := pinned[:limit]
			last := page[len(page)-1]
			return commentdomain.Page{Comments: page, NextCursor: commentdomain.EncodeCursor(
				commentdomain.Cursor{Phase: commentdomain.PhasePinned, TimeUnixNano: last.PinnedAt.UnixNano(), ID: last.ID},
			)}, nil
		}
		result = append(result, pinned...)
		// Pinned segment exhausted → continue into the main segment from the top.
		cur = commentdomain.Cursor{Phase: commentdomain.PhaseMain}
	}

	// Phase 2: non-pinned ranked segment.
	need := limit - len(result)
	mainFilter := bson.M{"postId": postID, "parentCommentId": "", "status": notDeleted(), "isPinned": bson.M{"$ne": true}}
	if cur.Phase == commentdomain.PhaseMain && cur.ID != "" {
		mainFilter["$and"] = bson.A{keysetAfter(scoreFieldForMode(mode), cur)}
	}
	if need <= 0 {
		// Pinned exactly filled the page; peek main to decide the next cursor.
		peek, err := s.fetchPage(ctx, mainFilter, mainSortSpec(mode), 1)
		if err != nil {
			return commentdomain.Page{}, err
		}
		next := ""
		if len(peek) > 0 {
			next = commentdomain.EncodeCursor(commentdomain.Cursor{Phase: commentdomain.PhaseMain})
		}
		return commentdomain.Page{Comments: result, NextCursor: next}, nil
	}
	main, err := s.fetchPage(ctx, mainFilter, mainSortSpec(mode), need+1)
	if err != nil {
		return commentdomain.Page{}, err
	}
	if len(main) > need {
		main = main[:need]
		result = append(result, main...)
		last := result[len(result)-1]
		return commentdomain.Page{Comments: result, NextCursor: commentdomain.EncodeCursor(mainCursorFor(last, mode))}, nil
	}
	result = append(result, main...)
	return commentdomain.Page{Comments: result, NextCursor: ""}, nil
}

// listFlat is the shared (createdAt desc, _id desc) keyset page used by replies,
// author and received feeds.
func (s *MongoCommentStore) listFlat(ctx context.Context, filter bson.M, cursor string, limit int) (commentdomain.Page, error) {
	limit = normalizeLimit(limit, 20)
	if cur, ok := commentdomain.DecodeCursor(cursor); ok && cur.ID != "" {
		filter["$and"] = bson.A{keysetAfter("", cur)}
	}
	docs, err := s.fetchPage(ctx, filter, flatSortSpec, limit+1)
	if err != nil {
		return commentdomain.Page{}, err
	}
	next := ""
	if len(docs) > limit {
		docs = docs[:limit]
		next = commentdomain.EncodeCursor(flatCursorFor(docs[len(docs)-1]))
	}
	return commentdomain.Page{Comments: docs, NextCursor: next}, nil
}

func (s *MongoCommentStore) ListReplies(
	ctx context.Context, postID, parentID, cursor string, limit int,
) (commentdomain.Page, error) {
	return s.listFlat(ctx, bson.M{"postId": postID, "parentCommentId": parentID, "status": notDeleted()}, cursor, normalizeLimit(limit, 10))
}

func (s *MongoCommentStore) RepliesForParents(
	ctx context.Context, postID string, parentIDs []string, perParent int,
) (map[string][]postmodel.Comment, error) {
	out := map[string][]postmodel.Comment{}
	if len(parentIDs) == 0 {
		return out, nil
	}
	if perParent <= 0 {
		perParent = 1
	}
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"postId":          postID,
			"parentCommentId": bson.M{"$in": parentIDs},
			"status":          notDeleted(),
		}}},
		{{Key: "$sort", Value: bson.D{{Key: "parentCommentId", Value: 1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}}},
		{{Key: "$group", Value: bson.M{"_id": "$parentCommentId", "docs": bson.M{"$push": "$$ROOT"}}}},
		{{Key: "$project", Value: bson.M{"docs": bson.M{"$slice": bson.A{"$docs", perParent}}}}},
	}
	cur, err := s.coll.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	var groups []struct {
		ID   string              `bson:"_id"`
		Docs []postmodel.Comment `bson:"docs"`
	}
	if err := cur.All(ctx, &groups); err != nil {
		return nil, err
	}
	for _, g := range groups {
		out[g.ID] = g.Docs
	}
	return out, nil
}

func (s *MongoCommentStore) ListByAuthor(
	ctx context.Context, authorID, cursor string, limit int,
) (commentdomain.Page, error) {
	return s.listFlat(ctx, bson.M{"authorId": authorID, "status": notDeleted()}, cursor, limit)
}

func (s *MongoCommentStore) ListReceivedByPostAuthor(
	ctx context.Context, postAuthorID string, postIDs []string, cursor string, limit int,
) (commentdomain.Page, error) {
	if len(postIDs) == 0 {
		return commentdomain.Page{Comments: []postmodel.Comment{}}, nil
	}
	filter := bson.M{
		"postId":   bson.M{"$in": postIDs},
		"authorId": bson.M{"$ne": postAuthorID},
		"status":   notDeleted(),
	}
	return s.listFlat(ctx, filter, cursor, limit)
}

func (s *MongoCommentStore) ListByPostForActivity(ctx context.Context, postID string) ([]postmodel.Comment, error) {
	cur, err := s.coll.Find(ctx, bson.M{"postId": postID, "status": notDeleted()})
	if err != nil {
		return nil, err
	}
	var docs []postmodel.Comment
	if err := cur.All(ctx, &docs); err != nil {
		return nil, err
	}
	return docs, nil
}

// SoftDelete marks the comment deleted and records the deletedAt timestamp
// (record retained for audit / explainable delta counting). Returns the
// pre-delete snapshot. An already-deleted comment is treated as not found so the
// delete is idempotent and never double-decrements the post comment counter.
func (s *MongoCommentStore) SoftDelete(
	ctx context.Context, id string, deletedAt time.Time,
) (*postmodel.Comment, bool, error) {
	if deletedAt.IsZero() {
		deletedAt = time.Now().UTC()
	}
	var pre postmodel.Comment
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": id, "status": notDeleted()},
		bson.M{"$set": bson.M{"status": "deleted", "deletedAt": deletedAt.UTC()}},
		options.FindOneAndUpdate().SetReturnDocument(options.Before),
	).Decode(&pre)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, false, nil
		}
		return nil, false, err
	}
	return &pre, true, nil
}

func (s *MongoCommentStore) SetPinned(
	ctx context.Context, id string, pinned bool, pinnedAt time.Time,
) (bool, error) {
	update := bson.M{"$set": bson.M{"isPinned": pinned, "pinnedAt": pinnedAt}}
	if !pinned {
		update = bson.M{"$set": bson.M{"isPinned": false, "pinnedAt": time.Time{}}}
	}
	res, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, update)
	if err != nil {
		return false, err
	}
	return res.MatchedCount > 0, nil
}

func (s *MongoCommentStore) AdjustReplyCount(
	ctx context.Context, id string, delta int64, recommendedScore float64,
) (*postmodel.Comment, bool, error) {
	var updated postmodel.Comment
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": id},
		bson.M{
			"$inc": bson.M{"replyCount": delta},
			"$set": bson.M{"recommendedScore": recommendedScore},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&updated)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, false, nil
		}
		return nil, false, err
	}
	return &updated, true, nil
}

func (s *MongoCommentStore) SetReactionState(
	ctx context.Context, id string, likeCount, dislikeCount int64, recommendedScore float64,
) (bool, error) {
	res, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{"$set": bson.M{
		"likeCount":        likeCount,
		"dislikeCount":     dislikeCount,
		"recommendedScore": recommendedScore,
	}})
	if err != nil {
		return false, err
	}
	return res.MatchedCount > 0, nil
}

func (s *MongoCommentStore) SetAttachments(
	ctx context.Context, id string, attachmentIDs []string, attachments []map[string]any,
) (bool, error) {
	res, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{"$set": bson.M{
		"attachmentMediaIds": attachmentIDs,
		"attachments":        attachments,
	}})
	if err != nil {
		return false, err
	}
	return res.MatchedCount > 0, nil
}

func (s *MongoCommentStore) CountByPost(ctx context.Context, postID string) (int64, error) {
	return s.coll.CountDocuments(ctx, bson.M{"postId": postID, "status": notDeleted()})
}

func (s *MongoCommentStore) CountReplies(ctx context.Context, postID, parentID string) (int64, error) {
	return s.coll.CountDocuments(ctx, bson.M{"postId": postID, "parentCommentId": parentID, "status": notDeleted()})
}

// timeWindow builds a half-open (since, until] range predicate for field. A zero
// since is treated as unbounded-below.
func timeWindow(field string, since, until time.Time) bson.M {
	rng := bson.M{"$lte": until.UTC()}
	if !since.IsZero() {
		rng["$gt"] = since.UTC()
	}
	return bson.M{field: rng}
}

func (s *MongoCommentStore) CountCreatedBetween(ctx context.Context, postID string, since, until time.Time) (int64, error) {
	filter := timeWindow("createdAt", since, until)
	filter["postId"] = postID
	return s.coll.CountDocuments(ctx, filter)
}

func (s *MongoCommentStore) CountDeletedBetween(ctx context.Context, postID string, since, until time.Time) (int64, error) {
	filter := timeWindow("deletedAt", since, until)
	filter["postId"] = postID
	filter["status"] = "deleted"
	return s.coll.CountDocuments(ctx, filter)
}
