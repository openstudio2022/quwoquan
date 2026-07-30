package media_upload_session_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	posthttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	sessionhttp "quwoquan_service/services/content-service/internal/media/media_upload_session/adapters/inbound/http"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	sessionmodel "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/model"
	sessionports "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

func TestGeneratedUploadRouteUsesObjectOwnedSessionAdapter(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	store := &httpSessionStore{}
	service := sessionapp.NewUseCases(
		store,
		httpObjectStore{},
		sessionapp.WithClock(func() time.Time { return now }),
		sessionapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			return prefix + "_test", nil
		}),
	)
	handler := posthttp.NewContentHandler(
		nil, nil, nil, nil, nil, nil, nil,
		posthttp.WithMediaUploadSessionHandler(sessionhttp.NewHandler(service)),
	).Routes()

	request := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads:init",
		strings.NewReader(`{"mediaType":"image","mimeType":"image/jpeg","fileSize":128,"expectedSha256":"sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}`),
	)
	request.Header.Set("Idempotency-Key", "media-upload-api-1")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{Subject: "account-1", Persona: "persona-1"},
		Actor:  operation.ActorContext{AccountID: "account-1", PersonaID: "persona-1"},
	}))
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d response=%s", recorder.Code, recorder.Body.String())
	}
	var response struct {
		SessionID string `json:"sessionId"`
		Status    string `json:"status"`
		UploadURL string `json:"uploadUrl"`
	}
	if err := json.NewDecoder(recorder.Body).Decode(&response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if response.SessionID != "mus_test" || response.Status != string(sessionmodel.StatusPending) || response.UploadURL == "" {
		t.Fatalf("unexpected object-owned HTTP response: %+v", response)
	}
	if store.ownerID != "persona-1" {
		t.Fatalf("expected authenticated persona owner, got %q", store.ownerID)
	}
}

type httpObjectStore struct{}

func (httpObjectStore) PrepareUpload(_ context.Context, params sessionapp.PrepareUploadParams) (sessionapp.UploadGrant, error) {
	return sessionapp.UploadGrant{
		ObjectKey: "uploads/" + params.SessionID,
		UploadURL: "https://upload.example/" + params.SessionID,
		ExpiresAt: params.ExpiresAt,
	}, nil
}

func (httpObjectStore) UploadURL(context.Context, string, string, string, time.Time) (string, error) {
	return "https://upload.example/replayed", nil
}

func (httpObjectStore) CompleteUpload(context.Context, sessionapp.CompleteUploadParams) (sessionapp.CompletedObject, error) {
	panic("complete is not exercised by this route contract")
}

func (httpObjectStore) DeleteTemporaryUpload(context.Context, string) error {
	panic("abort is not exercised by this route contract")
}

type httpSessionStore struct {
	session *sessionmodel.Session
	ownerID string
}

func (s *httpSessionStore) Load(context.Context, string) (*sessionmodel.Session, bool, error) {
	return nil, false, nil
}

func (s *httpSessionStore) FindForOwner(context.Context, string, string) (sessionmodel.Snapshot, bool, error) {
	return sessionmodel.Snapshot{}, false, nil
}

func (s *httpSessionStore) FindReceipt(context.Context, string, string, string) (sessionports.Receipt, bool, error) {
	return sessionports.Receipt{}, false, nil
}

func (s *httpSessionStore) Commit(_ context.Context, commit sessionports.Commit) (sessionports.Receipt, error) {
	s.session = commit.Session
	s.ownerID = commit.Session.OwnerID()
	return sessionports.Receipt{Session: commit.Session}, nil
}

func (s *httpSessionStore) Complete(context.Context, sessionports.CompleteCommit) (sessionports.Receipt, error) {
	panic("complete is not exercised by this route contract")
}

var _ sessionapp.ObjectStore = httpObjectStore{}
var _ sessionports.Store = (*httpSessionStore)(nil)
