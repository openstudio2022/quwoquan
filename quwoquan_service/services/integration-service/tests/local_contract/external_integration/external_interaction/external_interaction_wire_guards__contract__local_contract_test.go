// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/reliabletask"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	httpadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	externalapplication "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

// integrationInvalidArgumentCode 是 runtime errors 对「方法不支持」这类
// 传输层参数错误的稳定码；每条路由都必须落到它，不能各自造码。
const integrationInvalidArgumentCode = "INTEGRATION.USER.invalid_argument"

func performExternalInteractionWireRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	rawBody string,
	headers map[string]string,
) (int, map[string]any) {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewReader([]byte(rawBody)))
	request.Header.Set("Content-Type", "application/json")
	for name, value := range headers {
		request.Header.Set(name, value)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}

// 每个 operation 只绑定一个 HTTP 方法。错方法必须返回结构化 invalid_argument，
// 而不是 405 空体或落进业务分支产生副作用。
func TestExternalInteractionRoutesRejectMismatchedHTTPMethod(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	readiness := externalapplication.NewSmsOtpDeliveryReadinessQueryFacade(
		&readinessProbe{},
		&readinessRelay{},
	)
	handler := httpadapter.NewHandler(service, readiness).Routes()

	for _, testCase := range []struct {
		name   string
		method string
		path   string
	}{
		{
			name:   "readiness rejects post",
			method: http.MethodPost,
			path:   externalgenerated.SmsOtpDeliveryReadinessPath,
		},
		{
			name:   "submit rejects get",
			method: http.MethodGet,
			path:   externalgenerated.ExternalRequestsPath,
		},
		{
			name:   "get request rejects post",
			method: http.MethodPost,
			path:   externalgenerated.ExternalRequestsPath + "/request-wire-guard-001",
		},
		{
			name:   "attempts rejects post",
			method: http.MethodPost,
			path:   externalgenerated.ExternalRequestsPath + "/request-wire-guard-001/attempts",
		},
		{
			name:   "dead letters rejects post",
			method: http.MethodPost,
			path:   externalgenerated.ExternalRequestDeadLettersPath,
		},
		{
			name:   "recover rejects get",
			method: http.MethodGet,
			path:   externalgenerated.ExternalRequestDeadLetterRecoverPath,
		},
		{
			name:   "metrics rejects post",
			method: http.MethodPost,
			path:   externalgenerated.ExternalRequestMetricsSnapshotPath,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			status, decoded := performExternalInteractionWireRequest(
				t,
				handler,
				testCase.method,
				testCase.path,
				"",
				nil,
			)
			if status != http.StatusBadRequest ||
				decoded["code"] != integrationInvalidArgumentCode {
				t.Fatalf("status=%d body=%#v", status, decoded)
			}
		})
	}
}

// 装配缺失是系统故障而不是用户输入问题：facade 没接上时必须返回
// internal_error 并保持 500，不能返回 200 空结果让调用方误判能力可用。
func TestExternalInteractionRoutesFailClosedWhenFacadeIsUnwired(t *testing.T) {
	unwired := httpadapter.NewHandler(nil).Routes()

	status, decoded := performExternalInteractionWireRequest(
		t,
		unwired,
		http.MethodPost,
		externalgenerated.ExternalRequestsPath,
		`{"requestId":"req-unwired-001","operation":"sms_otp.send","idempotencyKey":"k"}`,
		nil,
	)
	if status != http.StatusInternalServerError ||
		decoded["code"] != externalgenerated.ErrExternalInteractionInternalError.Error() {
		t.Fatalf("unwired submit status=%d body=%#v", status, decoded)
	}

	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	withoutReadiness := httpadapter.NewHandler(service).Routes()
	request := httptest.NewRequest(
		http.MethodGet,
		externalgenerated.SmsOtpDeliveryReadinessPath,
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{Subject: "service:user-service"}},
	))
	recorder := httptest.NewRecorder()
	withoutReadiness.ServeHTTP(recorder, request)
	readinessBody := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &readinessBody); err != nil {
		t.Fatalf("decode readiness body=%q: %v", recorder.Body.String(), err)
	}
	if recorder.Code != http.StatusInternalServerError ||
		readinessBody["code"] != externalgenerated.ErrExternalInteractionInternalError.Error() {
		t.Fatalf("unwired readiness status=%d body=%#v", recorder.Code, readinessBody)
	}
	if _, leaked := readinessBody["availability"]; leaked {
		t.Fatalf("unwired readiness must not fabricate availability: %#v", readinessBody)
	}
}

// 已验证的 user-service principal 读到的就绪结果必须是探针真实结论，
// 依赖探针失败时只暴露 temporarily_unavailable 与重试间隔，不泄露内部诊断。
func TestReadinessWithVerifiedUserServicePrincipalReturnsProbeResult(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	probe := &readinessProbe{}
	relay := &readinessRelay{}
	handler := httpadapter.NewHandler(
		service,
		externalapplication.NewSmsOtpDeliveryReadinessQueryFacade(probe, relay),
	).Routes()

	request := httptest.NewRequest(
		http.MethodGet,
		externalgenerated.SmsOtpDeliveryReadinessPath,
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{Subject: "service:user-service"}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	var body externalapplication.SmsOtpDeliveryReadiness
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode readiness body=%q: %v", recorder.Body.String(), err)
	}
	if recorder.Code != http.StatusOK || body.Availability != "ready" ||
		body.RetryAfterSeconds != 0 {
		t.Fatalf("readiness status=%d body=%+v", recorder.Code, body)
	}
	if probe.calls != 1 || relay.calls != 1 {
		t.Fatalf("readiness must consult both probes: probe=%d relay=%d", probe.calls, relay.calls)
	}
}

// SubmitExternalInteractionRequest 的 wire 契约是强类型闭集：未知字段、
// 尾随 JSON、缺必填标识与非 RFC3339 时间都必须在受理前拒绝，
// 不能让半成品请求进入可靠任务账本。
func TestSubmitExternalInteractionRejectsMalformedWire(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	handler := httpadapter.NewHandler(service).Routes()

	for _, testCase := range []struct {
		name string
		body string
	}{
		{name: "not an object", body: `["req-1"]`},
		{
			name: "unknown field",
			body: `{"requestId":"req-1","operation":"sms_otp.send","idempotencyKey":"k","callbackUrl":"https://evil.test"}`,
		},
		{
			name: "trailing json",
			body: `{"requestId":"req-1","operation":"sms_otp.send","idempotencyKey":"k"} {"requestId":"req-2"}`,
		},
		{name: "missing operation and identifiers", body: `{}`},
		{
			name: "expiresAt not rfc3339",
			body: `{"requestId":"req-1","operation":"sms_otp.send","idempotencyKey":"k","expiresAt":"2030/01/01 00:00"}`,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			status, decoded := performExternalInteractionWireRequest(
				t,
				handler,
				http.MethodPost,
				externalgenerated.ExternalRequestsPath,
				testCase.body,
				nil,
			)
			if status != http.StatusBadRequest ||
				decoded["code"] != externalgenerated.ErrInvalidExternalRequest.Error() {
				t.Fatalf("status=%d body=%#v", status, decoded)
			}
		})
	}
}

// tenant/env/sensitivity/expiresAt 未给时由入口补 canonical 缺省值，聚合不变量
// 因此仍然成立，请求能一直走到应用层能力判定：push-only 装配下 sms_otp.send
// 必须是 unsupported_operation，而不是被误判成 envelope 参数缺失。
func TestSubmitExternalInteractionAppliesCanonicalEnvelopeDefaults(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	handler := httpadapter.NewHandler(service).Routes()

	status, decoded := performExternalInteractionWireRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestsPath,
		`{"requestId":"req-envelope-defaults-001","operation":"sms_otp.send","idempotencyKey":"otp:envelope-defaults-001","payloadRef":"otp_challenge:ch-envelope-defaults","payloadDigest":"digest","payload":{"challengeId":"ch-envelope-defaults","codeRef":"otpref.test"}}`,
		nil,
	)
	if status != http.StatusBadRequest ||
		decoded["code"] != externalgenerated.ErrUnsupportedOperation.Error() {
		t.Fatalf("status=%d body=%#v", status, decoded)
	}
}

// 死信恢复是带副作用的运维动作：body、taskId 与 Idempotency-Key 必须齐备，
// 未知 taskId 也只能返回参数错误，不能升级成 5xx 触发无意义告警。
func TestRecoverExternalDeadLetterRejectsIncompleteRecoveryRequest(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	handler := httpadapter.NewHandler(service).Routes()

	for _, testCase := range []struct {
		name    string
		body    string
		headers map[string]string
	}{
		{
			name:    "body is not a typed object",
			body:    `"task-1"`,
			headers: map[string]string{"Idempotency-Key": "recovery-guard-key"},
		},
		{
			name:    "unknown field",
			body:    `{"taskId":"task-1","force":true}`,
			headers: map[string]string{"Idempotency-Key": "recovery-guard-key"},
		},
		{
			name:    "trailing json",
			body:    `{"taskId":"task-1"} {"taskId":"task-2"}`,
			headers: map[string]string{"Idempotency-Key": "recovery-guard-key"},
		},
		{
			name:    "missing task id",
			body:    `{"taskId":"   "}`,
			headers: map[string]string{"Idempotency-Key": "recovery-guard-key"},
		},
		{
			name: "missing idempotency key",
			body: `{"taskId":"task-1"}`,
		},
		{
			name:    "unknown task id",
			body:    `{"taskId":"task-absent-001"}`,
			headers: map[string]string{"Idempotency-Key": "recovery-guard-absent-key"},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			status, decoded := performExternalInteractionWireRequest(
				t,
				handler,
				http.MethodPost,
				externalgenerated.ExternalRequestDeadLetterRecoverPath,
				testCase.body,
				testCase.headers,
			)
			if status != http.StatusBadRequest ||
				decoded["code"] != externalgenerated.ErrInvalidExternalRequest.Error() {
				t.Fatalf("status=%d body=%#v", status, decoded)
			}
		})
	}
}

// 只读控制面在标识缺失或对象不存在时必须返回 invalid_external_request，
// 而不是 200 空壳：调用方靠错误码区分「没有这条请求」与「查询失败」。
func TestExternalInteractionReadRoutesRejectMissingRequestIdentity(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	handler := httpadapter.NewHandler(service).Routes()

	for _, testCase := range []struct {
		name string
		path string
	}{
		{
			name: "dead letters without requestId query",
			path: externalgenerated.ExternalRequestDeadLettersPath,
		},
		{
			name: "attempts with blank requestId segment",
			path: externalgenerated.ExternalRequestsPath + "/%20/attempts",
		},
		{
			name: "get request that was never accepted",
			path: externalgenerated.ExternalRequestsPath + "/request-never-accepted-001",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			status, decoded := performExternalInteractionWireRequest(
				t,
				handler,
				http.MethodGet,
				testCase.path,
				"",
				nil,
			)
			if status != http.StatusBadRequest ||
				decoded["code"] != externalgenerated.ErrInvalidExternalRequest.Error() {
				t.Fatalf("status=%d body=%#v", status, decoded)
			}
		})
	}
}
