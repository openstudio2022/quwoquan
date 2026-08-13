// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004.t3
package runtimemessaging

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
)

type deadLetterReleaserStub struct {
	sourceStreamID string
	err            error
}

func (stub *deadLetterReleaserStub) RecoverDeadLetter(
	_ context.Context,
	sourceStreamID string,
) error {
	stub.sourceStreamID = sourceStreamID
	return stub.err
}

func TestDeadLetterRecoveryRouteReleasesOnlyCanonicalSourcePELReference(
	t *testing.T,
) {
	releaser := &deadLetterReleaserStub{}
	handler, err := WithDeadLetterRecoveryRoute(
		http.NotFoundHandler(),
		DeadLetterRecoveryRouteConfig{
			Path:     "/internal/content/account-closure/dead-letters:recover",
			Module:   rterr.ModuleContent,
			Releaser: releaser,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"1710000000000-42"}`),
	)
	request.Header.Set("Idempotency-Key", "recover-content-42")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if releaser.sourceStreamID != "1710000000000-42" {
		t.Fatalf("released source stream id=%q", releaser.sourceStreamID)
	}
	if !strings.Contains(response.Body.String(), `"recoveryAccepted":true`) {
		t.Fatalf("accepted response=%s", response.Body.String())
	}
}

func TestDeadLetterRecoveryRouteRejectsAmbiguousOrUnboundedInput(
	t *testing.T,
) {
	for name, body := range map[string]string{
		"invalid source": `{"sourceStreamId":"account-sensitive"}`,
		"unknown field":  `{"sourceStreamId":"1-2","payload":"secret"}`,
		"trailing value": `{"sourceStreamId":"1-2"} {}`,
	} {
		t.Run(name, func(t *testing.T) {
			releaser := &deadLetterReleaserStub{}
			handler, err := WithDeadLetterRecoveryRoute(
				http.NotFoundHandler(),
				DeadLetterRecoveryRouteConfig{
					Path:     "/internal/chat/account-closure/dead-letters:recover",
					Module:   rterr.ModuleChat,
					Releaser: releaser,
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			request := httptest.NewRequest(
				http.MethodPost,
				"/internal/chat/account-closure/dead-letters:recover",
				bytes.NewBufferString(body),
			)
			request.Header.Set("Idempotency-Key", "recover-chat")
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusBadRequest {
				t.Fatalf(
					"status=%d body=%s",
					response.Code,
					response.Body.String(),
				)
			}
			if releaser.sourceStreamID != "" {
				t.Fatalf("invalid request released %q", releaser.sourceStreamID)
			}
		})
	}
}

func TestDeadLetterRecoveryRouteRedactsReleaseFailure(t *testing.T) {
	const secret = "account-and-payload-secret"
	handler, err := WithDeadLetterRecoveryRoute(
		http.NotFoundHandler(),
		DeadLetterRecoveryRouteConfig{
			Path:   "/internal/rtc/account-closure/dead-letters:recover",
			Module: rterr.ModuleRTC,
			Releaser: &deadLetterReleaserStub{
				err: errors.New(secret),
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/rtc/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"2-3"}`),
	)
	request.Header.Set("Idempotency-Key", "recover-rtc")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusInternalServerError {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if strings.Contains(response.Body.String(), secret) {
		t.Fatalf("release failure leaked source error: %s", response.Body.String())
	}
}

func TestDeadLetterRecoveryOperationsAreGeneratedOperatorBoundaries(
	t *testing.T,
) {
	for _, testCase := range []struct {
		domain     string
		service    string
		permission string
	}{
		{domain: "content", service: "content", permission: "content.account_closure.recover"},
		{domain: "chat", service: "chat", permission: "chat.account_closure.recover"},
		{domain: "circle", service: "circle", permission: "circle.account_closure.recover"},
		{domain: "notification", service: "notification", permission: "notification.account_closure.recover"},
		{domain: "search", service: "search", permission: "search.account_closure.recover"},
		{domain: "realtime", service: "realtime", permission: "realtime.account_closure.recover"},
		{domain: "rtc", service: "rtc", permission: "rtc.account_closure.recover"},
	} {
		t.Run(testCase.domain, func(t *testing.T) {
			path := "/internal/" + testCase.service +
				"/account-closure/dead-letters:recover"
			descriptors := operationsecurity.ForDomain(testCase.domain)
			var descriptor *rtauth.OperationSecurityDescriptor
			for index := range descriptors {
				if descriptors[index].Method == http.MethodPost &&
					descriptors[index].PathTemplate == path {
					descriptor = &descriptors[index]
					break
				}
			}
			if descriptor == nil {
				t.Fatalf("generated recovery descriptor missing for %s", path)
			}
			if descriptor.AuthMode != "required" ||
				descriptor.Principal != "operator" ||
				descriptor.Idempotency != "required" ||
				descriptor.CommercialStatus != "ready" ||
				len(descriptor.Scopes) != 1 ||
				descriptor.Scopes[0] != "ops.account_closure.write" ||
				len(descriptor.Permissions) != 1 ||
				descriptor.Permissions[0] != testCase.permission {
				t.Fatalf("recovery authorization drifted: %+v", *descriptor)
			}

			called := false
			handler := rtauth.RequireGeneratedOperationAuthorization(
				descriptors,
			)(http.HandlerFunc(func(
				writer http.ResponseWriter,
				_ *http.Request,
			) {
				called = true
				writer.WriteHeader(http.StatusNoContent)
			}))
			request := httptest.NewRequest(http.MethodPost, path, nil)
			request.Header.Set("Idempotency-Key", "recovery-guard-contract")
			request = request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{Claims: rtauth.Claims{
					Scope:       "ops.account_closure.write",
					Permissions: []string{testCase.permission},
					Roles:       []string{"operator"},
				}},
			))
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusNoContent || !called {
				t.Fatalf(
					"authorized operator status=%d called=%t body=%s",
					response.Code,
					called,
					response.Body.String(),
				)
			}
		})
	}
}
