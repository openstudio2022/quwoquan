package http

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/services/search-service/internal/application"
)

type recentObserverSpy struct {
	observations []application.RecentSearchObservation
}

func (s *recentObserverSpy) ObserveRecentSearch(observation application.RecentSearchObservation) {
	s.observations = append(s.observations, observation)
}

func TestRecentSearchHandlerObservesUnauthorizedList(t *testing.T) {
	observer := &recentObserverSpy{}
	handler := NewRecentSearchHandler(nil, observer)
	mux := http.NewServeMux()
	handler.Register(mux)

	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/search/recent", nil))

	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d, want %d", recorder.Code, http.StatusUnauthorized)
	}
	assertRecentObservation(t, observer, "list", "unauthorized")
}

func TestRecentSearchHandlerObservesInvalidUpsert(t *testing.T) {
	observer := &recentObserverSpy{}
	handler := NewRecentSearchHandler(nil, observer)
	mux := http.NewServeMux()
	handler.Register(mux)

	request := httptest.NewRequest(
		http.MethodPost,
		"/search/recent",
		strings.NewReader("{"),
	)
	request.Header.Set("X-Client-User-Id", "persona_test")
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status=%d, want %d", recorder.Code, http.StatusBadRequest)
	}
	assertRecentObservation(t, observer, "upsert", "invalid")
}

func assertRecentObservation(
	t *testing.T,
	observer *recentObserverSpy,
	operation string,
	status string,
) {
	t.Helper()
	if len(observer.observations) != 1 {
		t.Fatalf("observations=%d, want 1", len(observer.observations))
	}
	observation := observer.observations[0]
	if observation.Operation != operation || observation.Status != status {
		t.Fatalf(
			"observation=%+v, want operation=%q status=%q",
			observation,
			operation,
			status,
		)
	}
	if observation.Seconds < 0 {
		t.Fatalf("seconds=%f, want non-negative", observation.Seconds)
	}
}
