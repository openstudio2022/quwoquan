// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	rtredis "quwoquan_service/runtime/redis"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

// TestAssistantSessionSkillSubscriptionService validates the contract at the public assistant application boundary.
func TestSkillSubscriptionServiceApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}

type proactiveDeliveryPolicyReader struct {
	policy ports.AssistantDeliveryPolicy
	err    error
	calls  int
}

func (r *proactiveDeliveryPolicyReader) ResolveAssistantDeliveryPolicy(
	context.Context,
	string,
) (ports.AssistantDeliveryPolicy, error) {
	r.calls++
	return r.policy, r.err
}

type proactiveNotificationWriter struct {
	commands []ports.NotificationAppMessageCommand
	failures int
}

func (w *proactiveNotificationWriter) CreateAppMessage(
	_ context.Context,
	command ports.NotificationAppMessageCommand,
) (ports.NotificationAppMessageReceipt, error) {
	w.commands = append(w.commands, command)
	if w.failures > 0 {
		w.failures--
		return ports.NotificationAppMessageReceipt{}, errors.New(
			"notification transport unavailable",
		)
	}
	return ports.NotificationAppMessageReceipt{
		MessageID: "message-" + command.IdempotencyKey,
	}, nil
}

type proactiveSkillRuntime struct{}

func (proactiveSkillRuntime) SelectSkill(
	context.Context,
	assistant.AssistantTurn,
) (runorchestration.SkillSelection, error) {
	return runorchestration.SkillSelection{
		SkillID:     "news_briefing",
		DomainID:    "assistant",
		DisplayName: "资讯简报",
	}, nil
}

type proactiveFinalModel struct{}

func (proactiveFinalModel) ModelExecutionCapabilities() runorchestration.ModelExecutionCapabilities {
	return durableTestModelCapabilities()
}

func (proactiveFinalModel) Complete(
	context.Context,
	runorchestration.ModelRequest,
) (runorchestration.ModelResponse, error) {
	return runorchestration.ModelResponse{Text: "主动订阅结果"}, nil
}

func newProactiveDeliveryService(
	t *testing.T,
	store subscriptionports.Store,
	cache rtredis.Client,
	policy *proactiveDeliveryPolicyReader,
	notification *proactiveNotificationWriter,
	options ...sessionorchestration.AssistantServiceOption,
) *sessionorchestration.AssistantService {
	loop := runorchestration.NewAgentLoop(
		proactiveSkillRuntime{},
		runorchestration.ReactRuntime{
			Model: proactiveFinalModel{},
			Tools: canonicalTestToolCoordinator(nil),
		},
		func() time.Time { return time.Now().UTC() },
	)
	loop.Catalog = skillfixture.Loader{}
	loop.PromptAssets = promptassets.MustResolver(t)
	runRuntime := assistantruntest.NewMemoryRuntime()
	runCommands := runruntime.NewCommandService(
		runRuntime,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(testRunPolicyResolver()),
	)
	runWorker := runruntime.NewDurableWorker(
		runRuntime,
		runRuntime,
		runorchestration.NewDurableRunExecutor(loop),
		"local-contract-proactive-worker",
	)
	workerContext, cancelWorker := context.WithTimeout(
		context.Background(),
		10*time.Second,
	)
	go func() {
		defer cancelWorker()
		runWorker.Run(workerContext)
	}()
	baseOptions := []sessionorchestration.AssistantServiceOption{
		sessionorchestration.WithSkillSubscriptionStore(store),
		sessionorchestration.WithAssistantDeliveryPolicyReader(policy),
		sessionorchestration.WithNotificationAppMessageCommandWriter(notification),
		sessionorchestration.WithSessionStore(
			persistence.NewMemorySessionStore(),
		),
		sessionorchestration.WithSkillCatalog(skillfixture.Loader{}),
		sessionorchestration.WithRunCommandService(runCommands),
	}
	baseOptions = append(baseOptions, options...)
	return sessionorchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		cache,
		baseOptions...,
	)
}

func proactiveSubscription(
	id string,
	cron string,
) skillmodel.SkillSubscription {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	return skillmodel.SkillSubscription{
		SubscriptionID: id,
		Owner: skillmodel.SkillSubscriptionOwner{
			OwnerType: "user",
			OwnerID:   "account-proactive",
		},
		CreatedByUserID:    "account-proactive",
		CreatedByPersonaID: "persona-proactive",
		SkillID:            "news_briefing",
		SearchQueryPlan: skillmodel.SkillSubscriptionSearchQueryPlan{
			RawText: "请生成本期订阅简报",
		},
		Status: skillmodel.SkillSubscriptionStatusActive,
		Trigger: skillmodel.SkillSubscriptionTrigger{
			Type:     "cron",
			Cron:     cron,
			Timezone: "UTC",
		},
		Destination: skillmodel.SkillSubscriptionDestination{
			DestinationType:  "user",
			DestinationID:    "account-proactive",
			MaxPerDay:        1,
			CooldownMinutes:  60,
			QuietHoursPolicy: "inherit_user_setting",
		},
		CreatedAt: now,
		UpdatedAt: now,
	}
}

func allowProactiveDeliveryPolicy() ports.AssistantDeliveryPolicy {
	return ports.AssistantDeliveryPolicy{
		UserID:           "account-proactive",
		AssistantEnabled: true,
		Version:          1,
	}
}

func TestSkillSubscriptionCreationAuthorizesDestination(
	t *testing.T,
) {
	newCommands := func(
		membershipCurrent bool,
	) *subscriptionapplication.UseCases {
		return subscriptionapplication.NewUseCases(
			subscriptionpersistence.NewMemoryStore(),
			&assistantSessionChatMentionServiceFakeChatGroundingClient{
				membershipDenied: !membershipCurrent,
			},
			nil,
			time.Now,
		)
	}
	input := func() skillmodel.CreateSkillSubscriptionInput {
		return skillmodel.CreateSkillSubscriptionInput{
			SkillID:            "news_briefing",
			DomainID:           "news",
			CreatedByPersonaID: "persona-proactive",
			ClientRequestID:    "request-destination",
			Trigger: skillmodel.SkillSubscriptionTrigger{
				Type:     "cron",
				Cron:     "30 8 * * *",
				Timezone: "UTC",
			},
			Destination: skillmodel.SkillSubscriptionDestination{
				DestinationType:  "chat_conversation",
				DestinationID:    "conv-1",
				MaxPerDay:        1,
				CooldownMinutes:  60,
				QuietHoursPolicy: "inherit_user_setting",
			},
		}
	}

	t.Run("user destination cannot target another account", func(t *testing.T) {
		request := input()
		request.Destination.DestinationType = "user"
		request.Destination.DestinationID = "another-account"
		if _, err := newCommands(true).Create(
			t.Context(),
			"account-proactive",
			request,
		); err == nil {
			t.Fatal("user destination outside owner account must be rejected")
		}
	})

	t.Run("chat conversation destination requires creator persona", func(t *testing.T) {
		request := input()
		request.CreatedByPersonaID = ""
		if _, err := newCommands(true).Create(
			t.Context(),
			"account-proactive",
			request,
		); err == nil {
			t.Fatal("chat conversation destination without creator persona must fail")
		}
	})

	t.Run("creator and assistant membership are both required", func(t *testing.T) {
		for _, name := range []string{"creator removed", "assistant removed"} {
			t.Run(name, func(t *testing.T) {
				if _, err := newCommands(false).Create(
					t.Context(),
					"account-proactive",
					input(),
				); err == nil {
					t.Fatal("incomplete destination membership must fail closed")
				}
			})
		}
	})

	t.Run("current creator and assistant membership permit creation", func(t *testing.T) {
		created, err := newCommands(true).Create(
			t.Context(),
			"account-proactive",
			input(),
		)
		if err != nil {
			t.Fatal(err)
		}
		if created.CreatedByPersonaID != "persona-proactive" {
			t.Fatalf("creator persona audit coordinate drifted: %+v", created)
		}
	})
}

func TestSkillSubscriptionDeliveryIsIdempotentAndPersistsAuditState(
	t *testing.T,
) {
	store := subscriptionpersistence.NewMemoryStore()
	subscription := proactiveSubscription("subscription-success", "30 8 * * *")
	store.SeedSkillSubscription(subscription)
	cache := rtredis.NewMemoryClient()
	policy := &proactiveDeliveryPolicyReader{
		policy: allowProactiveDeliveryPolicy(),
	}
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		t,
		store,
		cache,
		policy,
		notification,
	)
	now := time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC)

	first, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: now.Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatalf("首次投递失败: %v", err)
	}
	second, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: now.Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatalf("同窗口重放失败: %v", err)
	}
	if first.ProcessedCount != 1 ||
		second.ProcessedCount != 0 ||
		len(notification.commands) != 1 {
		t.Fatalf(
			"租约幂等漂移: first=%+v second=%+v commands=%d",
			first,
			second,
			len(notification.commands),
		)
	}
	stored, err := store.GetSkillSubscription(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
	)
	if err != nil {
		t.Fatal(err)
	}
	if stored.DeliveryState.LastDeliveredAt == nil ||
		stored.DeliveryState.NextAttemptAt == nil ||
		!stored.DeliveryState.NextAttemptAt.After(now) ||
		stored.DeliveryState.PendingDeliveryID != "" ||
		stored.DeliveryState.ConsecutiveFailures != 0 {
		t.Fatalf("成功投递审计状态不完整: %+v", stored.DeliveryState)
	}
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatal(err)
	}
	observed := map[string]bool{}
	for _, family := range families {
		observed[family.GetName()] = true
	}
	for _, metric := range []string{
		"assistant_subscription_delivery_attempt_total",
		"assistant_subscription_cron_tick_total",
	} {
		if !observed[metric] {
			t.Fatalf("主动投递商用指标 %s 未注册", metric)
		}
	}
}

func TestSkillSubscriptionDeliveryRecoversAWhileSchedulerWasDown(
	t *testing.T,
) {
	store := subscriptionpersistence.NewMemoryStore()
	subscription := proactiveSubscription(
		"subscription-missed-window",
		"30 8 * * *",
	)
	scheduledAt := time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC)
	subscription.DeliveryState.NextAttemptAt = &scheduledAt
	store.SeedSkillSubscription(subscription)
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		t,
		store,
		rtredis.NewMemoryClient(),
		&proactiveDeliveryPolicyReader{
			policy: allowProactiveDeliveryPolicy(),
		},
		notification,
	)
	result, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: scheduledAt.Add(7 * time.Minute).Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.ProcessedCount != 1 ||
		len(notification.commands) != 1 ||
		notification.commands[0].IdempotencyKey !=
			"assistant-proactive-subscription-missed-window-202607240830:"+
				"notification" {
		t.Fatalf(
			"调度停机窗口未按原 deliveryId 补偿: result=%+v commands=%+v",
			result,
			notification.commands,
		)
	}
}

func TestPausedSkillSubscriptionClearsPendingAndReactivationReschedules(
	t *testing.T,
) {
	store := subscriptionpersistence.NewMemoryStore()
	subscription := proactiveSubscription(
		"subscription-status",
		"* * * * *",
	)
	pendingAt := time.Now().UTC().Add(-time.Minute)
	subscription.DeliveryState.PendingDeliveryID = "delivery-before-pause"
	subscription.DeliveryState.NextAttemptAt = &pendingAt
	subscription.DeliveryState.ConsecutiveFailures = 2
	store.SeedSkillSubscription(subscription)
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		t,
		store,
		rtredis.NewMemoryClient(),
		&proactiveDeliveryPolicyReader{
			policy: allowProactiveDeliveryPolicy(),
		},
		notification,
	)
	commands := subscriptionapplication.NewUseCases(store, nil, service, time.Now)
	paused, err := commands.UpdateStatus(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
		skillmodel.UpdateSkillSubscriptionStatusInput{
			Status:          skillmodel.SkillSubscriptionStatusPaused,
			ClientRequestID: "pause-subscription-status",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if paused.DeliveryState.PendingDeliveryID != "" ||
		paused.DeliveryState.NextAttemptAt != nil ||
		paused.DeliveryState.ConsecutiveFailures != 0 {
		t.Fatalf("暂停后投递状态未清理: %+v", paused.DeliveryState)
	}
	result, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: time.Now().UTC().Add(time.Hour).Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.ProcessedCount != 0 || len(notification.commands) != 0 {
		t.Fatalf("暂停订阅仍被投递: result=%+v", result)
	}
	active, err := commands.UpdateStatus(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
		skillmodel.UpdateSkillSubscriptionStatusInput{
			Status:          skillmodel.SkillSubscriptionStatusActive,
			ClientRequestID: "reactivate-subscription-status",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if active.DeliveryState.NextAttemptAt == nil ||
		!active.DeliveryState.NextAttemptAt.After(active.UpdatedAt) {
		t.Fatalf("恢复订阅未重新调度: %+v", active.DeliveryState)
	}
}

func TestSkillSubscriptionDeliveryHonorsGlobalSwitchQuietHoursAndDailyLimit(
	t *testing.T,
) {
	tests := []struct {
		name   string
		policy ports.AssistantDeliveryPolicy
		now    time.Time
	}{
		{
			name: "global assistant disabled",
			policy: ports.AssistantDeliveryPolicy{
				UserID:           "account-proactive",
				AssistantEnabled: false,
				Version:          1,
			},
			now: time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC),
		},
		{
			name: "cross-midnight quiet hours",
			policy: func() ports.AssistantDeliveryPolicy {
				start := 22 * time.Hour
				end := 7 * time.Hour
				return ports.AssistantDeliveryPolicy{
					UserID:           "account-proactive",
					AssistantEnabled: true,
					QuietHoursStart:  &start,
					QuietHoursEnd:    &end,
					Version:          1,
				}
			}(),
			now: time.Date(2026, 7, 24, 23, 30, 0, 0, time.UTC),
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := subscriptionpersistence.NewMemoryStore()
			subscription := proactiveSubscription(
				"subscription-"+test.name,
				"* * * * *",
			)
			store.SeedSkillSubscription(subscription)
			notification := &proactiveNotificationWriter{}
			service := newProactiveDeliveryService(
				t,
				store,
				rtredis.NewMemoryClient(),
				&proactiveDeliveryPolicyReader{policy: test.policy},
				notification,
			)
			result, err := service.TickSkillSubscriptionCron(
				t.Context(),
				skillmodel.SkillSubscriptionCronTickInput{
					Now: test.now.Format(time.RFC3339),
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			if result.SuppressedCount != 1 ||
				result.ProcessedCount != 0 ||
				len(notification.commands) != 0 {
				t.Fatalf(
					"业务门控未在副作用前抑制: result=%+v commands=%d",
					result,
					len(notification.commands),
				)
			}
		})
	}

	store := subscriptionpersistence.NewMemoryStore()
	subscription := proactiveSubscription("subscription-daily-limit", "* * * * *")
	store.SeedSkillSubscription(subscription)
	cache := rtredis.NewMemoryClient()
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		t,
		store,
		cache,
		&proactiveDeliveryPolicyReader{
			policy: allowProactiveDeliveryPolicy(),
		},
		notification,
	)
	firstAt := time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC)
	if result, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: firstAt.Format(time.RFC3339),
		},
	); err != nil || result.ProcessedCount != 1 {
		t.Fatalf("首次日配额投递失败: result=%+v err=%v", result, err)
	}
	secondAt := firstAt.Add(61 * time.Minute)
	result, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: secondAt.Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.SuppressedCount != 1 || len(notification.commands) != 1 {
		t.Fatalf(
			"日频控失效: result=%+v commands=%d",
			result,
			len(notification.commands),
		)
	}
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, family := range families {
		if family.GetName() ==
			"assistant_subscription_delivery_suppressed_total" {
			return
		}
	}
	t.Fatal("主动投递抑制指标未注册")
}

func TestSkillSubscriptionDeliveryRetriesWithStableIdempotencyCoordinates(
	t *testing.T,
) {
	store := subscriptionpersistence.NewMemoryStore()
	subscription := proactiveSubscription("subscription-retry", "* * * * *")
	store.SeedSkillSubscription(subscription)
	cache := rtredis.NewMemoryClient()
	notification := &proactiveNotificationWriter{failures: 1}
	service := newProactiveDeliveryService(
		t,
		store,
		cache,
		&proactiveDeliveryPolicyReader{
			policy: allowProactiveDeliveryPolicy(),
		},
		notification,
	)
	firstAt := time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC)
	failed, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: firstAt.Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if failed.FailedCount != 1 || len(notification.commands) != 1 {
		t.Fatalf("失败审计缺失: result=%+v", failed)
	}
	stored, err := store.GetSkillSubscription(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
	)
	if err != nil {
		t.Fatal(err)
	}
	deliveryID := stored.DeliveryState.PendingDeliveryID
	if deliveryID == "" ||
		stored.DeliveryState.ConsecutiveFailures != 1 ||
		stored.DeliveryState.LastErrorCode == "" {
		t.Fatalf("失败补偿坐标未持久化: %+v", stored.DeliveryState)
	}
	if err := cache.Del(
		t.Context(),
		"assistant:subscription:lease:"+
			subscription.SubscriptionID+":"+deliveryID,
	); err != nil {
		t.Fatal(err)
	}
	retried, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{
			Now: firstAt.Add(5 * time.Minute).Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if retried.ProcessedCount != 1 ||
		len(notification.commands) != 2 ||
		notification.commands[0].IdempotencyKey !=
			notification.commands[1].IdempotencyKey {
		t.Fatalf(
			"失败重试未复用稳定幂等坐标: result=%+v commands=%+v",
			retried,
			notification.commands,
		)
	}
	stored, err = store.GetSkillSubscription(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
	)
	if err != nil {
		t.Fatal(err)
	}
	if stored.DeliveryState.PendingDeliveryID != "" ||
		stored.DeliveryState.ConsecutiveFailures != 0 ||
		stored.DeliveryState.LastDeliveredAt == nil {
		t.Fatalf("重试成功后状态未收敛: %+v", stored.DeliveryState)
	}
}

func TestSkillSubscriptionDeliveryFailsClosedForConsentAndGroupMembership(
	t *testing.T,
) {
	t.Run("sensitive skill consent revoked", func(t *testing.T) {
		store := subscriptionpersistence.NewMemoryStore()
		subscription := proactiveSubscription(
			"subscription-consent",
			"* * * * *",
		)
		subscription.SkillID = "travel_companion"
		subscription.DomainID = "travel"
		store.SeedSkillSubscription(subscription)
		notification := &proactiveNotificationWriter{}
		service := newProactiveDeliveryService(
			t,
			store,
			rtredis.NewMemoryClient(),
			&proactiveDeliveryPolicyReader{
				policy: allowProactiveDeliveryPolicy(),
			},
			notification,
			sessionorchestration.WithSkillCatalog(skillfixture.StaticLoader{
				Manifests: []skillpkg.Manifest{{
					SkillID: "travel_companion",
					ContextProfile: skillpkg.ContextProfile{
						ProfileID: "context.travel_companion.required_test",
						Requirements: []skillpkg.ContextRequirement{{
							SlotID:        "trip_context",
							Required:      true,
							ConsentScopes: []string{"assistant.learning.feedback_context.read"},
						}},
					},
				}},
			}),
		)
		result, err := service.TickSkillSubscriptionCron(
			t.Context(),
			skillmodel.SkillSubscriptionCronTickInput{
				Now: time.Date(
					2026,
					7,
					24,
					8,
					30,
					0,
					0,
					time.UTC,
				).Format(time.RFC3339),
			},
		)
		if err != nil {
			t.Fatal(err)
		}
		if result.SuppressedCount != 1 ||
			len(notification.commands) != 0 {
			t.Fatalf(
				"撤权后仍跨越投递边界: result=%+v commands=%d",
				result,
				len(notification.commands),
			)
		}
	})

	t.Run("destination membership revoked", func(t *testing.T) {
		for _, name := range []string{"assistant removed", "creator removed"} {
			t.Run(name, func(t *testing.T) {
				store := subscriptionpersistence.NewMemoryStore()
				subscription := proactiveSubscription(
					"subscription-membership-"+name,
					"* * * * *",
				)
				subscription.Destination.DestinationType = "chat_conversation"
				subscription.Destination.DestinationID = "conv-1"
				subscription.SkillID = "news_briefing"
				store.SeedSkillSubscription(subscription)
				chat := &assistantSessionChatMentionServiceFakeChatGroundingClient{
					membershipDenied: true,
				}
				service := newProactiveDeliveryService(
					t,
					store,
					rtredis.NewMemoryClient(),
					&proactiveDeliveryPolicyReader{
						policy: allowProactiveDeliveryPolicy(),
					},
					&proactiveNotificationWriter{},
					sessionorchestration.WithChatGroundingClient(chat),
				)
				result, err := service.TickSkillSubscriptionCron(
					t.Context(),
					skillmodel.SkillSubscriptionCronTickInput{
						Now: time.Date(
							2026,
							7,
							24,
							8,
							30,
							0,
							0,
							time.UTC,
						).Format(time.RFC3339),
					},
				)
				if err != nil {
					t.Fatal(err)
				}
				if result.SuppressedCount != 1 ||
					chat.listMessagesCalled ||
					len(chat.sent) != 0 {
					t.Fatalf(
						"已撤销成员资格仍跨越投递边界: result=%+v chat=%+v",
						result,
						chat,
					)
				}
			})
		}
	})

	t.Run("current creator and assistant membership delivers to chat", func(t *testing.T) {
		store := subscriptionpersistence.NewMemoryStore()
		subscription := proactiveSubscription(
			"subscription-membership-current",
			"* * * * *",
		)
		subscription.Destination.DestinationType = "chat_conversation"
		subscription.Destination.DestinationID = "conv-1"
		store.SeedSkillSubscription(subscription)
		chat := &assistantSessionChatMentionServiceFakeChatGroundingClient{}
		result, err := newProactiveDeliveryService(
			t,
			store,
			rtredis.NewMemoryClient(),
			&proactiveDeliveryPolicyReader{
				policy: allowProactiveDeliveryPolicy(),
			},
			&proactiveNotificationWriter{},
			sessionorchestration.WithChatGroundingClient(chat),
		).TickSkillSubscriptionCron(
			t.Context(),
			skillmodel.SkillSubscriptionCronTickInput{
				Now: time.Date(
					2026,
					7,
					24,
					8,
					30,
					0,
					0,
					time.UTC,
				).Format(time.RFC3339),
			},
		)
		if err != nil {
			t.Fatal(err)
		}
		if result.ProcessedCount != 1 || len(chat.sent) != 1 {
			t.Fatalf(
				"有效会话成员未收到唯一投递: result=%+v chat=%+v",
				result,
				chat,
			)
		}
	})
}
