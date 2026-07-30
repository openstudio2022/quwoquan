package local_contract

import (
	"net/http"
	"net/http/httptest"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestTagOperationSecuritySeparatesPublicUserAndServiceRoutes(
	t *testing.T,
) {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /tag/resolve", func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		writer.WriteHeader(http.StatusNoContent)
	})
	mux.HandleFunc("POST /tag/feedback", func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		writer.WriteHeader(http.StatusNoContent)
	})
	mux.HandleFunc("GET /internal/tag/shared-tags", func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		writer.WriteHeader(http.StatusNoContent)
	})
	handler := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("tag"),
	)(mux)

	publicRequest := httptest.NewRequest(
		http.MethodGet,
		"/tag/resolve",
		nil,
	)
	publicRecorder := httptest.NewRecorder()
	handler.ServeHTTP(publicRecorder, publicRequest)
	if publicRecorder.Code != http.StatusNoContent {
		t.Fatalf("public catalog status=%d", publicRecorder.Code)
	}

	feedbackRequest := httptest.NewRequest(
		http.MethodPost,
		"/tag/feedback",
		nil,
	)
	feedbackRequest.Header.Set("X-Client-Persona-Id", "forged-persona")
	feedbackRecorder := httptest.NewRecorder()
	handler.ServeHTTP(feedbackRecorder, feedbackRequest)
	if feedbackRecorder.Code != http.StatusUnauthorized {
		t.Fatalf(
			"unverified feedback identity status=%d",
			feedbackRecorder.Code,
		)
	}

	internalRequest := httptest.NewRequest(
		http.MethodGet,
		"/internal/tag/shared-tags",
		nil,
	).WithContext(rtauth.WithPrincipal(
		httptest.NewRequest(
			http.MethodGet,
			"/internal/tag/shared-tags",
			nil,
		).Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-1",
		}},
	))
	internalRecorder := httptest.NewRecorder()
	handler.ServeHTTP(internalRecorder, internalRequest)
	if internalRecorder.Code != http.StatusForbidden {
		t.Fatalf(
			"end-user internal graph access status=%d",
			internalRecorder.Code,
		)
	}

	serviceRequest := httptest.NewRequest(
		http.MethodGet,
		"/internal/tag/shared-tags",
		nil,
	)
	serviceRequest = serviceRequest.WithContext(rtauth.WithPrincipal(
		serviceRequest.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor: operation.ActorContext{
				AccountID: "service:search-service",
			},
		},
	))
	serviceRecorder := httptest.NewRecorder()
	handler.ServeHTTP(serviceRecorder, serviceRequest)
	if serviceRecorder.Code != http.StatusNoContent {
		t.Fatalf("service graph access status=%d", serviceRecorder.Code)
	}
}
