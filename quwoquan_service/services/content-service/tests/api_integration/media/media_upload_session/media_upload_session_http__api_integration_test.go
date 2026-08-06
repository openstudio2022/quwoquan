// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// readiness_case: init-media-upload-api
// readiness_case: complete-media-upload-api
// readiness_case: abort-media-upload-api
// readiness_case: get-media-upload-session-api
package media_upload_session_test

import (
	"context"
	"encoding/json"
	"fmt"
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
	store := &httpSessionStore{
		sessions: map[string]sessionmodel.Snapshot{},
		receipts: map[string]sessionports.Receipt{},
	}
	sequence := 0
	service := sessionapp.NewUseCases(
		store,
		httpObjectStore{},
		sessionapp.WithClock(func() time.Time { return now }),
		sessionapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			sequence++
			return fmt.Sprintf("%s_%d", prefix, sequence), nil
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
	if response.SessionID == "" || response.Status != string(sessionmodel.StatusPending) || response.UploadURL == "" {
		t.Fatalf("unexpected object-owned HTTP response: %+v", response)
	}
	if store.ownerID != "persona-1" {
		t.Fatalf("expected authenticated persona owner, got %q", store.ownerID)
	}

	pending := executeUploadSessionRequest(
		t, handler, http.MethodGet,
		"/content/media/uploads/"+response.SessionID,
		"", "",
	)
	if pending.Code != http.StatusOK || !strings.Contains(pending.Body.String(), `"status":"pending"`) {
		t.Fatalf("get pending session status=%d body=%s", pending.Code, pending.Body.String())
	}
	completed := executeUploadSessionRequest(
		t, handler, http.MethodPost,
		"/content/media/uploads/"+response.SessionID+":complete",
		`{"accessPolicy":"owner_only"}`, "media-upload-complete-api",
	)
	if completed.Code != http.StatusOK ||
		!strings.Contains(completed.Body.String(), `"status":"completed"`) ||
		!strings.Contains(completed.Body.String(), `"assetId":`) {
		t.Fatalf("complete upload status=%d body=%s", completed.Code, completed.Body.String())
	}
	completedView := executeUploadSessionRequest(
		t, handler, http.MethodGet,
		"/content/media/uploads/"+response.SessionID,
		"", "",
	)
	if completedView.Code != http.StatusOK || !strings.Contains(completedView.Body.String(), `"status":"completed"`) {
		t.Fatalf("get completed session status=%d body=%s", completedView.Code, completedView.Body.String())
	}

	abortInit := executeUploadSessionRequest(
		t, handler, http.MethodPost,
		"/content/media/uploads:init",
		`{"mediaType":"image","mimeType":"image/jpeg","fileSize":256,"expectedSha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`,
		"media-upload-abort-init-api",
	)
	if abortInit.Code != http.StatusOK {
		t.Fatalf("init abort session status=%d body=%s", abortInit.Code, abortInit.Body.String())
	}
	var abortSession struct {
		SessionID string `json:"sessionId"`
	}
	if err := json.Unmarshal(abortInit.Body.Bytes(), &abortSession); err != nil || abortSession.SessionID == "" {
		t.Fatalf("decode abort session: value=%+v err=%v", abortSession, err)
	}
	aborted := executeUploadSessionRequest(
		t, handler, http.MethodPost,
		"/content/media/uploads/"+abortSession.SessionID+":abort",
		"", "media-upload-abort-api",
	)
	if aborted.Code != http.StatusOK || !strings.Contains(aborted.Body.String(), `"status":"aborted"`) {
		t.Fatalf("abort upload status=%d body=%s", aborted.Code, aborted.Body.String())
	}
}

func executeUploadSessionRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{Subject: "account-1", Persona: "persona-1"},
		Actor:  operation.ActorContext{AccountID: "account-1", PersonaID: "persona-1"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
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

func (httpObjectStore) CompleteUpload(_ context.Context, params sessionapp.CompleteUploadParams) (sessionapp.CompletedObject, error) {
	return sessionapp.CompletedObject{
		ObjectKey: params.ObjectKey,
		SHA256:    params.ExpectedSHA256,
	}, nil
}

func (httpObjectStore) DeleteTemporaryUpload(context.Context, string) error {
	return nil
}

type httpSessionStore struct {
	sessions map[string]sessionmodel.Snapshot
	receipts map[string]sessionports.Receipt
	ownerID  string
}

func (s *httpSessionStore) Load(_ context.Context, sessionID string) (*sessionmodel.Session, bool, error) {
	snapshot, found := s.sessions[sessionID]
	if !found {
		return nil, false, nil
	}
	session, err := sessionmodel.Restore(snapshot)
	return session, err == nil, err
}

func (s *httpSessionStore) FindForOwner(_ context.Context, sessionID string, ownerID string) (sessionmodel.Snapshot, bool, error) {
	snapshot, found := s.sessions[sessionID]
	if !found || snapshot.OwnerID != ownerID {
		return sessionmodel.Snapshot{}, false, nil
	}
	return snapshot, true, nil
}

func (s *httpSessionStore) FindReceipt(_ context.Context, key string, name string, digest string) (sessionports.Receipt, bool, error) {
	receipt, found := s.receipts[uploadReceiptKey(key, name, digest)]
	if !found {
		return sessionports.Receipt{}, false, nil
	}
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *httpSessionStore) Commit(_ context.Context, commit sessionports.Commit) (sessionports.Receipt, error) {
	s.sessions[commit.Session.ID()] = commit.Session.Snapshot()
	s.ownerID = commit.Session.OwnerID()
	receipt := sessionports.Receipt{Session: commit.Session}
	s.receipts[uploadReceiptKey(commit.IdempotencyKey, commit.CommandName, commit.CommandDigest)] = receipt
	return receipt, nil
}

func (s *httpSessionStore) Complete(_ context.Context, commit sessionports.CompleteCommit) (sessionports.Receipt, error) {
	s.sessions[commit.Session.ID()] = commit.Session.Snapshot()
	receipt := sessionports.Receipt{
		Session: commit.Session, AssetID: commit.Asset.ID,
		AssetProcessingStatus: commit.Asset.ProcessingStatus,
		ObjectKey:             commit.Asset.ObjectKey,
	}
	s.receipts[uploadReceiptKey(commit.IdempotencyKey, commit.CommandName, commit.CommandDigest)] = receipt
	return receipt, nil
}

func uploadReceiptKey(key string, name string, digest string) string {
	return key + "\x00" + name + "\x00" + digest
}

var _ sessionapp.ObjectStore = httpObjectStore{}
var _ sessionports.Store = (*httpSessionStore)(nil)
