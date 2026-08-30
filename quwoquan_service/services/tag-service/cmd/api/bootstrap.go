package bootstrap

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"quwoquan_service/runtime/servicekit"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	signalstream "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/adapters/inbound/stream"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
	feedbackhttp "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/application/tagfeedback"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/infrastructure/tagfeedbackstore"
	nodehttp "quwoquan_service/services/tag-service/internal/tag/tag_node_view/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	releasehttp "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

// config 是 tag-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// Mongo/Redis 按「声明即装配」自动发现（DEC-028），env 覆盖键由服务名
// 派生前缀 TAG 拼出。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Mongo servicekit.MongoConfig `yaml:"mongo"`

	Redis struct {
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
	} `yaml:"redis"`
}

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定
// 键集不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix("tag-service"), &config{})
}

// NewModule assembles tag-service without binding a listener, starting
// workers, admitting traffic, or owning process signals.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap("tag-service", servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("tag"),
		// 本服务承载浏览器直连的标签面，按 env 派生 origin 策略开跨域。
		CORS:            servicekit.BrowserCORSFromEnv(),
		AuthorityScopes: []string{"user.account.security.read"},
		Assemble:        assembleTagDomain,
	})
}

func assembleTagDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	db := asm.MongoDB

	tagNodeStore := persistence.NewMongoTagNodeStore(db.Collection("tag_nodes"))
	objectTagStore := indexpersistence.NewMongoObjectTagIndexStore(db.Collection("object_tag_index"))
	if err := tagNodeStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure tag_nodes indexes: %w", err)
	}
	if err := objectTagStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure object_tag_index indexes: %w", err)
	}

	releaseStore := taxonomyreleasestore.NewStore(db)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure tag_taxonomy_releases indexes: %w", err)
	}
	tagService := application.NewTagService(tagNodeStore, objectTagStore, releaseStore)
	releaseFacade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		return fmt.Errorf("taxonomy release facade init failed: %w", err)
	}
	feedbackSink := tagfeedbackstore.NewSink(db)
	if err := feedbackSink.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure tag_feedback_fact indexes: %w", err)
	}
	feedbackFacade, err := tagfeedback.NewFacade(feedbackSink, tagService)
	if err != nil {
		return fmt.Errorf("tag feedback facade init failed: %w", err)
	}

	messageTransport, err := requireTagAPIMessageTransport(
		ctx,
		asm.Identity.AppEnv,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport init failed: %w", err)
	}
	profileTagConsumer, err := signalstream.NewUserProfileTagConsumer(
		messageTransport,
		objectTagStore,
		asm.Identity.ServiceName,
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("user profile tag consumer init failed: %w", err)
	}
	asm.Workers.Add(profileTagConsumer.Run)
	feedbackEventPublisher, err := tagfeedbackstore.NewStreamEventPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("feedback event publisher init failed: %w", err)
	}
	feedbackEventRelay, err := tagfeedbackstore.NewEventRelay(
		feedbackSink,
		feedbackEventPublisher,
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("feedback event relay init failed: %w", err)
	}
	asm.Workers.Add(feedbackEventRelay.Run)

	nodehttp.NewTagHandler(tagService).Register(asm.Mux)
	releasehttp.NewTaxonomyReleaseHandler(releaseFacade).Register(asm.Mux)
	feedbackhttp.NewTagFeedbackHandler(feedbackFacade).Register(asm.Mux)

	asm.Health.Register("taxonomy-projection", func(hctx context.Context) error {
		release, found, err := releaseStore.FindActive(hctx)
		if err != nil {
			return err
		}
		if !found {
			// 冷启动的空库尚无任何 taxonomy release：canonical taxonomy 由
			// Data CLI ship apply 在全栈就绪之后导入，若此处 fail 会构成
			// 「readiness 等导入、导入等 readiness」的环境死锁。空 taxonomy
			// 是合法初始状态（查询按空集服务）；只有「存在 active release
			// 但节点投影与其不一致」才是必须 fail-closed 的损坏状态。
			return nil
		}
		return tagNodeStore.ValidateReleaseProjection(
			hctx,
			release.ReleaseID,
			release.NodeCount,
		)
	})
	asm.Health.Register("profile-tag-consumer", func(context.Context) error {
		return profileTagConsumer.Healthy(15 * time.Second)
	})
	asm.Health.Register("feedback-event-relay", func(hctx context.Context) error {
		return feedbackEventRelay.Healthy(hctx, 15*time.Second)
	})
	return nil
}
