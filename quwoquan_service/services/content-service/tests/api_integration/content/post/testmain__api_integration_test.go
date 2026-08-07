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
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commenthttp "quwoquan_service/services/content-service/internal/content/comment/adapters/inbound/http"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmessaging "quwoquan_service/services/content-service/internal/content/comment/infrastructure/messaging"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	reactionhttp "quwoquan_service/services/content-service/internal/content/content_reaction/adapters/inbound/http"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactionmessaging "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/messaging"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	tombstonepost "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/adapters/inbound/post"
	tombstonepersistence "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/infrastructure/persistence"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	outboundsharehttp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/adapters/inbound/http"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	outboundshareinfra "quwoquan_service/services/content-service/internal/content/outbound_share_fact/infrastructure/persistence"
	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	accessinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/accesscontrol"
	contentmessaging "quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	profileactivityhttp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/adapters/inbound/http"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	profileinteractioninfra "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/infrastructure/persistence"
	profilereadfacthttp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/adapters/inbound/http"
	profileinteractionreadapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
	profilereadfactinfra "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/infrastructure/persistence"
	mediaassethttp "quwoquan_service/services/content-service/internal/media/media_asset/adapters/inbound/http"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediainfra "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/media"
	"quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/mediareferencefence"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
	originalaccessaudit "quwoquan_service/services/content-service/internal/media/media_original_access_fact/adapters/inbound/audit"
	originalaccessapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	originalaccesspersistence "quwoquan_service/services/content-service/internal/media/media_original_access_fact/infrastructure/persistence"
	uploadsessionhttp "quwoquan_service/services/content-service/internal/media/media_upload_session/adapters/inbound/http"
	uploadsessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	uploadsessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"
	originalaccessquotahttp "quwoquan_service/services/content-service/internal/media/original_access_quota/adapters/inbound/http"
	originalaccessquotaapp "quwoquan_service/services/content-service/internal/media/original_access_quota/application"
	originalaccessquotapersistence "quwoquan_service/services/content-service/internal/media/original_access_quota/infrastructure/persistence"
	moderationhttp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/adapters/inbound/http"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationpersistence "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/infrastructure/persistence"
)

var (
	testHandler                 http.Handler
	testFeedService             *feedapp.FeedService
	testPostService             *postapp.PostService
	testCommentService          *commentapp.CommentService
	postOutboxRelay             *postapp.OutboxRelay
	postReactionLifecycleRelay  *postapp.OutboxRelay
	postCommentTombstoneRelay   *postapp.OutboxRelay
	commentOutboxRelay          *commentapp.OutboxRelay
	commentCountProjectionRelay *commentapp.OutboxRelay
	reactionOutboxRelay         *reactionapp.OutboxRelay
	reactionPostProjectionRelay *reactionapp.OutboxRelay
	profileReactionRelay        *reactionapp.OutboxRelay
	profileCommentRelay         *commentapp.OutboxRelay
	profileShareRelay           *outboundshareapp.OutboxRelay
	sharePostCountRelay         *outboundshareapp.OutboxRelay
	profileReadFactRelay        *profileinteractionreadapp.ReadFactOutboxRelay
	profilePostTargetRelay      *postapp.OutboxRelay
	testReactionStore           *reactionpersistence.MongoContentReactionStore
	testReactionService         *reactionapp.Service
	testModerationStore         *moderationpersistence.MongoPostModerationCaseStore
	testModerationFacades       *moderationapp.Facades
	eventSpy                    *testinfra.EventSpy
	mongoDB                     *mongo.Database
	mongoClient                 *mongo.Client
	testRouter                  *rtredis.Router
	testPostgresFixture         *testinfra.PostgresFixture
)

func newMongoPostStore(collection *mongo.Collection) *persistence.MongoPostStore {
	fence, err := mediareferencefence.New(collection.Database())
	if err != nil {
		panic("create Post MediaAsset reference fence: " + err.Error())
	}
	return persistence.NewMongoPostStore(
		collection,
		tombstonepost.NewStorePort(
			tombstonepersistence.NewMongoStore(collection.Database()),
		),
		fence,
	)
}

const (
	integrationEnvironment    = "api_integration"
	integrationReleaseID      = "rel_api_integration"
	integrationSupplyPostID   = "api_integration_active_supply_video"
	integrationManifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)

type acceptingActiveTaxonomyLeafValidationPort struct{}

func (acceptingActiveTaxonomyLeafValidationPort) ValidateActiveTaxonomyLeaves(
	_ context.Context,
	expectedTaxonomyReleaseID string,
	tagRefs []string,
) error {
	if strings.TrimSpace(expectedTaxonomyReleaseID) != "tag-taxonomy-test-001" {
		return contentgenerated.AppErrorFromInvalidArgument(
			"controlled active taxonomy release mismatch",
		)
	}
	for _, tagRef := range tagRefs {
		if tagRef == "Topic/dependency-unavailable" {
			return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"controlled tag taxonomy dependency failure",
			)
		}
	}
	return nil
}

func newReportPostgresSuite(t *testing.T) *testinfra.Suite {
	t.Helper()
	if testPostgresFixture == nil {
		t.Fatal("content-service tests require TestMain to provision PostgreSQL")
	}
	return testinfra.NewSuite(
		t,
		testinfra.WithPostgresFixture(testPostgresFixture),
	)
}

func requireMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	if mongoDB == nil {
		tb.Fatal("content-service tests require TestMain to provision mongoDB or exit before execution")
	}
	return mongoDB
}

func newMongoCommentDataAdapter(
	tb testing.TB,
	database *mongo.Database,
) *commentpersistence.MongoCommentDataAdapter {
	tb.Helper()
	fence, err := mediareferencefence.New(database)
	if err != nil {
		tb.Fatalf("create Comment MediaAsset reference fence: %v", err)
	}
	return commentpersistence.NewMongoCommentDataAdapter(database, fence)
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
	if postReactionLifecycleRelay == nil ||
		postCommentTombstoneRelay == nil ||
		profilePostTargetRelay == nil {
		return fmt.Errorf("content-service api_integration requires a Post projection relay")
	}
	if _, err := postOutboxRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Post outbox: %w", err)
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
		profileReactionRelay == nil {
		t.Fatal("content-service api_integration requires ContentReaction outbox relays")
	}
	if _, err := reactionOutboxRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction runtime outbox: %v", err)
	}
	if _, err := reactionPostProjectionRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction Post projection outbox: %v", err)
	}
	if _, err := profileReactionRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain ContentReaction profile interaction projection outbox: %v", err)
	}
}

func drainCommentOutboxForHarness(ctx context.Context) error {
	if commentOutboxRelay == nil || commentCountProjectionRelay == nil ||
		profileCommentRelay == nil {
		return fmt.Errorf("content-service api_integration requires Comment outbox relays")
	}
	if _, err := commentOutboxRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment runtime outbox: %w", err)
	}
	if _, err := commentCountProjectionRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment count projection outbox: %w", err)
	}
	if _, err := profileCommentRelay.Drain(ctx, 100); err != nil {
		return fmt.Errorf("drain Comment profile interaction projection outbox: %w", err)
	}
	return nil
}

func TestMain(m *testing.M) {
	ctx := context.Background()

	eventSpy = testinfra.NewEventSpy()
	postgresRoot, err := os.MkdirTemp("", "qwq-content-api-postgres-")
	if err != nil {
		panic("create content-service PostgreSQL fixture root: " + err.Error())
	}
	testPostgresFixture, err = testinfra.StartPostgresFixture(postgresRoot, 0)
	if err != nil {
		_ = os.RemoveAll(postgresRoot)
		panic("content-service api_integration requires real PostgreSQL: " + err.Error())
	}

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
	personaAccessProjection := accessinfra.NewPersonaAccessProjection(mongoDB)
	if err := personaAccessProjection.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize Content persona access projection: " + err.Error())
	}
	personaBlockReader := accessinfra.NewPersonaBlockReader(mongoDB)
	postStore := newMongoPostStore(mongoDB.Collection("posts"))
	if err := postStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize Post aggregate/outbox indexes: " + err.Error())
	}
	commentReferenceFence, err := mediareferencefence.New(mongoDB)
	if err != nil {
		panic("failed to initialize Comment MediaAsset reference fence: " + err.Error())
	}
	commentStore := commentpersistence.NewMongoCommentDataAdapter(mongoDB, commentReferenceFence)
	if err := commentStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize Comment aggregate/outbox indexes: " + err.Error())
	}
	mediaStore := mediaassetpersistence.NewMongoMediaStore(mongoDB)
	if err := mediaStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize MediaAsset indexes: " + err.Error())
	}
	mediaObjects := newAPIIntegrationMediaObjectGateway()
	mediaOriginalAccessStore := originalaccesspersistence.NewMongoStore(mongoDB)
	if err := mediaOriginalAccessStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize MediaOriginalAccessFact indexes: " + err.Error())
	}
	originalAccessQuotaStore := originalaccessquotapersistence.NewMongoStore(mongoDB)
	if err := originalAccessQuotaStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize OriginalAccessQuota indexes: " + err.Error())
	}
	mediaUploadSessionStore := uploadsessionpersistence.NewMongoStore(
		mongoDB.Collection("media_upload_sessions"),
		mediaStore,
	)
	if err := mediaUploadSessionStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize MediaUploadSession indexes: " + err.Error())
	}
	mediaUploadSessionService := uploadsessionapp.NewUseCases(
		mediaUploadSessionStore,
		mediaObjects,
	)
	mediaPostReader := persistence.NewMongoPostQueryReader(mongoDB.Collection("posts"))
	mediaService := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(mediaStore),
		mediaObjects,
	)
	originalAccessQuotaService := originalaccessquotaapp.NewService(
		originalAccessQuotaStore,
		originalaccessaudit.NewAppender(
			originalaccessapp.NewService(mediaOriginalAccessStore),
		),
		mediaStore,
		postapp.NewMediaAssetVisibilityReader(mediaPostReader, personaBlockReader),
		mediaObjects,
	)
	testReactionStore = reactionpersistence.NewMongoContentReactionStore(mongoDB)
	if err := testReactionStore.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize ContentReaction aggregate/outbox indexes: " + err.Error())
	}
	commentViewerRelationships :=
		commentpersistence.NewCommentViewerRelationshipMongoProjection(mongoDB)
	if err := commentViewerRelationships.EnsureIndexes(ctx); err != nil {
		panic("failed to initialize Comment viewer relationship indexes: " + err.Error())
	}
	testCommentService = commentapp.NewCommentService(
		commentapp.BindDataPorts(
			commentStore,
			commentpersistence.NewCommentAttachmentReader(mediaStore, mediaObjects),
			testReactionStore,
			commentViewerRelationships,
			commentViewerRelationships,
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
			reactionpersistence.NewReactionTargetReader(commentStore, commentStore),
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
		reactionmessaging.NewContentReactionOutboxPublisher(eventSpy),
		"api-integration-reaction-events",
	)
	reactionPostProjectionRelay = reactionapp.NewOutboxRelay(
		testReactionStore,
		testReactionStore,
		reactionapp.NewActiveReactionCountProjector(testReactionStore, postStore),
		"api-integration-reaction-like-count",
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
	// Feed candidate recall, hydration and the active-release readback must observe
	// the same materialized database as production. Test cleanup preserves only
	// this fixed release-bound supply row; case-owned UGC remains isolated.
	activeSupplyDB := mongoDB
	if _, err := activeSupplyDB.Collection("data_release_state").UpdateOne(
		ctx,
		bson.M{"environment": integrationEnvironment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{
			"environment": integrationEnvironment, "sourceOwner": "qwq_data",
			"status": "active", "activeReleaseId": integrationReleaseID,
			"manifestDigest": integrationManifestDigest,
		}},
		mongoopts.UpdateOne().SetUpsert(true),
	); err != nil {
		panic(fmt.Errorf("seed api integration active supply snapshot: %w", err))
	}
	if _, err := activeSupplyDB.Collection("posts").UpdateOne(ctx,
		bson.M{"_id": integrationSupplyPostID},
		bson.M{"$set": bson.M{
			"sourceOwner": "qwq_data", "releaseId": integrationReleaseID,
			"manifestDigest":  integrationManifestDigest,
			"lifecycleStatus": "active", "status": "published", "visibility": "public",
			"moderationStatus": "approved", "contentIdentity": "work", "contentType": "video",
			"videoUrl": "https://media.example.test/api-integration.mp4", "durationMs": int64(1000),
		}}, mongoopts.UpdateOne().SetUpsert(true)); err != nil {
		panic(fmt.Errorf("seed api integration active supply post: %w", err))
	}
	feedService := feedapp.NewFeedService(
		persistence.NewMongoPostQueryReader(mongoDB.Collection("posts")),
		feedapp.WithFeedViewerBlockReader(personaBlockReader),
		feedapp.WithActiveSupplyReader(persistence.NewMongoActiveSupplyReader(
			activeSupplyDB,
			integrationEnvironment,
		)),
		feedapp.WithFeedDeliveryPageStore(
			deliveryredis.NewStore(testRouter.Scene("rec")),
		),
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
	profileReadFactStore := profilereadfactinfra.NewMongoReadFactStore(mongoDB)
	if err := profileReadFactStore.EnsureIndexes(ctx); err != nil {
		panic(fmt.Errorf("ensure ProfileInteractionReadFact indexes: %w", err))
	}
	profileProjector := profileinteractionapp.NewProfileInteractionActivityViewProjector(
		profileinteractioninfra.NewMongoProjectionSourceReader(mongoDB),
		profileActivityStore,
	)
	profileInteractionFacades := profileinteractionapp.BindFacades(
		profileinteractionapp.NewActivityQueryService(profileActivityStore),
		profileinteractionreadapp.NewReadFactService(
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
	profileReadFactRelay = profileinteractionreadapp.NewReadFactOutboxRelay(
		profileReadFactStore,
		profileReadFactStore,
		profileinteractionapp.NewReadFactProjector(profileProjector),
		"api-integration-profile-interaction-read",
	)
	profilePostTargetRelay = postapp.NewOutboxRelay(
		postStore,
		postStore,
		profileinteractionapp.NewPostTargetProjector(profileProjector),
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
	commentOutboxRelay = commentapp.NewOutboxRelay(
		commentStore,
		commentStore,
		commentmessaging.NewCommentOutboxPublisher(eventSpy),
		"api-integration-comment-events",
	)
	commentCountProjectionRelay = commentapp.NewOutboxRelay(
		commentStore,
		commentStore,
		postapp.NewCommentCountProjectionPublisher(
			postapp.NewCommentCountProjectionHandler(commentStore, postStore),
		),
		"api-integration-comment-count",
	)
	dailyMetricsStore := behaviorpersistence.NewDailyMetricsStore(mongoDB, slog.Default())
	testModerationStore = moderationpersistence.NewMongoPostModerationCaseStore(
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
	wishlistStore := behaviorpersistence.NewMongoWishlistEventStore(mongoDB, slog.Default())
	behaviorService := behaviorapp.NewBehaviorService(
		hotPath,
		postStore,
		behaviorapp.WithBehaviorEventStore(behaviorpersistence.NewMongoBehaviorEventStore(mongoDB, slog.Default())),
		behaviorapp.WithOnboardingInterestTaxonomyValidator(
			behaviorapp.CatalogBackedOnboardingInterestTaxonomy{
				DimensionRoots: map[string]string{
					"topic":    "Topic",
					"audience": "Audience",
					"format":   "Format",
					"entity":   "Entity",
				},
				MinSelections:            1,
				MaxSelections:            12,
				DimensionMinSelections:   map[string]int{"topic": 0, "audience": 0, "format": 0, "entity": 0},
				DimensionMaxSelections:   map[string]int{"topic": 4, "audience": 4, "format": 4, "entity": 4},
				ActiveLeafValidationPort: acceptingActiveTaxonomyLeafValidationPort{},
			},
		),
		// 写入与读取必须绑定同一个 Mongo port，保持 api_integration 与
		// cmd/api 生产装配同构，避免状态端点在测试中退化为 503。
		behaviorapp.WithWishlistEventStore(wishlistStore),
		behaviorapp.WithWishlistStateReader(wishlistStore),
		behaviorapp.WithDailyMetricsStore(dailyMetricsStore),
	)
	baseHandler := contenhttp.NewContentHandler(
		feedService,
		postapp.BindFacades(postServiceCore),
		postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
			Detail:       postQueryReader,
			Author:       postQueryReader,
			Tombstones:   postStore,
			ViewerBlocks: personaBlockReader,
		}),
		commenthttp.NewHandler(commentapp.BindFacades(testCommentService)),
		reactionhttp.NewHandler(reactionapp.BindFacades(reactionService)),
		nil,
		behaviorService,
		contenhttp.WithContentBehaviorHandler(behaviorhttp.NewHandler(behaviorService)),
		contenhttp.WithOutboundShareHandler(outboundsharehttp.NewHandler(outboundShareFacades)),
		contenhttp.WithProfileInteractionHandlers(
			profileactivityhttp.NewHandler(profileInteractionFacades.ActivityQueryFacade),
			profilereadfacthttp.NewHandler(profileInteractionFacades.ReadFactAppendFacade),
		),
		contenhttp.WithMediaAssetHandler(
			mediaassethttp.NewHandler(mediaapp.BindFacades(mediaService)),
		),
		contenhttp.WithOriginalAccessQuotaHandler(
			originalaccessquotahttp.NewHandler(originalAccessQuotaService),
		),
		contenhttp.WithMediaUploadSessionHandler(
			uploadsessionhttp.NewHandler(mediaUploadSessionService),
		),
		contenhttp.WithPostModerationCaseHandler(
			moderationhttp.NewHandler(testModerationFacades),
		),
	).Routes()
	testHandler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimSpace(r.Header.Get("X-Client-Persona-Id")) == "" {
			personaID := identity.AnonymousFallbackPersonaID
			if userID := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); userID != "" {
				personaID = userID
			}
			r.Header.Set("X-Client-Persona-Id", personaID)
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
			personaID := strings.TrimSpace(r.Header.Get("X-Client-Persona-Id"))
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
	if err := testPostgresFixture.Close(); err != nil && code == 0 {
		fmt.Fprintln(os.Stderr, "close content-service PostgreSQL fixture:", err)
		code = 1
	}
	os.Exit(code)
}

type apiIntegrationMediaObjectGateway struct {
	mu      sync.Mutex
	objects map[string]struct{}
}

func newAPIIntegrationMediaObjectGateway() *apiIntegrationMediaObjectGateway {
	return &apiIntegrationMediaObjectGateway{objects: map[string]struct{}{}}
}

func (g *apiIntegrationMediaObjectGateway) PrepareUpload(
	_ context.Context,
	params uploadsessionapp.PrepareUploadParams,
) (uploadsessionapp.UploadGrant, error) {
	key := "uploads/api-integration/" + params.SessionID
	g.mu.Lock()
	g.objects[key] = struct{}{}
	g.mu.Unlock()
	return uploadsessionapp.UploadGrant{
		ObjectKey: key,
		UploadURL: "https://upload.test/" + params.SessionID,
		ExpiresAt: params.ExpiresAt,
	}, nil
}

func (g *apiIntegrationMediaObjectGateway) UploadURL(_ context.Context, objectKey string, _ string, _ string, expiresAt time.Time) (string, error) {
	return "https://upload.test/" + objectKey, nil
}

func (g *apiIntegrationMediaObjectGateway) CompleteUpload(
	_ context.Context,
	params uploadsessionapp.CompleteUploadParams,
) (uploadsessionapp.CompletedObject, error) {
	g.mu.Lock()
	_, found := g.objects[params.ObjectKey]
	g.mu.Unlock()
	if !found {
		return uploadsessionapp.CompletedObject{}, fmt.Errorf(
			"object %s was not prepared",
			params.ObjectKey,
		)
	}
	return uploadsessionapp.CompletedObject{
		ObjectKey: "media/objects/" + strings.TrimPrefix(params.ExpectedSHA256, "sha256:"),
		SHA256:    params.ExpectedSHA256,
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
	g.objects[publicSliceKey] = struct{}{}
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
		"comment_viewer_relationship_projection",
		"comment_viewer_relationship_inbox",
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
		filter := bson.M{}
		switch coll {
		case "posts":
			filter = bson.M{"_id": bson.M{"$ne": integrationSupplyPostID}}
		}
		if _, err := mongoDB.Collection(coll).DeleteMany(ctx, filter); err != nil {
			t.Logf("cleanPosts(%s): %v", coll, err)
		}
	}
	eventSpy.Reset()
}
