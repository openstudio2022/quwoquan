package feed

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
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
	cursorCodec      *FeedCursorCodec
	deliveryPages    deliveryapp.Store
	rankedWindows    deliveryapp.RankedRecommendationGateway
	deliveryEvents   deliveryapp.FeedPageDeliveredPublisher
}

func NewFeedService(engine *rtrec.Engine, reader postports.PostFeedReader, opts ...FeedServiceOption) *FeedService {
	s := &FeedService{
		engine:      engine,
		postReader:  reader,
		cursorCodec: defaultFeedCursorCodec,
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

type FeedServiceOption func(*FeedService)

// ActiveSupplySnapshot is the environment-scoped canonical release selected by
// the data importer. Counts bind readiness to materialized post + feed supply;
// a status-only boolean is insufficient because it can point at an empty or
// partially imported release.
type ActiveSupplySnapshot = postports.ActiveSupplySnapshot

// ActiveSupplyReader reads the production data_release_state projection. It is
// required by every discovery/recommend, premium_stream/similar and video-book
// page. Following is an independent social feed and deliberately bypasses it.
type ActiveSupplyReader = postports.ActiveSupplyReader

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

const rankedFeedSessionIDMaxBytes = 128

func validateRankedFeedSessionID(sessionID string) error {
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" {
		return errors.New("session id is required for recommendation pagination")
	}
	if len(sessionID) > rankedFeedSessionIDMaxBytes || !utf8.ValidString(sessionID) {
		return errors.New("session id exceeds the recommendation pagination contract")
	}
	for _, value := range sessionID {
		if unicode.IsControl(value) || unicode.IsSpace(value) {
			return errors.New("session id contains unsupported whitespace or control characters")
		}
	}
	return nil
}

type FeedItemView struct {
	PostID                   string   `json:"postId"`
	ContentType              string   `json:"contentType"`
	ContentIdentity          string   `json:"contentIdentity"`
	AssistantUsePolicy       string   `json:"assistantUsePolicy,omitempty"`
	AuthorID                 string   `json:"authorId"`
	AuthorDisplayName        string   `json:"authorDisplayName,omitempty"`
	AuthorAvatarURL          string   `json:"authorAvatarUrl,omitempty"`
	Title                    string   `json:"title,omitempty"`
	Body                     string   `json:"body,omitempty"`
	Summary                  string   `json:"summary,omitempty"`
	MediaURLs                []string `json:"mediaUrls,omitempty"`
	VideoURL                 string   `json:"videoUrl,omitempty"`
	MediaAssetID             string   `json:"mediaAssetId,omitempty"`
	MediaAssetVersion        int64    `json:"mediaAssetVersion,omitempty"`
	HLSCMAFMasterManifestURL string   `json:"hlsCmafMasterManifestUrl,omitempty"`
	HLSCMAFDescriptorVersion int64    `json:"hlsCmafDescriptorVersion,omitempty"`
	CoverURL                 string   `json:"coverUrl,omitempty"`
	ThumbnailURL             string   `json:"thumbnailUrl,omitempty"`
	CoverStrategy            string   `json:"coverStrategy,omitempty"`
	CoverFrameTimeMs         int64    `json:"coverFrameTimeMs,omitempty"`
	DurationMs               int64    `json:"durationMs,omitempty"`
	Width                    int64    `json:"width,omitempty"`
	Height                   int64    `json:"height,omitempty"`
	TagRefs                  []string `json:"tagRefs,omitempty"`
	Visibility               string   `json:"visibility,omitempty"`
	LikeCount                int64    `json:"likeCount"`
	CommentCount             int64    `json:"commentCount"`
	ShareCount               int64    `json:"shareCount"`
	CreatedAt                string   `json:"createdAt"`
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
	// Outcome distinguishes a successful content page from a successful empty
	// page. Failures continue to use the canonical runtime-error envelope.
	Outcome     FeedResponseOutcome `json:"outcome"`
	EmptyReason FeedEmptyReason     `json:"emptyReason,omitempty"`
	// ObjectCards 混合对象卡（B4 插卡模式）：anchorIndex 指示插入在
	// items[anchorIndex] 之前；空即本页无对象卡（策略关闭 / 候选不足 / 匿名）。
	ObjectCards         []ObjectCardView `json:"objectCards,omitempty"`
	NextCursor          string           `json:"nextCursor,omitempty"`
	PreviousCursor      string           `json:"previousCursor,omitempty"`
	PaginationExpiresAt string           `json:"paginationExpiresAt,omitempty"`
	// FeedRequestID 服务端权威下发的归因 id（frq_ 前缀 ULID）；端侧回显 + 透传行为事件。
	FeedRequestID string `json:"feedRequestId"`
	// PolicyDigest 本次推荐结果唯一策略内容摘要；具名浏览查询为空。
	PolicyDigest string `json:"policyDigest,omitempty"`
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
		emptyReason := rtrec.FeedTerminalEmptyReasonNone
		if resp != nil && terminalOutcome == rtrec.FeedTerminalEmpty {
			emptyReason = rtrec.FeedTerminalEmptyReason(resp.EmptyReason)
		}
		rtrec.RecordFeedTerminal(
			terminalClass,
			terminalOutcome,
			emptyReason,
			terminalStage,
		)
	}()

	limit := NormalizeFeedLimit(req.Limit)
	req.UserID = identity.NormalizeAnonymousPersonaID(req.UserID)
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
	cursorState := feedCursorEnvelope{}
	if requestedCursor != "" {
		var cursorErr error
		cursorState, cursorErr = s.cursorCodec.decode(
			requestedCursor,
			feedCursorScope(req, route, requestedIdentity, requestedType),
		)
		if cursorErr != nil {
			return nil, contentgenerated.AppErrorFromInvalidArgument(ErrInvalidFeedCursor.Error())
		}
	}
	// feedRequestId 服务端权威化：首刷生成；续页优先使用受完整性保护的
	// cursor 内归因 id。客户端若同时回显不同 id，必须 fail closed。
	feedRequestID := strings.TrimSpace(req.FeedRequestID)
	if cursorFeedRequestID := strings.TrimSpace(cursorState.FeedRequestID); cursorFeedRequestID != "" {
		if feedRequestID != "" && feedRequestID != cursorFeedRequestID {
			return nil, contentgenerated.AppErrorFromInvalidArgument("feed request id does not match cursor")
		}
		feedRequestID = cursorFeedRequestID
	}
	if feedRequestID == "" {
		feedRequestID = rtrec.NewFeedRequestID()
	}
	postReaderCursor := ""
	if cursorState.Kind == feedCursorKindPostReader {
		postReaderCursor = strings.TrimSpace(cursorState.Value)
	}
	usePostReaderQuery := !channelRouted &&
		(postReaderCursor != "" || requestedType != "" || requestedIdentity != "")
	if requestedCursor != "" && cursorState.Kind != feedCursorKindDeliveryPage &&
		((usePostReaderQuery && cursorState.Kind != feedCursorKindPostReader) ||
			(!usePostReaderQuery && cursorState.Kind != feedCursorKindRecommendation)) {
		return nil, contentgenerated.AppErrorFromInvalidArgument("feed cursor does not match request route")
	}
	releaseBoundRecommend := !usePostReaderQuery &&
		(route.FeedType == rtrec.FeedDiscovery || route.FeedType == rtrec.FeedSimilar) &&
		normalizeFeedSort(req.Sort) == rtrec.FeedSortRecommend
	if releaseBoundRecommend {
		if sessionErr := validateRankedFeedSessionID(req.SessionID); sessionErr != nil {
			return nil, contentgenerated.AppErrorFromInvalidArgument(sessionErr.Error())
		}
	}
	releaseBoundVideoBook := usePostReaderQuery &&
		requestedIdentity == "work" &&
		requestedType == "video"
	initialRecommend := releaseBoundRecommend && requestedCursor == ""
	initialVideoBook := releaseBoundVideoBook && requestedCursor == ""
	switch {
	case route.FeedType == rtrec.FeedFollow:
		terminalClass = rtrec.FeedRequestClassFollowing
	case !usePostReaderQuery && requestedCursor != "":
		terminalClass = rtrec.FeedRequestClassContinuation
	case initialRecommend || initialVideoBook:
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

	var recommendationContinuation *rtrec.RankedFeedContinuation
	if cursorState.Kind == feedCursorKindRecommendation {
		recommendationContinuation = &rtrec.RankedFeedContinuation{
			WindowID:       strings.TrimSpace(cursorState.WindowID),
			AfterOrdinal:   cursorState.AfterOrdinal,
			AfterContentID: strings.TrimSpace(cursorState.AfterContentID),
			ExpiresAt:      time.UnixMilli(cursorState.ExpiresAt).UTC(),
		}
	}
	nextCursor := ""
	nextCursorKind := feedCursorKindRecommendation
	var nextRecommendationContinuation *rtrec.RankedFeedContinuation
	policyDigest := ""
	seenPostIDs := map[string]struct{}{}
	// 强负反馈（dislike / 隐藏作者 / 隐藏内容类型）是产品硬规则，
	// 必须在推荐召回和显式类型/身份查询两种具名读路径生效。
	feedbackExclusions := rtrec.FeedbackExclusions{
		NegativeContentIDs: map[string]bool{},
		HiddenAuthors:      map[string]bool{},
		HiddenContentTypes: map[string]bool{},
	}
	if !identity.IsAnonymousFallbackPersonaID(req.UserID) {
		var exclusionErr error
		feedbackExclusions, exclusionErr = s.engine.LoadFeedbackExclusions(ctx, req.UserID, req.SessionID)
		if exclusionErr != nil {
			terminalStage = rtrec.FailureStageHardExclusionStateUnavailable
			return nil, requiredDependencyFailure(
				terminalStage,
				fmt.Errorf("read hard feedback exclusions: %w", exclusionErr),
			)
		}
	}
	activeSupply := ActiveSupplySnapshot{}
	if releaseBoundRecommend || releaseBoundVideoBook {
		if s.activeSupply == nil {
			terminalStage = rtrec.FailureStageActiveSupplyMissing
			return nil, requiredDependencyFailure(
				terminalStage,
				fmt.Errorf("active content release snapshot reader is not configured"),
			)
		}
		var supplyErr error
		activeSupply, supplyErr = s.activeSupply.ActiveSupplySnapshot(ctx)
		if supplyErr != nil {
			terminalStage = rtrec.FailureStageActiveSupplyMissing
			return nil, requiredDependencyFailure(
				terminalStage,
				fmt.Errorf("read active content release snapshot: %w", supplyErr),
			)
		}
		if activeSupply.IsEmpty() {
			if requestedCursor != "" {
				terminalStage = rtrec.FailureStageActiveSupplyMissing
				return nil, requiredDependencyFailure(
					terminalStage,
					fmt.Errorf("active release disappeared during feed pagination"),
				)
			}
			terminalOutcome = rtrec.FeedTerminalEmpty
			return emptyListFeedResponse(
				feedRequestID,
				FeedEmptyReasonNoActiveRelease,
			), nil
		}
		if !activeSupply.ReleaseBoundReadbackReady() {
			terminalStage = rtrec.FailureStageActiveSupplyMissing
			return nil, requiredDependencyFailure(
				terminalStage,
				fmt.Errorf("active release readback binding is inconsistent"),
			)
		}
		requiresPremiumVideo := route.Surface == "premium_stream" || releaseBoundVideoBook
		if (!requiresPremiumVideo && !activeSupply.DiscoveryReady()) ||
			(requiresPremiumVideo && !activeSupply.PlayableVideoReady()) {
			if requestedCursor != "" {
				terminalStage = rtrec.FailureStageActiveSupplyMissing
				return nil, requiredDependencyFailure(
					terminalStage,
					fmt.Errorf("active release supply became empty during feed pagination"),
				)
			}
			terminalOutcome = rtrec.FeedTerminalEmpty
			return emptyListFeedResponse(
				feedRequestID,
				FeedEmptyReasonNoEligibleContent,
			), nil
		}
	}
	if (releaseBoundRecommend || releaseBoundVideoBook) &&
		requestedCursor != "" &&
		!feedCursorMatchesActiveRelease(
			cursorState,
			activeSupply.ActiveReleaseID,
			activeSupply.ManifestDigest,
		) {
		terminalStage = rtrec.FailureStageActiveSupplyMissing
		return nil, requiredDependencyFailure(
			terminalStage,
			fmt.Errorf("feed cursor does not match active content release"),
		)
	}
	canonicalReleaseDelivered := false
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
		adaptiveDelivery := firstVideoAdaptiveDelivery(post.MediaItems)
		views = append(views, FeedItemView{
			PostID:                   postID,
			ContentType:              string(post.ContentType),
			ContentIdentity:          postIdentity,
			AssistantUsePolicy:       post.AssistantUsePolicy,
			AuthorID:                 authorID,
			AuthorDisplayName:        post.AuthorDisplayName,
			AuthorAvatarURL:          post.AuthorAvatarURL,
			Title:                    post.Title,
			Body:                     post.Body,
			Summary:                  post.Summary,
			MediaURLs:                append([]string(nil), post.MediaURLs...),
			VideoURL:                 post.VideoURL,
			MediaAssetID:             adaptiveDelivery.MediaAssetID,
			MediaAssetVersion:        adaptiveDelivery.MediaAssetVersion,
			HLSCMAFMasterManifestURL: adaptiveDelivery.HLSCMAFMasterManifestURL,
			HLSCMAFDescriptorVersion: adaptiveDelivery.HLSCMAFDescriptorVersion,
			CoverURL:                 post.CoverURL,
			ThumbnailURL:             thumbnailURL,
			CoverStrategy:            post.CoverStrategy,
			CoverFrameTimeMs:         post.CoverFrameTimeMS,
			DurationMs:               post.DurationMS,
			Width:                    post.Width,
			Height:                   post.Height,
			TagRefs:                  append([]string(nil), post.TagRefs...),
			Visibility:               string(post.Visibility),
			LikeCount:                post.LikeCount,
			CommentCount:             post.CommentCount,
			ShareCount:               post.ShareCount,
			CreatedAt:                post.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
			UpdatedAt:                feedTimeOrEmpty(post.UpdatedAt),
			PublishedAt:              feedTimeOrEmpty(post.PublishedAt),
			QualityScore:             qualityScore,
			RecallPath:               recallPath,
			ContentVertical:          contentVertical,
			SupplySource:             supplySource,
			SourceTaskID:             post.SourceTaskID,
		})
		if canonicalReleasePostDelivered(
			post,
			activeSupply.ActiveReleaseID,
			activeSupply.ManifestDigest,
			initialVideoBook || route.Surface == "premium_stream",
		) {
			canonicalReleaseDelivered = true
		}
		return true
	}
	if cursorState.Kind == feedCursorKindDeliveryPage {
		terminalClass = rtrec.FeedRequestClassContinuation
		replay, replayErr := s.replayFeedDeliveryPage(
			ctx,
			req,
			route,
			requestedIdentity,
			requestedType,
			cursorState,
			appendPost,
			func() []FeedItemView { return views },
		)
		if replayErr != nil {
			if errors.Is(replayErr, deliveryapp.ErrNotFound) {
				return nil, contentgenerated.AppErrorFromInvalidArgument(
					ErrInvalidFeedCursor.Error(),
				)
			}
			var applicationError *rterr.AppError
			if errors.As(replayErr, &applicationError) {
				return nil, applicationError
			}
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(terminalStage, replayErr)
		}
		if len(replay.items) == 0 {
			terminalOutcome = rtrec.FeedTerminalEmpty
		}
		return &ListFeedResponse{
			Items:               replay.items,
			Outcome:             feedOutcomeForItemCount(len(replay.items)),
			EmptyReason:         feedEmptyReasonForContinuation(len(replay.items)),
			ObjectCards:         replay.objectCards,
			NextCursor:          replay.nextCursor,
			PreviousCursor:      replay.previousCursor,
			PaginationExpiresAt: paginationExpiryWire(replay.paginationExpiresAt),
			FeedRequestID:       replay.feedRequestID,
			PolicyDigest:        replay.policyDigest,
		}, nil
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
	var rankedDelivery *rankedRecommendationDelivery
	if releaseBoundRecommend {
		rankedDelivery = &rankedRecommendationDelivery{}
		for attempt := 0; attempt < 4 && len(views) < limit; attempt++ {
			page, rankedErr := s.rankedRecommendationPage(
				ctx,
				req,
				route,
				feedRequestID,
				recommendationContinuation,
				limit-len(views),
			)
			if rankedErr != nil {
				terminalStage = rtrec.FailureStageRankedWindowUnavailable
				return nil, requiredDependencyFailure(terminalStage, rankedErr)
			}
			if bindErr := rankedDelivery.bindPage(page); bindErr != nil {
				terminalStage = rtrec.FailureStageRankedWindowUnavailable
				return nil, requiredDependencyFailure(terminalStage, bindErr)
			}
			if policyDigest != "" && policyDigest != page.PolicyDigest {
				terminalStage = rtrec.FailureStageRankedWindowUnavailable
				return nil, requiredDependencyFailure(
					terminalStage,
					fmt.Errorf("recommendation policy digest changed within one feed response"),
				)
			}
			policyDigest = page.PolicyDigest
			nextRecommendationContinuation = rankedContinuation(page)
			recallIDs := make([]postports.PostID, 0, len(page.Items))
			for _, item := range page.Items {
				recallIDs = append(recallIDs, postports.NewPostID(item.ContentId))
			}
			hydrationRequested += len(recallIDs)
			postsByID, readErr := s.postReader.FindPublishedFeedPosts(
				ctx,
				postports.NewPostFeedHydrationRequest(
					recallIDs,
					activeSupply.ActiveReleaseID,
					activeSupply.ManifestDigest,
				),
			)
			if readErr != nil {
				return nil, storageReadFailure("hydrate recommended feed posts", readErr)
			}
			for _, item := range page.Items {
				post, ok := postsByID[postports.NewPostID(item.ContentId)]
				if !ok || (strings.TrimSpace(post.SourceOwner) == "qwq_data" &&
					!feedDeliveryReleaseMatches(
						&post,
						activeSupply.ActiveReleaseID,
						activeSupply.ManifestDigest,
					)) {
					continue
				}
				hydrationFound++
				recommendationItem := rankedFeedItem(item)
				if appendPost(&post, &recommendationItem) {
					rankedDelivery.delivered = append(
						rankedDelivery.delivered,
						deliveredRecommendationItem(item, views[len(views)-1]),
					)
				}
				if len(views) >= limit {
					break
				}
			}
			if nextRecommendationContinuation == nil {
				break
			}
			recommendationContinuation = nextRecommendationContinuation
		}
	} else {
		for attempt := 0; !usePostReaderQuery && attempt < 4 && len(views) < limit; attempt++ {
			recResp, err := s.engine.GetFeed(ctx, rtrec.GetFeedRequest{
				UserID:                  req.UserID,
				PersonaID:               req.ViewerPersonaID,
				SessionID:               req.SessionID,
				RankedWindowSubjectID:   identity.RankedFeedWindowSubjectID(req.UserID, req.SessionID),
				FeedType:                route.FeedType,
				Sort:                    normalizeFeedSort(req.Sort),
				Continuation:            recommendationContinuation,
				Limit:                   limit - len(views),
				Surface:                 route.Surface,
				ChannelID:               route.ChannelID,
				Vertical:                route.Vertical,
				FeedRequestID:           feedRequestID,
				ActiveReleaseID:         activeSupply.ActiveReleaseID,
				ActiveManifestDigest:    activeSupply.ManifestDigest,
				FeedbackExclusions:      &feedbackExclusions,
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
			nextRecommendationContinuation = recResp.NextContinuation
			responsePolicyDigest := strings.TrimSpace(recResp.PolicyDigest)
			if responsePolicyDigest == "" ||
				(policyDigest != "" && policyDigest != responsePolicyDigest) {
				terminalStage = rtrec.FailureStageRankedWindowUnavailable
				return nil, requiredDependencyFailure(
					terminalStage,
					fmt.Errorf("recommendation policy digest changed within one feed response"),
				)
			}
			policyDigest = responsePolicyDigest
			// N3-1：单次 $in 批量取回本轮召回条目（消除逐条 FindPublishedFeedPost
			// 的 N+1 往返），装配顺序仍严格跟随引擎排序。
			recallIDs := make([]postports.PostID, 0, len(recResp.Items))
			for _, item := range recResp.Items {
				recallIDs = append(recallIDs, postports.NewPostID(item.ContentID))
			}
			hydrationRequested += len(recallIDs)
			postsByID, readErr := s.postReader.FindPublishedFeedPosts(
				ctx,
				postports.NewPostFeedHydrationRequest(
					recallIDs,
					activeSupply.ActiveReleaseID,
					activeSupply.ManifestDigest,
				),
			)
			if readErr != nil {
				return nil, storageReadFailure("hydrate recommended feed posts", readErr)
			}
			attemptDelivery := make([]rtrec.FeedItem, 0, len(recResp.Items))
			for _, item := range recResp.Items {
				post, ok := postsByID[postports.NewPostID(item.ContentID)]
				if !ok || !releaseBoundHydrationMatches(
					&post,
					&item,
					activeSupply.ActiveReleaseID,
					activeSupply.ManifestDigest,
				) {
					continue
				}
				hydrationFound++
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
			if nextRecommendationContinuation == nil {
				break
			}
			recommendationContinuation = nextRecommendationContinuation
		}
	}
	if !usePostReaderQuery && hydrationRequested > 0 && hydrationFound == 0 {
		terminalStage = rtrec.FailureStageHydrationFullMiss
		return nil, requiredDependencyFailure(
			terminalStage,
			fmt.Errorf("none of %d recommended candidates could be hydrated", hydrationRequested),
		)
	}
	if initialRecommend && !canonicalReleaseDelivered {
		views = nil
		deliveryBatches = nil
		if rankedDelivery != nil {
			rankedDelivery.delivered = nil
		}
		nextCursor = ""
		nextRecommendationContinuation = nil
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
					activeSupply.ActiveReleaseID,
					activeSupply.ManifestDigest,
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
					nextCursor = string(post.PostID)
					nextCursorKind = feedCursorKindPostReader
					break
				}
			}
			if len(views) >= limit || len(page.Items) < readerLimit {
				break
			}
			pageCursor = string(page.Items[len(page.Items)-1].PostID)
		}
	}
	if initialVideoBook && !canonicalReleaseDelivered {
		views = nil
		nextCursor = ""
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
		// 空 continuation 不得携带可继续游标，否则客户端会在没有任何可见
		// 进展时形成分页循环，也无法写入合法的已交付页事实。
		nextCursor = ""
		nextRecommendationContinuation = nil
	}
	scope := feedCursorScope(req, route, requestedIdentity, requestedType)
	previousCursor, previousCursorExpiry, previousCursorErr :=
		s.previousCursorFromInbound(scope, cursorState)
	if previousCursorErr != nil {
		return nil, contentgenerated.AppErrorFromInternalError(
			fmt.Sprintf("encode previous feed cursor: %v", previousCursorErr),
		)
	}
	pageCreatedAt := s.cursorCodec.now().UTC()
	deliveryPageID := ""
	deliveryPageExpiresAt := time.Time{}
	if len(views) > 0 {
		if s.deliveryPages == nil {
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(
				terminalStage,
				deliveryapp.ErrStoreUnavailable,
			)
		}
		var pageIdentityErr error
		deliveryPageID, deliveryPageExpiresAt, pageIdentityErr =
			newFeedDeliveryPageIdentity(pageCreatedAt)
		if pageIdentityErr != nil {
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(terminalStage, pageIdentityErr)
		}
	}
	nextCursorExpiry := time.Time{}
	if nextCursor != "" || nextRecommendationContinuation != nil {
		nextCursorDepth := cursorState.Depth + 1
		if nextCursorDepth > s.cursorCodec.maxDepth {
			nextCursor = ""
		} else {
			cursorEnvelope := feedCursorEnvelope{
				Kind:           nextCursorKind,
				Value:          nextCursor,
				FeedRequestID:  feedRequestID,
				ReleaseID:      releaseBoundCursorValue(releaseBoundRecommend || releaseBoundVideoBook, activeSupply.ActiveReleaseID),
				ManifestDigest: releaseBoundCursorValue(releaseBoundRecommend || releaseBoundVideoBook, activeSupply.ManifestDigest),
				Depth:          nextCursorDepth,
				DeliveryPageID: deliveryPageID,
			}
			if !deliveryPageExpiresAt.IsZero() {
				cursorEnvelope.DeliveryPageExpiresAt = deliveryPageExpiresAt.UnixMilli()
			}
			if nextRecommendationContinuation != nil {
				cursorEnvelope.Kind = feedCursorKindRecommendation
				cursorEnvelope.Value = ""
				cursorEnvelope.WindowID = nextRecommendationContinuation.WindowID
				cursorEnvelope.AfterOrdinal = nextRecommendationContinuation.AfterOrdinal
				cursorEnvelope.AfterContentID = nextRecommendationContinuation.AfterContentID
				cursorEnvelope.ExpiresAt = nextRecommendationContinuation.ExpiresAt.UnixMilli()
			} else {
				cursorEnvelope.ExpiresAt = pageCreatedAt.Add(FeedCursorTTL).UnixMilli()
			}
			encodedCursor, cursorErr := s.cursorCodec.encode(
				cursorEnvelope,
				feedCursorScope(req, route, requestedIdentity, requestedType),
			)
			if cursorErr != nil {
				return nil, contentgenerated.AppErrorFromInternalError(
					fmt.Sprintf("encode feed cursor: %v", cursorErr),
				)
			}
			nextCursor = encodedCursor
			nextCursorExpiry = time.UnixMilli(cursorEnvelope.ExpiresAt).UTC()
		}
	}
	if deliveryPageID != "" {
		if appendErr := s.appendFeedDeliveryPage(ctx, feedDeliveryPageAppendInput{
			scope:          scope,
			deliveryPageID: deliveryPageID,
			feedRequestID:  feedRequestID,
			pageSize:       limit,
			depth:          cursorState.Depth,
			previousPageID: strings.TrimSpace(cursorState.DeliveryPageID),
			items:          views,
			objectCards:    objectCards,
			outboundCursor: nextCursor,
			releaseID: releaseBoundCursorValue(
				releaseBoundRecommend || releaseBoundVideoBook,
				activeSupply.ActiveReleaseID,
			),
			manifestDigest: releaseBoundCursorValue(
				releaseBoundRecommend || releaseBoundVideoBook,
				activeSupply.ManifestDigest,
			),
			policyDigest: policyDigest,
			createdAt:    pageCreatedAt,
			expiresAt:    deliveryPageExpiresAt,
		}); appendErr != nil {
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(terminalStage, appendErr)
		}
	}
	if rankedDelivery != nil && len(rankedDelivery.delivered) > 0 {
		if s.deliveryEvents == nil {
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(
				terminalStage,
				fmt.Errorf("FeedPageDelivered publisher is not configured"),
			)
		}
		if publishErr := s.deliveryEvents.Publish(
			ctx,
			rankedDelivery.event(
				deliveryPageID,
				feedRequestID,
				rankedRecommendationSubject(req),
				req.ViewerPersonaID,
				s.cursorCodec.now().UTC(),
			),
		); publishErr != nil {
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(terminalStage, publishErr)
		}
	}
	for _, batch := range deliveryBatches {
		// 交付页事实先成功落下，再登记 served；否则响应失败却污染曝光分母。
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
	paginationExpiresAt := earlierTime(nextCursorExpiry, previousCursorExpiry)
	responseOutcome, responseEmptyReason := classifyFeedResponse(
		len(views),
		requestedCursor,
		route.FeedType == rtrec.FeedFollow,
	)
	return &ListFeedResponse{
		Items:               views,
		Outcome:             responseOutcome,
		EmptyReason:         responseEmptyReason,
		ObjectCards:         objectCards,
		NextCursor:          nextCursor,
		PreviousCursor:      previousCursor,
		PaginationExpiresAt: paginationExpiryWire(paginationExpiresAt),
		FeedRequestID:       feedRequestID,
		PolicyDigest:        policyDigest,
	}, nil
}

type videoAdaptiveDelivery struct {
	MediaAssetID             string
	MediaAssetVersion        int64
	HLSCMAFMasterManifestURL string
	HLSCMAFDescriptorVersion int64
}

func firstVideoAdaptiveDelivery(items []postports.PostMediaItemSlice) videoAdaptiveDelivery {
	for _, item := range items {
		if !strings.EqualFold(strings.TrimSpace(item.Kind), "video") {
			continue
		}
		assetID := strings.TrimSpace(item.MediaAssetID)
		if assetID == "" || item.MediaAssetVersion <= 0 {
			return videoAdaptiveDelivery{}
		}
		delivery := videoAdaptiveDelivery{
			MediaAssetID:      assetID,
			MediaAssetVersion: item.MediaAssetVersion,
		}
		manifest := strings.TrimSpace(item.HLSCMAFMasterManifestURL)
		if manifest != "" && item.HLSCMAFDescriptorVersion > 0 {
			delivery.HLSCMAFMasterManifestURL = manifest
			delivery.HLSCMAFDescriptorVersion = item.HLSCMAFDescriptorVersion
		}
		return delivery
	}
	return videoAdaptiveDelivery{}
}

func canonicalReleasePostDelivered(
	post *postports.PostFeedItemSlice,
	activeReleaseID string,
	activeManifestDigest string,
	requirePlayableVideo bool,
) bool {
	if post == nil || strings.TrimSpace(activeReleaseID) == "" ||
		strings.TrimSpace(activeManifestDigest) == "" {
		return false
	}
	if strings.TrimSpace(post.SourceOwner) != "qwq_data" ||
		strings.TrimSpace(post.ReleaseID) != strings.TrimSpace(activeReleaseID) ||
		strings.TrimSpace(post.ManifestDigest) != strings.TrimSpace(activeManifestDigest) ||
		strings.TrimSpace(post.LifecycleStatus) != "active" {
		return false
	}
	if !requirePlayableVideo {
		return true
	}
	return strings.EqualFold(strings.TrimSpace(string(post.ContentType)), "video") &&
		strings.TrimSpace(post.VideoURL) != "" &&
		post.DurationMS > 0
}

func releaseBoundHydrationMatches(
	post *postports.PostFeedItemSlice,
	item *rtrec.FeedItem,
	activeReleaseID string,
	activeManifestDigest string,
) bool {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	activeManifestDigest = strings.TrimSpace(activeManifestDigest)
	if post == nil || item == nil || activeReleaseID == "" || activeManifestDigest == "" {
		return post != nil && item != nil
	}
	candidateCanonical := strings.TrimSpace(item.SourceOwner) == "qwq_data" ||
		strings.EqualFold(strings.TrimSpace(item.SupplySource), "data_engineering")
	postCanonical := strings.TrimSpace(post.SourceOwner) == "qwq_data"
	if !candidateCanonical && !postCanonical {
		return true
	}
	return candidateCanonical && postCanonical &&
		strings.TrimSpace(item.ReleaseID) == activeReleaseID &&
		strings.TrimSpace(item.ManifestDigest) == activeManifestDigest &&
		strings.TrimSpace(item.LifecycleStatus) == "active" &&
		strings.TrimSpace(post.ReleaseID) == activeReleaseID &&
		strings.TrimSpace(post.ManifestDigest) == activeManifestDigest &&
		strings.TrimSpace(post.LifecycleStatus) == "active"
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
