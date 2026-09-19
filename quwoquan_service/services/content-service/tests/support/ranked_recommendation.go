package support

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
)

// RankedRecommendationOptions adapts the retired in-process recommendation
// engine only inside local tests. Production composition never imports this
// package and always uses the generated HTTP transport.
func RankedRecommendationOptions(
	engine *rtrec.Engine,
	options ...feedapp.FeedServiceOption,
) []feedapp.FeedServiceOption {
	return append(options,
		feedapp.WithRankedRecommendationGateway(newEngineRankedGateway(engine)),
		feedapp.WithFeedPageDeliveredPublisher(noopDeliveryPublisher{}),
	)
}

// CapturedRankedRecommendationOptions exposes the canonical outbound command
// and final delivery event to local-contract tests. It intentionally records
// only the new generated boundary; tests cannot assert retired in-process
// engine request or delivery-accounting details through this probe.
func CapturedRankedRecommendationOptions(
	engine *rtrec.Engine,
	options ...feedapp.FeedServiceOption,
) (*RankedRecommendationProbe, []feedapp.FeedServiceOption) {
	probe := &RankedRecommendationProbe{
		gateway: newEngineRankedGateway(engine),
	}
	return probe, append(options,
		feedapp.WithRankedRecommendationGateway(probe),
		feedapp.WithFeedPageDeliveredPublisher(probe),
	)
}

type RankedRecommendationProbe struct {
	mu         sync.Mutex
	gateway    *engineRankedGateway
	creates    []transport.CreateRankedRecommendationWindowCommand
	deliveries []deliveryapp.FeedPageDelivered
}

func (probe *RankedRecommendationProbe) Create(
	ctx context.Context,
	command transport.CreateRankedRecommendationWindowCommand,
) (transport.RankedRecommendationPage, error) {
	probe.mu.Lock()
	probe.creates = append(probe.creates, command)
	probe.mu.Unlock()
	return probe.gateway.Create(ctx, command)
}

func (probe *RankedRecommendationProbe) GetPage(
	ctx context.Context,
	request transport.GetRankedRecommendationPageQuery,
) (transport.RankedRecommendationPage, error) {
	return probe.gateway.GetPage(ctx, request)
}

func (probe *RankedRecommendationProbe) Publish(
	_ context.Context,
	event deliveryapp.FeedPageDelivered,
) error {
	probe.mu.Lock()
	probe.deliveries = append(probe.deliveries, event)
	probe.mu.Unlock()
	return nil
}

func (probe *RankedRecommendationProbe) CreateCommands() []transport.CreateRankedRecommendationWindowCommand {
	probe.mu.Lock()
	defer probe.mu.Unlock()
	return append([]transport.CreateRankedRecommendationWindowCommand(nil), probe.creates...)
}

func (probe *RankedRecommendationProbe) DeliveryEvents() []deliveryapp.FeedPageDelivered {
	probe.mu.Lock()
	defer probe.mu.Unlock()
	return append([]deliveryapp.FeedPageDelivered(nil), probe.deliveries...)
}

type noopDeliveryPublisher struct{}

func (noopDeliveryPublisher) Publish(
	context.Context,
	deliveryapp.FeedPageDelivered,
) error {
	return nil
}

type engineRankedGateway struct {
	engine  *rtrec.Engine
	mu      sync.Mutex
	windows map[string]engineWindow
}

type engineWindow struct {
	subjectID    string
	scenario     string
	contentFence transport.ReleasePinnedQueryFence
	contract     transport.ClientContentPresentationContract
	metadata     testWindowMetadata
	items        []rtrec.FeedItem
}

type testWindowMetadata struct {
	experimentBucket      string
	modelBucket           string
	modelChannel          string
	modelReleaseID        string
	policyDigest          string
	rankingSnapshotDigest string
	featureSnapshotAt     time.Time
	expiresAt             time.Time
}

func newEngineRankedGateway(engine *rtrec.Engine) *engineRankedGateway {
	return &engineRankedGateway{
		engine:  engine,
		windows: make(map[string]engineWindow),
	}
}

func (gateway *engineRankedGateway) Create(
	ctx context.Context,
	command transport.CreateRankedRecommendationWindowCommand,
) (transport.RankedRecommendationPage, error) {
	if gateway == nil || gateway.engine == nil {
		return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
	}
	// 建窗能力是窗口身份的一部分：缺席或伪造摘要在生产侧会被拒绝，
	// 测试启动器同样不允许靠零值能力建窗。
	if err := transport.ValidateClientContentPresentationContract(
		command.ClientPresentationContract,
	); err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"test ranked window client presentation contract: %w", err,
		)
	}
	digest := sha256.Sum256([]byte(strings.TrimSpace(command.IdempotencyKey)))
	windowID := "test-ranked-" + hex.EncodeToString(digest[:8])
	request := rtrec.GetFeedRequest{
		UserID:                  strings.TrimSpace(command.SubjectId),
		PersonaID:               strings.TrimSpace(command.SubjectId),
		SessionID:               windowID,
		RankedWindowSubjectID:   strings.TrimSpace(command.SubjectId),
		FeedType:                scenarioFeedType(command.Scenario),
		Sort:                    rtrec.FeedSortRecommend,
		Limit:                   100,
		Surface:                 scenarioSurface(command.Scenario),
		Vertical:                scenarioVertical(command.Scenario),
		FeedRequestID:           strings.TrimSpace(command.IdempotencyKey),
		DeferDeliveryAccounting: true,
	}
	response, err := gateway.engine.GetFeed(ctx, request)
	if err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	metadata := newTestWindowMetadata(windowID, response)
	page := testRankedPage(
		windowID,
		command.Scenario,
		0,
		command.Limit,
		command.ContentFence,
		command.ClientPresentationContract,
		metadata,
		response.Items,
		nil,
	)
	gateway.mu.Lock()
	gateway.windows[windowID] = engineWindow{
		subjectID:    command.SubjectId,
		scenario:     command.Scenario,
		contentFence: command.ContentFence,
		contract:     command.ClientPresentationContract,
		metadata:     metadata,
		items:        append([]rtrec.FeedItem(nil), response.Items...),
	}
	gateway.mu.Unlock()
	return page, nil
}

func (gateway *engineRankedGateway) GetPage(
	ctx context.Context,
	request transport.GetRankedRecommendationPageQuery,
) (transport.RankedRecommendationPage, error) {
	gateway.mu.Lock()
	state, ok := gateway.windows[strings.TrimSpace(request.WindowId)]
	gateway.mu.Unlock()
	if request.FromOrdinal == nil || request.Limit == nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf("test ranked window continuation is invalid")
	}
	fromOrdinal := *request.FromOrdinal
	limit := *request.Limit
	if !ok || strings.TrimSpace(request.SubjectId) != strings.TrimSpace(state.subjectID) ||
		fromOrdinal < 0 ||
		fromOrdinal >= len(state.items) || limit <= 0 {
		return transport.RankedRecommendationPage{}, fmt.Errorf("test ranked window continuation is invalid")
	}
	// 与生产 read_page 同语义：窗口按建窗能力构造，续页必须回显建窗时的能力。
	// 请求换了一份能力就不是同一个窗口，交由调用方按摘要不一致处理。
	contract := state.contract
	// 未来窗口精确过滤（与生产 read_page 同语义）：窗口与 ordinal 不可变，
	// 但每次续页都按 subject 当前强负反馈投影过滤，页允许变短。
	exclusions, err := gateway.engine.LoadFeedbackExclusions(
		ctx,
		strings.TrimSpace(state.subjectID),
		"",
	)
	if err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"test ranked window hard exclusions: %w", err,
		)
	}
	page := testRankedPage(
		request.WindowId,
		state.scenario,
		fromOrdinal,
		limit,
		state.contentFence,
		contract,
		state.metadata,
		state.items,
		func(item rtrec.FeedItem) bool {
			return exclusions.NegativeContentIDs[strings.TrimSpace(item.ContentID)] ||
				exclusions.HiddenAuthors[strings.TrimSpace(item.AuthorID)] ||
				exclusions.HiddenContentTypes[strings.TrimSpace(item.ContentType)]
		},
	)
	return page, nil
}

func testRankedPage(
	windowID string,
	scenario string,
	fromOrdinal int,
	limit int,
	contentFence transport.ReleasePinnedQueryFence,
	contract transport.ClientContentPresentationContract,
	metadata testWindowMetadata,
	allItems []rtrec.FeedItem,
	excluded func(rtrec.FeedItem) bool,
) transport.RankedRecommendationPage {
	end := fromOrdinal + limit
	if end > len(allItems) {
		end = len(allItems)
	}
	pageItems := allItems[fromOrdinal:end]
	items := make([]transport.RankedRecommendationItem, 0, len(pageItems))
	for index, item := range pageItems {
		if excluded != nil && excluded(item) {
			continue
		}
		envelope := testPostListItemEnvelope(item)
		// 窗口只放建窗能力声明之内的候选；越界候选在生产侧不会进窗口，
		// ordinal 保持原位不重排，页允许变短。
		if !testEnvelopeWithinContract(envelope, contract) {
			continue
		}
		featureDigest := sha256.Sum256([]byte(item.ContentID))
		items = append(items, transport.RankedRecommendationItem{
			Ordinal:               fromOrdinal + index,
			Envelope:              envelope,
			Score:                 item.Score,
			FeatureSnapshotDigest: hex.EncodeToString(featureDigest[:]),
			ItemFeatureSnapshot: map[string]any{
				"recallPath":      item.RecallPath,
				"qualityScore":    item.QualityScore,
				"contentVertical": item.ContentVertical,
				"supplySource":    item.SupplySource,
			},
		})
	}
	page := transport.RankedRecommendationPage{
		ContentFence:               contentFence,
		WindowId:                   windowID,
		Scenario:                   strings.TrimSpace(scenario),
		ExperimentBucket:           metadata.experimentBucket,
		ModelBucket:                metadata.modelBucket,
		PolicyDigest:               metadata.policyDigest,
		RankingSnapshotDigest:      metadata.rankingSnapshotDigest,
		FeatureSnapshotAt:          metadata.featureSnapshotAt,
		UserFeatureSnapshot:        map[string]any{},
		Items:                      items,
		ClientPresentationContract: contract,
		ExpiresAt:                  metadata.expiresAt,
	}
	if metadata.modelBucket == "model" {
		modelChannel := metadata.modelChannel
		modelReleaseID := metadata.modelReleaseID
		page.ModelChannel = &modelChannel
		page.ModelReleaseId = &modelReleaseID
	}
	if end < len(allItems) {
		value := end
		page.NextOrdinal = &value
	}
	return page
}

// testPostListItemEnvelope 复刻 canonical 列表信封：objectKind 决定引用字段，
// openSurface 是点击去向的唯一出站字段，contentType 只做筛选/媒体槽。
func testEnvelopeWithinContract(
	envelope transport.ListItemPresentationEnvelope,
	contract transport.ClientContentPresentationContract,
) bool {
	declares := func(kind transport.ListObjectKind) bool {
		for _, candidate := range contract.ListObjectKinds {
			if candidate == kind {
				return true
			}
		}
		return false
	}
	opens := func(surface transport.ContentUiSurface) bool {
		for _, candidate := range contract.OpenSurfaces {
			if candidate == surface {
				return true
			}
		}
		return false
	}
	renders := func(contentType transport.ContentType) bool {
		for _, candidate := range contract.ContentTypes {
			if candidate == contentType {
				return true
			}
		}
		return false
	}
	if !declares(envelope.ObjectKind) || !opens(envelope.OpenSurface) {
		return false
	}
	return envelope.ContentType == nil || renders(*envelope.ContentType)
}

func testPostListItemEnvelope(item rtrec.FeedItem) transport.ListItemPresentationEnvelope {
	envelope := transport.ListItemPresentationEnvelope{
		ObjectKind:  transport.ListObjectKindPost,
		OpenSurface: transport.ContentUiSurfaceMediaImmersive,
		Post:        &transport.ListItemPostRef{PostId: strings.TrimSpace(item.ContentID)},
	}
	if raw := strings.TrimSpace(item.ContentType); raw != "" {
		contentType := transport.ContentType(raw)
		envelope.ContentType = &contentType
		if contentType == transport.ContentTypeArticle {
			envelope.OpenSurface = transport.ContentUiSurfaceArticleReader
		}
	}
	return envelope
}

func newTestWindowMetadata(
	windowID string,
	response *rtrec.FeedResponse,
) testWindowMetadata {
	now := time.Now().UTC()
	expiresAt := now.Add(rtrec.RankedFeedWindowTTL)
	if response.NextContinuation != nil &&
		!response.NextContinuation.ExpiresAt.IsZero() {
		expiresAt = response.NextContinuation.ExpiresAt.UTC()
	}
	policyDigest := strings.TrimSpace(response.PolicyDigest)
	if policyDigest == "" {
		policyDigest = "sha256:" + strings.Repeat("0", 64)
	}
	rankingDigest := sha256.Sum256([]byte(windowID + ":" + policyDigest))
	modelBucket := strings.TrimSpace(response.Attribution.ModelBucket)
	if modelBucket == "" {
		modelBucket = "rule"
	}
	metadata := testWindowMetadata{
		// This deterministic test gateway has no forced scorer degradation, so
		// its server-side assignment equals the actual model execution track.
		experimentBucket:      modelBucket,
		modelBucket:           modelBucket,
		policyDigest:          policyDigest,
		rankingSnapshotDigest: hex.EncodeToString(rankingDigest[:]),
		featureSnapshotAt:     now,
		expiresAt:             expiresAt,
	}
	if modelBucket == "model" {
		metadata.modelChannel = strings.TrimSpace(response.Attribution.ModelChannel)
		metadata.modelReleaseID = strings.TrimSpace(response.Attribution.ModelReleaseID)
	}
	return metadata
}

func scenarioFeedType(scenario string) rtrec.FeedType {
	switch strings.TrimSpace(scenario) {
	case "following":
		return rtrec.FeedFollow
	case "premium_stream":
		return rtrec.FeedSimilar
	default:
		return rtrec.FeedDiscovery
	}
}

func scenarioSurface(scenario string) string {
	if strings.TrimSpace(scenario) == "premium_stream" {
		return "premium_stream"
	}
	return "home"
}

func scenarioVertical(scenario string) string {
	if strings.TrimSpace(scenario) == "travel_photography" {
		return "travel_photography"
	}
	return ""
}

var _ deliveryapp.RankedRecommendationGateway = (*engineRankedGateway)(nil)
var _ deliveryapp.RankedRecommendationGateway = (*RankedRecommendationProbe)(nil)
var _ deliveryapp.FeedPageDeliveredPublisher = (*RankedRecommendationProbe)(nil)
