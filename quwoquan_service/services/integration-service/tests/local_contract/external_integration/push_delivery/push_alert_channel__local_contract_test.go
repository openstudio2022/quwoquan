// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#gwt-002
// readiness_case: invoke-push-delivery-provider-local
//
// 通用 alert 推送通道（契约 push_delivery action=alert）的三段证据：
//  1. payload 分类别校验：alert 十字段白名单严格生效，来电字段互斥，
//     ring/cancel 十一字段通道不回归；
//  2. FCM alert 消息形状：notification 块承载通知栏 title/body，data 块只带
//     targetType/targetId 路由锚点，collapse/TTL 与来电通道同语义；
//  3. APNs VoIP 通道对 alert 返回结构化不可用（iOS 可见推送依赖独立 alert
//     端点种类，见 spec OPEN），禁止静默降级。
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	generated "quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
	"quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
	"quwoquan_service/services/integration-service/internal/external_integration/push_delivery/infrastructure/provider"
)

const alertContractDeliveryKey = "chat-message:evt-001:persona-recipient-001"

func alertPushRequest(expiresAt time.Time) reliabletask.ExternalInteractionRequest {
	return reliabletask.ExternalInteractionRequest{
		RequestID:      "push-alert-request-001",
		Operation:      reliabletask.ExternalInteractionOperationPush,
		Tenant:         "quwoquan",
		Env:            "gamma",
		IdempotencyKey: "alert-delivery-001",
		PayloadRef:     "push:alert-delivery-001",
		PayloadDigest:  "sha256:25a929085a12cbf1b2bccf55dbef729df64e2ce16ecebd968afab8fc63d48d0a",
		Sensitivity:    "private",
		ExpiresAt:      expiresAt.UTC(),
		Payload: map[string]string{
			"action":          application.PushDeliveryActionAlert,
			"endpointRef":     localContractEndpointRef,
			"deliveryKey":     alertContractDeliveryKey,
			"targetPersonaId": "persona-recipient-001",
			"title":           "李明",
			"body":            "周六的观星聚会记得带上三脚架",
			"targetType":      "conversation",
			"targetId":        "conv-001",
			"expiresAt":       expiresAt.UTC().Format(time.RFC3339),
			"occurredAt":      time.Now().UTC().Add(-time.Second).Format(time.RFC3339),
		},
	}
}

// GWT-002（送达链）：alert 类别按契约十字段严格校验；来电字段互斥；
// ring/cancel 十一字段通道保持不回归。
func TestPushAlertPayloadValidation(t *testing.T) {
	expiresAt := time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second)
	valid := alertPushRequest(expiresAt)
	if err := application.ValidatePushDeliveryRequest(valid); err != nil {
		t.Fatalf("valid alert payload rejected: %v", err)
	}
	// 来电通道不回归。
	ring := pushRequest(expiresAt)
	if err := application.ValidatePushDeliveryRequest(ring); err != nil {
		t.Fatalf("valid ring payload rejected: %v", err)
	}
	tests := []struct {
		name   string
		mutate func(*reliabletask.ExternalInteractionRequest)
	}{
		{
			name: "missing_title",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["title"] = " "
			},
		},
		{
			name: "missing_body",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["body"] = ""
			},
		},
		{
			name: "missing_target_type",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				delete(request.Payload, "targetType")
				request.Payload["unused"] = "keep-count"
			},
		},
		{
			name: "carries_incoming_call_field",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				delete(request.Payload, "title")
				request.Payload["callId"] = "call-001"
			},
		},
		{
			name: "unknown_field",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				delete(request.Payload, "body")
				request.Payload["deviceToken"] = "must-never-be-accepted"
			},
		},
		{
			name: "extra_eleventh_field",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["deeplink"] = "/chat/conv-001"
			},
		},
		{
			name: "raw_token_as_endpoint_ref",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["endpointRef"] = "raw-device-token-must-not-be-persisted"
			},
		},
		{
			name: "expired",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				past := time.Now().UTC().Add(-time.Minute).Format(time.RFC3339)
				request.Payload["expiresAt"] = past
			},
		},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			request := alertPushRequest(expiresAt)
			testCase.mutate(&request)
			if err := application.ValidatePushDeliveryRequest(request); err == nil {
				t.Fatalf("mutated alert payload %s must be rejected", testCase.name)
			}
		})
	}
}

// GWT-002（可见形状）：FCM alert 消息使用 notification+data 组合形状——
// 通知栏可见 title/body 由 notification 块承载，data 块只带路由锚点与
// collapse 语义键，不携带任何来电字段。
func TestFCMAlertMessageShape(t *testing.T) {
	now := time.Date(2026, 8, 13, 6, 0, 0, 0, time.UTC)
	key := writeTemporaryRSAKey(t)
	var sendCalls atomic.Int32
	var server = newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/token":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"access_token": "oauth-access-token",
				"token_type":   "Bearer",
				"expires_in":   3600,
			})
		case "/v1/projects/qwq-test/messages:send":
			sendCalls.Add(1)
			var payload struct {
				Message struct {
					Token        string `json:"token"`
					Notification *struct {
						Title string `json:"title"`
						Body  string `json:"body"`
					} `json:"notification"`
					Data    map[string]string `json:"data"`
					Android struct {
						Priority    string `json:"priority"`
						TTL         string `json:"ttl"`
						CollapseKey string `json:"collapse_key"`
					} `json:"android"`
				} `json:"message"`
			}
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Errorf("decode FCM alert request: %v", err)
			}
			message := payload.Message
			if message.Notification == nil ||
				message.Notification.Title != "李明" ||
				message.Notification.Body != "周六的观星聚会记得带上三脚架" {
				t.Errorf("FCM alert must carry notification title/body: %+v", message.Notification)
			}
			if message.Data["action"] != application.PushDeliveryActionAlert ||
				message.Data["targetType"] != "conversation" ||
				message.Data["targetId"] != "conv-001" ||
				message.Data["deliveryKey"] != alertContractDeliveryKey ||
				message.Data["targetPersonaId"] != "persona-recipient-001" {
				t.Errorf("unexpected FCM alert data block: %+v", message.Data)
			}
			for _, forbidden := range []string{
				"callId", "callType", "callerName", "sourceLabel", "trustRelation",
				"title", "body",
			} {
				if _, exists := message.Data[forbidden]; exists {
					t.Errorf("FCM alert data must not carry %s", forbidden)
				}
			}
			if message.Android.Priority != "high" ||
				message.Android.TTL != "120s" ||
				message.Android.CollapseKey != expectedProviderCollapseKey(alertContractDeliveryKey) {
				t.Errorf("unexpected FCM alert android config: %+v", message.Android)
			}
			_ = json.NewEncoder(w).Encode(map[string]string{
				"name": fmt.Sprintf("projects/qwq-test/messages/alert-%d", sendCalls.Load()),
			})
		default:
			http.NotFound(w, request)
		}
	}))
	serviceAccountFile := writeServiceAccountFile(t, key, server.URL+"/token")
	fcm, err := provider.NewFCMProvider(provider.FCMConfig{
		ServiceAccountFile: serviceAccountFile,
		ProjectID:          "qwq-test",
		Timeout:            time.Second,
		APIBaseURL:         server.URL,
		Now:                func() time.Time { return now },
	}, server.Client())
	if err != nil {
		t.Fatalf("construct FCM provider: %v", err)
	}
	receipt, err := fcm.SendPush(context.Background(), "device-token-fcm", alertPushMessage(now))
	if err != nil {
		t.Fatalf("send FCM alert: %v", err)
	}
	if receipt.ProviderRequestID != "projects/qwq-test/messages/alert-1" ||
		sendCalls.Load() != 1 {
		t.Fatalf("unexpected FCM alert receipt=%+v calls=%d", receipt, sendCalls.Load())
	}
	// ring 消息保持 data-only 形状（无 notification 块）不回归。
	ringShapeServer := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/token":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"access_token": "oauth-access-token",
				"token_type":   "Bearer",
				"expires_in":   3600,
			})
		case "/v1/projects/qwq-test/messages:send":
			var raw map[string]json.RawMessage
			var message map[string]json.RawMessage
			if err := json.NewDecoder(request.Body).Decode(&raw); err != nil {
				t.Errorf("decode FCM ring request: %v", err)
			}
			if err := json.Unmarshal(raw["message"], &message); err != nil {
				t.Errorf("decode FCM ring message: %v", err)
			}
			if _, exists := message["notification"]; exists {
				t.Error("FCM ring message must stay data-only without notification block")
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"name": "projects/qwq-test/messages/ring-1"})
		default:
			http.NotFound(w, request)
		}
	}))
	ringAccountFile := writeServiceAccountFile(t, key, ringShapeServer.URL+"/token")
	ringFCM, err := provider.NewFCMProvider(provider.FCMConfig{
		ServiceAccountFile: ringAccountFile,
		ProjectID:          "qwq-test",
		Timeout:            time.Second,
		APIBaseURL:         ringShapeServer.URL,
		Now:                func() time.Time { return now },
	}, ringShapeServer.Client())
	if err != nil {
		t.Fatalf("construct ring FCM provider: %v", err)
	}
	if _, err := ringFCM.SendPush(
		context.Background(),
		"device-token-fcm",
		protocolPushMessage(now),
	); err != nil {
		t.Fatalf("send FCM ring: %v", err)
	}
}

// APNs VoIP 通道只承载来电信令：alert 消息必须得到结构化不可重试失败，
// 不允许被静默投到 VoIP 通道或降级吞掉。
func TestAPNsVoIPRejectsAlert(t *testing.T) {
	now := time.Date(2026, 8, 13, 6, 0, 0, 0, time.UTC)
	_, keyFile := writeTemporaryECKey(t)
	var calls atomic.Int32
	server := newHTTP2TLSServer(t, http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		calls.Add(1)
	}))
	apns, err := provider.NewAPNsVoIPProvider(provider.APNsVoIPConfig{
		Environment: application.APNsEnvironmentSandbox,
		KeyFile:     keyFile,
		KeyID:       "APNSKEY01",
		TeamID:      "TEAM000001",
		Topic:       "com.quwoquan.app.voip",
		Timeout:     time.Second,
		BaseURL:     server.URL,
		Now:         func() time.Time { return now },
	}, server.Client())
	if err != nil {
		t.Fatalf("construct APNs provider: %v", err)
	}
	_, sendErr := apns.SendPush(context.Background(), "device-token-apns", alertPushMessage(now))
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		failure.Code != generated.ErrPushDeliveryInvalidRequest.Error() ||
		failure.Retryable {
		t.Fatalf("APNs VoIP must reject alert with non-retryable failure, got %v", sendErr)
	}
	if calls.Load() != 0 {
		t.Fatalf("APNs VoIP must not reach provider endpoint for alert, calls=%d", calls.Load())
	}
}

func alertPushMessage(now time.Time) application.PushDeliveryMessage {
	return application.PushDeliveryMessage{
		Action:          application.PushDeliveryActionAlert,
		EndpointRef:     localContractEndpointRef,
		DeliveryKey:     alertContractDeliveryKey,
		TargetPersonaID: "persona-recipient-001",
		Title:           "李明",
		Body:            "周六的观星聚会记得带上三脚架",
		TargetType:      "conversation",
		TargetID:        "conv-001",
		ExpiresAt:       now.Add(2 * time.Minute),
		OccurredAt:      now,
	}
}
