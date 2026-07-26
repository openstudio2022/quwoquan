// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

// TestMigratedSkillSubscriptionService retains the contract at the public assistant application boundary.
func TestMigratedSkillSubscriptionServiceApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}

type proactiveDeliveryPolicyReader struct {
	policy application.AssistantDeliveryPolicy
	err    error
	calls  int
}

func (r *proactiveDeliveryPolicyReader) ResolveAssistantDeliveryPolicy(
	context.Context,
	string,
) (application.AssistantDeliveryPolicy, error) {
	r.calls++
	return r.policy, r.err
}

type proactiveNotificationWriter struct {
	commands []application.NotificationAppMessageCommand
	failures int
}

func (w *proactiveNotificationWriter) CreateAppMessage(
	_ context.Context,
	command application.NotificationAppMessageCommand,
) (application.NotificationAppMessageReceipt, error) {
	w.commands = append(w.commands, command)
	if w.failures > 0 {
		w.failures--
		return application.NotificationAppMessageReceipt{}, errors.New(
			"notification transport unavailable",
		)
	}
	return application.NotificationAppMessageReceipt{
		MessageID: "message-" + command.IdempotencyKey,
	}, nil
}

type proactiveSkillRuntime struct{}

func (proactiveSkillRuntime) SelectSkill(
	context.Context,
	assistant.AssistantTurn,
) (application.SkillSelection, error) {
	return application.SkillSelection{
		SkillID:     "news_briefing",
		DomainID:    "assistant",
		DisplayName: "资讯简报",
	}, nil
}

type proactiveFinalModel struct{}

func (proactiveFinalModel) Complete(
	context.Context,
	application.ModelRequest,
) (application.ModelResponse, error) {
	return application.ModelResponse{Text: "主动订阅结果"}, nil
}

func newProactiveDeliveryService(
	store application.SkillSubscriptionStore,
	cache rtredis.Client,
	policy *proactiveDeliveryPolicyReader,
	notification *proactiveNotificationWriter,
	options ...application.AssistantServiceOption,
) *application.AssistantService {
	loop := application.NewAgentLoop(
		proactiveSkillRuntime{},
		application.ReactRuntime{Model: proactiveFinalModel{}},
		func() time.Time { return time.Now().UTC() },
	)
	options = append(
		options,
		application.WithSkillSubscriptionStore(store),
		application.WithAssistantDeliveryPolicyReader(policy),
		application.WithNotificationAppMessageCommandWriter(notification),
		application.WithConversationRunStore(
			persistence.NewMemoryConversationRunStore(),
		),
		application.WithAgentLoop(loop),
	)
	return application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		cache,
		options...,
	)
}

func proactiveSubscription(
	id string,
	cron string,
) assistant.SkillSubscription {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	return assistant.SkillSubscription{
		SubscriptionID: id,
		Owner: assistant.SkillSubscriptionOwner{
			OwnerType: "user",
			OwnerID:   "account-proactive",
		},
		CreatedByUserID:    "account-proactive",
		CreatedByPersonaID: "persona-proactive",
		SkillID:            "news_briefing",
		Status:             assistant.SkillSubscriptionStatusActive,
		Trigger: assistant.SkillSubscriptionTrigger{
			Type: "cron",
			Cron: cron,
		},
		Destination: assistant.SkillSubscriptionDestination{
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

func allowProactiveDeliveryPolicy() application.AssistantDeliveryPolicy {
	return application.AssistantDeliveryPolicy{
		UserID:           "account-proactive",
		AssistantEnabled: true,
		Version:          1,
	}
}

func TestSkillSubscriptionCreationAuthorizesDestination(
	t *testing.T,
) {
	newService := func(
		membershipCurrent bool,
	) *application.AssistantService {
		return newProactiveDeliveryService(
			persistence.NewMemorySkillSubscriptionStore(),
			rtredis.NewMemoryClient(),
			&proactiveDeliveryPolicyReader{
				policy: allowProactiveDeliveryPolicy(),
			},
			&proactiveNotificationWriter{},
			application.WithChatGroundingClient(
				&migratedChatMentionServiceFakeChatGroundingClient{
					membershipDenied: !membershipCurrent,
				},
			),
		)
	}
	input := func() assistant.CreateSkillSubscriptionInput {
		return assistant.CreateSkillSubscriptionInput{
			SkillID:            "news_briefing",
			CreatedByPersonaID: "persona-proactive",
			ClientRequestID:    "request-destination",
			Trigger: assistant.SkillSubscriptionTrigger{
				Type: "cron",
				Cron: "30 8 * * *",
			},
			Destination: assistant.SkillSubscriptionDestination{
				DestinationType:  "group",
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
		if _, err := newService(true).CreateSkillSubscription(
			t.Context(),
			"account-proactive",
			request,
		); err == nil {
			t.Fatal("user destination outside owner account must be rejected")
		}
	})

	t.Run("conversation destination requires creator persona", func(t *testing.T) {
		request := input()
		request.CreatedByPersonaID = ""
		if _, err := newService(true).CreateSkillSubscription(
			t.Context(),
			"account-proactive",
			request,
		); err == nil {
			t.Fatal("conversation destination without creator persona must fail")
		}
	})

	t.Run("creator and assistant membership are both required", func(t *testing.T) {
		for _, name := range []string{"creator removed", "assistant removed"} {
			t.Run(name, func(t *testing.T) {
				if _, err := newService(false).CreateSkillSubscription(
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
		created, err := newService(true).CreateSkillSubscription(
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
	store := persistence.NewMemorySkillSubscriptionStore()
	subscription := proactiveSubscription("subscription-success", "30 8 * * *")
	if _, err := store.CreateSkillSubscription(t.Context(), subscription); err != nil {
		t.Fatal(err)
	}
	cache := rtredis.NewMemoryClient()
	policy := &proactiveDeliveryPolicyReader{
		policy: allowProactiveDeliveryPolicy(),
	}
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		store,
		cache,
		policy,
		notification,
	)
	now := time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC)

	first, err := service.TickSkillSubscriptionCron(
		t.Context(),
		assistant.SkillSubscriptionCronTickInput{
			Now: now.Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatalf("首次投递失败: %v", err)
	}
	second, err := service.TickSkillSubscriptionCron(
		t.Context(),
		assistant.SkillSubscriptionCronTickInput{
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
	store := persistence.NewMemorySkillSubscriptionStore()
	subscription := proactiveSubscription(
		"subscription-missed-window",
		"30 8 * * *",
	)
	scheduledAt := time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC)
	subscription.DeliveryState.NextAttemptAt = &scheduledAt
	if _, err := store.CreateSkillSubscription(t.Context(), subscription); err != nil {
		t.Fatal(err)
	}
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		store,
		rtredis.NewMemoryClient(),
		&proactiveDeliveryPolicyReader{
			policy: allowProactiveDeliveryPolicy(),
		},
		notification,
	)
	result, err := service.TickSkillSubscriptionCron(
		t.Context(),
		assistant.SkillSubscriptionCronTickInput{
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
	store := persistence.NewMemorySkillSubscriptionStore()
	subscription := proactiveSubscription(
		"subscription-status",
		"* * * * *",
	)
	pendingAt := time.Now().UTC().Add(-time.Minute)
	subscription.DeliveryState.PendingDeliveryID = "delivery-before-pause"
	subscription.DeliveryState.NextAttemptAt = &pendingAt
	subscription.DeliveryState.ConsecutiveFailures = 2
	if _, err := store.CreateSkillSubscription(t.Context(), subscription); err != nil {
		t.Fatal(err)
	}
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
		store,
		rtredis.NewMemoryClient(),
		&proactiveDeliveryPolicyReader{
			policy: allowProactiveDeliveryPolicy(),
		},
		notification,
	)
	paused, err := service.UpdateSkillSubscriptionStatus(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
		assistant.UpdateSkillSubscriptionStatusInput{
			Status: assistant.SkillSubscriptionStatusPaused,
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
		assistant.SkillSubscriptionCronTickInput{
			Now: time.Now().UTC().Add(time.Hour).Format(time.RFC3339),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.ProcessedCount != 0 || len(notification.commands) != 0 {
		t.Fatalf("暂停订阅仍被投递: result=%+v", result)
	}
	active, err := service.UpdateSkillSubscriptionStatus(
		t.Context(),
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
		assistant.UpdateSkillSubscriptionStatusInput{
			Status: assistant.SkillSubscriptionStatusActive,
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
		policy application.AssistantDeliveryPolicy
		now    time.Time
	}{
		{
			name: "global assistant disabled",
			policy: application.AssistantDeliveryPolicy{
				UserID:           "account-proactive",
				AssistantEnabled: false,
				Version:          1,
			},
			now: time.Date(2026, 7, 24, 8, 30, 0, 0, time.UTC),
		},
		{
			name: "cross-midnight quiet hours",
			policy: func() application.AssistantDeliveryPolicy {
				start := 22 * time.Hour
				end := 7 * time.Hour
				return application.AssistantDeliveryPolicy{
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
			store := persistence.NewMemorySkillSubscriptionStore()
			subscription := proactiveSubscription(
				"subscription-"+test.name,
				"* * * * *",
			)
			if _, err := store.CreateSkillSubscription(
				t.Context(),
				subscription,
			); err != nil {
				t.Fatal(err)
			}
			notification := &proactiveNotificationWriter{}
			service := newProactiveDeliveryService(
				store,
				rtredis.NewMemoryClient(),
				&proactiveDeliveryPolicyReader{policy: test.policy},
				notification,
			)
			result, err := service.TickSkillSubscriptionCron(
				t.Context(),
				assistant.SkillSubscriptionCronTickInput{
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

	store := persistence.NewMemorySkillSubscriptionStore()
	subscription := proactiveSubscription("subscription-daily-limit", "* * * * *")
	if _, err := store.CreateSkillSubscription(t.Context(), subscription); err != nil {
		t.Fatal(err)
	}
	cache := rtredis.NewMemoryClient()
	notification := &proactiveNotificationWriter{}
	service := newProactiveDeliveryService(
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
		assistant.SkillSubscriptionCronTickInput{
			Now: firstAt.Format(time.RFC3339),
		},
	); err != nil || result.ProcessedCount != 1 {
		t.Fatalf("首次日配额投递失败: result=%+v err=%v", result, err)
	}
	secondAt := firstAt.Add(61 * time.Minute)
	result, err := service.TickSkillSubscriptionCron(
		t.Context(),
		assistant.SkillSubscriptionCronTickInput{
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
	store := persistence.NewMemorySkillSubscriptionStore()
	subscription := proactiveSubscription("subscription-retry", "* * * * *")
	if _, err := store.CreateSkillSubscription(t.Context(), subscription); err != nil {
		t.Fatal(err)
	}
	cache := rtredis.NewMemoryClient()
	notification := &proactiveNotificationWriter{failures: 1}
	service := newProactiveDeliveryService(
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
		assistant.SkillSubscriptionCronTickInput{
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
		assistant.SkillSubscriptionCronTickInput{
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
		store := persistence.NewMemorySkillSubscriptionStore()
		subscription := proactiveSubscription(
			"subscription-consent",
			"* * * * *",
		)
		subscription.SkillID = application.SkillPersonalContentAccess
		if _, err := store.CreateSkillSubscription(
			t.Context(),
			subscription,
		); err != nil {
			t.Fatal(err)
		}
		notification := &proactiveNotificationWriter{}
		service := newProactiveDeliveryService(
			store,
			rtredis.NewMemoryClient(),
			&proactiveDeliveryPolicyReader{
				policy: allowProactiveDeliveryPolicy(),
			},
			notification,
		)
		result, err := service.TickSkillSubscriptionCron(
			t.Context(),
			assistant.SkillSubscriptionCronTickInput{
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
				store := persistence.NewMemorySkillSubscriptionStore()
				subscription := proactiveSubscription(
					"subscription-membership-"+name,
					"* * * * *",
				)
				subscription.Destination.DestinationType = "group"
				subscription.Destination.DestinationID = "conv-1"
				subscription.SkillID = "general"
				if _, err := store.CreateSkillSubscription(
					t.Context(),
					subscription,
				); err != nil {
					t.Fatal(err)
				}
				chat := &migratedChatMentionServiceFakeChatGroundingClient{
					membershipDenied: true,
				}
				service := newProactiveDeliveryService(
					store,
					rtredis.NewMemoryClient(),
					&proactiveDeliveryPolicyReader{
						policy: allowProactiveDeliveryPolicy(),
					},
					&proactiveNotificationWriter{},
					application.WithChatGroundingClient(chat),
				)
				result, err := service.TickSkillSubscriptionCron(
					t.Context(),
					assistant.SkillSubscriptionCronTickInput{
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
		store := persistence.NewMemorySkillSubscriptionStore()
		subscription := proactiveSubscription(
			"subscription-membership-current",
			"* * * * *",
		)
		subscription.Destination.DestinationType = "group"
		subscription.Destination.DestinationID = "conv-1"
		subscription.SkillID = "general"
		if _, err := store.CreateSkillSubscription(
			t.Context(),
			subscription,
		); err != nil {
			t.Fatal(err)
		}
		chat := &migratedChatMentionServiceFakeChatGroundingClient{}
		result, err := newProactiveDeliveryService(
			store,
			rtredis.NewMemoryClient(),
			&proactiveDeliveryPolicyReader{
				policy: allowProactiveDeliveryPolicy(),
			},
			&proactiveNotificationWriter{},
			application.WithChatGroundingClient(chat),
		).TickSkillSubscriptionCron(
			t.Context(),
			assistant.SkillSubscriptionCronTickInput{
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
