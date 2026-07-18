package runtimeerrors

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHTTPWriteOptionsFromRequest(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/assistant/run", nil)
	req.Header.Set("X-Request-Id", "req-1")
	req.Header.Set("X-Trace-Id", "trace-1")

	opts := HTTPWriteOptionsFromRequest(req)

	if opts.RequestID != "req-1" || opts.TraceID != "trace-1" {
		t.Fatalf("unexpected opts: %+v", opts)
	}
}

func TestWriteHTTPErrorPropagatesIDs(t *testing.T) {
	rec := httptest.NewRecorder()
	err := NewInvalidArgument(ModuleAssistant, "请求体无效", "bad body")

	WriteHTTPError(rec, err, HTTPWriteOptions{
		RequestID: "req-1",
		TraceID:   "trace-1",
	})

	if rec.Header().Get("X-Request-Id") != "req-1" {
		t.Fatalf("missing request id header: %s", rec.Header().Get("X-Request-Id"))
	}
	if rec.Header().Get("X-Trace-Id") != "trace-1" {
		t.Fatalf("missing trace id header: %s", rec.Header().Get("X-Trace-Id"))
	}
	var body ErrorResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.RequestID != "req-1" || body.TraceID != "trace-1" {
		t.Fatalf("ids not propagated to body: %+v", body)
	}
	if body.Origin == "" || body.Nature == "" || body.Location.BusinessObject == "" {
		t.Fatalf("runtime fields should be present: %+v", body)
	}
}

func TestRecoveryFromAppErrorDownlinked(t *testing.T) {
	err := NewAppError(NewCode(ModuleUser, KindUser, "otp_rate_limited"), "发送过于频繁", "throttled").
		WithRecovery("retry", 42)

	body := ToResponse(err, "req-1", "trace-1")

	if body.Recovery.Action != "retry" {
		t.Fatalf("expected recovery action retry, got %q", body.Recovery.Action)
	}
	if body.Recovery.AfterSeconds != 42 {
		t.Fatalf("expected afterSeconds 42, got %d", body.Recovery.AfterSeconds)
	}
	if body.Recovery.DisruptionLevel != "snackbar" {
		t.Fatalf("expected snackbar disruption, got %q", body.Recovery.DisruptionLevel)
	}
}

func TestRecoveryDefaultsWhenAbsent(t *testing.T) {
	transient := ToResponse(NewUnavailable(ModuleGateway, "上游不可用", "down"), "req", "trace")
	if transient.Recovery.Action != "retry" || transient.Recovery.DisruptionLevel != "snackbar" {
		t.Fatalf("transient should default retry/snackbar, got %+v", transient.Recovery)
	}

	validation := ToResponse(NewInvalidArgument(ModuleUser, "参数错误", "bad"), "req", "trace")
	if validation.Recovery.Action != "surface" || validation.Recovery.DisruptionLevel != "inlineCard" {
		t.Fatalf("validation should default surface/inlineCard, got %+v", validation.Recovery)
	}
}

func TestUserMessageOverrideFailSafe(t *testing.T) {
	t.Cleanup(func() { SetUserMessageResolver(nil) })

	code := NewCode(ModuleUser, KindUser, "otp_mismatch")
	baseline := NewAppError(code, "验证码不正确", "mismatch")

	// 命中 override：返回运营态文案。
	SetUserMessageResolver(func(c string, locale string) (string, bool) {
		if c == "USER.USER.otp_mismatch" && locale == "zh" {
			return "验证码错误，请重新输入", true
		}
		return "", false
	})
	got := ToResponseWithOptions(baseline, ResponseOptions{Locale: "zh"})
	if got.UserMessage != "验证码错误，请重新输入" {
		t.Fatalf("expected override message, got %q", got.UserMessage)
	}

	// 未命中 locale：回退 codegen baseline（fail-safe）。
	fallback := ToResponseWithOptions(NewAppError(code, "验证码不正确", "mismatch"), ResponseOptions{Locale: "en"})
	if fallback.UserMessage != "验证码不正确" {
		t.Fatalf("expected baseline fallback, got %q", fallback.UserMessage)
	}

	// resolver 返回空串：同样回退 baseline。
	SetUserMessageResolver(func(string, string) (string, bool) { return "  ", true })
	empty := ToResponseWithOptions(NewAppError(code, "验证码不正确", "mismatch"), ResponseOptions{Locale: "zh"})
	if empty.UserMessage != "验证码不正确" {
		t.Fatalf("empty override should fall back to baseline, got %q", empty.UserMessage)
	}
}

func TestLocaleFromRequest(t *testing.T) {
	cases := map[string]string{
		"":               "zh",
		"zh-CN":          "zh",
		"en-US,en;q=0.9": "en",
		"  en  ":         "en",
	}
	for header, want := range cases {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		if header != "" {
			req.Header.Set("Accept-Language", header)
		}
		if got := localeFromRequest(req); got != want {
			t.Fatalf("locale for %q: want %q got %q", header, want, got)
		}
	}
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("X-Client-Locale", "en")
	req.Header.Set("Accept-Language", "zh-CN")
	if got := localeFromRequest(req); got != "en" {
		t.Fatalf("X-Client-Locale should win, got %q", got)
	}
}

func TestRouteNotFoundMapsToHTTPNotFound(t *testing.T) {
	rec := httptest.NewRecorder()
	WriteHTTPError(
		rec,
		NewAppError(
			NewCode(ModuleContent, KindUser, "route_not_found"),
			"接口不存在",
			"route not found",
		),
		HTTPWriteOptions{},
	)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for route_not_found, got %d", rec.Code)
	}
	var body ErrorResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Code != "CONTENT.USER.route_not_found" {
		t.Fatalf("expected route_not_found code, got %q", body.Code)
	}
}

func TestRuntimeOriginFromCurrentKindUsesCanonicalMapping(t *testing.T) {
	cases := []struct {
		name   string
		err    *AppError
		origin string
	}{
		{
			name: "network is environment",
			err: NewAppError(
				NewCode(ModuleGateway, KindNetwork, "connection_refused"),
				"网络不可用",
				"dial refused",
			),
			origin: "environment",
		},
		{
			name:   "middleware is remote dependency",
			err:    NewUnavailable(ModuleGateway, "上游不可用", "upstream unavailable"),
			origin: "remoteDependency",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			body := ToResponse(tc.err, "req-1", "trace-1")
			if body.Origin != tc.origin {
				t.Fatalf("expected origin %q, got %q", tc.origin, body.Origin)
			}
		})
	}
}

func TestParseCodeAllowsMetadataUserSubKinds(t *testing.T) {
	cases := []string{
		"USER.GREETING.already_contact",
		"USER.AUTH.token_expired",
		"USER.SUB_ACCOUNT.not_found",
		"USER.SUB_ACCOUNT.retired_guard",
		"USER.SUB_ACCOUNT.delete_empty_only",
		"USER.SUB_ACCOUNT.handle_taken",
		"USER.CONTACT.rate_limited",
		"USER.INVITE.expired",
		"USER.SETTING.invalid_call_ringtone",
		"NOTIFICATION.USER.app_message_not_found",
	}
	for _, raw := range cases {
		t.Run(raw, func(t *testing.T) {
			code, err := ParseCode(raw)
			if err != nil {
				t.Fatalf("ParseCode(%q) returned error: %v", raw, err)
			}
			if code.String() != raw {
				t.Fatalf("round trip mismatch: got %q want %q", code.String(), raw)
			}
		})
	}
}

func TestHTTPStatusFromErrorSupportsMetadataUserSubKinds(t *testing.T) {
	cases := []struct {
		name string
		raw  string
		want int
	}{
		{name: "greeting conflict", raw: "USER.GREETING.already_contact", want: http.StatusConflict},
		{name: "contact limited", raw: "USER.CONTACT.rate_limited", want: http.StatusTooManyRequests},
		{name: "invite expired", raw: "USER.INVITE.expired", want: http.StatusGone},
		{name: "auth expired", raw: "USER.AUTH.token_expired", want: http.StatusUnauthorized},
		{name: "sub account missing", raw: "USER.SUB_ACCOUNT.not_found", want: http.StatusNotFound},
		{name: "retired sub account", raw: "USER.SUB_ACCOUNT.retired_guard", want: http.StatusBadRequest},
		{name: "delete empty only", raw: "USER.SUB_ACCOUNT.delete_empty_only", want: http.StatusBadRequest},
		{name: "sub account handle taken", raw: "USER.SUB_ACCOUNT.handle_taken", want: http.StatusConflict},
		{name: "setting invalid", raw: "USER.SETTING.invalid_call_ringtone", want: http.StatusBadRequest},
		{name: "rtc already in call", raw: "RTC.USER.already_in_call", want: http.StatusConflict},
		{name: "rtc call full", raw: "RTC.USER.call_full", want: http.StatusConflict},
		{name: "rtc cannot answer", raw: "RTC.USER.cannot_answer", want: http.StatusConflict},
		{name: "rtc invalid call action", raw: "RTC.USER.invalid_call_action", want: http.StatusConflict},
		{name: "rtc screen share conflict", raw: "RTC.USER.screen_share_conflict", want: http.StatusConflict},
		{name: "rtc call ended", raw: "RTC.USER.call_ended", want: http.StatusGone},
		{name: "rtc call not found", raw: "RTC.USER.call_not_found", want: http.StatusNotFound},
		{name: "rtc not participant", raw: "RTC.USER.not_participant", want: http.StatusForbidden},
		{name: "rtc not mutual", raw: "RTC.USER.not_mutual", want: http.StatusForbidden},
		{name: "rtc blocked", raw: "RTC.USER.blocked", want: http.StatusForbidden},
		{name: "rtc recording not allowed", raw: "RTC.USER.recording_not_allowed", want: http.StatusForbidden},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			code, err := ParseCode(tc.raw)
			if err != nil {
				t.Fatalf("ParseCode(%q): %v", tc.raw, err)
			}
			got := HTTPStatusFromError(NewAppError(code, "msg", "debug"))
			if got != tc.want {
				t.Fatalf("status = %d, want %d", got, tc.want)
			}
		})
	}
}

func TestMetadataBindingPreservesStableCodeAndTransportSemantics(t *testing.T) {
	code, err := ParseCode("CONTENT.USER.comment_pin_forbidden")
	if err != nil {
		t.Fatalf("ParseCode: %v", err)
	}
	appErr := NewAppError(code, "仅内容作者可置顶评论", "forbidden").
		WithMetadata("forbidden", http.StatusForbidden)

	if got := HTTPStatusFromError(appErr); got != http.StatusForbidden {
		t.Fatalf("HTTP status = %d, want %d", got, http.StatusForbidden)
	}
	response := ToResponse(appErr, "request-1", "trace-1")
	if response.Code != "CONTENT.USER.comment_pin_forbidden" {
		t.Fatalf("stable code = %q", response.Code)
	}
	if response.Reason != "forbidden" || response.Kind != "permission" {
		t.Fatalf("transport semantics = reason %q kind %q", response.Reason, response.Kind)
	}
}
