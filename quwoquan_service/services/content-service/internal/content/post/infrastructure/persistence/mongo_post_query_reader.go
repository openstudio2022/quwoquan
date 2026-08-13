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

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// MongoPostQueryReader 是 canonical Post 查询的读侧适配器。
// 它刻意不提供 AggregateStore 方法，也绝不解码 postmodel.Post。
type MongoPostQueryReader struct {
	coll *mongo.Collection
}

func (r *MongoPostQueryReader) PostExists(
	ctx context.Context,
	postID string,
) (bool, error) {
	if r == nil || r.coll == nil {
		return false, fmt.Errorf("Post target reader is not configured")
	}
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return false, fmt.Errorf("Post id is required")
	}
	count, err := r.coll.CountDocuments(
		ctx,
		bson.M{"_id": postID, "status": bson.M{"$ne": "deleted"}},
		options.Count().SetLimit(1),
	)
	if err != nil {
		return false, fmt.Errorf("read Post target existence: %w", err)
	}
	return count == 1, nil
}

// ListPublicPostIDs 返回最新公开已发布 postId（公开 sitemap 读面专用，
// 只取 _id 投影，不出全文）。
func (r *MongoPostQueryReader) ListPublicPostIDs(
	ctx context.Context,
	limit int,
) ([]string, error) {
	if limit <= 0 || limit > 5000 {
		limit = 500
	}
	cursor, err := r.coll.Find(
		ctx,
		bson.M{"visibility": "public", "status": "published"},
		options.Find().
			SetProjection(bson.M{"_id": 1}).
			SetSort(bson.D{{Key: "publishedAt", Value: -1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var rows []struct {
		ID string `bson:"_id"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(rows))
	for _, row := range rows {
		if row.ID != "" {
			ids = append(ids, row.ID)
		}
	}
	return ids, nil
}

func NewMongoPostQueryReader(coll *mongo.Collection) *MongoPostQueryReader {
	return &MongoPostQueryReader{coll: coll}
}

func (r *MongoPostQueryReader) FindPostRevision(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostRevisionSlice, bool, error) {
	if err := r.ready(); err != nil {
		return postports.PostRevisionSlice{}, false, err
	}
	if strings.TrimSpace(string(postID)) == "" {
		return postports.PostRevisionSlice{}, false, errors.New("post revision query requires post id")
	}

	var revision postports.PostRevisionSlice
	err := r.coll.FindOne(
		ctx,
		bson.D{
			{Key: "_id", Value: string(postID)},
			{Key: "status", Value: bson.D{{Key: "$ne", Value: "deleted"}}},
		},
		options.FindOne().SetProjection(PostRevisionProjection()),
	).Decode(&revision)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return postports.PostRevisionSlice{}, false, nil
	}
	if err != nil {
		return postports.PostRevisionSlice{}, false, fmt.Errorf("decode post revision slice: %w", err)
	}
	return revision, true, nil
}

func (r *MongoPostQueryReader) FindPostDetail(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	if err := r.ready(); err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	if strings.TrimSpace(string(postID)) == "" {
		return postports.PostDetailSlice{}, false, errors.New("post detail query requires post id")
	}

	var detail postports.PostDetailSlice
	err := r.coll.FindOne(
		ctx,
		bson.D{
			{Key: "_id", Value: string(postID)},
			{Key: "accountRestricted", Value: bson.M{"$ne": true}},
		},
		options.FindOne().SetProjection(PostDetailProjection()),
	).Decode(&detail)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return postports.PostDetailSlice{}, false, nil
	}
	if err != nil {
		return postports.PostDetailSlice{}, false, fmt.Errorf("decode post detail slice: %w", err)
	}
	return detail, true, nil
}

func (r *MongoPostQueryReader) ListPostsReferencingMedia(
	ctx context.Context,
	mediaAssetID string,
) ([]postports.MediaReferencedPostSlice, error) {
	if err := r.ready(); err != nil {
		return nil, err
	}
	mediaAssetID = strings.TrimSpace(mediaAssetID)
	if mediaAssetID == "" {
		return nil, errors.New("media reference query requires media asset id")
	}

	cursor, err := r.coll.Find(
		ctx,
		bson.D{
			{Key: "mediaAssetIds", Value: mediaAssetID},
			{Key: "status", Value: bson.D{{Key: "$ne", Value: "deleted"}}},
		},
		options.Find().
			SetProjection(bson.D{
				{Key: "_id", Value: 1},
				{Key: "authorId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "moderationStatus", Value: 1},
			}).
			SetSort(bson.D{{Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, fmt.Errorf("find Post media references: %w", err)
	}
	defer func() { _ = cursor.Close(ctx) }()

	references := make([]postports.MediaReferencedPostSlice, 0)
	for cursor.Next(ctx) {
		var reference postports.MediaReferencedPostSlice
		if err := cursor.Decode(&reference); err != nil {
			return nil, fmt.Errorf("decode Post media reference: %w", err)
		}
		references = append(references, reference)
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate Post media references: %w", err)
	}
	return references, nil
}

func (r *MongoPostQueryReader) ListAuthorPosts(
	ctx context.Context,
	request postports.AuthorPostReadRequest,
) (postports.AuthorPostPageSlice, error) {
	if err := r.ready(); err != nil {
		return postports.AuthorPostPageSlice{}, err
	}
	if strings.TrimSpace(string(request.AuthorPersonaID())) == "" {
		return postports.AuthorPostPageSlice{}, errors.New("author post query requires author persona")
	}
	if request.Limit() <= 0 || request.Limit() > postports.MaxPostQueryPageSize {
		return postports.AuthorPostPageSlice{}, errors.New("author post query has invalid limit")
	}

	filter, err := AuthorPostFilter(request)
	if err != nil {
		return postports.AuthorPostPageSlice{}, err
	}
	sortField := request.SortField()
	if cursor := request.Cursor(); cursor.IsSet() {
		filter = bson.D{{Key: "$and", Value: bson.A{
			filter,
			bson.D{afterAuthorPostCursor(sortField, cursor)},
		}}}
	}

	cursor, err := r.coll.Find(
		ctx,
		filter,
		options.Find().
			SetProjection(AuthorPostProjection()).
			SetSort(bson.D{{Key: sortField, Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(request.Limit()+1)),
	)
	if err != nil {
		return postports.AuthorPostPageSlice{}, fmt.Errorf("find author post page: %w", err)
	}
	defer func() { _ = cursor.Close(ctx) }()

	items := make([]postports.AuthorPostItemSlice, 0, request.Limit()+1)
	for cursor.Next(ctx) {
		var item postports.AuthorPostItemSlice
		if err := cursor.Decode(&item); err != nil {
			return postports.AuthorPostPageSlice{}, fmt.Errorf("decode author post slice: %w", err)
		}
		items = append(items, item)
	}
	if err := cursor.Err(); err != nil {
		return postports.AuthorPostPageSlice{}, fmt.Errorf("iterate author post page: %w", err)
	}

	page := postports.AuthorPostPageSlice{Items: items}
	if len(page.Items) > request.Limit() {
		page.HasMore = true
		page.Items = page.Items[:request.Limit()]
		last := page.Items[len(page.Items)-1]
		page.NextCursor = postports.NewAuthorPostCursor(
			request.CursorScope(),
			authorPostSortAt(last, request.AccessScope()),
			last.PostID,
		).Encode()
	}
	return page, nil
}

func (r *MongoPostQueryReader) ListGatheringPosts(
	ctx context.Context,
	request postports.GatheringPostReadRequest,
) (postports.GatheringPostPageSlice, error) {
	if err := r.ready(); err != nil {
		return postports.GatheringPostPageSlice{}, err
	}
	if strings.TrimSpace(request.GatheringID()) == "" {
		return postports.GatheringPostPageSlice{}, errors.New(
			"gathering post query requires gatheringId",
		)
	}
	if request.Limit() <= 0 || request.Limit() > postports.MaxPostQueryPageSize {
		return postports.GatheringPostPageSlice{}, errors.New(
			"gathering post query has invalid limit",
		)
	}

	filter := GatheringPostFilter(request)
	sortField := request.SortField()
	if cursor := request.Cursor(); cursor.IsSet() {
		filter = bson.D{{Key: "$and", Value: bson.A{
			filter,
			bson.D{afterAuthorPostCursor(sortField, cursor)},
		}}}
	}

	cursor, err := r.coll.Find(
		ctx,
		filter,
		options.Find().
			SetProjection(AuthorPostProjection()).
			SetSort(bson.D{{Key: sortField, Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(request.Limit()+1)),
	)
	if err != nil {
		return postports.GatheringPostPageSlice{}, fmt.Errorf(
			"find gathering post page: %w",
			err,
		)
	}
	defer func() { _ = cursor.Close(ctx) }()

	items := make([]postports.AuthorPostItemSlice, 0, request.Limit()+1)
	for cursor.Next(ctx) {
		var item postports.AuthorPostItemSlice
		if err := cursor.Decode(&item); err != nil {
			return postports.GatheringPostPageSlice{}, fmt.Errorf(
				"decode gathering post slice: %w",
				err,
			)
		}
		items = append(items, item)
	}
	if err := cursor.Err(); err != nil {
		return postports.GatheringPostPageSlice{}, fmt.Errorf(
			"iterate gathering post page: %w",
			err,
		)
	}

	page := postports.GatheringPostPageSlice{Items: items}
	if len(page.Items) > request.Limit() {
		page.HasMore = true
		page.Items = page.Items[:request.Limit()]
		last := page.Items[len(page.Items)-1]
		page.NextCursor = postports.NewAuthorPostCursor(
			request.CursorScope(),
			last.PublishedAt,
			last.PostID,
		).Encode()
	}
	return page, nil
}

// GatheringPostFilter 是共同经历聚合区的存储侧过滤：只允许 public +
// published + approved 且作者主动写入 gatheringRef 的内容进入聚合区。
func GatheringPostFilter(request postports.GatheringPostReadRequest) bson.D {
	return bson.D{
		{Key: "gatheringRef", Value: strings.TrimSpace(request.GatheringID())},
		{Key: "status", Value: "published"},
		{Key: "visibility", Value: "public"},
		{Key: "moderationStatus", Value: "approved"},
		{Key: "accountRestricted", Value: bson.M{"$ne": true}},
	}
}

type postFeedDimensionsDocument struct {
	Width       bson.RawValue `bson:"width"`
	Height      bson.RawValue `bson:"height"`
	ImageWidth  bson.RawValue `bson:"imageWidth"`
	ImageHeight bson.RawValue `bson:"imageHeight"`
	DurationMS  bson.RawValue `bson:"durationMs"`
	Duration    bson.RawValue `bson:"duration"`
}

type postFeedDocument struct {
	postports.PostFeedItemSlice `bson:",inline"`
	TopLevelDimensions          postFeedDimensionsDocument `bson:",inline"`
	DeviceInfo                  postFeedDimensionsDocument `bson:"deviceInfo"`
	ArticleRenderProfile        postFeedDimensionsDocument `bson:"articleRenderProfile"`
	PrimaryHomepageSnapshot     postFeedDimensionsDocument `bson:"primaryHomepageSnapshot"`
}

func (r *MongoPostQueryReader) FindPublishedFeedPost(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	if err := r.ready(); err != nil {
		return postports.PostFeedItemSlice{}, false, err
	}
	if strings.TrimSpace(string(postID)) == "" {
		return postports.PostFeedItemSlice{}, false, errors.New("feed post query requires post id")
	}

	var document postFeedDocument
	err := r.coll.FindOne(
		ctx,
		bson.D{
			{Key: "_id", Value: string(postID)},
			{Key: "status", Value: "published"},
			{Key: "visibility", Value: "public"},
			{Key: "moderationStatus", Value: "approved"},
			{Key: "accountRestricted", Value: bson.M{"$ne": true}},
		},
		options.FindOne().SetProjection(PostFeedProjection()),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return postports.PostFeedItemSlice{}, false, nil
	}
	if err != nil {
		return postports.PostFeedItemSlice{}, false, fmt.Errorf("decode published feed post slice: %w", err)
	}
	return normalizePostFeedDocument(document), true, nil
}

// FindPublishedFeedPosts 单次 $in 批量取回（N3-1）：与单条读同一可见性谓词
// （published/public/approved），未命中的 id 缺席于返回 map。
func (r *MongoPostQueryReader) FindPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	if err := r.ready(); err != nil {
		return nil, err
	}
	postIDs := request.PostIDs()
	ids := make([]string, 0, len(postIDs))
	seen := make(map[string]bool, len(postIDs))
	for _, id := range postIDs {
		trimmed := strings.TrimSpace(string(id))
		if trimmed == "" || seen[trimmed] {
			continue
		}
		seen[trimmed] = true
		ids = append(ids, trimmed)
	}
	out := make(map[postports.PostID]postports.PostFeedItemSlice, len(ids))
	if len(ids) == 0 {
		return out, nil
	}
	filter := bson.D{
		{Key: "_id", Value: bson.M{"$in": ids}},
		{Key: "status", Value: "published"},
		{Key: "visibility", Value: "public"},
		{Key: "moderationStatus", Value: "approved"},
		{Key: "accountRestricted", Value: bson.M{"$ne": true}},
	}
	filter = appendReleaseBoundHydrationFilter(
		filter,
		request.ActiveReleaseID(),
		request.ManifestDigest(),
	)
	cursor, err := r.coll.Find(
		ctx,
		filter,
		options.Find().SetProjection(PostFeedProjection()),
	)
	if err != nil {
		return nil, fmt.Errorf("batch find published feed posts: %w", err)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var document postFeedDocument
		if decodeErr := cursor.Decode(&document); decodeErr != nil {
			return nil, fmt.Errorf("decode published feed post slice: %w", decodeErr)
		}
		slice := normalizePostFeedDocument(document)
		out[slice.PostID] = slice
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate published feed posts: %w", err)
	}
	return out, nil
}

func (r *MongoPostQueryReader) ListPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	if err := r.ready(); err != nil {
		return postports.PostFeedSlice{}, err
	}
	if request.Limit() <= 0 || request.Limit() > postports.MaxPostQueryPageSize {
		return postports.PostFeedSlice{}, errors.New("published feed query has invalid limit")
	}

	identity := strings.TrimSpace(string(request.Identity()))
	if identity != "" && identity != "moment" && identity != "work" {
		return postports.PostFeedSlice{}, errors.New("published feed query has invalid identity")
	}
	contentType := strings.TrimSpace(string(request.ContentType()))
	switch contentType {
	case "", "image", "video", "article", "micro", "moment":
	default:
		return postports.PostFeedSlice{}, errors.New("published feed query has invalid content type")
	}

	filter := bson.D{
		{Key: "status", Value: "published"},
		{Key: "visibility", Value: "public"},
		{Key: "moderationStatus", Value: "approved"},
		{Key: "accountRestricted", Value: bson.M{"$ne": true}},
	}
	if identity != "" {
		filter = append(filter, bson.E{Key: "contentIdentity", Value: identity})
	}
	if contentType != "" {
		filter = append(filter, bson.E{Key: "contentType", Value: contentType})
	}
	filter = appendCanonicalReleaseFilter(
		filter,
		request.ActiveReleaseID(),
		request.ManifestDigest(),
	)
	if cursorPostID := request.CursorPostID(); cursorPostID != "" {
		var cursor struct {
			PostID    string    `bson:"_id"`
			CreatedAt time.Time `bson:"createdAt"`
		}
		err := r.coll.FindOne(
			ctx,
			bson.D{{Key: "_id", Value: string(cursorPostID)}},
			options.FindOne().SetProjection(bson.D{{Key: "_id", Value: 1}, {Key: "createdAt", Value: 1}}),
		).Decode(&cursor)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return postports.PostFeedSlice{}, errors.New("published feed cursor post does not exist")
		}
		if err != nil {
			return postports.PostFeedSlice{}, fmt.Errorf("read published feed cursor: %w", err)
		}
		filter = append(filter, bson.E{Key: "$or", Value: bson.A{
			bson.D{{Key: "createdAt", Value: bson.D{{Key: "$lt", Value: cursor.CreatedAt}}}},
			bson.D{
				{Key: "createdAt", Value: cursor.CreatedAt},
				{Key: "_id", Value: bson.D{{Key: "$lt", Value: cursor.PostID}}},
			},
		}})
	}

	cursor, err := r.coll.Find(
		ctx,
		filter,
		options.Find().
			SetProjection(PostFeedProjection()).
			SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(request.Limit())),
	)
	if err != nil {
		return postports.PostFeedSlice{}, fmt.Errorf("find published feed posts: %w", err)
	}
	defer func() { _ = cursor.Close(ctx) }()

	items := make([]postports.PostFeedItemSlice, 0, request.Limit())
	for cursor.Next(ctx) {
		var document postFeedDocument
		if err := cursor.Decode(&document); err != nil {
			return postports.PostFeedSlice{}, fmt.Errorf("decode published feed post slice: %w", err)
		}
		items = append(items, normalizePostFeedDocument(document))
	}
	if err := cursor.Err(); err != nil {
		return postports.PostFeedSlice{}, fmt.Errorf("iterate published feed posts: %w", err)
	}
	return postports.PostFeedSlice{Items: items}, nil
}

func appendReleaseBoundHydrationFilter(
	filter bson.D,
	activeReleaseID string,
	manifestDigest string,
) bson.D {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	if activeReleaseID == "" {
		return filter
	}
	manifestDigest = strings.TrimSpace(manifestDigest)
	canonical := bson.M{
		"sourceOwner":     "qwq_data",
		"releaseId":       activeReleaseID,
		"lifecycleStatus": "active",
	}
	if manifestDigest != "" {
		canonical["manifestDigest"] = manifestDigest
	}
	return append(filter, bson.E{Key: "$or", Value: bson.A{
		bson.M{"sourceOwner": bson.M{"$ne": "qwq_data"}},
		canonical,
	}})
}

func appendCanonicalReleaseFilter(
	filter bson.D,
	activeReleaseID string,
	manifestDigest string,
) bson.D {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	if activeReleaseID == "" {
		return filter
	}
	filter = append(filter,
		bson.E{Key: "sourceOwner", Value: "qwq_data"},
		bson.E{Key: "releaseId", Value: activeReleaseID},
		bson.E{Key: "lifecycleStatus", Value: "active"},
	)
	if manifestDigest = strings.TrimSpace(manifestDigest); manifestDigest != "" {
		filter = append(filter, bson.E{Key: "manifestDigest", Value: manifestDigest})
	}
	return filter
}

func normalizePostFeedDocument(document postFeedDocument) postports.PostFeedItemSlice {
	item := document.PostFeedItemSlice
	for _, dimensions := range []postFeedDimensionsDocument{
		document.TopLevelDimensions,
		document.DeviceInfo,
		document.ArticleRenderProfile,
		document.PrimaryHomepageSnapshot,
	} {
		width := positiveBSONInt64(dimensions.Width)
		if width <= 0 {
			width = positiveBSONInt64(dimensions.ImageWidth)
		}
		height := positiveBSONInt64(dimensions.Height)
		if height <= 0 {
			height = positiveBSONInt64(dimensions.ImageHeight)
		}
		if item.Width <= 0 && width > 0 {
			item.Width = width
		}
		if item.Height <= 0 && height > 0 {
			item.Height = height
		}
		duration := positiveBSONInt64(dimensions.DurationMS)
		if duration <= 0 {
			duration = positiveBSONInt64(dimensions.Duration)
		}
		if item.DurationMS <= 0 && duration > 0 {
			item.DurationMS = duration
		}
	}
	return item
}

func positiveBSONInt64(value bson.RawValue) int64 {
	if converted, ok := value.AsInt64OK(); ok && converted > 0 {
		return converted
	}
	if converted, ok := value.DoubleOK(); ok && converted > 0 {
		return int64(converted)
	}
	return 0
}

func (r *MongoPostQueryReader) ready() error {
	if r == nil || r.coll == nil {
		return errors.New("mongo post query reader is not configured")
	}
	return nil
}

func AuthorPostFilter(request postports.AuthorPostReadRequest) (bson.D, error) {
	filter := bson.D{{Key: "authorId", Value: string(request.AuthorPersonaID())}}
	switch request.AccessScope() {
	case postports.AuthorPostAccessPublic:
		// 非 owner 永远只看到已发布且公开的内容，不会通过列表探测 draft/private。
		filter = append(
			filter,
			bson.E{Key: "status", Value: "published"},
			bson.E{Key: "visibility", Value: "public"},
			bson.E{Key: "moderationStatus", Value: "approved"},
			bson.E{Key: "accountRestricted", Value: bson.M{"$ne": true}},
		)
	case postports.AuthorPostAccessOwner:
		// Owner 可读取自己的 draft/published 和所有 visibility；删除记录不属于
		// canonical list。
		filter = append(filter, bson.E{Key: "status", Value: bson.D{{Key: "$ne", Value: "deleted"}}})
		if visibility := strings.TrimSpace(string(request.Visibility())); visibility != "" {
			filter = append(filter, bson.E{Key: "visibility", Value: visibility})
		}
	default:
		return nil, errors.New("author post query has invalid access scope")
	}

	if identity := strings.TrimSpace(string(request.Identity())); identity != "" {
		filter = append(filter, bson.E{Key: "contentIdentity", Value: identity})
	}
	if contentType := strings.TrimSpace(string(request.ContentType())); contentType != "" {
		filter = append(filter, bson.E{Key: "contentType", Value: contentType})
	}
	return filter, nil
}

func afterAuthorPostCursor(
	sortField string,
	cursor postports.AuthorPostCursor,
) bson.E {
	return bson.E{
		Key: "$or",
		Value: bson.A{
			bson.D{{Key: sortField, Value: bson.D{{Key: "$lt", Value: cursor.SortAt()}}}},
			bson.D{
				{Key: sortField, Value: cursor.SortAt()},
				{Key: "_id", Value: bson.D{{Key: "$lt", Value: string(cursor.PostID())}}},
			},
		},
	}
}

func authorPostSortAt(
	item postports.AuthorPostItemSlice,
	scope postports.AuthorPostAccessScope,
) time.Time {
	if scope == postports.AuthorPostAccessOwner {
		return item.UpdatedAt
	}
	return item.PublishedAt
}

// PostDetailProjection 是封闭的 BSON 白名单。新增 Post 聚合字段除非显式进入
// 此 query slice 及其契约测试，否则不能通过 GetPost 读取。
func PostDetailProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "creatorProfileId", Value: 1},
		{Key: "creatorArchetype", Value: 1},
		{Key: "creatorProfileVersion", Value: 1},
		{Key: "creatorDisclosure", Value: 1},
		{Key: "experienceClaimMode", Value: 1},
		{Key: "authorDisplayNameSnapshot", Value: 1},
		{Key: "authorAvatarUrlSnapshot", Value: 1},
		{Key: "personaContextVersion", Value: 1},
		{Key: "contentType", Value: 1},
		{Key: "contentIdentity", Value: 1},
		{Key: "title", Value: 1},
		{Key: "body", Value: 1},
		{Key: "summary", Value: 1},
		{Key: "tagRefs", Value: 1},
		{Key: "entityRefs", Value: 1},
		{Key: "semanticMentions", Value: 1},
		{Key: "mediaAssetIds", Value: 1},
		{Key: "mediaUrls", Value: 1},
		{Key: "mediaItems", Value: 1},
		{Key: "coverUrl", Value: 1},
		{Key: "thumbnailUrl", Value: 1},
		{Key: "width", Value: 1},
		{Key: "height", Value: 1},
		{Key: "durationMs", Value: 1},
		{Key: "articleMarkdown", Value: 1},
		{Key: "markdownDialect", Value: 1},
		{Key: "articleMarkdownDigest", Value: 1},
		{Key: "articleAssetManifest", Value: 1},
		{Key: "articleRenderProfile", Value: 1},
		{Key: "contentVertical", Value: 1},
		{Key: "entityMentions", Value: 1},
		{Key: "articleTemplate", Value: 1},
		{Key: "articleFontPreset", Value: 1},
		{Key: "videoUrl", Value: 1},
		{Key: "sourceAttribution", Value: 1},
		{Key: "coverStrategy", Value: 1},
		{Key: "coverFrameTimeMs", Value: 1},
		{Key: "location", Value: 1},
		{Key: "locationName", Value: 1},
		{Key: "geoTagRef", Value: 1},
		{Key: "visitedAt", Value: 1},
		{Key: "primaryHomepageId", Value: 1},
		{Key: "canonicalEntityId", Value: 1},
		{Key: "primaryHomepageType", Value: 1},
		{Key: "primaryHomepageSnapshot", Value: 1},
		{Key: "status", Value: 1},
		{Key: "visibility", Value: 1},
		{Key: "moderationStatus", Value: 1},
		{Key: "assistantUsePolicy", Value: 1},
		{Key: "sourcePostId", Value: 1},
		{Key: "sourceType", Value: 1},
		{Key: "gatheringRef", Value: 1},
		{Key: "illustrationAssetId", Value: 1},
		{Key: "likeCount", Value: 1},
		{Key: "commentCount", Value: 1},
		{Key: "pinnedCommentId", Value: 1},
		{Key: "shareCount", Value: 1},
		{Key: "viewCount", Value: 1},
		{Key: "helperReadSummary", Value: 1},
		{Key: "createdAt", Value: 1},
		{Key: "updatedAt", Value: 1},
		{Key: "publishedAt", Value: 1},
		{Key: "lastActiveAt", Value: 1},
		{Key: "sourceTaskId", Value: 1},
	}
}

func PostRevisionProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "version", Value: 1},
		{Key: "contentDigest", Value: 1},
	}
}

func AuthorPostProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "authorDisplayNameSnapshot", Value: 1},
		{Key: "authorAvatarUrlSnapshot", Value: 1},
		{Key: "contentType", Value: 1},
		{Key: "contentIdentity", Value: 1},
		{Key: "title", Value: 1},
		{Key: "body", Value: 1},
		{Key: "summary", Value: 1},
		{Key: "coverUrl", Value: 1},
		{Key: "thumbnailUrl", Value: 1},
		{Key: "mediaUrls", Value: 1},
		{Key: "videoUrl", Value: 1},
		{Key: "articleTemplate", Value: 1},
		{Key: "articleFontPreset", Value: 1},
		{Key: "contentVertical", Value: 1},
		{Key: "locationName", Value: 1},
		{Key: "geoTagRef", Value: 1},
		{Key: "primaryHomepageId", Value: 1},
		{Key: "canonicalEntityId", Value: 1},
		{Key: "status", Value: 1},
		{Key: "visibility", Value: 1},
		{Key: "likeCount", Value: 1},
		{Key: "commentCount", Value: 1},
		{Key: "shareCount", Value: 1},
		{Key: "viewCount", Value: 1},
		{Key: "createdAt", Value: 1},
		{Key: "updatedAt", Value: 1},
		{Key: "publishedAt", Value: 1},
		{Key: "lastActiveAt", Value: 1},
		{Key: "personaContextVersion", Value: 1},
	}
}

// PostFeedProjection 是首页 Feed 的封闭 BSON 白名单。mediaItems 只读取
// adaptive delivery 所需的 typed 子字段，避免为 HLS/CMAF 绑定把完整媒体序列
// （封面、预览轨与展示文案等）放大到每次首页 hydration。
func PostFeedProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "authorDisplayNameSnapshot", Value: 1},
		{Key: "authorAvatarUrlSnapshot", Value: 1},
		{Key: "contentType", Value: 1},
		{Key: "contentIdentity", Value: 1},
		{Key: "title", Value: 1},
		{Key: "body", Value: 1},
		{Key: "summary", Value: 1},
		{Key: "mediaUrls", Value: 1},
		{Key: "mediaItems.kind", Value: 1},
		{Key: "mediaItems.mediaAssetId", Value: 1},
		{Key: "mediaItems.mediaAssetVersion", Value: 1},
		{Key: "mediaItems.hlsCmafMasterManifestUrl", Value: 1},
		{Key: "mediaItems.hlsCmafDescriptorVersion", Value: 1},
		{Key: "videoUrl", Value: 1},
		{Key: "coverUrl", Value: 1},
		{Key: "thumbnailUrl", Value: 1},
		{Key: "coverStrategy", Value: 1},
		{Key: "coverFrameTimeMs", Value: 1},
		{Key: "durationMs", Value: 1},
		{Key: "width", Value: 1},
		{Key: "height", Value: 1},
		{Key: "tagRefs", Value: 1},
		{Key: "entityRefs", Value: 1},
		{Key: "visibility", Value: 1},
		{Key: "contentVertical", Value: 1},
		{Key: "primaryHomepageId", Value: 1},
		{Key: "primaryHomepageType", Value: 1},
		{Key: "gatheringRef", Value: 1},
		{Key: "sourceTaskId", Value: 1},
		{Key: "sourceOwner", Value: 1},
		{Key: "releaseId", Value: 1},
		{Key: "manifestDigest", Value: 1},
		{Key: "lifecycleStatus", Value: 1},
		{Key: "likeCount", Value: 1},
		{Key: "commentCount", Value: 1},
		{Key: "shareCount", Value: 1},
		{Key: "createdAt", Value: 1},
		{Key: "updatedAt", Value: 1},
		{Key: "publishedAt", Value: 1},
		{Key: "deviceInfo", Value: 1},
		{Key: "articleRenderProfile", Value: 1},
		{Key: "primaryHomepageSnapshot", Value: 1},
	}
}

var (
	_ postports.PostRevisionSliceReader = (*MongoPostQueryReader)(nil)
	_ postports.PostDetailReader        = (*MongoPostQueryReader)(nil)
	_ postports.AuthorPostReader        = (*MongoPostQueryReader)(nil)
	_ postports.GatheringPostReader     = (*MongoPostQueryReader)(nil)
	_ postports.PostFeedReader          = (*MongoPostQueryReader)(nil)
)
