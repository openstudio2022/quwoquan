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
	"quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type FeedService struct {
	postReader       postports.PostFeedReader
	intersections    feedIntersectionProvider
	objectCardPolicy func() recpolicy.ObjectCardConfig
	filterObserver   FeedFilterObserver
	viewerBlocks     FeedViewerBlockReader
	activeSupply     ActiveSupplyReader
	cursorCodec      *FeedCursorCodec
	deliveryPages    deliveryapp.Store
	rankedWindows    deliveryapp.RankedRecommendationGateway
	deliveryEvents   deliveryapp.FeedPageDeliveredPublisher
}

func NewFeedService(reader postports.PostFeedReader, opts ...FeedServiceOption) *FeedService {
	s := &FeedService{
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
		(route.FeedType == rtrec.FeedDiscovery ||
			route.FeedType == rtrec.FeedSimilar ||
			route.FeedType == rtrec.FeedFollow) &&
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
		if (!requiresPremiumVideo && !activeSupply.ContentReady()) ||
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
	// 对象卡候选与理由只取自同一个 Recommendation 不可变窗口；Content
	// 仅在 Post hydration 后计算本页 anchor 并与 FeedDeliveryPage 同时落盘。
	var objectCards []ObjectCardView
	if !usePostReaderQuery && route.Surface == "home" && rankedDelivery != nil {
		objectCards, err = s.resolveObjectCards(
			rankedDelivery.page.ObjectCards,
			len(views),
		)
		if err != nil {
			terminalStage = rtrec.FailureStageRankedWindowUnavailable
			return nil, requiredDependencyFailure(terminalStage, err)
		}
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
				rankedRecommendationSubject(req, route),
				req.ViewerPersonaID,
				s.cursorCodec.now().UTC(),
			),
		); publishErr != nil {
			terminalStage = rtrec.FailureStageDeliveryPageUnavailable
			return nil, requiredDependencyFailure(terminalStage, publishErr)
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
