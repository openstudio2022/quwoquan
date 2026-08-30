package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/artifactidentity"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"

	runtimeconfig "quwoquan_service/runtime/config"
	httpadapter "quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/http"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/mq"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
	rtccache "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/livekit"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/persistence"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/providerbinding"
	rtcconfig "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/runtimeconfig"
)

// config 是 rtc-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// 装配骨架由 servicekit.Bootstrap 承担（DEC-028）。MongoDB 键沿用环境
// secretRefs 已固定的无前缀契约键（envAbsolute）。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	CallSession struct {
		RingTimeout rtcconfig.RingTimeoutSettings `yaml:"ring_timeout"`
	} `yaml:"call_session"`

	MongoDB struct {
		URI      string `yaml:"uri" env:"MONGO_URI" required:"true"`
		Database string `yaml:"database" env:"MONGO_DATABASE" required:"true"`
	} `yaml:"mongodb"`

	Redis struct {
		Realtime servicekit.RedisSceneConfig `yaml:"realtime" envPrefix:"REDIS_REALTIME"`
		General  servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
		// SharedAddr 是部署面为两个 scene 共享注入的兜底地址，scene 专属
		// addr 优先。声明在此而非 os.Getenv 裸读，键才进 DeclaredEnvKeys。
		SharedAddr string `yaml:"-" env:"REDIS_ADDR"`
	} `yaml:"redis"`
}

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定
// 键集不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix("rtc-service"), &config{})
}

func main() {
	if _, err := artifactidentity.LoadAndValidate(
		os.Getenv("QWQ_ARTIFACT_IDENTITY_FILE"),
		os.Getenv("APP_ENV"),
	); err != nil {
		log.Fatalf("rtc-service artifact identity invalid: %v", err)
	}
	servicekit.RunStandalone("rtc-service", func() (servicehost.Module, error) {
		return newModule()
	})
}

func newModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap("rtc-service", servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("rtc"),
		AuthorityScopes:      []string{"user.account.security.read"},
		RedisScenes:          resolveRedisScenes,
		Assemble:             assembleRTCDomain,
	})
}

// resolveRedisScenes 装配三个 codegen scene：realtime 独立，rec 复用 general。
//
// 地址有两个声明位：scene 专属 addr 与 RTC_REDIS_ADDR。后者是 compose 与 prod
// plane 为两个 scene 共享注入的本服务部署面既有契约。两者构成固定优先级——
// scene 专属优先、共享其次——与配置渲染的分层默认同构：每一层都是显式声明，
// 生效值总能指回一处写下它的地方。这不是「地址为空就去猜」，两层都缺就是没人
// 声明过地址，交给 DeclaredMode 按声明的 mode 判否。
func resolveRedisScenes(cfg *config) map[string]servicekit.RedisSceneConfig {
	general := cfg.Redis.General
	realtime := cfg.Redis.Realtime
	shared := strings.TrimSpace(cfg.Redis.SharedAddr)
	general.Addr = firstDeclaredAddr(general.Addr, shared)
	realtime.Addr = firstDeclaredAddr(realtime.Addr, shared)
	return map[string]servicekit.RedisSceneConfig{
		"realtime": realtime,
		"general":  general,
		"rec":      general,
	}
}

// firstDeclaredAddr 按声明位优先级取第一个被声明过的地址。
func firstDeclaredAddr(layers ...string) string {
	for _, layer := range layers {
		if declared := strings.TrimSpace(layer); declared != "" {
			return declared
		}
	}
	return ""
}

func assembleRTCDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	logger := slog.Default()

	ringTimeoutConfiguration, err := cfg.CallSession.RingTimeout.Resolve()
	if err != nil {
		return fmt.Errorf("ring timeout configuration invalid: %w", err)
	}
	accountSecurityAuthority := asm.Auth.AccountSecurityAuthority

	if err := asm.RedisRouter.PingAll(ctx); err != nil {
		log.Printf("WARN: rtc-service redis ping: %v", err)
	}
	messageTransport, err := requireRTCMessageTransport(
		ctx,
		asm.Identity.AppEnv,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport preflight failed: %w", err)
	}

	mongoDB, err := asm.Mongo(servicekit.MongoConfig{
		URI:      cfg.MongoDB.URI,
		Database: cfg.MongoDB.Database,
	})
	if err != nil {
		return err
	}
	callStore := persistence.NewMongoCallStore(mongoDB)
	if err := callStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("call session indexes unavailable: %w", err)
	}
	callCache := rtccache.NewCallStateCache(asm.RedisRouter.Scene("general"))
	realtimePublisher := mq.NewRealtimePublisher(messageTransport)

	mediaBinding, err := providerbinding.ResolveMediaTransport(
		asm.Identity.AppEnv,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("media transport binding invalid: %w", err)
	}
	if mediaBinding.AdapterID != livekit.AdapterID {
		return fmt.Errorf(
			"media transport adapter mismatch: got %q", mediaBinding.AdapterID,
		)
	}
	livekitCB := rtgov.NewCircuitBreaker(5, 15*time.Second, logger)
	livekitClient := rtgov.WrapClientWithCB(
		&http.Client{Timeout: mediaBinding.Timeout},
		livekitCB,
	)
	var roomAdapter application.MediaRoomProvider = livekit.NewLiveKitRoomAdapter(
		mediaBinding.ConnectionURL,
		mediaBinding.APIKey,
		mediaBinding.APISecret,
		livekit.WithHTTPClient(livekitClient),
	)
	domainSvc, err := callsession.NewCallSessionService(
		ringTimeoutConfiguration.DomainPolicy,
	)
	if err != nil {
		return fmt.Errorf("call session domain policy invalid: %w", err)
	}

	userServiceBaseURL := strings.TrimSpace(os.Getenv("USER_SERVICE_BASE_URL"))
	if userServiceBaseURL == "" && failFastEnvironment(asm.Identity.AppEnv) {
		return fmt.Errorf(
			"USER_SERVICE_BASE_URL is required in %s for the one-to-one relationship gate",
			asm.Identity.AppEnv,
		)
	}
	relationshipGate := application.DenyRelationshipGate()
	if userServiceBaseURL != "" {
		profileCB := rtgov.NewCircuitBreaker(5, 15*time.Second, logger)
		profileClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 2 * time.Second}, profileCB)
		relationshipGate = httpadapter.NewUserRelationshipGate(userServiceBaseURL, profileClient)
	}
	orchestrator := application.NewCallOrchestrator(
		callStore,
		callCache,
		domainSvc,
		roomAdapter,
		relationshipGate,
		application.WithCallAccountSecurityGate(
			application.NewCallAccountSecurityGate(accountSecurityAuthority),
		),
	)
	signalDeliveryCoordinator := application.NewCallSignalDeliveryRelay(
		callStore,
		realtimePublisher,
	)
	accountSecurityFailures := rtccache.NewAccountSecurityEventFailureStore(
		asm.RedisRouter.Scene("general"),
	)
	accountSecurityConsumer, err := mq.NewUserAccountSecurityConsumer(
		messageTransport,
		orchestrator,
		accountSecurityFailures,
		asm.Identity.InstanceID,
		logger,
		mq.DefaultUserAccountSecurityConsumerConfig(),
	)
	if err != nil {
		return fmt.Errorf("account security consumer invalid: %w", err)
	}

	asm.Workers.Add(func(workerCtx context.Context) {
		runRecoveringWorker(
			workerCtx,
			logger,
			"rtc call outbox relay",
			func(runCtx context.Context) error {
				return signalDeliveryCoordinator.Run(runCtx, 100*time.Millisecond)
			},
		)
	})
	// 振铃超时收割：无人接听迁移 ended/no_answer 并经 outbox 下发 call.ended。
	// 扫描间隔与领域阈值来自同一 typed service runtime configuration。
	asm.Workers.Add(func(workerCtx context.Context) {
		runRecoveringWorker(
			workerCtx,
			logger,
			"rtc ring timeout sweeper",
			func(runCtx context.Context) error {
				return orchestrator.RunRingTimeoutSweeper(
					runCtx,
					ringTimeoutConfiguration.SweepInterval,
				)
			},
		)
	})
	asm.Workers.Add(accountSecurityConsumer.Run)

	domainHandler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		httpadapter.NewCallHandler(orchestrator).Routes(),
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/rtc/account-closure/dead-letters:recover",
			Module:   rterr.ModuleRTC,
			Releaser: accountSecurityConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route failed: %w", err)
	}
	asm.Mux.Handle("/", domainHandler)

	asm.Health.Register("user_account_security_consumer", func(context.Context) error {
		return accountSecurityConsumer.Healthy(10 * time.Second)
	})
	return nil
}

func runRecoveringWorker(
	ctx context.Context,
	logger *slog.Logger,
	name string,
	run func(context.Context) error,
) {
	for {
		err := run(ctx)
		if err == nil || ctx.Err() != nil {
			return
		}
		logger.Error(name+" stopped", "error", err)
		retry := time.NewTimer(time.Second)
		select {
		case <-ctx.Done():
			if !retry.Stop() {
				select {
				case <-retry.C:
				default:
				}
			}
			return
		case <-retry.C:
		}
	}
}

func failFastEnvironment(appEnv string) bool {
	switch strings.TrimSpace(appEnv) {
	case "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}
