package api_integration

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	behaviorapp "quwoquan_service/services/content-service/internal/application/behavior"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	outboundshareapp "quwoquan_service/services/content-service/internal/application/content/outbound_share_fact/command"
	profileinteractionapp "quwoquan_service/services/content-service/internal/application/content/profile_interaction"
	feedapp "quwoquan_service/services/content-service/internal/application/feed"
	"quwoquan_service/services/content-service/internal/application/identity"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	"quwoquan_service/services/content-service/internal/application/ports"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	mediainfra "quwoquan_service/services/content-service/internal/infrastructure/content/media"
	outboundshareinfra "quwoquan_service/services/content-service/internal/infrastructure/content/outbound_share_fact/persistence"
	profileinteractioninfra "quwoquan_service/services/content-service/internal/infrastructure/content/profile_interaction/persistence"
	contentmessaging "quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/testsupport"
)

var (
	testHandler                 http.Handler
	testFeedService             *feedapp.FeedService
	testPostService             *postapp.PostService
	testCommentService          *commentapp.CommentService
	postOutboxRelay             *postapp.OutboxRelay
	postProjectionRelay         *postapp.OutboxRelay
	postReactionLifecycleRelay  *postapp.OutboxRelay
	postCommentTombstoneRelay   *postapp.OutboxRelay
	commentOutboxRelay          *commentapp.OutboxRelay
	commentCountProjectionRelay *commentapp.OutboxRelay
	commentFeedCountRelay       *commentapp.OutboxRelay
	reactionOutboxRelay         *reactionapp.OutboxRelay
	reactionPostProjectionRelay *reactionapp.OutboxRelay
	reactionFeedProjectionRelay *reactionapp.OutboxRelay
	reactionRecommendRelay      *reactionapp.OutboxRelay
	profileReactionRelay        *reactionapp.OutboxRelay
	profileCommentRelay         *commentapp.OutboxRelay
	profileShareRelay           *outboundshareapp.OutboxRelay
	sharePostCountRelay         *outboundshareapp.OutboxRelay
	shareFeedCountRelay         *outboundshareapp.OutboxRelay
	profileReadFactRelay        *profileinteractionapp.ReadFactOutboxRelay
	profilePostTargetRelay      *postapp.OutboxRelay
	testReactionStore           *persistence.MongoContentReactionStore
	testReactionService         *reactionapp.Service
	testModerationStore         *persistence.MongoPostModerationCaseStore
	testModerationFacades       *moderationapp.Facades
	eventSpy                    *testinfra.EventSpy
	mongoDB                     *mongo.Database
	mongoClient                 *mongo.Client
	testRouter                  *rtredis.Router
	testBehaviorProjectionRelay *recinfra.BehaviorProjectionRelay
	testBehaviorProjectionMu    sync.Mutex
)

func requireMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	if mongoDB == nil {
		tb.Fatal("content-service tests require TestMain to provision mongoDB or exit before execution")
	}
	return mongoDB
}

func requireTestRouter(tb testing.TB) *rtredis.Router {
	tb.Helper()
	if testRouter == nil {
		tb.Fatal("content-service tests require TestMain to provision testRouter or exit before execution")
	}
	return testRouter
}

func drainPostOutbox(t *testing.T) {
	t.Helper()
	if err := drainPostOutboxForHarness(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func drainPostOutboxForHarness(ctx context.Context) error {
	if postOutboxRelay == nil {
		return fmt.Errorf("content-service api_integration requires a Post outbox relay")
	}
	if postProjectionRelay == nil || postReactionLifecycleRelay == nil ||
		postCommentTombstoneRelay == nil ||
		profilePostTargetRelay == nil {
		return fmt.Errorf("content-service api_integration requires a Post projection relay")
	}
	if _, err := postOutboxRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Post outbox: %w", err)
	}
	if _, err := postProjectionRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Post discovery projection: %w", err)
	}
	if _, err := postReactionLifecycleRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Post ContentReaction lifecycle: %w", err)
	}
	if _, err := postCommentTombstoneRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Post Comment tombstone projection: %w", err)
	}
	if _, err := profilePostTargetRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Post profile interaction target projection: %w", err)
	}
	return nil
}

func drainReactionOutbox(t *testing.T) {
	t.Helper()
	if reactionOutboxRelay == nil || reactionPostProjectionRelay == nil ||
		reactionFeedProjectionRelay == nil || reactionRecommendRelay == nil ||
		profileReactionRelay == nil {
		t.Fatal("content-service api_integration requires ContentReaction outbox relays")
	}
	if _, err := reactionOutboxRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction runtime outbox: %v", err)
	}
	if _, err := reactionPostProjectionRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction Post projection outbox: %v", err)
	}
	if _, err := reactionFeedProjectionRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction DiscoveryFeed projection outbox: %v", err)
	}
	if _, err := reactionRecommendRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction RecommendFeature projection outbox: %v", err)
	}
	if _, err := profileReactionRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction profile interaction projection outbox: %v", err)
	}
}

func drainCommentOutboxForHarness(ctx context.Context) error {
	if commentOutboxRelay == nil || commentCountProjectionRelay == nil ||
		commentFeedCountRelay == nil || profileCommentRelay == nil {
		return fmt.Errorf("content-service api_integration requires Comment outbox relays")
	}
	if _, err := commentOutboxRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment runtime outbox: %w", err)
	}
	if _, err := commentCountProjectionRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment count projection outbox: %w", err)
	}
	if _, err := commentFeedCountRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment DiscoveryFeed count projection outbox: %w", err)
	}
	if _, err := profileCommentRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment profile interaction projection outbox: %w", err)
	}
	return nil
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	eventSpy = testinfra.NewEventSpy()

	// api_integration 使用真实 Redis 协议实现（外部依赖优先，否则
	// testcontainer/native redis-server），禁止以内存替身充当端云证据。
	integrationRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		panic("content-service api_integration requires real Redis: " + err.Error())
	}
	if err := integrationRedis.FlushDBs(ctx, 0, 1, 2); err != nil {
		panic("flush content-service integration Redis: " + err.Error())
	}

	// Start MongoDB testcontainer (mongo:7-jammy) for realistic L2 tests.
	// Falls back to TEST_MONGO_URI env var for CI environments that pre-provision Mongo.
	// 缺少真实 MongoDB 时必须失败，禁止把未执行的集成测试记为通过。
	var mongoContainer *mongomod.MongoDBContainer

	mongoURI := os.Getenv("TEST_MONGO_URI")
	if mongoURI == "" {
		container, runErr := tryRunMongoContainer(ctx)
		if runErr != nil {
			panic(
				"content-service api_integration requires a real MongoDB; " +
					"set TEST_MONGO_URI or start Docker: " + runErr.Error(),
			)
		}
		mongoContainer = container
		uri, connErr := container.ConnectionString(ctx)
		if connErr != nil {
			panic("failed to get mongo connection string: " + connErr.Error())
		}
		mongoURI = uri
	}

	mongoClientOptions := mongoopts.Client().ApplyURI(mongoURI)
	if mongoContainer != nil {
		// Colima exposes the replica-set member through a forwarded localhost
		// port while Mongo advertises its container IP. Direct mode keeps the
		// driver on that reachable endpoint; the server still runs as rs0 so
		// aggregate/outbox transactions remain available.
		mongoClientOptions.SetDirect(true)
	}
	mongoClient, err = mongo.Connect(mongoClientOptions)
	if err != nil {
		panic("failed to connect to mongo: " + err.Error())
	}
	mongoDB = mongoClient.Database("content_test")
	testBehaviorProjector := recinfra.NewRecommendFeatureProjector(mongoDB)
	if err := testBehaviorProjector.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize behavior recommendation projection indexes: " + err.Error())
	}
	// 测试进程内复用同一个 relay owner；每个 case 创建新 owner 会被上一 case
	// 15 秒 lease 阻塞，造成把“standby 尚未接管”误判为“投影已完成”的假绿/假红。
	testBehaviorProjectionRelay = recinfra.NewBehaviorProjectionRelay(
		mongoDB,
		testBehaviorProjector,
		recinfra.NewDiscoveryFeedProjector(mongoDB),
	).WithWatermarkLag(0).WithConsumer(
		fmt.Sprintf("api-integration-behavior-feature-projection-%d", time.Now().UnixNano()),
	)
	postStore := persistence.NewMongoPostStore(mongoDB.Collection("posts"))
	if err := postStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize Post aggregate/outbox indexes: " + err.Error())
	}
	commentStore := persistence.NewMongoCommentDataAdapter(mongoDB)
	if err := commentStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize Comment aggregate/outbox indexes: " + err.Error())
	}
	mediaStore := persistence.NewMongoMediaStore(mongoDB.Collection("media_upload_sessions"))
	if err := mediaStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize MediaUploadSession/MediaAsset indexes: " + err.Error())
	}
	mediaObjects := newAPIIntegrationMediaObjectGateway()
	mediaPostReader := persistence.NewMongoPostQueryReader(mongoDB.Collection("posts"))
	mediaService := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(mediaStore),
		mediaObjects,
		mediaapp.WithOriginalAccessPostVisibilityReader(
			postapp.NewMediaAssetVisibilityReader(
				mediaPostReader,
				recinfra.NewPersonaBlockReader(mongoDB),
			),
		),
	)
	testReactionStore = persistence.NewMongoContentReactionStore(mongoDB)
	if err := testReactionStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize ContentReaction aggregate/outbox indexes: " + err.Error())
	}
	testCommentService = commentapp.NewCommentService(
		commentapp.BindDataPorts(
			commentStore,
			persistence.NewCommentAttachmentReader(mediaStore, mediaObjects),
			testReactionStore,
			persistence.NewCommentViewerRelationMongoReader(mongoDB),
			recinfra.NewPersonaBlockReader(mongoDB),
		),
		// fixture seed 是受控测试装配（同一 author 批量种评论），关闭滑动窗口
		// 频控避免与生产默认（30s ≤ 5 条）冲突；频控行为本身由专属
		// comment rate-limit 测试用显式窗口覆盖验证。
		commentapp.WithRateLimitConfig(commentapp.RateLimitConfig{}),
	)
	// 与生产 main.go 对齐：posts/comments 目标读取都由 comment data adapter 承载
	// （MongoPostQueryReader 不再提供 FindPostOwnership 所有权读端口）。
	reactionService := reactionapp.NewService(
		reactionapp.BindDataPorts(
			testReactionStore,
			persistence.NewReactionTargetReader(commentStore, commentStore),
		),
	)
	testReactionService = reactionService
	postReactionLifecycleRelay = postapp.NewOutboxRelay(
		postStore,
		postStore,
		reactionapp.NewPostDeletionConsumer(reactionService, testReactionStore),
		"api-integration-post-deletion-reaction-lifecycle",
	)
	postCommentTombstoneRelay = postapp.NewOutboxRelay(
		postStore,
		postStore,
		commentapp.NewCommentTombstoneProjector(commentStore),
		"api-integration-post-comment-tombstone",
	)
	reactionOutboxRelay = reactionapp.NewOutboxRelay(
		testReactionStore,
		testReactionStore,
		contentmessaging.NewContentReactionOutboxPublisher(eventSpy),
		"api-integration-reaction-events",
	)
	reactionPostProjectionRelay = reactionapp.NewOutboxRelay(
		testReactionStore,
		testReactionStore,
		reactionapp.NewActiveReactionCountProjector(testReactionStore, postStore),
		"api-integration-reaction-like-count",
	)
	reactionFeedProjectionRelay = reactionapp.NewOutboxRelay(
		testReactionStore,
		testReactionStore,
		reactionapp.NewActiveReactionCountProjector(
			testReactionStore,
			persistence.NewMongoDiscoveryFeedLikeCountWriter(mongoDB),
		),
		"api-integration-reaction-feed-like-count",
	)
	reactionRecommendRelay = reactionapp.NewOutboxRelay(
		testReactionStore,
		testReactionStore,
		reactionapp.NewPersonaLikeCountProjector(
			testReactionStore,
			persistence.NewMongoRecommendFeatureLikeCountWriter(mongoDB),
		),
		"api-integration-reaction-recommend-like-count",
	)
	// Wire services with redis.Router. Every scene uses an isolated DB on the same
	// real Redis runtime so EXPIRE/DEL/SET, serialization and key routing all cross
	// an authentic network boundary. The comment domain no
	// longer touches Redis at all (the write-only/racy ZSet + reaction-counter
	// caches were removed in R-CMT01); comment counts/ranking are authoritative on Mongo.
	testRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 0, TLS: integrationRedis.TLS},
			"rec":      {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 1, TLS: integrationRedis.TLS},
			"realtime": {Mode: "standalone", Addr: integrationRedis.Addr, Password: integrationRedis.Password, DB: 2, TLS: integrationRedis.TLS},
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	})
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec")))
	source := recinfra.NewPostProjectionSource(postStore, postStore)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := feedapp.NewFeedService(
		engine,
		persistence.NewMongoPostQueryReader(mongoDB.Collection("posts")),
		feedapp.WithFeedViewerBlockReader(recinfra.NewPersonaBlockReader(mongoDB)),
	)
	testFeedService = feedService

	// Comment 与 ContentReaction 使用各自对象聚合、事务 outbox 和具名 Reader；
	// Post 只消费投影，不持有评论命令或反应写入口。
	postQueryReader := persistence.NewMongoPostQueryReader(mongoDB.Collection("posts"))
	outboundShareSink := outboundshareinfra.NewMongoAppendSink(mongoDB)
	if err := outboundShareSink.EnsureIndexes(context.Background()); err != nil {
		panic(fmt.Errorf("ensure OutboundShareFact indexes: %w", err))
	}
	outboundShareService := outboundshareapp.NewService(
		outboundShareSink,
		outboundshareinfra.NewShareablePostReader(postQueryReader),
	)
	outboundShareFacades := outboundshareapp.BindFacades(outboundShareService)
	profileActivityStore := profileinteractioninfra.NewMongoActivityStore(mongoDB)
	if err := profileActivityStore.EnsureIndexes(ctx); err != nil {
		panic(fmt.Errorf("ensure ProfileInteractionActivityView indexes: %w", err))
	}
	profileReadFactStore := profileinteractioninfra.NewMongoReadFactStore(mongoDB)
	if err := profileReadFactStore.EnsureIndexes(ctx); err != nil {
		panic(fmt.Errorf("ensure ProfileInteractionReadFact indexes: %w", err))
	}
	profileProjector := profileinteractionapp.NewProjector(
		profileinteractioninfra.NewMongoProjectionSourceReader(mongoDB),
		profileActivityStore,
	)
	profileInteractionFacades := profileinteractionapp.BindFacades(
		profileinteractionapp.NewActivityQueryService(profileActivityStore),
		profileinteractionapp.NewReadFactService(
			profileActivityStore,
			profileReadFactStore,
		),
	)
	profileReactionRelay = reactionapp.NewOutboxRelay(
		testReactionStore,
		testReactionStore,
		profileinteractionapp.NewReactionProjector(profileProjector),
		"api-integration-reaction-profile-interaction",
	)
	profileCommentRelay = commentapp.NewOutboxRelay(
		commentStore,
		commentStore,
		profileinteractionapp.NewCommentProjector(profileProjector),
		"api-integration-comment-profile-interaction",
	)
	profileShareRelay = outboundshareapp.NewOutboxRelay(
		outboundShareSink,
		outboundShareSink,
		profileinteractionapp.NewOutboundShareProjector(profileProjector),
		"api-integration-share-profile-interaction",
	)
	sharePostCountRelay = outboundshareapp.NewOutboxRelay(
		outboundShareSink,
		outboundShareSink,
		outboundshareapp.NewShareCountProjector(outboundShareSink, postStore),
		"api-integration-share-post-count",
	)
	shareFeedCountRelay = outboundshareapp.NewOutboxRelay(
		outboundShareSink,
		outboundShareSink,
		outboundshareapp.NewShareCountProjector(
			outboundShareSink,
			persistence.NewMongoDiscoveryFeedShareCountWriter(mongoDB),
		),
		"api-integration-share-feed-count",
	)
	profileReadFactRelay = profileinteractionapp.NewReadFactOutboxRelay(
		profileReadFactStore,
		profileReadFactStore,
		profileinteractionapp.NewReadFactProjector(profileActivityStore),
		"api-integration-profile-interaction-read",
	)
	profilePostTargetRelay = postapp.NewOutboxRelay(
		postStore,
		postStore,
		profileinteractionapp.NewPostTargetProjector(profileActivityStore),
		"api-integration-post-profile-interaction-target",
	)
	postServiceCore := postapp.NewPostService(
		postapp.WithMediaAssetBindingReader(
			postapp.BindDataPorts(postStore),
			mediainfra.NewPostBindingReader(mediaStore, mediaObjects),
		),
		postapp.WithEventPublisher(eventSpy),
		postapp.WithCommentReaders(commentStore),
		postapp.WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	testPostService = postServiceCore
	postOutboxRelay = postapp.NewOutboxRelay(
		postStore,
		postStore,
		contentmessaging.NewPostOutboxPublisher(eventSpy),
		"api-integration-event-spy",
	)
	postProjectionRelay = postapp.NewOutboxRelay(
		postStore,
		postStore,
		contentmessaging.NewPostOutboxPublisher(
			contentmessaging.NewInProcessProjectorPublisher(&discoveryProjectorAdapter{
				projector: recinfra.NewDiscoveryFeedProjector(mongoDB),
			}),
		),
		"api-integration-discovery-projection",
	)
	commentOutboxRelay = commentapp.NewOutboxRelay(
		commentStore,
		commentStore,
		contentmessaging.NewCommentOutboxPublisher(eventSpy),
		"api-integration-comment-events",
	)
	commentCountProjectionRelay = commentapp.NewOutboxRelay(
		commentStore,
		commentStore,
		commentapp.NewCommentCountProjector(commentStore, postStore),
		"api-integration-comment-count",
	)
	commentFeedCountRelay = commentapp.NewOutboxRelay(
		commentStore,
		commentStore,
		commentapp.NewCommentCountProjector(
			commentStore,
			persistence.NewMongoDiscoveryFeedCommentCountWriter(mongoDB),
		),
		"api-integration-comment-feed-count",
	)
	dailyMetricsStore := persistence.NewDailyMetricsStore(mongoDB, slog.Default())
	authorImpactStore := persistence.NewAuthorImpactStore(mongoDB, slog.Default())
	authorImpactEvidenceStore := persistence.NewAuthorImpactEvidenceStore(mongoDB, slog.Default())
	testModerationStore = persistence.NewMongoPostModerationCaseStore(
		mongoDB.Collection("post_moderation_cases"),
	)
	if err := testModerationStore.EnsureIndexes(ctx); err != nil {
		panic(fmt.Errorf("ensure post moderation indexes: %w", err))
	}
	testModerationFacades = moderationapp.BindFacades(moderationapp.NewModerationService(
		moderationapp.DataPorts{
			Aggregate:   testModerationStore,
			Eligibility: testModerationStore,
			CurrentCase: testModerationStore,
		},
	))
	wishlistStore := persistence.NewMongoWishlistEventStore(mongoDB, slog.Default())
	behaviorService := behaviorapp.NewBehaviorService(
		hotPath,
		postStore,
		behaviorapp.WithBehaviorEventStore(persistence.NewMongoBehaviorEventStore(mongoDB, slog.Default())),
		// 写入与读取必须绑定同一个 Mongo port，保持 api_integration 与
		// cmd/api 生产装配同构，避免状态端点在测试中退化为 503。
		behaviorapp.WithWishlistEventStore(wishlistStore),
		behaviorapp.WithWishlistStateReader(wishlistStore),
		behaviorapp.WithDailyMetricsStore(dailyMetricsStore),
		behaviorapp.WithAuthorImpactStore(authorImpactStore),
		behaviorapp.WithAuthorImpactEvidenceStore(authorImpactEvidenceStore),
	)
	baseHandler := contenhttp.NewContentHandler(
		feedService,
		postapp.BindFacades(postServiceCore),
		postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
			Detail:       postQueryReader,
			Author:       postQueryReader,
			Tombstones:   postStore,
			ViewerBlocks: recinfra.NewPersonaBlockReader(mongoDB),
		}),
		commentapp.BindFacades(testCommentService),
		reactionapp.BindFacades(reactionService),
		nil,
		behaviorService,
		contenhttp.WithOutboundShareService(outboundShareFacades),
		contenhttp.WithProfileInteractionService(profileInteractionFacades),
		contenhttp.WithMediaService(mediaapp.BindFacades(mediaService)),
		contenhttp.WithModerationService(testModerationFacades),
		contenhttp.WithAuthorImpactStore(authorImpactStore),
		contenhttp.WithAuthorImpactEvidenceStore(authorImpactEvidenceStore),
	).Routes()
	testHandler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id")) == "" {
			subAccountID := identity.AnonymousFallbackSubAccountID
			if userID := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); userID != "" {
				subAccountID = userID
			}
			r.Header.Set("X-Client-Sub-Account-Id", subAccountID)
		}
		if r.Method != http.MethodGet &&
			r.Method != http.MethodHead &&
			strings.TrimSpace(r.Header.Get("Idempotency-Key")) == "" &&
			strings.TrimSpace(r.Header.Get("X-Request-Id")) == "" {
			// App CloudRequestHeaders always provides a stable request ID before
			// the HTTP retry layer. The integration harness supplies the same
			// transport invariant so individual business tests can focus on
			// their object contract; missing-header rejection is covered by the
			// HTTP local-contract test.
			r.Header.Set("X-Request-Id", fmt.Sprintf("api-integration-%p", r))
		}
		// The production stack injects ActorContext only after token verification.
		// This in-process harness has no auth server, so it converts the test actor
		// declared by each case into an explicitly verified principal before the
		// handler. Security negative cases use their own real auth middleware.
		if _, verified := rtauth.PrincipalFromContext(r.Context()); !verified {
			accountID := strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
			personaID := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id"))
			if accountID == "" {
				accountID = personaID
			}
			principal := rtauth.Principal{
				Claims: rtauth.Claims{Subject: accountID, Persona: personaID},
				Actor: rtoperation.ActorContext{
					AccountID: accountID,
					PersonaID: personaID,
				},
			}
			r = r.WithContext(rtauth.WithPrincipal(r.Context(), principal))
		}
		baseHandler.ServeHTTP(w, r)
		// Production owns continuously running durable relays. The synchronous
		// harness drain gives API integration tests the same convergence boundary
		// without publishing from inside the request transaction.
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			if err := drainPostOutboxForHarness(r.Context()); err != nil {
				panic(err)
			}
			if err := drainCommentOutboxForHarness(r.Context()); err != nil {
				panic(err)
			}
			if _, err := reactionOutboxRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain ContentReaction runtime outbox: %w", err))
			}
			if _, err := reactionPostProjectionRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain ContentReaction Post projection outbox: %w", err))
			}
			if _, err := profileReactionRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain ContentReaction profile interaction projection: %w", err))
			}
			if _, err := profileShareRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain OutboundShareFact profile interaction projection: %w", err))
			}
			if _, err := sharePostCountRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain OutboundShareFact Post count projection: %w", err))
			}
			if _, err := shareFeedCountRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain OutboundShareFact feed count projection: %w", err))
			}
			if _, err := profileReadFactRelay.Drain(r.Context(), 100); err != nil {
				panic(fmt.Errorf("drain ProfileInteractionReadFact projection: %w", err))
			}
		}
	})

	code := m.Run()

	// Teardown: disconnect and terminate in reverse order.
	_ = mongoClient.Disconnect(ctx)
	if mongoContainer != nil {
		_ = mongoContainer.Terminate(ctx)
	}
	_ = testRouter.Close()
	_ = integrationRedis.Close(ctx)
	os.Exit(code)
}

type apiIntegrationMediaObjectGateway struct {
	mu      sync.Mutex
	objects map[string]mediaapp.PrepareUploadParams
}

func newAPIIntegrationMediaObjectGateway() *apiIntegrationMediaObjectGateway {
	return &apiIntegrationMediaObjectGateway{objects: map[string]mediaapp.PrepareUploadParams{}}
}

func (g *apiIntegrationMediaObjectGateway) PrepareUpload(_ context.Context, params mediaapp.PrepareUploadParams) (mediaapp.UploadGrant, error) {
	key := "uploads/api-integration/" + params.SessionID
	g.mu.Lock()
	g.objects[key] = params
	g.mu.Unlock()
	return mediaapp.UploadGrant{ObjectKey: key, UploadURL: "https://upload.test/" + params.SessionID, ExpiresAt: params.ExpiresAt}, nil
}

func (g *apiIntegrationMediaObjectGateway) UploadURL(_ context.Context, objectKey string, _ string, _ string, expiresAt time.Time) (string, error) {
	return "https://upload.test/" + objectKey, nil
}

func (g *apiIntegrationMediaObjectGateway) CompleteUpload(_ context.Context, params mediaapp.CompleteUploadParams) (mediaapp.CompletedUploadObject, error) {
	g.mu.Lock()
	_, found := g.objects[params.ObjectKey]
	g.mu.Unlock()
	if !found {
		return mediaapp.CompletedUploadObject{}, fmt.Errorf("object %s was not prepared", params.ObjectKey)
	}
	return mediaapp.CompletedUploadObject{
		ObjectKey:   "media/objects/" + strings.TrimPrefix(params.ExpectedSHA256, "sha256:"),
		SHA256:      params.ExpectedSHA256,
		DeliveryURL: "https://cdn.test/media/" + strings.TrimPrefix(params.ExpectedSHA256, "sha256:"),
	}, nil
}

func (g *apiIntegrationMediaObjectGateway) DeleteTemporaryUpload(
	_ context.Context,
	objectKey string,
) error {
	if !strings.HasPrefix(objectKey, "uploads/") {
		return fmt.Errorf("object %s is not a temporary upload", objectKey)
	}
	g.mu.Lock()
	delete(g.objects, objectKey)
	g.mu.Unlock()
	return nil
}

func (g *apiIntegrationMediaObjectGateway) PublishPublicSlice(
	_ context.Context,
	sourceObjectKey string,
	publicSliceKey string,
) error {
	if !strings.HasPrefix(sourceObjectKey, "media/objects/") &&
		!strings.HasPrefix(sourceObjectKey, "media/processed/image/") {
		return fmt.Errorf("object %s was not completed", sourceObjectKey)
	}
	g.mu.Lock()
	g.objects[publicSliceKey] = mediaapp.PrepareUploadParams{}
	g.mu.Unlock()
	return nil
}

func (g *apiIntegrationMediaObjectGateway) DeliveryURL(_ context.Context, objectKey string) (string, error) {
	return "https://cdn.test/" + objectKey, nil
}

func (g *apiIntegrationMediaObjectGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return fmt.Sprintf("https://cdn.test/%s?expires=%d", objectKey, expiresAt.UTC().Unix()), nil
}

// tryRunMongoContainer attempts to start a mongo:7-jammy testcontainer.
// Returns (nil, err) when Docker is unavailable or the container fails to start,
// capturing both returned errors and internal panics from the testcontainers runtime.
func tryRunMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	return
}

// cleanPosts clears the Post aggregate and its durable command/outbox state so
// an integration test cannot inherit a receipt or relay checkpoint.
func cleanPosts(t *testing.T) {
	t.Helper()
	if mongoDB == nil {
		return
	}
	ctx := context.Background()
	for _, coll := range []string{
		"posts",
		"post_command_receipts",
		"content_outbox",
		"content_outbox_sequences",
		"projection_checkpoints",
		"content_reaction_aggregates",
		"content_reaction_command_receipts",
		"content_reaction_outbox",
		"content_reaction_outbox_sequences",
		"content_reaction_projection_checkpoints",
		"comment_command_receipts",
		"comment_author_rate_limit_locks",
		"comment_outbox",
		"comment_projection_checkpoints",
		"outbound_share_facts",
		"outbound_share_receipts",
		"outbound_share_outbox",
		"outbound_share_outbox_sequences",
		"outbound_share_projection_checkpoints",
		"profile_interaction_activity_views",
		"profile_interaction_read_facts",
		"profile_interaction_read_fact_outbox",
		"profile_interaction_read_fact_outbox_sequences",
		"profile_interaction_read_fact_projection_checkpoints",
		"rm_discovery_feed",
		"rm_recommend_feature",
		"comments",
		"media_upload_sessions",
		"media_assets",
		"media_upload_session_command_receipts",
		"media_asset_command_receipts",
		"media_upload_session_outbox",
		"media_asset_outbox",
		"media_original_access_facts",
		"media_original_access_receipts",
		"rm_behavior_events",
	} {
		if _, err := mongoDB.Collection(coll).DeleteMany(ctx, bson.M{}); err != nil {
			t.Logf("cleanPosts(%s): %v", coll, err)
		}
	}
	eventSpy.Reset()
}

type discoveryProjectorAdapter struct {
	projector *recinfra.DiscoveryFeedProjector
}

func (a *discoveryProjectorAdapter) Project(ctx context.Context, event ports.ProjectorEvent) error {
	return a.projector.Project(ctx, recinfra.ProjectorEvent{
		Type:          event.Type,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Payload:       event.Payload,
		OccurredAt:    event.OccurredAt,
	})
}
