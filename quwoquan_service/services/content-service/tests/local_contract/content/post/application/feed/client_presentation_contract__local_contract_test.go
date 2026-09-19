// readiness_case: get-feed-local
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
package feed_test

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

const presentationPolicyDigestHex = "d1c0ffee" +
	"00000000000000000000000000000000000000000000000000000000"

// signedFeedContract 用生成的 canonical digest 补齐一份合法能力声明，
// 避免测试写死摘要字面量把服务端重算退化成字符串比对。
func signedFeedContract(
	t *testing.T,
	contentTypes []transport.ContentType,
	objectKinds []transport.ListObjectKind,
	surfaces []transport.ContentUiSurface,
) transport.ClientContentPresentationContract {
	t.Helper()
	contract := transport.ClientContentPresentationContract{
		ContentTypes:        contentTypes,
		ListObjectKinds:     objectKinds,
		OpenSurfaces:        surfaces,
		PresentationRecipes: []transport.FeedPresentationRecipe{"cover_media_card"},
	}
	digest, err := transport.DigestClientContentPresentationContract(contract)
	if err != nil {
		t.Fatalf("digest contract: %v", err)
	}
	contract.ContractDigest = digest
	return contract
}

func presentationFeedFixture() ([]postmodel.Post, []rtrec.ContentCandidate) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{
			ID: "presentation-video-1", AuthorId: "presentation-author-1",
			ContentType: "video", Status: "published", Visibility: "public",
			VideoUrl:   "https://media.example.test/presentation-1.mp4",
			DurationMs: 5000, CreatedAt: now, PublishedAt: now,
		},
		{
			ID: "presentation-video-2", AuthorId: "presentation-author-2",
			ContentType: "video", Status: "published", Visibility: "public",
			VideoUrl:   "https://media.example.test/presentation-2.mp4",
			DurationMs: 5000, CreatedAt: now.Add(-time.Minute),
			PublishedAt: now.Add(-time.Minute),
		},
	}
	candidates := make([]rtrec.ContentCandidate, 0, len(posts))
	for _, post := range posts {
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID: post.ID, ContentType: post.ContentType,
			AuthorID: post.AuthorId, PublishedAt: post.PublishedAt,
		})
	}
	return posts, candidates
}

// 整份缺席只落到生成的 MissingDeclaration 固定基线，绝不升级成编译期全能力；
// 基线摘要必须真正出现在建窗命令里，否则窗口的候选闭集无从裁剪。
func TestListFeedSendsMissingDeclarationBaselineWhenClientDeclaresNothing(t *testing.T) {
	posts, candidates := presentationFeedFixture()
	probe, options := testsupport.CapturedRankedRecommendationOptions(
		newTerminalFeedEngine(candidates),
		readyActiveSupplyOption(),
		WithFeedViewerBlockReader(terminalAllowAllBlockReader{}),
	)
	service := NewFeedService(fixtureFeedReader{posts: posts}, options...)

	if _, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-baseline", SessionID: "s-baseline", ChannelID: "recommend", Limit: 1,
	}); err != nil {
		t.Fatalf("ListFeed: %v", err)
	}

	commands := probe.CreateCommands()
	if len(commands) != 1 {
		t.Fatalf("create commands = %d, want 1", len(commands))
	}
	carried := commands[0].ClientPresentationContract
	if carried.ContractDigest != transport.MissingDeclarationContentPresentationContractDigest {
		t.Fatalf("carried digest=%s want missing-declaration baseline", carried.ContractDigest)
	}
	if carried.ContractDigest == transport.CompiledContentPresentationContractDigest {
		t.Fatal("absent declaration must never be upgraded to the compiled full capability")
	}
}

func TestListFeedSendsDeclaredCapabilityToWindowCreation(t *testing.T) {
	posts, candidates := presentationFeedFixture()
	probe, options := testsupport.CapturedRankedRecommendationOptions(
		newTerminalFeedEngine(candidates),
		readyActiveSupplyOption(),
		WithFeedViewerBlockReader(terminalAllowAllBlockReader{}),
	)
	service := NewFeedService(fixtureFeedReader{posts: posts}, options...)
	contract := signedFeedContract(
		t,
		[]transport.ContentType{"video"},
		[]transport.ListObjectKind{"post"},
		[]transport.ContentUiSurface{"media_immersive"},
	)

	if _, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-declared", SessionID: "s-declared", ChannelID: "recommend", Limit: 1,
		ClientPresentationContract: contract,
	}); err != nil {
		t.Fatalf("ListFeed: %v", err)
	}

	commands := probe.CreateCommands()
	if len(commands) != 1 ||
		commands[0].ClientPresentationContract.ContractDigest != contract.ContractDigest {
		t.Fatalf("create commands=%+v want declared digest %s", commands, contract.ContractDigest)
	}
}

func TestListFeedRejectsForgedPresentationDigest(t *testing.T) {
	posts, candidates := presentationFeedFixture()
	service := newTerminalFeedService(
		newTerminalFeedEngine(candidates),
		fixtureFeedReader{posts: posts},
		readyActiveSupplyOption(),
	)
	forged := signedFeedContract(
		t,
		[]transport.ContentType{"video"},
		[]transport.ListObjectKind{"post"},
		[]transport.ContentUiSurface{"media_immersive"},
	)
	forged.ContractDigest = "sha256:" +
		"0000000000000000000000000000000000000000000000000000000000000000"

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-forged", SessionID: "s-forged", ChannelID: "recommend", Limit: 1,
		ClientPresentationContract: forged,
	})

	requireAppErrorCodeAndStage(t, err, "CONTENT.USER.invalid_argument", rtrec.FailureStageNone)
}

// 有效能力摘要是 cursor scope 的一部分：换一份能力就换一个 scope，
// 旧续页游标无法认证，不会让两种能力共享同一个窗口或交付页。
func TestListFeedCursorScopeIsolatesPresentationCapabilities(t *testing.T) {
	posts, candidates := presentationFeedFixture()
	service := newTerminalFeedService(
		newTerminalFeedEngine(candidates),
		fixtureFeedReader{posts: posts},
		readyActiveSupplyOption(),
	)
	mediaContract := signedFeedContract(
		t,
		[]transport.ContentType{"video"},
		[]transport.ListObjectKind{"post"},
		[]transport.ContentUiSurface{"media_immersive"},
	)
	request := ListFeedRequest{
		UserID: "u-scope", SessionID: "s-scope", ChannelID: "recommend", Limit: 1,
		ClientPresentationContract: mediaContract,
	}

	first, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("initial page: %v", err)
	}
	if first.NextCursor == "" {
		t.Fatal("initial page did not return a continuation cursor")
	}
	request.Cursor = first.NextCursor
	request.FeedRequestID = first.FeedRequestID
	if _, err := service.ListFeed(context.Background(), request); err != nil {
		t.Fatalf("same-capability continuation: %v", err)
	}

	switched := request
	switched.ClientPresentationContract = signedFeedContract(
		t,
		[]transport.ContentType{"video", "image"},
		[]transport.ListObjectKind{"post"},
		[]transport.ContentUiSurface{"media_immersive"},
	)
	_, err = service.ListFeed(context.Background(), switched)
	requireAppErrorCodeAndStage(t, err, "CONTENT.USER.invalid_argument", rtrec.FailureStageNone)
}

// scriptedRankedGateway 让测试直接构造窗口回显，用来覆盖真实 recommendation
// 不该出现但必须 fail-closed 的窗口状态。
type scriptedRankedGateway struct {
	contract    transport.ClientContentPresentationContract
	items       []transport.RankedRecommendationItem
	continuable bool
	pages       int
	expiresAt   time.Time
}

func (gateway *scriptedRankedGateway) page(
	fence transport.ReleasePinnedQueryFence,
	scenario string,
	windowID string,
) transport.RankedRecommendationPage {
	gateway.pages++
	// 窗口身份在一次响应内不可变：过期时间必须冻结，否则续页会被
	// 「同一响应内归因变化」判定拦下，测不到能力过滤的补足预算。
	if gateway.expiresAt.IsZero() {
		gateway.expiresAt = time.Now().UTC().Add(10 * time.Minute)
	}
	page := transport.RankedRecommendationPage{
		ContentFence:               fence,
		WindowId:                   windowID,
		Scenario:                   scenario,
		ExperimentBucket:           "control",
		ModelBucket:                "rule",
		PolicyDigest:               "sha256:" + presentationPolicyDigestHex,
		RankingSnapshotDigest:      "scripted-ranking-snapshot",
		FeatureSnapshotAt:          time.Unix(1_800_000_000, 0).UTC(),
		UserFeatureSnapshot:        map[string]any{},
		Items:                      gateway.items,
		ClientPresentationContract: gateway.contract,
		ExpiresAt:                  gateway.expiresAt,
	}
	if gateway.continuable {
		next := gateway.pages * len(gateway.items)
		page.NextOrdinal = &next
	}
	return page
}

func (gateway *scriptedRankedGateway) Create(
	_ context.Context,
	command transport.CreateRankedRecommendationWindowCommand,
) (transport.RankedRecommendationPage, error) {
	return gateway.page(command.ContentFence, command.Scenario, "scripted-window"), nil
}

func (gateway *scriptedRankedGateway) GetPage(
	_ context.Context,
	request transport.GetRankedRecommendationPageQuery,
) (transport.RankedRecommendationPage, error) {
	return gateway.page(request.ContentFence, "content_feed", request.WindowId), nil
}

func newScriptedFeedService(gateway *scriptedRankedGateway) *FeedService {
	posts, _ := presentationFeedFixture()
	return NewFeedService(
		fixtureFeedReader{posts: posts},
		readyActiveSupplyOption(),
		WithFeedViewerBlockReader(terminalAllowAllBlockReader{}),
		WithRankedRecommendationGateway(gateway),
		WithFeedPageDeliveredPublisher(noopPresentationDeliveryPublisher{}),
	)
}

type noopPresentationDeliveryPublisher struct{}

func (noopPresentationDeliveryPublisher) Publish(
	context.Context,
	deliveryapp.FeedPageDelivered,
) error {
	return nil
}

// 窗口绑定的能力与请求声明不一致时必须给出 presentation_contract_changed：
// 客户端只能弃用旧游标从首屏刷新，不允许跨摘要续页。
func TestListFeedRejectsWindowBoundToAnotherPresentationContract(t *testing.T) {
	requested := signedFeedContract(
		t,
		[]transport.ContentType{"video"},
		[]transport.ListObjectKind{"post"},
		[]transport.ContentUiSurface{"media_immersive"},
	)
	service := newScriptedFeedService(&scriptedRankedGateway{
		contract: signedFeedContract(
			t,
			[]transport.ContentType{"video", "image"},
			[]transport.ListObjectKind{"post"},
			[]transport.ContentUiSurface{"media_immersive"},
		),
		items: []transport.RankedRecommendationItem{postRankedItem("presentation-video-1", 1)},
	})

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-window", SessionID: "s-window", ChannelID: "recommend", Limit: 1,
		ClientPresentationContract: requested,
	})

	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.USER.presentation_contract_changed",
		rtrec.FailureStageNone,
	)
}

func postRankedItem(postID string, ordinal int) transport.RankedRecommendationItem {
	contentType := transport.ContentTypeVideo
	return transport.RankedRecommendationItem{
		Ordinal: ordinal,
		Envelope: transport.ListItemPresentationEnvelope{
			ObjectKind:  transport.ListObjectKindPost,
			ContentType: &contentType,
			OpenSurface: transport.ContentUiSurfaceMediaImmersive,
			Post:        &transport.ListItemPostRef{PostId: postID},
		},
		Score:                 1,
		FeatureSnapshotDigest: "digest",
		ItemFeatureSnapshot:   map[string]any{},
	}
}

func homepageRankedItem(homepageID string, ordinal int) transport.RankedRecommendationItem {
	return transport.RankedRecommendationItem{
		Ordinal: ordinal,
		Envelope: transport.ListItemPresentationEnvelope{
			ObjectKind:  transport.ListObjectKindEntityHomepage,
			OpenSurface: transport.ContentUiSurfaceHomepageDetail,
			Homepage:    &transport.ListItemHomepageRef{HomepageId: homepageID},
		},
		Score:                 1,
		FeatureSnapshotDigest: "digest",
		ItemFeatureSnapshot:   map[string]any{},
	}
}

// 能力之内但当前扁平响应投不出的候选（混排信封归另一条收口）必须被过滤后
// 按预算补足；窗口候选耗尽与请求预算耗尽是两个不同终态，不共用一个出口。
func TestListFeedSeparatesCandidateExhaustionFromBudgetExhaustion(t *testing.T) {
	mixedContract := signedFeedContract(
		t,
		[]transport.ContentType{"video"},
		[]transport.ListObjectKind{"post", "entity_homepage"},
		[]transport.ContentUiSurface{"media_immersive", "homepage_detail"},
	)
	request := ListFeedRequest{
		UserID: "u-mixed", SessionID: "s-mixed", ChannelID: "recommend", Limit: 2,
		ClientPresentationContract: mixedContract,
	}

	t.Run("candidates exhausted", func(t *testing.T) {
		gateway := &scriptedRankedGateway{
			contract: mixedContract,
			items: []transport.RankedRecommendationItem{
				homepageRankedItem("homepage-dali", 0),
			},
		}
		response, err := newScriptedFeedService(gateway).ListFeed(
			context.Background(),
			request,
		)
		if err != nil {
			t.Fatalf("exhausted window must terminate as an empty page: %v", err)
		}
		if response.Outcome != FeedResponseOutcomeEmpty ||
			response.EmptyReason != FeedEmptyReasonNoEligibleContent ||
			response.NextCursor != "" {
			t.Fatalf("unexpected exhausted-window response: %+v", response)
		}
		if gateway.pages != 1 {
			t.Fatalf("exhausted window pages=%d, want 1", gateway.pages)
		}
	})

	t.Run("budget exhausted", func(t *testing.T) {
		gateway := &scriptedRankedGateway{
			contract: mixedContract,
			items: []transport.RankedRecommendationItem{
				homepageRankedItem("homepage-dali", 0),
			},
			continuable: true,
		}
		_, err := newScriptedFeedService(gateway).ListFeed(
			context.Background(),
			request,
		)
		requireAppErrorCodeAndStage(
			t,
			err,
			"CONTENT.SYSTEM.feed_capacity_unavailable",
			rtrec.FailureStageNone,
		)
		if gateway.pages < 2 {
			t.Fatalf("filtered candidates must be topped up within budget, pages=%d", gateway.pages)
		}
	})
}

// 窗口返回声明能力之外的条目是建窗契约被破坏，必须 fail-closed，
// 不能靠读侧静默丢弃后重排序位。
func TestListFeedFailsClosedOnItemOutsideDeclaredCapability(t *testing.T) {
	postOnly := signedFeedContract(
		t,
		[]transport.ContentType{"video"},
		[]transport.ListObjectKind{"post"},
		[]transport.ContentUiSurface{"media_immersive"},
	)
	gateway := &scriptedRankedGateway{
		contract: postOnly,
		items: []transport.RankedRecommendationItem{
			homepageRankedItem("homepage-out-of-contract", 0),
		},
	}

	_, err := newScriptedFeedService(gateway).ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-out", SessionID: "s-out", ChannelID: "recommend", Limit: 1,
		ClientPresentationContract: postOnly,
	})

	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageRankedWindowUnavailable,
	)
}
