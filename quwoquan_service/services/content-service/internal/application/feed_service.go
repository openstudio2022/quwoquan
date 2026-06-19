package application

import (
	"context"
	"encoding/base64"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type postReader interface {
	GetByID(ctx context.Context, id string) (*postmodel.Post, bool)
}

type publishedPostReader interface {
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
}

type FeedService struct {
	engine        *rtrec.Engine
	postReader    postReader
	intersections feedIntersectionProvider
}

func NewFeedService(engine *rtrec.Engine, reader postReader, opts ...FeedServiceOption) *FeedService {
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
	ID           string   `json:"id"`
	PostID       string   `json:"postId"`
	WireID       string   `json:"_id"`
	Type         string   `json:"type"`
	ContentType  string   `json:"contentType"`
	AuthorID     string   `json:"authorId"`
	Title        string   `json:"title,omitempty"`
	Body         string   `json:"body,omitempty"`
	Images       []string `json:"images,omitempty"`
	VideoURL     string   `json:"videoUrl,omitempty"`
	CoverURL     string   `json:"coverUrl,omitempty"`
	Width        int64    `json:"width,omitempty"`
	Height       int64    `json:"height,omitempty"`
	LikeCount    int64    `json:"likesCount"`
	CommentCount int64    `json:"commentsCount"`
	ShareCount   int64    `json:"shares"`
	CreatedAt    string   `json:"createdAt"`
	// UpdatedAt 最后实质更新时间；与 createdAt 相等或更早时端只显示创作时间。零值省略。
	UpdatedAt string `json:"updatedAt,omitempty"`
	// PublishedAt 首次公开时间；零值（未发布/未知）时省略。
	PublishedAt string `json:"publishedAt,omitempty"`
	// IntersectionReasons 内容卡交集行（70/20/10 频率契约；空即无交集，端不渲染）。
	IntersectionReasons []IntersectionReasonView `json:"intersectionReasons,omitempty"`
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
	req.UserID = normalizeAnonymousSubAccountID(req.UserID)
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
	blockedUsers := toLowerSet(req.BlockedUserIDs)
	blockedKeywords := toLowerSet(req.BlockedKeywords)

	requestedCursor := strings.TrimSpace(req.Cursor)
	repositoryCursor := decodeRepositoryFeedCursor(requestedCursor)
	cursor := requestedCursor
	nextCursor := ""
	seenPostIDs := map[string]struct{}{}
	// 强负反馈（dislike / 隐藏作者 / 隐藏内容类型）是产品硬规则：必须在所有 feed 路径生效，
	// 包括绕过推荐召回的 repository fallback 兜底。来源与召回过滤同一真相源（hotpath 负反馈/
	// 隐藏集），不引入 served/impressed 重复曝光治理（那是召回管线内部职责，避免误伤兜底分页）。
	feedbackExclusions := s.engine.LoadFeedbackExclusions(ctx, req.UserID, req.SessionID)
	_, cursorIsPostID := s.postReader.GetByID(ctx, repositoryCursor)
	useRepositoryPagination := cursorIsPostID || requestedType != "" || requestedIdentity != ""
	appendPost := func(post *postmodel.Post) bool {
		if post == nil {
			return false
		}
		if _, seen := seenPostIDs[post.ID]; seen {
			return false
		}
		if _, blocked := blockedUsers[strings.ToLower(strings.TrimSpace(post.AuthorId))]; blocked {
			return false
		}
		if feedbackExclusions.NegativeContentIDs[strings.TrimSpace(post.ID)] {
			return false
		}
		if feedbackExclusions.HiddenAuthors[strings.TrimSpace(post.AuthorId)] {
			return false
		}
		if feedbackExclusions.HiddenContentTypes[strings.TrimSpace(post.ContentType)] {
			return false
		}
		if containsBlockedKeyword(post, blockedKeywords) {
			return false
		}
		postIdentity := resolvedContentIdentity(post.ContentType, post.ContentIdentity)
		if requestedIdentity != "" && postIdentity != requestedIdentity {
			return false
		}
		viewType := mapContentTypeToViewType(post.ContentType)
		if requestedType != "" && requestedIdentity != "moment" && viewType != requestedType {
			return false
		}
		seenPostIDs[post.ID] = struct{}{}
		width, height := resolvePostDimensions(post)
		views = append(views, FeedItemView{
			ID:           post.ID,
			PostID:       post.ID,
			WireID:       post.ID,
			Type:         viewType,
			ContentType:  post.ContentType,
			AuthorID:     post.AuthorId,
			Title:        post.Title,
			Body:         post.Body,
			Images:       toStringSlice(post.MediaUrls),
			VideoURL:     post.VideoUrl,
			CoverURL:     post.CoverUrl,
			Width:        width,
			Height:       height,
			LikeCount:    post.LikeCount,
			CommentCount: post.CommentCount,
			ShareCount:   post.ShareCount,
			CreatedAt:    post.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
			UpdatedAt:    feedTimeOrEmpty(post.UpdatedAt),
			PublishedAt:  feedTimeOrEmpty(post.PublishedAt),
		})
		return true
	}
	for attempt := 0; !useRepositoryPagination && attempt < 4 && len(views) < limit; attempt++ {
		recResp, err := s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
			UserID:        req.UserID,
			SessionID:     req.SessionID,
			FeedType:      rtrec.FeedDiscovery,
			Sort:          normalizeFeedSort(req.Sort),
			Cursor:        cursor,
			Limit:         limit,
			FeedRequestID: feedRequestID,
		})
		if err != nil {
			return nil, err
		}
		nextCursor = recResp.NextCursor
		for _, item := range recResp.Items {
			post, ok := s.postReader.GetByID(ctx, item.ContentID)
			if !ok {
				continue
			}
			appendPost(post)
			if len(views) >= limit {
				break
			}
		}
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}
	if len(views) < limit {
		if publishedReader, ok := s.postReader.(publishedPostReader); ok {
			fallbackCursor := repositoryCursor
			for attempt := 0; attempt < 4 && len(views) < limit; attempt++ {
				posts := publishedReader.ListPublished(ctx, limit*2, fallbackCursor)
				if len(posts) == 0 {
					break
				}
				for i := range posts {
					post := posts[i]
					if appendPost(&post) && len(views) >= limit {
						nextCursor = encodeRepositoryFeedCursor(post.ID)
						break
					}
				}
				if len(views) >= limit || len(posts) < limit*2 {
					break
				}
				fallbackCursor = posts[len(posts)-1].ID
			}
		}
	}
	if s.intersections != nil && strings.TrimSpace(req.UserID) != "" {
		if reasons, reasonErr := s.intersections.Feed(ctx, req.UserID, "", feedIntersectionPoolLimit); reasonErr == nil {
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

func encodeRepositoryFeedCursor(postID string) string {
	trimmed := strings.TrimSpace(postID)
	if trimmed == "" {
		return ""
	}
	return "repo:" + base64.RawURLEncoding.EncodeToString([]byte(trimmed))
}

func decodeRepositoryFeedCursor(cursor string) string {
	trimmed := strings.TrimSpace(cursor)
	if strings.HasPrefix(trimmed, "repo:") {
		decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(trimmed, "repo:"))
		if err == nil {
			return strings.TrimSpace(string(decoded))
		}
		return ""
	}
	return trimmed
}

func (s *FeedService) GetPost(ctx context.Context, id string) (*postmodel.Post, bool) {
	return s.postReader.GetByID(ctx, id)
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
	case "", "recommended", "following":
		return ""
	case "photo":
		return "image"
	case "note":
		return "article"
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
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

func resolvePostDimensions(post *postmodel.Post) (int64, int64) {
	if post == nil {
		return 0, 0
	}
	if width, height, ok := extractDimensions(post.DeviceInfo); ok {
		return width, height
	}
	if width, height, ok := extractDimensions(post.ArticleRenderProfile); ok {
		return width, height
	}
	if width, height, ok := extractDimensions(post.PrimaryHomepageSnapshot); ok {
		return width, height
	}
	return 0, 0
}

func extractDimensions(source map[string]any) (int64, int64, bool) {
	if len(source) == 0 {
		return 0, 0, false
	}
	width, widthOK := extractDimension(source, "width", "imageWidth", "image_width", "w")
	height, heightOK := extractDimension(source, "height", "imageHeight", "image_height", "h")
	return width, height, widthOK && heightOK
}

func extractDimension(source map[string]any, keys ...string) (int64, bool) {
	for _, key := range keys {
		value, ok := source[key]
		if !ok || value == nil {
			continue
		}
		switch v := value.(type) {
		case int:
			if v > 0 {
				return int64(v), true
			}
		case int32:
			if v > 0 {
				return int64(v), true
			}
		case int64:
			if v > 0 {
				return v, true
			}
		case uint:
			if v > 0 {
				return int64(v), true
			}
		case uint32:
			if v > 0 {
				return int64(v), true
			}
		case uint64:
			if v > 0 {
				return int64(v), true
			}
		case float32:
			if v > 0 {
				return int64(v), true
			}
		case float64:
			if v > 0 {
				return int64(v), true
			}
		}
	}
	return 0, false
}

func toStringSlice(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			s := strings.TrimSpace(toString(item))
			if s != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

func toString(v any) string {
	switch vv := v.(type) {
	case string:
		return vv
	default:
		return ""
	}
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

func containsBlockedKeyword(post *postmodel.Post, blocked map[string]struct{}) bool {
	if len(blocked) == 0 {
		return false
	}
	targets := []string{
		post.Title,
		post.Body,
	}
	if tags := toStringSlice(post.TagRefs); len(tags) > 0 {
		targets = append(targets, tags...)
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

func SortPostsByCreatedAtDesc(posts []postmodel.Post) {
	sort.Slice(posts, func(i, j int) bool {
		return posts[i].CreatedAt.After(posts[j].CreatedAt)
	})
}
