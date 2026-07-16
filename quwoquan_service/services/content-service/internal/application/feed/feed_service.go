package feed

import (
	"context"
	"encoding/base64"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/services/content-service/internal/application/identity"
	"quwoquan_service/services/content-service/internal/application/intersection"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

type FeedService struct {
	engine        *rtrec.Engine
	postReader    postports.PostFeedReader
	intersections feedIntersectionProvider
}

func NewFeedService(engine *rtrec.Engine, reader postports.PostFeedReader, opts ...FeedServiceOption) *FeedService {
	s := &FeedService{
		engine:     engine,
		postReader: reader,
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

type FeedServiceOption func(*FeedService)

// WithFeedIntersectionProvider 注入交集理由池来源（70/20/10 内容流附着）。
func WithFeedIntersectionProvider(provider feedIntersectionProvider) FeedServiceOption {
	return func(s *FeedService) { s.intersections = provider }
}

type ListFeedRequest struct {
	UserID      string
	SessionID   string
	Identity    string
	Type        string
	Sort        string
	SubCategory string
	Cursor      string
	Limit       int
	// FeedRequestID 客户端回显的归因 id：首刷为空，分页/继续加载回显服务端首刷下发的 id。
	FeedRequestID   string
	BlockedUserIDs  []string
	BlockedKeywords []string
}

type FeedItemView struct {
	ID               string   `json:"id"`
	PostID           string   `json:"postId"`
	WireID           string   `json:"_id"`
	Type             string   `json:"type"`
	ContentType      string   `json:"contentType"`
	AuthorID         string   `json:"authorId"`
	Title            string   `json:"title,omitempty"`
	Body             string   `json:"body,omitempty"`
	Images           []string `json:"images,omitempty"`
	VideoURL         string   `json:"videoUrl,omitempty"`
	CoverURL         string   `json:"coverUrl,omitempty"`
	ThumbnailURL     string   `json:"thumbnailUrl,omitempty"`
	CoverStrategy    string   `json:"coverStrategy,omitempty"`
	CoverFrameTimeMs int64    `json:"coverFrameTimeMs,omitempty"`
	DurationMs       int64    `json:"durationMs,omitempty"`
	Width            int64    `json:"width,omitempty"`
	Height           int64    `json:"height,omitempty"`
	LikeCount        int64    `json:"likesCount"`
	CommentCount     int64    `json:"commentsCount"`
	ShareCount       int64    `json:"shares"`
	CreatedAt        string   `json:"createdAt"`
	// UpdatedAt 最后实质更新时间；与 createdAt 相等或更早时端只显示创作时间。零值省略。
	UpdatedAt string `json:"updatedAt,omitempty"`
	// PublishedAt 首次公开时间；零值（未发布/未知）时省略。
	PublishedAt string `json:"publishedAt,omitempty"`
	// IntersectionReasons 内容卡交集行（70/20/10 频率契约；空即无交集，端不渲染）。
	IntersectionReasons []intersection.IntersectionReasonView `json:"intersectionReasons,omitempty"`
	QualityScore        float64                               `json:"qualityScore,omitempty"`
	RecallPath          string                                `json:"recallPath,omitempty"`
	ContentVertical     string                                `json:"contentVertical,omitempty"`
	SupplySource        string                                `json:"supplySource,omitempty"`
	SourceTaskID        string                                `json:"sourceTaskId,omitempty"`
}

type ListFeedResponse struct {
	Items      []FeedItemView `json:"items"`
	NextCursor string         `json:"nextCursor,omitempty"`
	Cursor     string         `json:"cursor,omitempty"`
	// FeedRequestID 服务端权威下发的归因 id（frq_ 前缀 ULID）；端侧回显 + 透传行为事件。
	FeedRequestID string `json:"feedRequestId"`
	// RankingVersion / ReasonVersion 本次结果的排序与理由管线版本。
	RankingVersion string `json:"rankingVersion,omitempty"`
	ReasonVersion  string `json:"reasonVersion,omitempty"`
}

// feedTimeOrEmpty 把零值时间渲染为空串（配合 json omitempty 省略），
// 非零按统一 UTC RFC3339 输出，供端侧「创作 vs 更新」展示判定。
func feedTimeOrEmpty(t time.Time) string {
	if t.IsZero() {
		return ""
	}
	return t.UTC().Format("2006-01-02T15:04:05Z")
}

func (s *FeedService) ListFeed(ctx context.Context, req ListFeedRequest) (resp *ListFeedResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rec.ListFeed",
		attribute.String("feed.type", req.Type),
		attribute.String("feed.sort", req.Sort),
		attribute.Int("feed.limit", req.Limit))
	defer func() { rtobs.EndSpan(span, err) }()

	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	req.UserID = identity.NormalizeAnonymousSubAccountID(req.UserID)
	// feedRequestId 服务端权威化：首刷（无回显 id）生成新的 frq_ ULID；
	// 分页/继续加载时客户端回显原 id，这里复用以保持同一 feed 会话归因连续。
	// 该 id 既写入响应 envelope，也作为 recall 归因下传给 engine。
	feedRequestID := strings.TrimSpace(req.FeedRequestID)
	if feedRequestID == "" {
		feedRequestID = rtrec.NewFeedRequestID()
	}
	views := make([]FeedItemView, 0, limit)
	requestedIdentity := normalizeRequestedIdentity(req.Identity)
	requestedType := normalizeRequestType(req.Type)
	route := resolveFeedRoute(req)
	blockedUsers := toLowerSet(req.BlockedUserIDs)
	blockedKeywords := toLowerSet(req.BlockedKeywords)

	requestedCursor := strings.TrimSpace(req.Cursor)
	postReaderCursor := decodePostReaderFeedCursor(requestedCursor)
	cursor := requestedCursor
	nextCursor := ""
	seenPostIDs := map[string]struct{}{}
	// 强负反馈（dislike / 隐藏作者 / 隐藏内容类型）是产品硬规则，
	// 必须在推荐召回和显式类型/身份查询两种具名读路径生效。
	feedbackExclusions := s.engine.LoadFeedbackExclusions(ctx, req.UserID, req.SessionID)
	usePostReaderQuery := postReaderCursor != "" || requestedType != "" || requestedIdentity != ""
	appendPost := func(post *postports.PostFeedItemSlice, recItem *rtrec.FeedItem) bool {
		if post == nil {
			return false
		}
		postID := string(post.PostID)
		if _, seen := seenPostIDs[postID]; seen {
			return false
		}
		authorID := string(post.AuthorPersonaID)
		if _, blocked := blockedUsers[strings.ToLower(strings.TrimSpace(authorID))]; blocked {
			return false
		}
		if feedbackExclusions.NegativeContentIDs[strings.TrimSpace(postID)] {
			return false
		}
		if feedbackExclusions.HiddenAuthors[strings.TrimSpace(authorID)] {
			return false
		}
		if feedbackExclusions.HiddenContentTypes[strings.TrimSpace(string(post.ContentType))] {
			return false
		}
		if !postMatchesVertical(post, route.Vertical) {
			return false
		}
		if containsBlockedKeyword(post, blockedKeywords) {
			return false
		}
		postIdentity := resolvedContentIdentity(string(post.ContentType), string(post.ContentIdentity))
		if requestedIdentity != "" && postIdentity != requestedIdentity {
			return false
		}
		viewType := mapContentTypeToViewType(string(post.ContentType))
		if requestedType != "" && requestedIdentity != "moment" && viewType != requestedType {
			return false
		}
		seenPostIDs[postID] = struct{}{}
		thumbnailURL := strings.TrimSpace(post.ThumbnailURL)
		if thumbnailURL == "" {
			thumbnailURL = strings.TrimSpace(post.CoverURL)
		}
		qualityScore, recallPath, contentVertical, supplySource := feedItemAttribution(post, recItem)
		views = append(views, FeedItemView{
			ID:               postID,
			PostID:           postID,
			WireID:           postID,
			Type:             viewType,
			ContentType:      string(post.ContentType),
			AuthorID:         authorID,
			Title:            post.Title,
			Body:             post.Body,
			Images:           append([]string(nil), post.MediaURLs...),
			VideoURL:         post.VideoURL,
			CoverURL:         post.CoverURL,
			ThumbnailURL:     thumbnailURL,
			CoverStrategy:    post.CoverStrategy,
			CoverFrameTimeMs: post.CoverFrameTimeMS,
			DurationMs:       post.DurationMS,
			Width:            post.Width,
			Height:           post.Height,
			LikeCount:        post.LikeCount,
			CommentCount:     post.CommentCount,
			ShareCount:       post.ShareCount,
			CreatedAt:        post.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
			UpdatedAt:        feedTimeOrEmpty(post.UpdatedAt),
			PublishedAt:      feedTimeOrEmpty(post.PublishedAt),
			QualityScore:     qualityScore,
			RecallPath:       recallPath,
			ContentVertical:  contentVertical,
			SupplySource:     supplySource,
			SourceTaskID:     post.SourceTaskID,
		})
		return true
	}
	for attempt := 0; !usePostReaderQuery && attempt < 4 && len(views) < limit; attempt++ {
		recResp, err := s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
			UserID:        req.UserID,
			SessionID:     req.SessionID,
			FeedType:      route.FeedType,
			Sort:          normalizeFeedSort(req.Sort),
			Cursor:        cursor,
			Limit:         limit,
			Surface:       route.Surface,
			ChannelID:     route.ChannelID,
			Vertical:      route.Vertical,
			FeedRequestID: feedRequestID,
		})
		if err != nil {
			return nil, err
		}
		nextCursor = recResp.NextCursor
		for _, item := range recResp.Items {
			post, ok, readErr := s.postReader.FindPublishedFeedPost(
				ctx,
				postports.NewPostID(item.ContentID),
			)
			if readErr != nil {
				return nil, readErr
			}
			if !ok {
				continue
			}
			appendPost(&post, &item)
			if len(views) >= limit {
				break
			}
		}
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}
	// 只有显式类型/身份过滤或 PostReader cursor 才使用具名查询。
	// 普通推荐请求不允许在召回不足时偷渡到第二读主线。
	if len(views) < limit && route.Surface != "premium_stream" && usePostReaderQuery {
		pageCursor := postReaderCursor
		feedContentType := requestedType
		readerLimit := limit * 2
		if readerLimit > postports.MaxPostQueryPageSize {
			readerLimit = postports.MaxPostQueryPageSize
		}
		if requestedIdentity == "moment" {
			feedContentType = ""
		}
		for attempt := 0; attempt < 4 && len(views) < limit; attempt++ {
			page, readErr := s.postReader.ListPublishedFeedPosts(
				ctx,
				postports.NewPostFeedReadRequest(
					postports.ContentIdentity(requestedIdentity),
					postports.ContentType(feedContentType),
					postports.NewPostID(pageCursor),
					readerLimit,
				),
			)
			if readErr != nil {
				return nil, readErr
			}
			if len(page.Items) == 0 {
				break
			}
			for i := range page.Items {
				post := page.Items[i]
				if appendPost(&post, nil) && len(views) >= limit {
					nextCursor = encodePostReaderFeedCursor(string(post.PostID))
					break
				}
			}
			if len(views) >= limit || len(page.Items) < readerLimit {
				break
			}
			pageCursor = string(page.Items[len(page.Items)-1].PostID)
		}
	}
	if s.intersections != nil && strings.TrimSpace(req.UserID) != "" {
		if reasons, reasonErr := s.intersections.Feed(ctx, req.UserID, route.ChannelID, feedIntersectionPoolLimit); reasonErr == nil {
			attachFeedIntersections(views, reasons, req.UserID)
		}
	}
	return &ListFeedResponse{
		Items:          views,
		NextCursor:     nextCursor,
		Cursor:         nextCursor,
		FeedRequestID:  feedRequestID,
		RankingVersion: rtrec.RankingVersion,
		ReasonVersion:  rtrec.ReasonVersion,
	}, nil
}

func encodePostReaderFeedCursor(postID string) string {
	trimmed := strings.TrimSpace(postID)
	if trimmed == "" {
		return ""
	}
	return "post:" + base64.RawURLEncoding.EncodeToString([]byte(trimmed))
}

func decodePostReaderFeedCursor(cursor string) string {
	trimmed := strings.TrimSpace(cursor)
	if !strings.HasPrefix(trimmed, "post:") {
		return ""
	}
	decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(trimmed, "post:"))
	if err == nil {
		return strings.TrimSpace(string(decoded))
	}
	return ""
}

func normalizeFeedSort(sortValue string) string {
	switch strings.TrimSpace(strings.ToLower(sortValue)) {
	case "", rtrec.FeedSortRecommend:
		return rtrec.FeedSortRecommend
	default:
		return rtrec.FeedSortRecommend
	}
}

func mapContentTypeToViewType(contentType string) string {
	switch strings.TrimSpace(contentType) {
	case "micro":
		return "moment"
	case "image":
		return "image"
	case "video":
		return "video"
	case "article":
		return "article"
	default:
		return "image"
	}
}

func normalizeRequestType(t string) string {
	switch strings.TrimSpace(strings.ToLower(t)) {
	case "", "recommended", "following", "travel", "travel_photography", "premium", "similar", "featured", "immersive", "精品", "旅行", "旅游":
		return ""
	case "photo":
		return "image"
	case "note":
		return "article"
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
}

type feedRoute struct {
	FeedType  rtrec.FeedType
	Surface   string
	Vertical  string
	ChannelID string
}

func resolveFeedRoute(req ListFeedRequest) feedRoute {
	tokens := []string{
		strings.TrimSpace(strings.ToLower(req.Type)),
		strings.TrimSpace(strings.ToLower(req.SubCategory)),
	}
	for _, token := range tokens {
		switch token {
		case "premium", "similar", "featured", "immersive", "精品", "quality":
			return feedRoute{
				FeedType:  rtrec.FeedSimilar,
				Surface:   "premium_stream",
				ChannelID: "premium_stream",
			}
		case "travel", "travel_photography", "旅行", "旅游":
			return feedRoute{
				FeedType:  rtrec.FeedDiscovery,
				Surface:   "travel_photography",
				Vertical:  "travel_photography",
				ChannelID: "travel_photography",
			}
		}
	}
	return feedRoute{
		FeedType:  rtrec.FeedDiscovery,
		Surface:   "home",
		ChannelID: "discovery",
	}
}

func feedItemAttribution(post *postports.PostFeedItemSlice, item *rtrec.FeedItem) (float64, string, string, string) {
	if item != nil {
		return item.QualityScore,
			strings.TrimSpace(item.RecallPath),
			firstNonEmptyLocal(item.ContentVertical, postContentVertical(post)),
			firstNonEmptyLocal(item.SupplySource, postSupplySource(post))
	}
	return 0,
		"post_query",
		postContentVertical(post),
		postSupplySource(post)
}

func firstNonEmptyLocal(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func postContentVertical(post *postports.PostFeedItemSlice) string {
	if post == nil {
		return "general"
	}
	if vertical := strings.TrimSpace(strings.ToLower(post.ContentVertical)); vertical != "" {
		return vertical
	}
	if postMatchesVertical(post, "travel_photography") {
		return "travel_photography"
	}
	return "general"
}

func postSupplySource(post *postports.PostFeedItemSlice) string {
	if post == nil {
		return "unknown"
	}
	if strings.TrimSpace(post.SourceTaskID) != "" {
		return "data_engineering"
	}
	return "ugc"
}

func postMatchesVertical(post *postports.PostFeedItemSlice, vertical string) bool {
	vertical = strings.TrimSpace(strings.ToLower(vertical))
	if vertical == "" {
		return true
	}
	if strings.TrimSpace(strings.ToLower(post.ContentVertical)) == vertical {
		return true
	}
	haystack := strings.ToLower(strings.Join(postVerticalTokens(post), " "))
	switch vertical {
	case "travel_photography":
		return strings.Contains(haystack, "travel") ||
			strings.Contains(haystack, "旅行") ||
			strings.Contains(haystack, "旅游") ||
			strings.Contains(haystack, "景区") ||
			strings.Contains(haystack, "路线") ||
			strings.Contains(haystack, "自驾")
	default:
		return false
	}
}

func postVerticalTokens(post *postports.PostFeedItemSlice) []string {
	tokens := []string{string(post.ContentType), post.SourceTaskID}
	tokens = append(tokens, post.TagRefs...)
	tokens = append(tokens, post.EntityRefs...)
	return tokens
}

func normalizeRequestedIdentity(identity string) string {
	switch strings.TrimSpace(strings.ToLower(identity)) {
	case "moment", "work":
		return strings.TrimSpace(strings.ToLower(identity))
	default:
		return ""
	}
}

func resolvedContentIdentity(contentType, contentIdentity string) string {
	normalized := strings.TrimSpace(strings.ToLower(contentIdentity))
	if normalized == "moment" || normalized == "work" {
		return normalized
	}
	if strings.TrimSpace(strings.ToLower(contentType)) == "micro" {
		return "moment"
	}
	return "work"
}

func toLowerSet(items []string) map[string]struct{} {
	out := make(map[string]struct{}, len(items))
	for _, item := range items {
		v := strings.ToLower(strings.TrimSpace(item))
		if v != "" {
			out[v] = struct{}{}
		}
	}
	return out
}

func containsBlockedKeyword(post *postports.PostFeedItemSlice, blocked map[string]struct{}) bool {
	if len(blocked) == 0 {
		return false
	}
	targets := []string{
		post.Title,
		post.Body,
	}
	if len(post.TagRefs) > 0 {
		targets = append(targets, post.TagRefs...)
	}
	for _, text := range targets {
		normalized := strings.ToLower(strings.TrimSpace(text))
		if normalized == "" {
			continue
		}
		for keyword := range blocked {
			if strings.Contains(normalized, keyword) {
				return true
			}
		}
	}
	return false
}
