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
	windowID string,
	fromOrdinal int,
	limit int,
) (transport.RankedRecommendationPage, error) {
	return probe.gateway.GetPage(ctx, windowID, fromOrdinal, limit)
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
	scenario string
	metadata testWindowMetadata
	items    []rtrec.FeedItem
}

type testWindowMetadata struct {
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
		metadata,
		response.Items,
	)
	gateway.mu.Lock()
	gateway.windows[windowID] = engineWindow{
		scenario: command.Scenario,
		metadata: metadata,
		items:    append([]rtrec.FeedItem(nil), response.Items...),
	}
	gateway.mu.Unlock()
	return page, nil
}

func (gateway *engineRankedGateway) GetPage(
	ctx context.Context,
	windowID string,
	fromOrdinal int,
	limit int,
) (transport.RankedRecommendationPage, error) {
	gateway.mu.Lock()
	state, ok := gateway.windows[strings.TrimSpace(windowID)]
	gateway.mu.Unlock()
	if !ok || fromOrdinal < 0 || fromOrdinal >= len(state.items) || limit <= 0 {
		return transport.RankedRecommendationPage{}, fmt.Errorf("test ranked window continuation is invalid")
	}
	page := testRankedPage(
		windowID,
		state.scenario,
		fromOrdinal,
		limit,
		state.metadata,
		state.items,
	)
	return page, nil
}

func testRankedPage(
	windowID string,
	scenario string,
	fromOrdinal int,
	limit int,
	metadata testWindowMetadata,
	allItems []rtrec.FeedItem,
) transport.RankedRecommendationPage {
	end := fromOrdinal + limit
	if end > len(allItems) {
		end = len(allItems)
	}
	pageItems := allItems[fromOrdinal:end]
	items := make([]transport.RankedRecommendationItem, 0, len(pageItems))
	for index, item := range pageItems {
		featureDigest := sha256.Sum256([]byte(item.ContentID))
		items = append(items, transport.RankedRecommendationItem{
			Ordinal:               fromOrdinal + index,
			ContentId:             item.ContentID,
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
		WindowId:              windowID,
		Scenario:              strings.TrimSpace(scenario),
		ModelBucket:           metadata.modelBucket,
		PolicyDigest:          metadata.policyDigest,
		RankingSnapshotDigest: metadata.rankingSnapshotDigest,
		FeatureSnapshotAt:     metadata.featureSnapshotAt,
		UserFeatureSnapshot:   map[string]any{},
		Items:                 items,
		ExpiresAt:             metadata.expiresAt,
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

func newTestWindowMetadata(
	windowID string,
	response *rtrec.FeedResponse,
) testWindowMetadata {
	now := time.Now().UTC()
	expiresAt := now.Add(15 * time.Minute)
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
	if strings.TrimSpace(scenario) == "premium_stream" {
		return rtrec.FeedSimilar
	}
	return rtrec.FeedDiscovery
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
