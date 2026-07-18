package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func TestGeneratedEntityOperationGuardUsesCurrentCommercialContract(t *testing.T) {
	t.Parallel()

	handlerCalls := 0
	guarded := generatedEntityOperationHandler(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		handlerCalls++
		w.WriteHeader(http.StatusOK)
	}))

	for _, testCase := range []struct {
		method     string
		path       string
		wantStatus int
	}{
		{method: http.MethodGet, path: "/homepages/search", wantStatus: http.StatusOK},
		{method: http.MethodPost, path: "/homepages/candidates", wantStatus: http.StatusForbidden},
		{method: http.MethodGet, path: "/entity/legacy-unregistered-route", wantStatus: http.StatusNotFound},
	} {
		recorder := httptest.NewRecorder()
		guarded.ServeHTTP(recorder, httptest.NewRequest(testCase.method, testCase.path, nil))
		if recorder.Code != testCase.wantStatus {
			t.Fatalf("%s %s status = %d, want %d; body=%s", testCase.method, testCase.path, recorder.Code, testCase.wantStatus, recorder.Body.String())
		}
	}
	if handlerCalls != 1 {
		t.Fatalf("only the ready public route may reach handler, calls=%d", handlerCalls)
	}
}

func TestEntityAuthMiddlewareAdmitsSignedAccountToReadyReload(t *testing.T) {
	t.Parallel()
	config := rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "quwoquan.entity.test",
		Audience:     "quwoquan-app",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
		ClockSkew:    30 * time.Second,
	}
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		t.Fatalf("signer: %v", err)
	}
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatalf("verifier: %v", err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "data-release-operator",
		PersonaID: "data-release-operator",
	})
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}

	handlerCalls := 0
	handler := rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(generatedEntityOperationHandler(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		handlerCalls++
		w.WriteHeader(http.StatusOK)
	})))

	unauthorized := httptest.NewRecorder()
	handler.ServeHTTP(
		unauthorized,
		httptest.NewRequest(http.MethodPost, "/homepages:reload", nil),
	)
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("reload without bearer status=%d want=%d", unauthorized.Code, http.StatusUnauthorized)
	}

	authorizedRequest := httptest.NewRequest(http.MethodPost, "/homepages:reload", nil)
	authorizedRequest.Header.Set("Authorization", "Bearer "+token)
	authorized := httptest.NewRecorder()
	handler.ServeHTTP(authorized, authorizedRequest)
	if authorized.Code != http.StatusOK || handlerCalls != 1 {
		t.Fatalf("signed account reload status=%d calls=%d body=%s", authorized.Code, handlerCalls, authorized.Body.String())
	}
}
