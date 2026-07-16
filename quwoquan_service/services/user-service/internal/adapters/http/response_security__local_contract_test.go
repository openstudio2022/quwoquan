package http

import (
	"net/http/httptest"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
)

func TestWriteHTTPErrorRedactsSensitiveDebugDataInEveryEnvironment(t *testing.T) {
	const (
		appSecret = "wechat-secret-security-contract"
		authCode  = "wechat-auth-code-security-contract"
		token     = "wechat-access-token-security-contract"
	)
	debugMessage := "upstream failed: secret=" + appSecret +
		"&code=" + authCode +
		"&access_token=" + token
	appError := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleUser, rterr.KindSystem, "external_auth_failed"),
		"第三方登录暂不可用，请改用其他方式",
		debugMessage,
	)

	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			request := httptest.NewRequest("POST", "/v1/users/auth/wechat", nil)
			request.Header.Set("X-App-Environment", environment)
			request.Header.Set("X-Request-Id", "request-"+environment)
			request.Header.Set("X-Trace-Id", "trace-"+environment)

			writeHTTPError(recorder, request, appError)

			body := recorder.Body.String()
			for _, sensitiveValue := range []string{appSecret, authCode, token, debugMessage} {
				if strings.Contains(body, sensitiveValue) {
					t.Fatalf("%s response leaked sensitive value %q: %s", environment, sensitiveValue, body)
				}
			}
			if !strings.Contains(body, rterr.RedactedDebugMessage) {
				t.Fatalf("%s response must expose only the redaction marker: %s", environment, body)
			}
			if !strings.Contains(body, "request-"+environment) ||
				!strings.Contains(body, "trace-"+environment) {
				t.Fatalf("%s response must preserve correlation ids: %s", environment, body)
			}
		})
	}
}
