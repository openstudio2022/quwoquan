package feed

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	"quwoquan_service/services/content-service/internal/content/post/application/intersection"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type FeedService struct {
	engine           *rtrec.Engine
	postReader       postports.PostFeedReader
	intersections    feedIntersectionProvider
	objectCards      ObjectCardProvider
	objectCardPolicy func() recpolicy.ObjectCardConfig
	filterObserver   FeedFilterObserver
	viewerBlocks     FeedViewerBlockReader
	activeSupply     ActiveSupplyReader
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

// ActiveSupplyReader reads the production data_release_state projection. It is
// consulted only by the initial discovery/recommend route; continuation and
// following feeds deliberately bypass this guard.
type ActiveSupplyReader interface {
	HasActiveSupply(ctx context.Context) (bool, error)
}

func WithActiveSupplyReader(reader ActiveSupplyReader) FeedServiceOption {
	return func(service *FeedService) {
		service.activeSupply = reader
	}
}

// FeedViewerBlockReader 返回与当前 viewer 任一方向存在拉黑关系的 persona。
// 该事实来自 user 域 PersonaBlocked 投影，客户端不得通过 header/query 自报拉黑集合。
type FeedViewerBlockReader interface {
	ListBlockedPersonaIDs(
		ctx context.Context,
		viewerPersonaID string,
	) ([]string, error)
}

func WithFeedViewerBlockReader(reader FeedViewerBlockReader) FeedServiceOption {
	return func(service *FeedService) {
		service.viewerBlocks = reader
	}
}

type FeedFilterObserver interface {
	ObserveBlockedKeywordFilter(
		ctx context.Context,
		evaluated int,
		filtered int,
	)
}

func WithFeedFilterObserver(observer FeedFilterObserver) FeedServiceOption {
	return func(service *FeedService) {
		service.filterObserver = observer
	}
}

// WithFeedIntersectionProvider 注入交集理由池来源（70/20/10 内容流附着）。
func WithFeedIntersectionProvider(provider feedIntersectionProvider) FeedServiceOption {
	return func(s *FeedService) { s.intersections = provider }
}

type ListFeedRequest struct {
	UserID          string
	ViewerPersonaID string
	SessionID       string
	Identity        string
	Type            string
	Sort            string
	// ChannelID 首页频道路由标识（home_channels.feed_query.channel 真相源）。
	// 频道推荐主链路与 identity/type 浏览流互斥：channelId 非空时 identity/type 被忽略，
	// 请求必须进推荐引擎并按 channelId 归因，禁止落入 PostReader 时间线具名查询。
	ChannelID   string
	SubCategory string
	Cursor      string
	Limit       int
	// FeedRequestID 客户端回显的归因 id：首刷为空，分页/继续加载回显服务端首刷下发的 id。
	FeedRequestID   string
	BlockedKeywords []string
}

type FeedItemView struct {
	PostID             string   `json:"postId"`
	ContentType        string   `json:"contentType"`
	ContentIdentity    string   `json:"contentIdentity"`
	AssistantUsePolicy string   `json:"assistantUsePolicy,omitempty"`
	AuthorID           string   `json:"authorId"`
	AuthorDisplayName  string   `json:"authorDisplayName,omitempty"`
	AuthorAvatarURL    string   `json:"authorAvatarUrl,omitempty"`
	Title              string   `json:"title,omitempty"`
	Body               string   `json:"body,omitempty"`
	Summary            string   `json:"summary,omitempty"`
	MediaURLs          []string `json:"mediaUrls,omitempty"`
	VideoURL           string   `json:"videoUrl,omitempty"`
	CoverURL           string   `json:"coverUrl,omitempty"`
	ThumbnailURL       string   `json:"thumbnailUrl,omitempty"`
	CoverStrategy      string   `json:"coverStrategy,omitempty"`
	CoverFrameTimeMs   int64    `json:"coverFrameTimeMs,omitempty"`
	DurationMs         int64    `json:"durationMs,omitempty"`
	Width              int64    `json:"width,omitempty"`
	Height             int64    `json:"height,omitempty"`
	TagRefs            []string `json:"tagRefs,omitempty"`
	Visibility         string   `json:"visibility,omitempty"`
	LikeCount          int64    `json:"likeCount"`
	CommentCount       int64    `json:"commentCount"`
	ShareCount         int64    `json:"shareCount"`
	CreatedAt          string   `json:"createdAt"`
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
	Items []FeedItemView `json:"items"`
	// ObjectCards 混合对象卡（B4 插卡模式）：anchorIndex 指示插入在
	// items[anchorIndex] 之前；空即本页无对象卡（策略关闭 / 候选不足 / 匿名）。
	ObjectCards []ObjectCardView `json:"objectCards,omitempty"`
	NextCursor  string           `json:"nextCursor,omitempty"`
	Cursor      string           `json:"cursor,omitempty"`
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
	terminalClass := rtrec.FeedRequestClassBrowse
	terminalOutcome := rtrec.FeedTerminalSuccess
	terminalStage := rtrec.FailureStageNone
	defer func() {
		if err != nil {
			terminalOutcome = rtrec.FeedTerminalFailure
		}
		rtrec.RecordFeedTerminal(terminalClass, terminalOutcome, terminalStage)
	}()

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
	// 频道推荐主链路与浏览流互斥（B1 收口）：channelId 非空即为首页频道请求，
	// identity/type 一律忽略，禁止据此落入 PostReader 时间线具名查询。
	channelRouted := strings.TrimSpace(req.ChannelID) != ""
	if channelRouted {
		requestedIdentity = ""
		requestedType = ""
	}
	route := resolveFeedRoute(req)
	requestedCursor := strings.TrimSpace(req.Cursor)
	postReaderCursor := DecodePostReaderFeedCursor(requestedCursor)
	usePostReaderQuery := !channelRouted &&
		(postReaderCursor != "" || requestedType != "" || requestedIdentity != "")
	initialRecommend := !usePostReaderQuery &&
		route.FeedType == rtrec.FeedDiscovery &&
		normalizeFeedSort(req.Sort) == rtrec.FeedSortRecommend &&
		requestedCursor == ""
	switch {
	case route.FeedType == rtrec.FeedFollow:
		terminalClass = rtrec.FeedRequestClassFollowing
	case !usePostReaderQuery && requestedCursor != "":
		terminalClass = rtrec.FeedRequestClassContinuation
	case initialRecommend:
		terminalClass = rtrec.FeedRequestClassInitialRecommend
	default:
		terminalClass = rtrec.FeedRequestClassBrowse
	}
	blockedPersonaIDs, blockErr := s.resolveViewerBlockedPersonaIDs(
		ctx,
		req.ViewerPersonaID,
	)
	if blockErr != nil {
		return nil, storageReadFailure("read feed viewer block facts", blockErr)
	}
	blockedUsers := toLowerSet(blockedPersonaIDs)
	blockedKeywords := toLowerSet(req.BlockedKeywords)
	blockedKeywordEvaluated := 0
	blockedKeywordFiltered := 0
	defer func() {
		if s.filterObserver != nil && len(blockedKeywords) > 0 {
			s.filterObserver.ObserveBlockedKeywordFilter(
				ctx,
				blockedKeywordEvaluated,
				blockedKeywordFiltered,
			)
		}
	}()

	cursor := requestedCursor
	nextCursor := ""
	seenPostIDs := map[string]struct{}{}
	// 强负反馈（dislike / 隐藏作者 / 隐藏内容类型）是产品硬规则，
	// 必须在推荐召回和显式类型/身份查询两种具名读路径生效。
	feedbackExclusions := s.engine.LoadFeedbackExclusions(ctx, req.UserID, req.SessionID)
	if initialRecommend && s.activeSupply != nil {
		hasActiveSupply, supplyErr := s.activeSupply.HasActiveSupply(ctx)
		if supplyErr != nil {
			return nil, storageReadFailure("read active content release state", supplyErr)
		}
		if !hasActiveSupply {
			terminalStage = rtrec.FailureStageActiveSupplyMissing
			return nil, requiredDependencyFailure(
				terminalStage,
				fmt.Errorf("no active content release is available for initial discovery feed"),
			)
		}
	}
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
		if len(blockedKeywords) > 0 {
			blockedKeywordEvaluated++
			if containsBlockedKeyword(post, blockedKeywords) {
				blockedKeywordFiltered++
				return false
			}
		}
		postIdentity := ResolvedContentIdentity(string(post.ContentType), string(post.ContentIdentity))
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
			PostID:             postID,
			ContentType:        string(post.ContentType),
			ContentIdentity:    postIdentity,
			AssistantUsePolicy: post.AssistantUsePolicy,
			AuthorID:           authorID,
			AuthorDisplayName:  post.AuthorDisplayName,
			AuthorAvatarURL:    post.AuthorAvatarURL,
			Title:              post.Title,
			Body:               post.Body,
			Summary:            post.Summary,
			MediaURLs:          append([]string(nil), post.MediaURLs...),
			VideoURL:           post.VideoURL,
			CoverURL:           post.CoverURL,
			ThumbnailURL:       thumbnailURL,
			CoverStrategy:      post.CoverStrategy,
			CoverFrameTimeMs:   post.CoverFrameTimeMS,
			DurationMs:         post.DurationMS,
			Width:              post.Width,
			Height:             post.Height,
			TagRefs:            append([]string(nil), post.TagRefs...),
			Visibility:         string(post.Visibility),
			LikeCount:          post.LikeCount,
			CommentCount:       post.CommentCount,
			ShareCount:         post.ShareCount,
			CreatedAt:          post.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
			UpdatedAt:          feedTimeOrEmpty(post.UpdatedAt),
			PublishedAt:        feedTimeOrEmpty(post.PublishedAt),
			QualityScore:       qualityScore,
			RecallPath:         recallPath,
			ContentVertical:    contentVertical,
			SupplySource:       supplySource,
			SourceTaskID:       post.SourceTaskID,
		})
		return true
	}
	// N3-3 served 记账口径：engine 推迟记账（DeferDeliveryAccounting），装配层
	// 按「真正进入响应」的最终下发集回调 RecordDelivery——hydration 失败、
	// 拉黑、负反馈、垂类/关键词过滤丢弃的候选不再被记 served（否则曝光过滤
	// 会拉黑用户从未见过的内容，训练样本分母也被污染）。
	type deliveryBatch struct {
		attribution rtrec.DeliveryAttribution
		items       []rtrec.FeedItem
	}
	deliveryBatches := make([]deliveryBatch, 0, 4)
	hydrationRequested := 0
	hydrationFound := 0
	for attempt := 0; !usePostReaderQuery && attempt < 4 && len(views) < limit; attempt++ {
		recResp, err := s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
			UserID:                  req.UserID,
			PersonaID:               req.ViewerPersonaID,
			SessionID:               req.SessionID,
			FeedType:                route.FeedType,
			Sort:                    normalizeFeedSort(req.Sort),
			Cursor:                  cursor,
			Limit:                   limit,
			Surface:                 route.Surface,
			ChannelID:               route.ChannelID,
			Vertical:                route.Vertical,
			FeedRequestID:           feedRequestID,
			DeferDeliveryAccounting: true,
		})
		if err != nil {
			if errors.Is(err, rtrec.ErrInvalidFeedCursor) {
				return nil, contentgenerated.AppErrorFromInvalidArgument(err.Error())
			}
			stage := rtrec.FailureStageOf(err)
			if stage != rtrec.FailureStageNone {
				terminalStage = stage
				return nil, requiredDependencyFailure(stage, err)
			}
			return nil, err
		}
		if recResp.TerminalOutcome == rtrec.FeedTerminalDegraded &&
			terminalOutcome == rtrec.FeedTerminalSuccess {
			terminalOutcome = rtrec.FeedTerminalDegraded
			terminalStage = recResp.FailureStage
		}
		nextCursor = recResp.NextCursor
		// N3-1：单次 $in 批量取回本轮召回条目（消除逐条 FindPublishedFeedPost
		// 的 N+1 往返），装配顺序仍严格跟随引擎排序。
		recallIDs := make([]postports.PostID, 0, len(recResp.Items))
		for _, item := range recResp.Items {
			recallIDs = append(recallIDs, postports.NewPostID(item.ContentID))
		}
		hydrationRequested += len(recallIDs)
		postsByID, readErr := s.postReader.FindPublishedFeedPosts(ctx, recallIDs)
		if readErr != nil {
			return nil, storageReadFailure("hydrate recommended feed posts", readErr)
		}
		hydrationFound += len(postsByID)
		attemptDelivery := make([]rtrec.FeedItem, 0, len(recResp.Items))
		for _, item := range recResp.Items {
			post, ok := postsByID[postports.NewPostID(item.ContentID)]
			if !ok {
				continue
			}
			if appendPost(&post, &item) {
				attemptDelivery = append(attemptDelivery, item)
			}
			if len(views) >= limit {
				break
			}
		}
		if len(attemptDelivery) > 0 {
			deliveryBatches = append(deliveryBatches, deliveryBatch{
				attribution: recResp.Attribution,
				items:       attemptDelivery,
			})
		}
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}
	if !usePostReaderQuery && hydrationRequested > 0 && hydrationFound == 0 {
		terminalStage = rtrec.FailureStageHydrationFullMiss
		return nil, requiredDependencyFailure(
			terminalStage,
			fmt.Errorf("none of %d recommended candidates could be hydrated", hydrationRequested),
		)
	}
	if initialRecommend && len(views) == 0 {
		terminalStage = rtrec.FailureStageExposureExhausted
		return nil, requiredDependencyFailure(
			terminalStage,
			fmt.Errorf("initial recommend page has no deliverable candidates after hard filters"),
		)
	}
	for _, batch := range deliveryBatches {
		// 每次 engine 分页调用保留自己的 scorer/modelRelease 归因；模型热切换
		// 或单次降级时，禁止把后续页错误归因到首批结果。
		if err := s.engine.RecordDelivery(
			ctx,
			req.UserID,
			req.SessionID,
			batch.attribution,
			batch.items,
		); err != nil {
			return nil, err
		}
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
				return nil, storageReadFailure("list published feed posts", readErr)
			}
			if len(page.Items) == 0 {
				break
			}
			for i := range page.Items {
				post := page.Items[i]
				if appendPost(&post, nil) && len(views) >= limit {
					nextCursor = EncodePostReaderFeedCursor(string(post.PostID))
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
			AttachFeedIntersections(views, reasons, req.UserID)
		}
	}
	// 混合对象卡只注入推荐主链路首刷/续页（引擎路由页面），浏览流具名查询不混排。
	var objectCards []ObjectCardView
	if !usePostReaderQuery && route.Surface == "home" {
		objectCards = s.resolveObjectCards(ctx, req.UserID, len(views))
	}
	if len(views) == 0 {
		terminalOutcome = rtrec.FeedTerminalEmpty
		terminalStage = rtrec.FailureStageNone
	}
	return &ListFeedResponse{
		Items:          views,
		ObjectCards:    objectCards,
		NextCursor:     nextCursor,
		Cursor:         nextCursor,
		FeedRequestID:  feedRequestID,
		RankingVersion: rtrec.RankingVersion,
		ReasonVersion:  rtrec.ReasonVersion,
	}, nil
}

func (s *FeedService) resolveViewerBlockedPersonaIDs(
	ctx context.Context,
	viewerPersonaID string,
) ([]string, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if viewerPersonaID == "" {
		return nil, nil
	}
	if s == nil || s.viewerBlocks == nil {
		return nil, fmt.Errorf("feed viewer block reader is not configured")
	}
	blocked, err := s.viewerBlocks.ListBlockedPersonaIDs(ctx, viewerPersonaID)
	if err != nil {
		return nil, fmt.Errorf("read feed viewer block facts: %w", err)
	}
	return blocked, nil
}

func requiredDependencyFailure(stage rtrec.FailureStage, cause error) *rterr.AppError {
	typed := rtrec.NewFeedFailure(stage, cause)
	return contentgenerated.AppErrorFromRequiredDependencyUnavailable(typed.Error()).
		WithContextAttributes(rterr.RuntimeErrorContextAttribute{
			Key:   "failureStage",
			Value: string(stage),
		})
}

func storageReadFailure(operation string, cause error) *rterr.AppError {
	message := strings.TrimSpace(operation)
	if cause != nil {
		message = fmt.Sprintf("%s: %v", message, cause)
	}
	return contentgenerated.AppErrorFromStorageReadFailed(message)
}

func EncodePostReaderFeedCursor(postID string) string {
	trimmed := strings.TrimSpace(postID)
	if trimmed == "" {
		return ""
	}
	return "post:" + base64.RawURLEncoding.EncodeToString([]byte(trimmed))
}

func DecodePostReaderFeedCursor(cursor string) string {
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
	// 首页频道路由（B1/B16 收口）：channelId 是频道推荐主链路的唯一路由标识，
	// 优先于 type/subCategory token。following 走关注召回主路（fail-closed），
	// travel 归入 travel_photography 垂类，其余频道进推荐引擎并按 channelId 归因。
	if channel := strings.TrimSpace(strings.ToLower(req.ChannelID)); channel != "" {
		switch channel {
		case "following":
			return feedRoute{
				FeedType:  rtrec.FeedFollow,
				Surface:   "home",
				ChannelID: "following",
			}
		case "travel", "travel_photography":
			return feedRoute{
				FeedType:  rtrec.FeedDiscovery,
				Surface:   "travel_photography",
				Vertical:  "travel_photography",
				ChannelID: "travel_photography",
			}
		case "premium", "premium_stream":
			return feedRoute{
				FeedType:  rtrec.FeedSimilar,
				Surface:   "premium_stream",
				ChannelID: "premium_stream",
			}
		default:
			// recommend/campus/photography/tech/car 及运营远程新增频道：
			// 统一进推荐引擎，channelId 原样归因（交集池与埋点按频道区分）。
			return feedRoute{
				FeedType:  rtrec.FeedDiscovery,
				Surface:   "home",
				ChannelID: channel,
			}
		}
	}
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

func ResolvedContentIdentity(contentType, contentIdentity string) string {
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
