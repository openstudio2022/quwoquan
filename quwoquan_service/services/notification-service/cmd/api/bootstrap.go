// Package bootstrap owns notification-service's private composition for
// servicehost.
package bootstrap

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicekit"
	httpadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/http"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	integrationclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/integration"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/persistence"
	realtimeclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/realtime"
	userclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/user"
	deliveryhttp "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/http"
	deliverystream "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/stream"
	deliveryapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	deliverymessaging "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/messaging"
	deliverypersistence "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/persistence"
)

const serviceName = "notification-service"

// consumerHealthWindow 是四个 stream consumer 与 outbox relay 的就绪判定窗口：
// 超过该时长没有推进即视为该投影链路失联。
const consumerHealthWindow = 10 * time.Second

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集
// 不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// NewModule performs fail-fast service-owned assembly. It does not bind a
// listener, start workers, manage signals or decide process exit status.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("notification"),
		AuthorityScopes:      []string{accountSecurityReadScope},
		// 外发推送目的地、presence 快照与投递载荷会进入 provider 调用的
		// input/output，KV 元数据一律不落盘。
		ObservabilityKVFilter: robs.NewKVMetadataFilter(nil),
		RetiredEnvKeys:        retiredEnvKeys(),
		SnapshotGuard:         snapshotGuard,
		ValidateConfig:        validateNotificationConfig,
		Assemble:              assembleNotificationDomain,
	})
}

func assembleNotificationDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	database := asm.MongoDB

	dependencyTimeout := time.Duration(cfg.Dependencies.TimeoutMS) * time.Millisecond
	integrationTimeout := time.Duration(cfg.IntegrationService.TimeoutMS) * time.Millisecond

	deliveryAdapter, pushDestinations, presenceReader, err := assembleOutboundDependencies(
		asm, cfg, integrationTimeout, dependencyTimeout,
	)
	if err != nil {
		return err
	}

	deliveryLifecycle := deliverypersistence.NewMongoAccountLifecycle(database)
	accountRestrictionStore, err := persistence.NewMongoUserAccountRestrictionProjection(
		database,
		deliveryLifecycle,
	)
	if err != nil {
		return fmt.Errorf("account restriction projection init failed: %w", err)
	}
	store := deliverypersistence.NewMongoNotificationDeliveryJobStore(
		database,
		accountRestrictionStore,
	)
	appMessageStore := persistence.NewMongoAppMessageStore(database)
	accountClosureStore, err := persistence.NewMongoUserAccountClosedProjection(
		database,
		deliveryLifecycle,
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed projection init failed: %w", err)
	}
	interactionFailures := persistence.NewMongoInteractionFailureStore(database)
	if err := ensureIndexes(
		ctx,
		"reliable-task",
		store.EnsureIndexes,
		appMessageStore.EnsureIndexes,
		deliveryLifecycle.EnsureIndexes,
		accountClosureStore.EnsureIndexes,
		accountRestrictionStore.EnsureIndexes,
	); err != nil {
		return err
	}
	if err := ensureIndexes(
		ctx, "interaction failure store", interactionFailures.EnsureIndexes,
	); err != nil {
		return err
	}
	_ = prometheus.Register(reliabletask.NewMetricsCollector(store))

	service, err := application.NewNotificationDeliveryService(
		store,
		deliveryAdapter,
		reliabletask.RateLimitPolicy{
			ClaimPerSecond:    cfg.Notification.Delivery.ClaimPerSecond,
			DispatchPerSecond: cfg.Notification.Delivery.DispatchPerSecond,
			RetryPerSecond:    cfg.Notification.Delivery.RetryPerSecond,
		},
	)
	if err != nil {
		return fmt.Errorf("notification delivery service init failed: %w", err)
	}
	appMessageCommands, err := application.NewAppMessageCommandFacade(
		appMessageStore,
		appMessageStore,
		store,
	)
	if err != nil {
		return fmt.Errorf("app message command facade init failed: %w", err)
	}
	accountClosureProjection, err := application.NewUserAccountClosedProjection(
		accountClosureStore,
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed application facet init failed: %w", err)
	}
	accountRestrictionProjection, err := application.NewUserAccountRestrictionProjection(
		accountRestrictionStore,
	)
	if err != nil {
		return fmt.Errorf("account restriction application facet init failed: %w", err)
	}

	messageTransport, err := requireNotificationAPIMessageTransport(
		ctx,
		cfg.Environment,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("notification message transport construction failed: %w", err)
	}
	if err := messageTransport.SetDurableRetention(
		ctx,
		deliverymessaging.NotificationDeliveryJobEventStream,
		deliverymessaging.NotificationDeliveryJobEventStreamRetention,
	); err != nil {
		return fmt.Errorf("NotificationDeliveryJob event stream retention setup failed: %w", err)
	}
	deliveryEventPublisher, err := deliverymessaging.NewEventPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("NotificationDeliveryJob event publisher init failed: %w", err)
	}
	deliveryOutboxRelay, err := deliveryapplication.NewOutboxRelay(
		store,
		deliveryEventPublisher,
		fmt.Sprintf(
			"notification-delivery-job-relay-%s-%d",
			asm.Identity.InstanceID,
			os.Getpid(),
		),
	)
	if err != nil {
		return fmt.Errorf("NotificationDeliveryJob outbox relay init failed: %w", err)
	}

	gatheringInvitations, err := application.NewGatheringInvitationProjection(appMessageStore)
	if err != nil {
		return fmt.Errorf("Gathering invitation projection init failed: %w", err)
	}
	interactionConsumer, err := streamadapter.NewInteractionNotificationConsumer(
		messageTransport,
		appMessageCommands,
		interactionFailures,
		cfg.Notification.Consumers.Interaction,
		slog.Default(),
		gatheringInvitations,
	)
	if err != nil {
		return fmt.Errorf("interaction notification consumer init failed: %w", err)
	}
	// chat 离线推送投影：presence 在线抑制 + push 投递作业（不落 inbox）。
	// kill-switch：关闭后降级为「仅在线接收」（message-reliability design §6）。
	if cfg.Notification.ChatOfflinePush.Enabled {
		chatOfflinePush, chatPushErr := application.NewChatOfflinePushProjectionHandler(
			presenceReader,
			store,
		)
		if chatPushErr != nil {
			return fmt.Errorf("chat offline push projection init failed: %w", chatPushErr)
		}
		interactionConsumer = interactionConsumer.WithChatOfflinePush(chatOfflinePush)
	}

	externalResultRecorder, err := deliveryapplication.NewExternalInteractionResultRecorder(store)
	if err != nil {
		return fmt.Errorf("external interaction result recorder init failed: %w", err)
	}
	externalResultConsumer, err := streamadapter.NewExternalInteractionResultConsumer(
		messageTransport,
		externalResultRecorder,
		interactionFailures,
		cfg.Notification.Consumers.ExternalInteractionResult,
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("external interaction result consumer init failed: %w", err)
	}
	if err := ensureConsumerGroup(
		ctx, "external interaction result", externalResultConsumer.EnsureGroup,
	); err != nil {
		return err
	}

	accountClosureConsumer, err := streamadapter.NewUserAccountClosedConsumer(
		messageTransport,
		accountClosureProjection,
		accountClosureStore,
		cfg.Notification.Consumers.AccountClosure,
		slog.Default(),
		streamadapter.DefaultUserAccountClosedConsumerConfig(),
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed consumer init failed: %w", err)
	}
	accountClosureConsumer.WithUserAccountRestrictionProjection(accountRestrictionProjection)
	if err := ensureConsumerGroup(
		ctx, "UserAccountClosed", accountClosureConsumer.EnsureGroup,
	); err != nil {
		return err
	}

	incomingPublisher, err := realtimeclient.NewIncomingCallPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("incoming call realtime publisher init failed: %w", err)
	}
	incomingCoordinator, err := deliveryapplication.NewIncomingCallDeliveryCoordinator(
		store,
		pushDestinations,
		presenceReader,
		incomingPublisher,
		deliveryAdapter,
		deliveryapplication.WithIncomingCallObserver(registerIncomingCallMetrics()),
	)
	if err != nil {
		return fmt.Errorf("incoming call coordinator init failed: %w", err)
	}
	rtcConsumer, err := deliverystream.NewRTCIncomingCallConsumer(
		messageTransport,
		incomingCoordinator,
		cfg.Notification.Consumers.IncomingCall,
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("rtc incoming call consumer init failed: %w", err)
	}

	if err := registerNotificationRoutes(
		asm, appMessageStore, appMessageCommands, store, incomingCoordinator, accountClosureConsumer,
	); err != nil {
		return err
	}

	asm.Health.Register("interaction-consumer", func(context.Context) error {
		return interactionConsumer.Healthy(consumerHealthWindow)
	})
	asm.Health.Register("account-closure-consumer", func(context.Context) error {
		return accountClosureConsumer.Healthy(consumerHealthWindow)
	})
	asm.Health.Register("rtc-consumer", func(context.Context) error {
		return rtcConsumer.Healthy(consumerHealthWindow)
	})
	asm.Health.Register("external-result-consumer", func(context.Context) error {
		return externalResultConsumer.Healthy(consumerHealthWindow)
	})
	asm.Health.Register("delivery-outbox-relay", func(context.Context) error {
		return deliveryOutboxRelay.Healthy(consumerHealthWindow)
	})

	asm.Workers.Add(func(workerCtx context.Context) {
		if err := deliveryOutboxRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
			slog.Error("NotificationDeliveryJob outbox relay stopped", "err", err)
		}
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		interactionConsumer.Run(workerCtx, 250*time.Millisecond)
	})
	asm.Workers.Add(externalResultConsumer.Run)
	asm.Workers.Add(accountClosureConsumer.Run)
	asm.Workers.Add(func(workerCtx context.Context) {
		rtcConsumer.Run(workerCtx, 100*time.Millisecond)
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		runWorkerLoop(workerCtx, service)
	})
	asm.Workers.Add(func(workerCtx context.Context) {
		runIncomingCallWorkerLoop(workerCtx, incomingCoordinator)
	})
	return nil
}

// assembleOutboundDependencies 装配三条出站依赖：integration 投递、user 推送
// 目的地与 realtime presence。三者共用同一 access token 配置派生的最小 scope
// 服务凭据，且都关闭 HTTP 层重试——重投由 reliable-task 的投递作业承担，客户端
// 重试会让同一条通知重复外发。
func assembleOutboundDependencies(
	asm *servicekit.Assembly,
	cfg *config,
	integrationTimeout time.Duration,
	dependencyTimeout time.Duration,
) (
	*integrationclient.ExternalInteractionDeliveryAdapter,
	*userclient.PushDestinationClient,
	*realtimeclient.PresenceClient,
	error,
) {
	integrationClient := newObservedClient(
		asm, integrationTimeout, "notification-service.integration-delivery",
	)
	userHTTPClient := newObservedClient(
		asm, dependencyTimeout, "notification-service.user-push-destinations",
	)
	realtimeHTTPClient := newObservedClient(
		asm, dependencyTimeout, "notification-service.realtime-presence",
	)

	userCredentials, err := asm.Auth.ServiceCredentials("user.push_destination.read")
	if err != nil {
		return nil, nil, nil, err
	}
	pushDestinations, err := userclient.NewPushDestinationClient(
		userclient.PushDestinationClientConfig{
			BaseURL:     cfg.UserService.BaseURL,
			Credentials: userCredentials,
			Timeout:     dependencyTimeout,
		},
		userHTTPClient,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("user push destination client init failed: %w", err)
	}

	integrationCredentials, err := asm.Auth.ServiceCredentials(
		"integration.external_interaction.submit",
	)
	if err != nil {
		return nil, nil, nil, err
	}
	deliveryAdapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     cfg.IntegrationService.BaseURL,
			Credentials: integrationCredentials,
			Environment: cfg.Environment,
			Timeout:     integrationTimeout,
		},
		integrationClient,
		pushDestinations,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("integration delivery adapter init failed: %w", err)
	}

	realtimeCredentials, err := asm.Auth.ServiceCredentials("realtime.presence.read")
	if err != nil {
		return nil, nil, nil, err
	}
	presenceReader, err := realtimeclient.NewPresenceClient(
		realtimeclient.PresenceClientConfig{
			BaseURL:     cfg.RealtimeGateway.BaseURL,
			Credentials: realtimeCredentials,
			Timeout:     dependencyTimeout,
		},
		realtimeHTTPClient,
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("realtime presence client init failed: %w", err)
	}
	return deliveryAdapter, pushDestinations, presenceReader, nil
}

func newObservedClient(
	asm *servicekit.Assembly,
	timeout time.Duration,
	sourceID string,
) *http.Client {
	factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
	factoryCfg.Timeout = timeout
	factoryCfg.MaxRetries = -1
	factoryCfg.RetryBackoff = -1
	factoryCfg.RetryOnCodes = map[int]struct{}{}
	return rthttp.NewObservedHTTPClient(
		nil,
		factoryCfg,
		rthttp.HTTPClientMiddlewareConfig{
			Service:           serviceName,
			Origin:            "cloud",
			Direction:         robs.DirectionOutbound,
			SourceID:          sourceID,
			Src:               serviceName,
			ServiceName:       serviceName,
			ServiceInstanceID: asm.Identity.InstanceID,
		},
		asm.Observability.IOLogger,
		asm.Observability.ProcessLogger,
		asm.Observability.ExceptionLogger,
	)
}

// registerNotificationRoutes 把领域路由与运营专用的死信恢复路由组装成同一个
// 入站面。恢复路由挂在领域 mux 之内，因此仍受 generated operation guard 管辖。
func registerNotificationRoutes(
	asm *servicekit.Assembly,
	appMessageStore *persistence.MongoAppMessageStore,
	appMessageCommands *application.AppMessageCommandFacade,
	store *deliverypersistence.MongoNotificationDeliveryJobStore,
	incomingCoordinator *deliveryapplication.IncomingCallDeliveryCoordinator,
	accountClosureConsumer runtimemessaging.DeadLetterReleaser,
) error {
	appMessageQueries, err := application.NewAppMessageQueryFacade(
		appMessageStore,
		appMessageStore,
		appMessageStore,
	)
	if err != nil {
		return fmt.Errorf("app message query facade init failed: %w", err)
	}
	deliveryQueries, err := deliveryapplication.NewNotificationDeliveryJobQueryFacade(
		store, store, store,
	)
	if err != nil {
		return fmt.Errorf("notification delivery query facade init failed: %w", err)
	}
	deliveryCommands, err := deliveryapplication.NewNotificationDeliveryJobCommandFacade(store)
	if err != nil {
		return fmt.Errorf("notification delivery command facade init failed: %w", err)
	}
	handler, err := httpadapter.NewHandler(httpadapter.HandlerDependencies{
		AppMessageCommands: appMessageCommands,
		AppMessageQueries:  appMessageQueries,
	})
	if err != nil {
		return fmt.Errorf("notification http handler init failed: %w", err)
	}
	deliveryHandler, err := deliveryhttp.NewHandler(deliveryCommands, deliveryQueries)
	if err != nil {
		return fmt.Errorf("notification delivery http handler init failed: %w", err)
	}
	deliveryHandler.WithIncomingCallCoordinator(incomingCoordinator)

	serviceMux := http.NewServeMux()
	handler.RegisterRoutes(serviceMux)
	deliveryHandler.RegisterRoutes(serviceMux)
	serviceHandler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		serviceMux,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/notification/account-closure/dead-letters:recover",
			Module:   rterr.ModuleNotification,
			Releaser: accountClosureConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route: %w", err)
	}
	asm.Mux.Handle("/", serviceHandler)
	return nil
}

func ensureIndexes(
	ctx context.Context,
	label string,
	ensures ...func(context.Context) error,
) error {
	indexCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	for _, ensure := range ensures {
		if err := ensure(indexCtx); err != nil {
			return fmt.Errorf("%s EnsureIndexes failed: %w", label, err)
		}
	}
	return nil
}

func ensureConsumerGroup(
	ctx context.Context,
	label string,
	ensure func(context.Context) error,
) error {
	setupCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if err := ensure(setupCtx); err != nil {
		return fmt.Errorf("%s consumer group setup failed: %w", label, err)
	}
	return nil
}

func runWorkerLoop(ctx context.Context, service *application.NotificationDeliveryService) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for i := 0; i < 100; i++ {
				processed, err := service.ProcessOne(ctx)
				if err != nil {
					log.Printf("notification delivery worker failed: %v", err)
					break
				}
				if !processed {
					break
				}
			}
		}
	}
}

func runIncomingCallWorkerLoop(
	ctx context.Context,
	coordinator *deliveryapplication.IncomingCallDeliveryCoordinator,
) {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for i := 0; i < 100; i++ {
				processed, err := coordinator.ProcessDue(ctx)
				if err != nil {
					log.Printf("notification incoming call worker failed: %v", err)
					break
				}
				if !processed {
					break
				}
			}
		}
	}
}

type incomingCallMetrics struct {
	transitions *prometheus.CounterVec
	acks        *prometheus.CounterVec
}

func registerIncomingCallMetrics() *incomingCallMetrics {
	metrics := &incomingCallMetrics{
		transitions: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "notification_incoming_call_transitions_total",
				Help: "Incoming call delivery job transitions.",
			},
			[]string{"from_status", "to_status", "outcome"},
		),
		acks: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "notification_incoming_call_presentation_ack_total",
				Help: "Incoming call presentation ACK outcomes.",
			},
			[]string{"raced"},
		),
	}
	_ = prometheus.Register(metrics.transitions)
	_ = prometheus.Register(metrics.acks)
	return metrics
}

func (m *incomingCallMetrics) RecordIncomingCallTransition(
	fromStatus string,
	toStatus string,
	outcome string,
) {
	m.transitions.WithLabelValues(fromStatus, toStatus, outcome).Inc()
}

func (m *incomingCallMetrics) RecordIncomingCallAck(raced bool) {
	m.acks.WithLabelValues(strconv.FormatBool(raced)).Inc()
}
