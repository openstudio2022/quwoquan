// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001

package media_upload_session_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	sessionmodel "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/model"
	sessionports "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

func TestMediaUploadSessionLifecycleCreatesIndependentAssetAtomically(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	store := newMemoryStore()
	objects := &memoryObjectStore{now: now}
	sequence := 0
	service := sessionapp.NewUseCases(
		store,
		objects,
		sessionapp.WithClock(func() time.Time { return now }),
		sessionapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			sequence++
			return fmt.Sprintf("%s_%d", prefix, sequence), nil
		}),
	)

	initContext := commandmeta.WithIdempotencyKey(context.Background(), "upload-init-1")
	initialized, err := service.Init(initContext, sessionapp.InitCommand{
		OwnerID: "persona-1", MediaType: "image", ContentType: "image/jpeg",
		FileSize: 128, ExpectedSHA256: testSHA256,
	})
	if err != nil {
		t.Fatalf("init media upload: %v", err)
	}
	if initialized.Status != sessionmodel.StatusPending || initialized.SessionID == "" || initialized.UploadURL == "" {
		t.Fatalf("unexpected initialized result: %+v", initialized)
	}
	if objects.prepareCalls != 1 {
		t.Fatalf("expected one object-store upload grant, got %d", objects.prepareCalls)
	}

	replayed, err := service.Init(initContext, sessionapp.InitCommand{
		OwnerID: "persona-1", MediaType: "image", ContentType: "image/jpeg",
		FileSize: 128, ExpectedSHA256: testSHA256,
	})
	if err != nil {
		t.Fatalf("replay media upload init: %v", err)
	}
	if !replayed.Replayed || replayed.SessionID != initialized.SessionID || replayed.UploadURL == "" {
		t.Fatalf("init replay must retain session and renew upload grant: %+v", replayed)
	}
	if objects.prepareCalls != 1 {
		t.Fatalf("init replay must not prepare a second upload grant, got %d", objects.prepareCalls)
	}

	completeContext := commandmeta.WithIdempotencyKey(context.Background(), "upload-complete-1")
	completed, err := service.Complete(
		completeContext,
		sessionapp.CompleteCommand{
			SessionID: initialized.SessionID, OwnerID: "persona-1", AccessPolicy: "owner_only",
		},
	)
	if err != nil {
		t.Fatalf("complete media upload: %v", err)
	}
	if completed.Status != sessionmodel.StatusCompleted || completed.AssetID == "" {
		t.Fatalf("unexpected completed result: %+v", completed)
	}
	if store.completedAssetID != completed.AssetID || store.completeEventCount != 2 {
		t.Fatalf("completion must commit session and independent asset together: asset=%q events=%d", store.completedAssetID, store.completeEventCount)
	}
	if objects.completeCalls != 1 {
		t.Fatalf("expected one object-store promotion, got %d", objects.completeCalls)
	}
	replayedCompletion, err := service.Complete(
		completeContext,
		sessionapp.CompleteCommand{
			SessionID: initialized.SessionID, OwnerID: "persona-1", AccessPolicy: "owner_only",
		},
	)
	if err != nil {
		t.Fatalf("replay media upload completion: %v", err)
	}
	if !replayedCompletion.Replayed || replayedCompletion.AssetID != completed.AssetID {
		t.Fatalf("completion replay must retain the committed asset: %+v", replayedCompletion)
	}
	if objects.completeCalls != 1 {
		t.Fatalf("completion replay must not promote the object twice, got %d", objects.completeCalls)
	}

	session, err := service.Get(context.Background(), sessionapp.GetQuery{
		SessionID: initialized.SessionID, OwnerID: "persona-1",
	})
	if err != nil {
		t.Fatalf("get completed session: %v", err)
	}
	if session.AssetID != completed.AssetID || session.Status != sessionmodel.StatusCompleted {
		t.Fatalf("stored session must point to the atomically-created asset: %+v", session)
	}
}

func TestExpiredUploadInitRequiresANewDurableAttemptKey(t *testing.T) {
	t.Parallel()

	current := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	store := newMemoryStore()
	objects := &memoryObjectStore{now: current}
	sequence := 0
	service := sessionapp.NewUseCases(
		store,
		objects,
		sessionapp.WithClock(func() time.Time { return current }),
		sessionapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			sequence++
			return fmt.Sprintf("%s_%d", prefix, sequence), nil
		}),
	)
	command := sessionapp.InitCommand{
		OwnerID: "persona-expiry", MediaType: "image",
		ContentType: "image/jpeg", FileSize: 128, ExpectedSHA256: testSHA256,
	}
	first, err := service.Init(
		commandmeta.WithIdempotencyKey(context.Background(), "upload-expired-0"),
		command,
	)
	if err != nil {
		t.Fatalf("init expiring upload: %v", err)
	}
	current = first.ExpiresAt
	expired, err := service.Init(
		commandmeta.WithIdempotencyKey(context.Background(), "upload-expired-0"),
		command,
	)
	if err != nil {
		t.Fatalf("read expired upload replay: %v", err)
	}
	if !expired.Replayed ||
		expired.SessionID != first.SessionID ||
		expired.UploadURL != "" {
		t.Fatalf("expired replay must retain identity without a stale grant: %+v", expired)
	}

	restarted, err := service.Init(
		commandmeta.WithIdempotencyKey(context.Background(), "upload-expired-1"),
		command,
	)
	if err != nil {
		t.Fatalf("restart expired upload with new attempt key: %v", err)
	}
	if restarted.SessionID == first.SessionID || objects.prepareCalls != 2 {
		t.Fatalf(
			"expired upload did not open one new session: first=%+v restarted=%+v prepareCalls=%d",
			first,
			restarted,
			objects.prepareCalls,
		)
	}
}

func TestMediaUploadSessionAdmissionRejectsUnsupportedOrOversizedMediaBeforeObjectSideEffects(t *testing.T) {
	t.Parallel()

	for _, scenario := range []struct {
		name        string
		mediaType   string
		contentType string
		fileSize    int64
	}{
		{
			name:      "unsupported content type",
			mediaType: "image", contentType: "video/mp4", fileSize: 128,
		},
		{
			name:      "oversized file",
			mediaType: "image", contentType: "image/jpeg", fileSize: 1 << 62,
		},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			t.Parallel()

			objects := &memoryObjectStore{}
			service := sessionapp.NewUseCases(newMemoryStore(), objects)
			_, err := service.Init(
				commandmeta.WithIdempotencyKey(context.Background(), "admission-"+scenario.name),
				sessionapp.InitCommand{
					OwnerID:        "persona-1",
					MediaType:      scenario.mediaType,
					ContentType:    scenario.contentType,
					FileSize:       scenario.fileSize,
					ExpectedSHA256: testSHA256,
				},
			)

			if err == nil {
				t.Fatal("expected generated upload-policy admission rejection")
			}
			if objects.prepareCalls != 0 {
				t.Fatalf("rejected admission must not prepare an upload grant, got %d", objects.prepareCalls)
			}
		})
	}
}

func TestMediaUploadAbortPersistsIntentAndRetriesTemporaryCleanup(t *testing.T) {
	now := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	store := newMemoryStore()
	objects := &memoryObjectStore{
		now:       now,
		deleteErr: errors.New("temporary object store unavailable"),
	}
	service := sessionapp.NewUseCases(
		store,
		objects,
		sessionapp.WithClock(func() time.Time { return now }),
		sessionapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			return prefix + "_abort", nil
		}),
	)
	initialized, err := service.Init(
		commandmeta.WithIdempotencyKey(context.Background(), "upload-init-abort"),
		sessionapp.InitCommand{
			OwnerID: "persona-abort", MediaType: "image",
			ContentType: "image/jpeg", FileSize: 128,
			ExpectedSHA256: testSHA256,
		},
	)
	if err != nil {
		t.Fatalf("init upload before abort: %v", err)
	}
	abortContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"upload-abort-retry",
	)
	if _, err := service.Abort(abortContext, sessionapp.AbortCommand{
		SessionID: initialized.SessionID,
		OwnerID:   "persona-abort",
	}); err == nil {
		t.Fatal("first abort must report temporary cleanup failure")
	}
	persisted, err := service.Get(context.Background(), sessionapp.GetQuery{
		SessionID: initialized.SessionID,
		OwnerID:   "persona-abort",
	})
	if err != nil {
		t.Fatalf("read durably aborted session: %v", err)
	}
	if persisted.Status != sessionmodel.StatusAborted || objects.deleteCalls != 1 {
		t.Fatalf(
			"abort intent was not durable before cleanup: session=%+v calls=%d",
			persisted,
			objects.deleteCalls,
		)
	}
	objects.deleteErr = nil
	replayed, err := service.Abort(abortContext, sessionapp.AbortCommand{
		SessionID: initialized.SessionID,
		OwnerID:   "persona-abort",
	})
	if err != nil {
		t.Fatalf("retry aborted cleanup: %v", err)
	}
	if !replayed.Replayed || objects.deleteCalls != 2 {
		t.Fatalf(
			"abort retry must replay receipt and retry cleanup: result=%+v calls=%d",
			replayed,
			objects.deleteCalls,
		)
	}
}

const testSHA256 = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

type memoryObjectStore struct {
	now           time.Time
	prepareCalls  int
	completeCalls int
	deleteCalls   int
	deleteErr     error
}

func (s *memoryObjectStore) PrepareUpload(_ context.Context, params sessionapp.PrepareUploadParams) (sessionapp.UploadGrant, error) {
	s.prepareCalls++
	return sessionapp.UploadGrant{
		ObjectKey: "uploads/" + params.SessionID,
		UploadURL: "https://upload.example/" + params.SessionID,
		ExpiresAt: params.ExpiresAt,
	}, nil
}

func (s *memoryObjectStore) UploadURL(_ context.Context, objectKey, _, _ string, _ time.Time) (string, error) {
	return "https://upload.example/" + objectKey, nil
}

func (s *memoryObjectStore) CompleteUpload(_ context.Context, params sessionapp.CompleteUploadParams) (sessionapp.CompletedObject, error) {
	s.completeCalls++
	return sessionapp.CompletedObject{
		ObjectKey: "media/objects/" + strings.TrimPrefix(params.ExpectedSHA256, "sha256:"),
		SHA256:    params.ExpectedSHA256,
	}, nil
}

func (s *memoryObjectStore) DeleteTemporaryUpload(context.Context, string) error {
	s.deleteCalls++
	return s.deleteErr
}

type memoryStore struct {
	sessions           map[string]*sessionmodel.Session
	receipts           map[string]sessionports.Receipt
	completedAssetID   string
	completeEventCount int
}

func newMemoryStore() *memoryStore {
	return &memoryStore{
		sessions: map[string]*sessionmodel.Session{},
		receipts: map[string]sessionports.Receipt{},
	}
}

func (s *memoryStore) Load(_ context.Context, id string) (*sessionmodel.Session, bool, error) {
	session, found := s.sessions[id]
	return session, found, nil
}

func (s *memoryStore) FindForOwner(_ context.Context, id, ownerID string) (sessionmodel.Snapshot, bool, error) {
	session, found := s.sessions[id]
	if !found || session.OwnerID() != ownerID {
		return sessionmodel.Snapshot{}, false, nil
	}
	return session.Snapshot(), true, nil
}

func (s *memoryStore) FindReceipt(_ context.Context, key, commandName, commandDigest string) (sessionports.Receipt, bool, error) {
	receipt, found := s.receipts[receiptKey(key, commandName, commandDigest)]
	if found {
		receipt.Replayed = true
	}
	return receipt, found, nil
}

func (s *memoryStore) Commit(_ context.Context, commit sessionports.Commit) (sessionports.Receipt, error) {
	s.sessions[commit.Session.ID()] = commit.Session
	receipt := sessionports.Receipt{Session: commit.Session}
	s.receipts[receiptKey(commit.IdempotencyKey, commit.CommandName, commit.CommandDigest)] = receipt
	return receipt, nil
}

func (s *memoryStore) Complete(_ context.Context, commit sessionports.CompleteCommit) (sessionports.Receipt, error) {
	s.sessions[commit.Session.ID()] = commit.Session
	s.completedAssetID = commit.Asset.ID
	s.completeEventCount = len(commit.Events)
	receipt := sessionports.Receipt{
		Session:   commit.Session,
		AssetID:   commit.Asset.ID,
		ObjectKey: commit.Asset.ObjectKey,
	}
	s.receipts[receiptKey(commit.IdempotencyKey, commit.CommandName, commit.CommandDigest)] = receipt
	return receipt, nil
}

func receiptKey(key, commandName, commandDigest string) string {
	return key + "|" + commandName + "|" + commandDigest
}

var _ sessionapp.ObjectStore = (*memoryObjectStore)(nil)
var _ sessionports.Store = (*memoryStore)(nil)
