package tests

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	runtimesync "quwoquan_service/runtime/sync"
	chathttp "quwoquan_service/services/chat-service/internal/adapters/http"
	"quwoquan_service/services/chat-service/internal/adapters/mq"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type delayedFailingGroupAvatarAssetizer struct {
	delay time.Duration
}

func (f delayedFailingGroupAvatarAssetizer) Register(
	ctx context.Context,
	req runtimemedia.RegisterGroupAvatarRequest,
) (runtimemedia.DerivedAvatarAsset, error) {
	if f.delay > 0 {
		time.Sleep(f.delay)
	}
	return runtimemedia.DerivedAvatarAsset{}, errors.New("runtime/media register failed")
}

type flakyGroupAvatarAssetizer struct {
	mu       sync.Mutex
	failures int
	delegate application.GroupAvatarAssetizer
}

func (f *flakyGroupAvatarAssetizer) Register(
	ctx context.Context,
	req runtimemedia.RegisterGroupAvatarRequest,
) (runtimemedia.DerivedAvatarAsset, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failures > 0 {
		f.failures--
		return runtimemedia.DerivedAvatarAsset{}, errors.New("transient runtime/media register failure")
	}
	return f.delegate.Register(ctx, req)
}

type flakyUserSyncPublisher struct {
	mu           sync.Mutex
	failuresLeft map[string]int
	delegate     *runtimesync.Service
}

func (f *flakyUserSyncPublisher) AppendPatch(
	ctx context.Context,
	userID string,
	patchType string,
	payload map[string]any,
) (runtimesync.Patch, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if remaining := f.failuresLeft[userID]; remaining > 0 {
		f.failuresLeft[userID] = remaining - 1
		return runtimesync.Patch{}, errors.New("transient sync append failure")
	}
	return f.delegate.AppendPatch(ctx, userID, patchType, payload)
}

func (f *flakyUserSyncPublisher) AppendPatchBatch(
	ctx context.Context,
	userIDs []string,
	patchType string,
	payload map[string]any,
) (runtimesync.BatchAppendResult, error) {
	failedUserIDs := make([]string, 0)
	succeededUserIDs := make([]string, 0, len(userIDs))
	for _, userID := range userIDs {
		f.mu.Lock()
		remaining := f.failuresLeft[userID]
		if remaining > 0 {
			f.failuresLeft[userID] = remaining - 1
			f.mu.Unlock()
			failedUserIDs = append(failedUserIDs, userID)
			continue
		}
		f.mu.Unlock()
		succeededUserIDs = append(succeededUserIDs, userID)
	}
	result, err := f.delegate.AppendPatchBatch(ctx, succeededUserIDs, patchType, payload)
	if err != nil {
		return runtimesync.BatchAppendResult{}, err
	}
	result.FailedUserIDs = append(result.FailedUserIDs, failedUserIDs...)
	return result, nil
}

func newGroupAvatarTestHandler(
	t *testing.T,
	media application.GroupAvatarAssetizer,
	syncPublisher application.UserSyncPublisher,
) (http.Handler, *runtimesync.Service) {
	t.Helper()
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	userSyncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	if syncPublisher == nil {
		syncPublisher = userSyncService
	}
	eventPublisher := mq.NewEventPublisher(redisRouter.Scene("realtime"))
	scheduler := application.NewRedisGroupAvatarTaskScheduler(
		redisRouter.Scene("general"),
		chatStore,
		eventPublisher,
		media,
		syncPublisher,
		nil,
	)
	schedulerCtx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	_ = scheduler.Start(schedulerCtx)
	profiles := testProfileResolver{}
	conversationSvc := application.NewConversationService(
		chatStore,
		convCache,
		eventPublisher,
		profiles,
		media,
		syncPublisher,
		scheduler,
	)
	memberSvc := application.NewMemberService(
		chatStore,
		convCache,
		eventPublisher,
		profiles,
		media,
		syncPublisher,
		scheduler,
	)
	messageSvc := application.NewMessageService(chatStore, convCache, eventPublisher)
	inboxSvc := application.NewInboxService(chatStore)
	return chathttp.NewChatHandler(conversationSvc, messageSvc, memberSvc, inboxSvc).Routes(), userSyncService
}

func doHandlerJSON(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	payload string,
	userID string,
	expectedStatus int,
) map[string]any {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(payload))
	if method == http.MethodPost || method == http.MethodPatch || method == http.MethodPut {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("X-Client-User-Id", userID)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != expectedStatus {
		t.Fatalf("%s %s: expected %d, got %d: %s", method, path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return result
}

func TestGroupAvatar_CreateConversationReturnsBeforeSlowRecomputeFailure(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, syncService := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 250 * time.Millisecond}, nil)
	start := time.Now()
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"async create failure"}`,
		"user_test_001",
		http.StatusCreated,
	)
	elapsed := time.Since(start)
	if elapsed >= 200*time.Millisecond {
		t.Fatalf("expected create conversation to return before async recompute, elapsed=%s", elapsed)
	}

	convID := created["_id"].(string)
	time.Sleep(320 * time.Millisecond)

	_, detail := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if version, _ := detail["groupAvatarVersion"].(float64); int(version) != 0 {
		t.Fatalf("expected groupAvatarVersion to remain 0 after failed first recompute, got %v", detail["groupAvatarVersion"])
	}
	if groupAvatarURL, _ := detail["groupAvatarUrl"].(string); groupAvatarURL != "" {
		t.Fatalf("expected empty groupAvatarUrl after failed first recompute, got %q", groupAvatarURL)
	}

	resp, err := syncService.Pull(context.Background(), "user_test_001", 0, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no avatar patches after failed create recompute, got %d", len(resp.Patches))
	}
}

func TestGroupAvatar_AddMembersFailureDoesNotBlockOrCorruptExistingAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"async add failure","initialMemberIds":["user_test_002"]}`)
	convID := conv["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	_, before := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	beforeVersion := int(before["groupAvatarVersion"].(float64))
	beforeURL := before["groupAvatarUrl"].(string)
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	handler, _ := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 250 * time.Millisecond}, nil)
	start := time.Now()
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_003"]}`,
		"user_test_001",
		http.StatusOK,
	)
	elapsed := time.Since(start)
	if elapsed >= 200*time.Millisecond {
		t.Fatalf("expected add members to return before async recompute, elapsed=%s", elapsed)
	}

	time.Sleep(320 * time.Millisecond)
	_, after := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if got := int(after["groupAvatarVersion"].(float64)); got != beforeVersion {
		t.Fatalf("expected avatar version unchanged after failed async add recompute, before=%d after=%d", beforeVersion, got)
	}
	if got := after["groupAvatarUrl"].(string); got != beforeURL {
		t.Fatalf("expected avatar url unchanged after failed async add recompute, before=%q after=%q", beforeURL, got)
	}

	resp, err := syncService.Pull(context.Background(), "user_test_001", beforeSeq, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no avatar patch after failed async add recompute, got %d", len(resp.Patches))
	}
}

func TestGroupAvatar_RemoveMemberFailureDoesNotBlockOrCorruptExistingAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"async remove failure","initialMemberIds":["user_test_002","user_test_003"]}`)
	convID := conv["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	_, before := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	beforeVersion := int(before["groupAvatarVersion"].(float64))
	beforeURL := before["groupAvatarUrl"].(string)
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	handler, _ := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 250 * time.Millisecond}, nil)
	start := time.Now()
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/v1/chat/conversations/"+convID+"/members/user_test_003",
		"",
		"user_test_001",
		http.StatusOK,
	)
	elapsed := time.Since(start)
	if elapsed >= 200*time.Millisecond {
		t.Fatalf("expected remove member to return before async recompute, elapsed=%s", elapsed)
	}

	time.Sleep(320 * time.Millisecond)
	_, after := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if got := int(after["groupAvatarVersion"].(float64)); got != beforeVersion {
		t.Fatalf("expected avatar version unchanged after failed async remove recompute, before=%d after=%d", beforeVersion, got)
	}
	if got := after["groupAvatarUrl"].(string); got != beforeURL {
		t.Fatalf("expected avatar url unchanged after failed async remove recompute, before=%q after=%q", beforeURL, got)
	}

	resp, err := syncService.Pull(context.Background(), "user_test_001", beforeSeq, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no avatar patch after failed async remove recompute, got %d", len(resp.Patches))
	}
}

func TestGroupAvatar_RecomputeWorkerRetriesUntilSuccess(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	assetizer := &flakyGroupAvatarAssetizer{
		failures: 2,
		delegate: runtimemedia.NewGroupAvatarService(redisRouter.Scene("general"), ""),
	}
	handler, _ := newGroupAvatarTestHandler(t, assetizer, nil)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"retry until success"}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
}

func TestGroupAvatar_PatchFanoutRetriesAfterTransientFailure(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	delegate := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	flakyPublisher := &flakyUserSyncPublisher{
		failuresLeft: map[string]int{
			"user_test_001": 1,
		},
		delegate: delegate,
	}
	handler, syncService := newGroupAvatarTestHandler(
		t,
		runtimemedia.NewGroupAvatarService(redisRouter.Scene("general"), ""),
		flakyPublisher,
	)

	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"patch retry","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)

	for i := 0; i < 40; i++ {
		resp, err := syncService.Pull(context.Background(), "user_test_001", 0, 20)
		if err != nil {
			t.Fatalf("Pull: %v", err)
		}
		if len(resp.Patches) > 0 {
			last := resp.Patches[len(resp.Patches)-1]
			if last.Type == "conversation.avatar.updated" && last.Payload["conversationId"] == convID {
				return
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("expected patch fanout retry to eventually deliver conversation.avatar.updated")
}
