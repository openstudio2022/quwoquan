package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
)

// smsOTPProviderFixture 把「密封的验证码引用 + 一台可编排的 TLS 上游」绑成一组，
// 使每个用例只需要描述上游行为，凭据与 codeRef 的构造保持同一条真实路径。
type smsOTPProviderFixture struct {
	provider   *provider.HTTPExternalProvider
	references *memoryOTPReferenceStore
	upstream   *httptest.Server
	requestID  string
	challengID string
	expiresAt  time.Time
}

func newSMSOTPProviderFixture(
	t *testing.T,
	requestID string,
	timeout time.Duration,
	handler http.HandlerFunc,
) smsOTPProviderFixture {
	t.Helper()
	expiresAt := time.Now().UTC().Add(time.Minute)
	challengeID := "challenge-" + requestID
	sealer, references := smsOTPDependencies(t, requestID, challengeID, expiresAt)
	upstream := httptest.NewTLSServer(handler)
	t.Cleanup(upstream.Close)
	externalProvider, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:      "aliyun_sms",
			Operation: reliabletask.ExternalInteractionOperationSmsOTP,
			// 路径与 sms-provider-substitute 声明的 INTEGRATION_SMS_ENDPOINT 一致；
			// query 单独拼接，否则 path authority 的匹配会被 ?trace= 截断。
			Endpoint: upstream.URL + "/v1/provider/sms/send" +
				"?trace=must-not-reach-probe",
			BearerToken:       "provider-token",
			Timeout:           timeout,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		},
		upstream.Client(),
	)
	if err != nil {
		t.Fatalf("construct HTTP provider: %v", err)
	}
	return smsOTPProviderFixture{
		provider:   externalProvider,
		references: references,
		upstream:   upstream,
		requestID:  requestID,
		challengID: challengeID,
		expiresAt:  expiresAt,
	}
}

func (fixture smsOTPProviderFixture) request() reliabletask.ExternalInteractionRequest {
	return reliabletask.ExternalInteractionRequest{
		RequestID:      fixture.requestID,
		Operation:      reliabletask.ExternalInteractionOperationSmsOTP,
		Tenant:         "quwoquan",
		Env:            "gamma",
		IdempotencyKey: "otp:" + fixture.requestID,
		Sensitivity:    "secret",
		ExpiresAt:      fixture.expiresAt,
		Payload: map[string]string{
			"challengeId": fixture.challengID,
			"templateId":  "sms_otp_login_acceptance",
			"platform":    "acceptance",
			"requestRef":  fixture.requestID,
		},
	}
}

// 就绪探针只允许打 provider 根下的 /healthz：send 路径的 query 不得被带上，
// 否则探针会被上游当成一次真实投递计费。
func TestSMSOTPProviderReadinessProbesHealthzWithoutSendMaterial(t *testing.T) {
	var mu sync.Mutex
	var probed []string
	fixture := newSMSOTPProviderFixture(t, "readiness-ready-001", time.Second,
		func(w http.ResponseWriter, r *http.Request) {
			mu.Lock()
			probed = append(probed, r.Method+" "+r.URL.Path+"?"+r.URL.RawQuery)
			mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{"status": "ready"})
		})

	if err := fixture.provider.CheckSMSOTPProviderReadiness(context.Background()); err != nil {
		t.Fatalf("ready provider must pass readiness: %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(probed) != 1 || probed[0] != "GET /healthz?" {
		t.Fatalf("readiness probe target drift: %#v", probed)
	}
}

// 就绪判定是 fail closed 的：状态码、响应体结构、status 值任一不符都必须
// 报错，让 SmsOtpDeliveryReadiness 回落到 temporarily_unavailable。
func TestSMSOTPProviderReadinessFailsClosedOnUnhealthyUpstream(t *testing.T) {
	for _, testCase := range []struct {
		name    string
		handler http.HandlerFunc
		wantErr string
	}{
		{
			name: "non 200 status",
			handler: func(w http.ResponseWriter, _ *http.Request) {
				http.Error(w, "provider maintenance", http.StatusServiceUnavailable)
			},
			wantErr: "SMS OTP provider readiness status 503",
		},
		{
			name: "response is not json",
			handler: func(w http.ResponseWriter, _ *http.Request) {
				_, _ = w.Write([]byte("<html>ready</html>"))
			},
			wantErr: "SMS OTP provider readiness response is invalid",
		},
		{
			name: "status is not ready",
			handler: func(w http.ResponseWriter, _ *http.Request) {
				_ = json.NewEncoder(w).Encode(map[string]any{"status": "degraded"})
			},
			wantErr: "SMS OTP provider probe is not ready",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			fixture := newSMSOTPProviderFixture(
				t,
				"readiness-unhealthy-001",
				time.Second,
				testCase.handler,
			)
			err := fixture.provider.CheckSMSOTPProviderReadiness(context.Background())
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}
}

// 探针预算被硬顶在 500ms：即使 provider 超时配置更长，登录页的就绪查询
// 也不能被上游拖住。上游停摆时必须报错而不是挂起。
func TestSMSOTPProviderReadinessCapsProbeBudgetAndFailsClosedWhenUnreachable(t *testing.T) {
	const slowerThanProbeBudget = 1500 * time.Millisecond
	stalled := newSMSOTPProviderFixture(t, "readiness-stalled-001", 5*time.Second,
		func(w http.ResponseWriter, r *http.Request) {
			select {
			case <-r.Context().Done():
			case <-time.After(slowerThanProbeBudget):
				_ = json.NewEncoder(w).Encode(map[string]any{"status": "ready"})
			}
		})
	started := time.Now()
	if err := stalled.provider.CheckSMSOTPProviderReadiness(context.Background()); err == nil {
		t.Fatal("stalled upstream must fail readiness")
	}
	if elapsed := time.Since(started); elapsed >= slowerThanProbeBudget {
		t.Fatalf("readiness probe budget was not capped below the provider timeout: elapsed=%s", elapsed)
	}

	unreachable := newSMSOTPProviderFixture(t, "readiness-unreachable-001", 200*time.Millisecond,
		func(w http.ResponseWriter, _ *http.Request) {
			_ = json.NewEncoder(w).Encode(map[string]any{"status": "ready"})
		})
	unreachable.upstream.Close()
	if err := unreachable.provider.CheckSMSOTPProviderReadiness(context.Background()); err == nil {
		t.Fatal("unreachable upstream must fail readiness")
	}

	var absent *provider.HTTPExternalProvider
	if err := absent.CheckSMSOTPProviderReadiness(context.Background()); err == nil ||
		!strings.Contains(err.Error(), "SMS OTP provider is not initialized") {
		t.Fatalf("unwired provider must fail readiness: %v", err)
	}
}

// 上游超时归一化为 sms_provider_timeout 且必须可重试：可靠任务据此重投，
// 不能被压成不可重试的 rejected 而丢失验证码。
func TestSendNormalizesUpstreamTimeoutAsRetryableSMSProviderTimeout(t *testing.T) {
	fixture := newSMSOTPProviderFixture(t, "sms-request-timeout-001", 80*time.Millisecond,
		func(w http.ResponseWriter, _ *http.Request) {
			// POST 的连接取消不会立刻传播到 handler，这里用有界等待越过
			// provider 超时，避免测试反过来卡在 httptest 关闭上。
			time.Sleep(400 * time.Millisecond)
			w.WriteHeader(http.StatusAccepted)
		})
	result, err := fixture.provider.Send(
		context.Background(),
		fixture.request(),
		reliabletask.ReliableAsyncTask{TaskID: "task-timeout-001"},
	)
	var providerErr *provider.ExternalProviderError
	if !errors.As(err, &providerErr) {
		t.Fatalf("expected structured provider error, got %T: %v", err, err)
	}
	if providerErr.Code != "INTEGRATION.MIDDLEWARE.sms_provider_timeout" || !providerErr.Retryable {
		t.Fatalf("timeout must be retryable sms_provider_timeout: %+v", providerErr)
	}
	if result.Status != reliabletask.ExternalInteractionStatusFailed ||
		result.NormalizedError != providerErr.Code || !result.Retryable {
		t.Fatalf("normalized timeout result drift: %+v", result)
	}
}

// 上游显式回报的 retryable 覆盖 HTTP 状态推断：5xx 默认可重试，
// 但 provider 说不可重试时必须尊重它，否则会对永久失败无限重投。
func TestSendHonoursProviderRetryableOverStatusInference(t *testing.T) {
	for _, testCase := range []struct {
		name          string
		status        int
		body          map[string]any
		wantRetryable bool
	}{
		{
			name:          "server error infers retryable",
			status:        http.StatusInternalServerError,
			body:          map[string]any{"status": "failed"},
			wantRetryable: true,
		},
		{
			name:          "rate limited infers retryable",
			status:        http.StatusTooManyRequests,
			body:          map[string]any{"status": "failed"},
			wantRetryable: true,
		},
		{
			name:          "explicit retryable false wins",
			status:        http.StatusBadGateway,
			body:          map[string]any{"status": "failed", "retryable": false},
			wantRetryable: false,
		},
		{
			name:          "client error infers non retryable",
			status:        http.StatusUnprocessableEntity,
			body:          map[string]any{"status": "rejected"},
			wantRetryable: false,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			fixture := newSMSOTPProviderFixture(t, "sms-request-status-001", time.Second,
				func(w http.ResponseWriter, _ *http.Request) {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(testCase.status)
					_ = json.NewEncoder(w).Encode(testCase.body)
				})
			result, err := fixture.provider.Send(
				context.Background(),
				fixture.request(),
				reliabletask.ReliableAsyncTask{TaskID: "task-status-001"},
			)
			var providerErr *provider.ExternalProviderError
			if !errors.As(err, &providerErr) {
				t.Fatalf("expected structured provider error, got %T: %v", err, err)
			}
			if providerErr.StatusCode != testCase.status ||
				providerErr.Retryable != testCase.wantRetryable {
				t.Fatalf("provider error drift: %+v", providerErr)
			}
			if result.Retryable != testCase.wantRetryable ||
				result.NormalizedError != "INTEGRATION.MIDDLEWARE.sms_provider_rejected" {
				t.Fatalf("normalized result drift: %+v", result)
			}
		})
	}
}

// 2xx 也不代表投递成立：没有可追溯的 provider 请求标识、或 status 是拒绝/
// 未知值时都必须归一化为 failed，不能当成已发送。
func TestSendRejectsUntraceableOrUnsupportedProviderAcknowledgement(t *testing.T) {
	for _, testCase := range []struct {
		name          string
		body          map[string]any
		wantRetryable bool
	}{
		{
			name:          "missing traceable identifier",
			body:          map[string]any{"status": "queued"},
			wantRetryable: true,
		},
		{
			name:          "provider rejected request",
			body:          map[string]any{"messageId": "provider-sms-rejected", "status": "rejected"},
			wantRetryable: false,
		},
		{
			name: "provider rejected retryably",
			body: map[string]any{
				"messageId": "provider-sms-failed",
				"status":    "failed",
				"retryable": true,
			},
			wantRetryable: true,
		},
		{
			name: "unsupported provider status",
			body: map[string]any{
				"messageId": "provider-sms-unknown",
				"status":    "half_delivered",
			},
			wantRetryable: true,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			fixture := newSMSOTPProviderFixture(t, "sms-request-ack-001", time.Second,
				func(w http.ResponseWriter, _ *http.Request) {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusOK)
					_ = json.NewEncoder(w).Encode(testCase.body)
				})
			result, err := fixture.provider.Send(
				context.Background(),
				fixture.request(),
				reliabletask.ReliableAsyncTask{TaskID: "task-ack-001"},
			)
			var providerErr *provider.ExternalProviderError
			if !errors.As(err, &providerErr) {
				t.Fatalf("expected structured provider error, got %T: %v", err, err)
			}
			if providerErr.Retryable != testCase.wantRetryable {
				t.Fatalf("provider error retryable drift: %+v", providerErr)
			}
			if result.Status != reliabletask.ExternalInteractionStatusFailed {
				t.Fatalf("unacknowledged send must be failed: %+v", result)
			}
		})
	}
}

// provider 自称 delivered 只能证明它接手了自己的投递；设备呈现是
// NotificationDeliveryJob 的事实，因此 integration 永远只发 sent_unconfirmed。
// 缺 messageId 时回落到 X-Request-ID 也必须仍然可追溯。
func TestSendNeverEmitsDeliveredAndFallsBackToResponseRequestHeader(t *testing.T) {
	fixture := newSMSOTPProviderFixture(t, "sms-request-delivered-001", time.Second,
		func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("X-Request-ID", "provider-trace-delivered-001")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]any{"status": "delivered"})
		})
	result, err := fixture.provider.Send(
		context.Background(),
		fixture.request(),
		reliabletask.ReliableAsyncTask{TaskID: "task-delivered-001"},
	)
	if err != nil {
		t.Fatalf("delivered acknowledgement must be accepted: %v", err)
	}
	if result.Status != reliabletask.ExternalInteractionStatusSentUnconfirmed ||
		result.ProviderRequestID != "provider-trace-delivered-001" || result.Retryable {
		t.Fatalf("delivered must normalize to sent_unconfirmed: %+v", result)
	}
	if _, err := fixture.references.Get(
		context.Background(),
		fixture.requestID,
		fixture.challengID,
	); err == nil {
		t.Fatal("accepted send must consume the one-time OTP code reference")
	}
}

// 投递材料不成立时不得触达 provider：平台白名单、requestRef 自指与
// 引用存在性都在本地判定，避免把无效请求计费到运营商。
func TestSendRejectsInvalidOTPMaterialBeforeCallingProvider(t *testing.T) {
	for _, testCase := range []struct {
		name     string
		mutate   func(*reliabletask.ExternalInteractionRequest)
		wantCode string
	}{
		{
			name: "unknown client platform",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["platform"] = "smart_fridge"
			},
			wantCode: "INTEGRATION.SYSTEM.sms_otp_code_ref_invalid",
		},
		{
			name: "request reference does not match request id",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["requestRef"] = "sms-request-other-001"
			},
			wantCode: "INTEGRATION.SYSTEM.sms_otp_code_ref_invalid",
		},
		{
			name: "challenge id absent",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				delete(request.Payload, "challengeId")
			},
			wantCode: "INTEGRATION.SYSTEM.sms_otp_code_ref_invalid",
		},
		{
			name: "template id absent",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				delete(request.Payload, "templateId")
			},
			wantCode: "INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			called := false
			fixture := newSMSOTPProviderFixture(t, "sms-request-material-001", time.Second,
				func(w http.ResponseWriter, _ *http.Request) {
					called = true
					w.WriteHeader(http.StatusAccepted)
				})
			request := fixture.request()
			testCase.mutate(&request)
			result, err := fixture.provider.Send(
				context.Background(),
				request,
				reliabletask.ReliableAsyncTask{TaskID: "task-material-001"},
			)
			if called {
				t.Fatal("invalid delivery material must not reach the provider")
			}
			var providerErr *provider.ExternalProviderError
			if !errors.As(err, &providerErr) {
				t.Fatalf("expected structured provider error, got %T: %v", err, err)
			}
			if providerErr.Code != testCase.wantCode || providerErr.Retryable {
				t.Fatalf("provider error drift: %+v", providerErr)
			}
			if result.NormalizedError != testCase.wantCode {
				t.Fatalf("normalized result drift: %+v", result)
			}
		})
	}
}

// 请求 operation 与装配 operation 不一致属于装配错误：必须不可重试地拒绝，
// 未装配的 provider 也不能被当成可用通道。
func TestSendFailsClosedOnOperationMismatchAndUnwiredProvider(t *testing.T) {
	fixture := newSMSOTPProviderFixture(t, "sms-request-mismatch-001", time.Second,
		func(w http.ResponseWriter, _ *http.Request) {
			t.Error("mismatched operation must not reach the provider")
		})
	request := fixture.request()
	request.Operation = reliabletask.ExternalInteractionOperationPush
	result, err := fixture.provider.Send(
		context.Background(),
		request,
		reliabletask.ReliableAsyncTask{TaskID: "task-mismatch-001"},
	)
	var providerErr *provider.ExternalProviderError
	if !errors.As(err, &providerErr) ||
		providerErr.Code != "INTEGRATION.MIDDLEWARE.sms_provider_rejected" ||
		providerErr.Retryable {
		t.Fatalf("operation mismatch drift: %+v", providerErr)
	}
	if result.Operation != reliabletask.ExternalInteractionOperationPush ||
		result.Status != reliabletask.ExternalInteractionStatusFailed {
		t.Fatalf("normalized mismatch result drift: %+v", result)
	}

	var absent *provider.HTTPExternalProvider
	if _, err := absent.Send(
		context.Background(),
		fixture.request(),
		reliabletask.ReliableAsyncTask{TaskID: "task-unwired-001"},
	); err == nil || !strings.Contains(err.Error(), "external HTTP provider is not initialized") {
		t.Fatalf("unwired provider must fail closed: %v", err)
	}
}

// 结构化 provider 错误是可观测与重试决策的唯一载体：带状态码时必须暴露状态码，
// 并且始终能 Unwrap 出根因供日志脱敏后记录。
func TestExternalProviderErrorRendersRetryDecisionAndPreservesCause(t *testing.T) {
	cause := errors.New("dial tcp: connection reset")
	withStatus := &provider.ExternalProviderError{
		Code:       "INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		Provider:   "aliyun_sms",
		StatusCode: http.StatusBadGateway,
		Retryable:  true,
		Cause:      cause,
	}
	if got := withStatus.Error(); got !=
		"external provider aliyun_sms failed with INTEGRATION.MIDDLEWARE.sms_provider_rejected (status=502 retryable=true)" {
		t.Fatalf("status-bearing message drift: %q", got)
	}
	if !errors.Is(withStatus, cause) {
		t.Fatalf("provider error must unwrap to its cause: %v", withStatus.Unwrap())
	}

	withoutStatus := &provider.ExternalProviderError{
		Code:      "INTEGRATION.MIDDLEWARE.sms_provider_timeout",
		Provider:  "aliyun_sms",
		Retryable: false,
	}
	if got := withoutStatus.Error(); got !=
		"external provider aliyun_sms failed with INTEGRATION.MIDDLEWARE.sms_provider_timeout (retryable=false)" {
		t.Fatalf("statusless message drift: %q", got)
	}
	if withoutStatus.Unwrap() != nil {
		t.Fatalf("provider error without cause must unwrap to nil: %v", withoutStatus.Unwrap())
	}

	var absent *provider.ExternalProviderError
	if absent.Error() != "" || absent.Unwrap() != nil {
		t.Fatalf("nil provider error must stay inert: %q", absent.Error())
	}
}

// provider 构造是启动期唯一的凭据与端点校验点：非 https、内嵌凭据、
// 非法超时、缺 HTTP 客户端、缺 OTP 依赖与非白名单 provider 名都必须阻断。
func TestNewHTTPExternalProviderRejectsUnsafeComposition(t *testing.T) {
	expiresAt := time.Now().UTC().Add(time.Minute)
	sealer, references := smsOTPDependencies(
		t,
		"sms-request-composition-001",
		"challenge-composition-001",
		expiresAt,
	)
	validConfig := func() provider.HTTPExternalProviderConfig {
		return provider.HTTPExternalProviderConfig{
			Name:              "aliyun_sms",
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          "https://sms.example.test/v1/send",
			BearerToken:       "provider-token",
			Timeout:           time.Second,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		}
	}

	for _, testCase := range []struct {
		name    string
		mutate  func(*provider.HTTPExternalProviderConfig)
		client  *http.Client
		wantErr string
	}{
		{
			name: "plaintext endpoint",
			mutate: func(cfg *provider.HTTPExternalProviderConfig) {
				cfg.Endpoint = "http://sms.example.test/v1/send"
			},
			client:  http.DefaultClient,
			wantErr: "endpoint must be an absolute https URL",
		},
		{
			name: "endpoint embeds credentials",
			mutate: func(cfg *provider.HTTPExternalProviderConfig) {
				cfg.Endpoint = "https://user:secret@sms.example.test/v1/send"
			},
			client:  http.DefaultClient,
			wantErr: "endpoint must be an absolute https URL",
		},
		{
			name: "non positive timeout",
			mutate: func(cfg *provider.HTTPExternalProviderConfig) {
				cfg.Timeout = 0
			},
			client:  http.DefaultClient,
			wantErr: "timeout must be positive",
		},
		{
			name:    "missing observed http client",
			mutate:  func(*provider.HTTPExternalProviderConfig) {},
			client:  nil,
			wantErr: "observed HTTP client is required",
		},
		{
			name: "missing otp code sealer",
			mutate: func(cfg *provider.HTTPExternalProviderConfig) {
				cfg.OTPCodeSealer = nil
			},
			client:  http.DefaultClient,
			wantErr: "otp code reference dependencies are required",
		},
		{
			name: "missing otp reference store",
			mutate: func(cfg *provider.HTTPExternalProviderConfig) {
				cfg.OTPCodeReferences = nil
			},
			client:  http.DefaultClient,
			wantErr: "otp code reference dependencies are required",
		},
		{
			name: "provider name outside operation allowlist",
			mutate: func(cfg *provider.HTTPExternalProviderConfig) {
				cfg.Name = "unlisted_sms"
			},
			client:  http.DefaultClient,
			wantErr: `provider "unlisted_sms" is not valid for operation`,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			cfg := validConfig()
			testCase.mutate(&cfg)
			_, err := provider.NewHTTPExternalProvider(cfg, testCase.client)
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}
}
