// realtime-gateway：统一实时通信网关（runtime_session）。
// 职责最小化：ticket 鉴权、WS/LongPoll 连接管理（lease+fencing+presence）、
// 按可信身份订阅 Redis realtime scene 并透传事件。不承载任何业务聚合。
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
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
	streamadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/stream"
	wsadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/ws"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
	presenceconnection "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/connection"
	presencehttp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/http"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
	presenceredis "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/redisstore"

	httpadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/http"
)

const serviceName = "realtime-gateway"

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定
// 键集不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

func main() {
	if _, err := artifactidentity.LoadAndValidate(
		os.Getenv("QWQ_ARTIFACT_IDENTITY_FILE"),
		os.Getenv("APP_ENV"),
	); err != nil {
		log.Fatalf("realtime-gateway artifact identity invalid: %v", err)
	}
	servicekit.RunStandalone(serviceName, func() (servicehost.Module, error) {
		return newModule()
	})
}

func newModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("realtime"),
		AuthorityScopes:      []string{"user.account.security.read"},
		// ticket、access token 与 presence 载荷都会经过进程 trace，
		// KV 元数据一律不落盘。
		ObservabilityKVFilter: robs.NewKVMetadataFilter(nil),
		// 网关按 runtime boundary 执行请求级契约：被 block 的 operation 仍要
		// 能在本服务上产出候选证据，公开边界的商用状态门由 api-edge 承担。
		OperationGuard: func(servicekit.Identity) (
			func(http.Handler) http.Handler, error,
		) {
			return rtauth.EnforceRuntimeOperationContract(
				operationsecurity.ForDomain("realtime"),
			), nil
		},
		// WS 升级后连接被 hijack，写截止时间不会被重置。
		HijacksConnections: true,
		ValidateConfig:     validateRealtimeConfig,
		Assemble:           assembleRealtimeDomain,
	})
}

func assembleRealtimeDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	logger := slog.Default()
	nodeID := asm.Identity.InstanceID

	realtimeClient := asm.RedisRouter.Scene("realtime")
	if err := realtimeClient.Ping(ctx); err != nil {
		if failFastEnvironment(cfg.Environment) {
			return fmt.Errorf("realtime redis unavailable: %w", err)
		}
		log.Printf(
			"WARN: realtime-gateway redis ping errorDigest=%s",
			application.ErrorDigest(err),
		)
	}
	messageTransport, err := requireMessageTransport(
		ctx,
		cfg.Environment,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("realtime-gateway message transport preflight failed: %w", err)
	}

	accountSecurityAuthority := asm.Auth.AccountSecurityAuthority
	presenceStore, err := presenceredis.NewStore(realtimeClient)
	if err != nil {
		return err
	}
	presenceProjector, err := presenceapp.NewProjector(presenceStore)
	if err != nil {
		return err
	}
	presenceQueries, err := presenceapp.NewQueryFacade(presenceStore)
	if err != nil {
		return err
	}
	presenceRevoker, err := presenceapp.NewRevoker(presenceStore)
	if err != nil {
		return err
	}
	presenceConnection, err := presenceconnection.NewProjector(presenceProjector, presenceRevoker)
	if err != nil {
		return err
	}
	resumeReader, err := redisstore.NewResumableEventReader(messageTransport)
	if err != nil {
		return fmt.Errorf("realtime resumable event reader init failed: %w", err)
	}
	accountSecurityStore := redisstore.NewAccountSecurityStateStore(
		realtimeClient,
		presenceConnection,
	)
	accountSecurityRelay := redisstore.NewAccountSecurityRelay(realtimeClient)

	tickets, err := application.NewTicketService(
		redisstore.NewTicketStore(realtimeClient),
		accountSecurityAuthority,
		accountSecurityStore,
	)
	if err != nil {
		return err
	}
	hub, err := application.NewHub(
		redisstore.NewLeaseStore(realtimeClient),
		presenceConnection,
		redisstore.NewEventSource(messageTransport),
		accountSecurityAuthority,
		accountSecurityStore,
		accountSecurityRelay,
		nodeID,
		logger,
	)
	if err != nil {
		return err
	}
	if err := hub.StartAccountSecurityRelay(ctx); err != nil {
		return fmt.Errorf("account security relay startup failed: %w", err)
	}
	asm.Cleanups.Add(func(context.Context) error {
		hub.CloseAccountSecurityRelay()
		return nil
	})

	durableTransport, ok := messageTransport.(streamadapter.DurableMessageTransport)
	if !ok {
		return fmt.Errorf(
			"realtime message transport does not support durable account security consumption",
		)
	}
	accountSecurityConsumer, err := streamadapter.NewUserAccountSecurityConsumer(
		durableTransport,
		accountSecurityStore,
		accountSecurityRelay,
		hub,
		redisstore.NewAccountSecurityEventFailureStore(realtimeClient),
		"realtime-account-security-"+nodeID,
		logger,
		streamadapter.DefaultUserAccountSecurityConsumerConfig(),
	)
	if err != nil {
		return fmt.Errorf("account security consumer init failed: %w", err)
	}
	authorityTimeout := time.Duration(cfg.UserAccountSecurityAuthority.TimeoutMs) * time.Millisecond
	consumerSetupCtx, cancelConsumerSetup := context.WithTimeout(ctx, authorityTimeout)
	consumerSetupErr := accountSecurityConsumer.EnsureGroup(consumerSetupCtx)
	cancelConsumerSetup()
	if consumerSetupErr != nil {
		return fmt.Errorf("account security consumer group setup failed: %w", consumerSetupErr)
	}
	asm.Workers.Add(accountSecurityConsumer.Run)

	connectionHandler, err := httpadapter.NewHandler(
		tickets,
		hub,
		resumeReader,
		httpadapter.DefaultTransportConfig(),
	)
	if err != nil {
		return err
	}
	domainMux := http.NewServeMux()
	connectionHandler.Routes(domainMux)
	presencehttp.NewHandler(presenceQueries).Routes(domainMux)
	domainHandler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		domainMux,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/realtime/account-closure/dead-letters:recover",
			Module:   rterr.ModuleRealtime,
			Releaser: accountSecurityConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route: %w", err)
	}
	asm.Mux.Handle("/", domainHandler)

	// WebSocket 在 handler 内先消费一次性 ticket，注入可信 principal 后再
	// 执行同一 runtime operation contract；浏览器握手无需伪造 Bearer header，
	// 因此该路由挂在 operation guard 之外。
	upgradeHandler, err := wsadapter.NewHandler(
		tickets,
		hub,
		logger,
		operationsecurity.ForDomain("realtime"),
	)
	if err != nil {
		return err
	}
	asm.Unguarded().HandleFunc("GET /realtime/ws", upgradeHandler.HandleUpgrade)

	asm.Health.Register("realtime_redis", realtimeClient.Ping)
	asm.Health.Register("account_security_relay", func(context.Context) error {
		return hub.AccountSecurityRelayHealthy()
	})
	asm.Health.Register("user_account_security_consumer", func(context.Context) error {
		return accountSecurityConsumer.Healthy(10 * time.Second)
	})
	return nil
}

func failFastEnvironment(environment string) bool {
	switch strings.TrimSpace(environment) {
	case "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}
