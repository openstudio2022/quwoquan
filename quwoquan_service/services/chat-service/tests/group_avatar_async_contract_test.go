package tests

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/runtime/reliabletask"
	runtimesync "quwoquan_service/runtime/sync"
	chathttp "quwoquan_service/services/chat-service/internal/adapters/http"
	"quwoquan_service/services/chat-service/internal/adapters/mq"
	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
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

type countingGroupAvatarAssetizer struct {
	mu       sync.Mutex
	calls    int
	delegate application.GroupAvatarAssetizer
}

func (c *countingGroupAvatarAssetizer) Register(
	ctx context.Context,
	req runtimemedia.RegisterGroupAvatarRequest,
) (runtimemedia.DerivedAvatarAsset, error) {
	c.mu.Lock()
	c.calls++
	c.mu.Unlock()
	return c.delegate.Register(ctx, req)
}

func (c *countingGroupAvatarAssetizer) Calls() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.calls
}

type flakyUserSyncPublisher struct {
	mu           sync.Mutex
	failuresLeft map[string]int
	delegate     *runtimesync.Service
}

type failingGroupAvatarScheduler struct{}

func (failingGroupAvatarScheduler) EnqueueRecompute(context.Context, application.GroupAvatarRecomputeTask) error {
	return errors.New("injected reliable task outbox failure")
}

func (failingGroupAvatarScheduler) EnqueueConversationAvatarPatch(context.Context, application.ConversationAvatarPatchTask) error {
	return errors.New("injected notification outbox failure")
}

type completeTaskFailOnceStore struct {
	*reliabletask.MongoStore
	mu       sync.Mutex
	failures int
}

type completeNotificationFailOnceStore struct {
	*reliabletask.MongoStore
	mu       sync.Mutex
	failures int
}

func (s *completeTaskFailOnceStore) CompleteTask(ctx context.Context, taskID string, leaseToken string) error {
	s.mu.Lock()
	if s.failures > 0 {
		s.failures--
		s.mu.Unlock()
		return errors.New("injected task ack failure")
	}
	s.mu.Unlock()
	return s.MongoStore.CompleteTask(ctx, taskID, leaseToken)
}

func (s *completeNotificationFailOnceStore) CompleteNotification(ctx context.Context, notificationID string, leaseToken string) error {
	s.mu.Lock()
	if s.failures > 0 {
		s.failures--
		s.mu.Unlock()
		return errors.New("injected notification ack failure")
	}
	s.mu.Unlock()
	return s.MongoStore.CompleteNotification(ctx, notificationID, leaseToken)
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
	return newGroupAvatarTestHandlerWithStore(t, media, syncPublisher, reliabletask.NewMongoStore(mongoDB))
}

func newGroupAvatarTestHandlerWithStore(
	t *testing.T,
	media application.GroupAvatarAssetizer,
	syncPublisher application.UserSyncPublisher,
	reliableTaskStore reliabletask.Store,
	opts ...application.ReliableGroupAvatarSchedulerOption,
) (http.Handler, *runtimesync.Service) {
	handler, syncService, _ := newGroupAvatarTestHandlerWithStoreAndScheduler(t, media, syncPublisher, reliableTaskStore, opts...)
	return handler, syncService
}

func newGroupAvatarTestHandlerWithStoreAndScheduler(
	t *testing.T,
	media application.GroupAvatarAssetizer,
	syncPublisher application.UserSyncPublisher,
	reliableTaskStore reliabletask.Store,
	opts ...application.ReliableGroupAvatarSchedulerOption,
) (http.Handler, *runtimesync.Service, *application.ReliableGroupAvatarTaskScheduler) {
	t.Helper()
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	userSyncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	if syncPublisher == nil {
		syncPublisher = userSyncService
	}
	eventPublisher := mq.NewEventPublisher(redisRouter.Scene("realtime"))
	catalog, err := reliabletask.LoadCatalog("../../../../deploy/shared/reliable_task_module_catalog.yaml")
	if err != nil {
		t.Fatalf("load reliable task catalog: %v", err)
	}
	if err := reliableTaskStore.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure reliable task indexes: %v", err)
	}
	readyIndex, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: redisRouter.Scene("reliabletask"),
		Stream: "reliabletask:chat:avatar:ready:test",
		Group:  "chat.group_avatar_worker.test",
		Queue:  "reliabletask.chat.avatar",
	})
	if err != nil {
		t.Fatalf("new redis ready index: %v", err)
	}
	if err := readyIndex.Ensure(context.Background()); err != nil {
		t.Fatalf("ensure redis ready index: %v", err)
	}
	schedulerOpts := []application.ReliableGroupAvatarSchedulerOption{
		application.WithReliableGroupAvatarDelay(80 * time.Millisecond),
		application.WithReliableGroupAvatarTick(40 * time.Millisecond),
		application.WithReliableGroupAvatarReadyIndex(readyIndex),
	}
	schedulerOpts = append(schedulerOpts, opts...)
	scheduler := application.NewReliableGroupAvatarTaskScheduler(
		reliableTaskStore,
		catalog,
		chatStore,
		eventPublisher,
		media,
		syncPublisher,
		nil,
		schedulerOpts...,
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
	return chathttp.NewChatHandler(conversationSvc, messageSvc, memberSvc, inboxSvc).Routes(), userSyncService, scheduler
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

func TestGroupAvatar_CreateConversationReturnsDefaultBeforeAsyncAvatarReady(t *testing.T) {
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
	if elapsed := time.Since(start); elapsed >= 200*time.Millisecond {
		t.Fatalf("expected create conversation to return before async recompute, elapsed=%s", elapsed)
	}
	if got := strings.TrimSpace(created["avatarUrl"].(string)); got != "https://test.avatar/user_test_001" {
		t.Fatalf("expected creator avatar url on create, got %q", got)
	}
	if got := int(created["groupAvatarVersion"].(float64)); got != 0 {
		t.Fatalf("expected groupAvatarVersion 0 before async recompute, got %d", got)
	}

	resp, err := syncService.Pull(context.Background(), "user_test_001", 0, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no avatar patches after failed create recompute, got %d", len(resp.Patches))
	}
}

func TestGroupAvatar_RecomputeCoalescesEarlyMemberAdds(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	assetizer := &countingGroupAvatarAssetizer{
		delegate: runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
	}
	handler, _ := newGroupAvatarTestHandler(t, assetizer, nil)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"coalesce early joins"}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_003"]}`,
		"user_test_001",
		http.StatusOK,
	)

	waitForConversationAvatarVersion(t, convID, 1)
	time.Sleep(700 * time.Millisecond)
	if got := assetizer.Calls(); got != 1 {
		t.Fatalf("expected early create/add recomputes to coalesce into one render, got %d", got)
	}
}

func TestGroupAvatar_AddMembersFailureDoesNotBlockOrCorruptExistingAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"async add failure","initialMemberIds":["user_test_002"]}`)
	convID := conv["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	_, before := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	beforeVersion := int(before["groupAvatarVersion"].(float64))
	beforeURL := before["avatarUrl"].(string)
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

	time.Sleep(900 * time.Millisecond)
	_, after := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if got := int(after["groupAvatarVersion"].(float64)); got != beforeVersion {
		t.Fatalf("expected avatar version unchanged after failed async add recompute, before=%d after=%d", beforeVersion, got)
	}
	if got := after["avatarUrl"].(string); got != beforeURL {
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
	beforeURL := before["avatarUrl"].(string)
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

	time.Sleep(900 * time.Millisecond)
	_, after := doGet(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if got := int(after["groupAvatarVersion"].(float64)); got != beforeVersion {
		t.Fatalf("expected avatar version unchanged after failed async remove recompute, before=%d after=%d", beforeVersion, got)
	}
	if got := after["avatarUrl"].(string); got != beforeURL {
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
		delegate: runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
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
		runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
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

	deliveredAfterRetry := false
	for i := 0; i < 40; i++ {
		resp, err := syncService.Pull(context.Background(), "user_test_001", 0, 20)
		if err != nil {
			t.Fatalf("Pull: %v", err)
		}
		if len(resp.Patches) > 0 {
			last := resp.Patches[len(resp.Patches)-1]
			if last.Type == "conversation.avatar.updated" && last.Payload["conversationId"] == convID {
				deliveredAfterRetry = true
				break
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	if !deliveredAfterRetry {
		t.Fatal("expected patch fanout retry to eventually deliver conversation.avatar.updated")
	}
	resp, err := syncService.Pull(context.Background(), "user_test_002", 0, 20)
	if err != nil {
		t.Fatalf("Pull user_test_002: %v", err)
	}
	patchCount := 0
	for _, patch := range resp.Patches {
		if patch.Type == "conversation.avatar.updated" && patch.Payload["conversationId"] == convID {
			patchCount++
		}
	}
	if patchCount != 1 {
		t.Fatalf("expected delivered recipient to receive one avatar patch, got %d", patchCount)
	}
}

func TestGroupAvatar_ReliableTaskOutboxToMemberSyncEndToEnd(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, syncService := newGroupAvatarTestHandler(
		t,
		runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
		nil,
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"reliable e2e","initialMemberIds":["user_test_002","user_test_003"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)

	waitForCollectionCount(t, "reliable_task_outbox", bson.M{
		"taskType":    "chat.group_avatar.recompute",
		"aggregateId": convID,
	}, 1)
	waitForConversationAvatarVersion(t, convID, 1)
	waitForCollectionCount(t, "notification_outbox", bson.M{
		"eventType":   "conversation.avatar.updated",
		"aggregateId": convID,
		"status":      reliabletask.NotificationStatusSucceeded,
	}, 1)
	waitForCollectionCount(t, "notification_delivery_ledger", bson.M{
		"eventType": "conversation.avatar.updated",
		"status":    reliabletask.RecipientStatusDelivered,
	}, 3)
	for _, userID := range []string{"user_test_001", "user_test_002", "user_test_003"} {
		waitForAvatarPatch(t, syncService, userID, convID)
	}
}

func TestGroupAvatar_TaskAckFailureReplaysAndCompletesIdempotently(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	store := &completeTaskFailOnceStore{
		MongoStore: reliabletask.NewMongoStore(mongoDB),
		failures:   1,
	}
	handler, syncService := newGroupAvatarTestHandlerWithStore(
		t,
		runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
		nil,
		store,
		application.WithReliableGroupAvatarLeaseTTL(80*time.Millisecond),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"ack replay","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	waitForCollectionCount(t, "reliable_async_task", bson.M{
		"taskType":    "chat.group_avatar.recompute",
		"aggregateId": convID,
		"status":      reliabletask.TaskStatusSucceeded,
	}, 1)
	waitForCollectionCount(t, "notification_outbox", bson.M{
		"eventType":   "conversation.avatar.updated",
		"aggregateId": convID,
		"status":      reliabletask.NotificationStatusSucceeded,
	}, 1)
	waitForAvatarPatch(t, syncService, "user_test_001", convID)
	waitForAvatarPatch(t, syncService, "user_test_002", convID)
}

func TestGroupAvatar_NotificationAckFailureReplaysLedgerWithoutDuplicatePatch(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	store := &completeNotificationFailOnceStore{
		MongoStore: reliabletask.NewMongoStore(mongoDB),
		failures:   1,
	}
	handler, syncService := newGroupAvatarTestHandlerWithStore(
		t,
		runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
		nil,
		store,
		application.WithReliableGroupAvatarLeaseTTL(80*time.Millisecond),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"notification ack replay","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	waitForCollectionCount(t, "notification_outbox", bson.M{
		"eventType":   "conversation.avatar.updated",
		"aggregateId": convID,
		"status":      reliabletask.NotificationStatusSucceeded,
	}, 1)

	for _, userID := range []string{"user_test_001", "user_test_002"} {
		resp, err := syncService.Pull(context.Background(), userID, 0, 20)
		if err != nil {
			t.Fatalf("Pull %s: %v", userID, err)
		}
		patchCount := 0
		for _, patch := range resp.Patches {
			if patch.Type == "conversation.avatar.updated" && patch.Payload["conversationId"] == convID {
				patchCount++
			}
		}
		if patchCount != 1 {
			t.Fatalf("expected one avatar patch for %s after notification ack replay, got %d", userID, patchCount)
		}
	}
}

func TestGroupAvatar_SourceHashReplayRecreatesMissingNotification(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, syncService, scheduler := newGroupAvatarTestHandlerWithStoreAndScheduler(
		t,
		runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
		nil,
		reliabletask.NewMongoStore(mongoDB),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"notification compensation","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	waitForAvatarPatch(t, syncService, "user_test_001", convID)

	if _, err := mongoDB.Collection("notification_delivery_ledger").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatalf("delete ledgers: %v", err)
	}
	if _, err := mongoDB.Collection("notification_outbox").DeleteMany(context.Background(), bson.M{"aggregateId": convID}); err != nil {
		t.Fatalf("delete notifications: %v", err)
	}
	if err := scheduler.EnqueueRecompute(context.Background(), application.GroupAvatarRecomputeTask{
		ConversationID: convID,
		ActorID:        "user_test_001",
		Trigger:        "test.notification_missing",
	}); err != nil {
		t.Fatalf("enqueue recompute: %v", err)
	}
	waitForCollectionCount(t, "notification_outbox", bson.M{
		"eventType":   "conversation.avatar.updated",
		"aggregateId": convID,
		"status":      reliabletask.NotificationStatusSucceeded,
	}, 1)
	waitForCollectionCount(t, "notification_delivery_ledger", bson.M{
		"eventType": "conversation.avatar.updated",
		"status":    reliabletask.RecipientStatusDelivered,
	}, 2)
}

func TestGroupAvatar_CreateConversationRollsBackWhenOutboxFails(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	conversationSvc := application.NewConversationService(
		chatStore,
		convCache,
		nil,
		testProfileResolver{},
		nil,
		nil,
		failingGroupAvatarScheduler{},
	)
	_, err := conversationSvc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:      "group",
		Title:     "rollback create",
		CreatorId: "user_test_001",
	})
	if err == nil {
		t.Fatal("expected create conversation to fail when outbox write fails")
	}
	waitForExactCollectionCount(t, "conversations", bson.M{"title": "rollback create"}, 0)
	waitForExactCollectionCount(t, "conversation_members", bson.M{"userId": "user_test_001"}, 0)
	waitForExactCollectionCount(t, "reliable_task_outbox", bson.M{"taskType": "chat.group_avatar.recompute"}, 0)
}

func TestGroupAvatar_AddMembersRollsBackWhenOutboxFails(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(t, `{"type":"group","title":"rollback add"}`)
	convID := created["_id"].(string)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	memberSvc := application.NewMemberService(
		chatStore,
		convCache,
		nil,
		testProfileResolver{},
		nil,
		nil,
		failingGroupAvatarScheduler{},
	)
	err := memberSvc.AddMembers(context.Background(), application.AddMembersRequest{
		ConversationId: convID,
		UserIds:        []string{"user_test_009"},
		InvitedBy:      "user_test_001",
	})
	if err == nil {
		t.Fatal("expected add members to fail when outbox write fails")
	}
	waitForExactCollectionCount(t, "conversation_members", bson.M{
		"conversationId": convID,
		"userId":         "user_test_009",
	}, 0)
}

func TestGroupAvatar_RemoveMemberRollsBackWhenOutboxFails(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(t, `{"type":"group","title":"rollback remove","initialMemberIds":["user_test_002"]}`)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	memberSvc := application.NewMemberService(
		chatStore,
		convCache,
		nil,
		testProfileResolver{},
		nil,
		nil,
		failingGroupAvatarScheduler{},
	)
	err := memberSvc.RemoveMember(context.Background(), convID, "user_test_002")
	if err == nil {
		t.Fatal("expected remove member to fail when outbox write fails")
	}
	waitForExactCollectionCount(t, "conversation_members", bson.M{
		"conversationId": convID,
		"userId":         "user_test_002",
	}, 1)
}

func TestGroupAvatar_AddRemoveStormUsesLatestTopNineSourceHash(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, _ := newGroupAvatarTestHandler(
		t,
		runtimemedia.NewGroupAvatarService(
			redisRouter.Scene("general"),
			"http://127.0.0.1:18081",
			testChatMediaRoot,
		),
		nil,
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations",
		`{"type":"group","title":"add remove storm","initialMemberIds":["user_test_002","user_test_003","user_test_004","user_test_005","user_test_006","user_test_007","user_test_008","user_test_009","user_test_010"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["_id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_011","user_test_012","user_test_013","user_test_014"]}`,
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/v1/chat/conversations/"+convID+"/members/user_test_003",
		"",
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/v1/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_015"]}`,
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/v1/chat/conversations/"+convID+"/members/user_test_002",
		"",
		"user_test_001",
		http.StatusOK,
	)

	chatStore := persistence.NewMongoChatStore(mongoDB)
	for i := 0; i < 100; i++ {
		conv, err := chatStore.FindConversationByID(context.Background(), convID)
		if err != nil {
			t.Fatalf("find conversation: %v", err)
		}
		members, err := chatStore.ListMembers(context.Background(), convID, 200, "", "", persistence.SortMembersJoinedAsc)
		if err != nil {
			t.Fatalf("list members: %v", err)
		}
		top9 := make([]model.ConversationMember, 0, 9)
		for _, member := range members {
			if strings.TrimSpace(member.MemberType) != "user" {
				continue
			}
			top9 = append(top9, member)
			if len(top9) >= 9 {
				break
			}
		}
		expectedHash := application.BuildGroupAvatarSourceHash(top9)
		if expectedHash == conv.GroupAvatarSourceHash && conv.GroupAvatarVersion >= 2 {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("expected add/remove storm to converge to latest top9 group avatar source hash")
}

func TestGroupAvatar_RedisReadyIndexAlphaBetaLocalLoop(t *testing.T) {
	for _, env := range []string{"alpha", "beta"} {
		t.Run(env, func(t *testing.T) {
			cleanAll(t)
			readyIndex, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
				Client: redisRouter.Scene("reliabletask"),
				Stream: "reliabletask:chat:avatar:ready:" + env,
				Group:  "chat.group_avatar_worker." + env,
				Queue:  "reliabletask.chat.avatar",
			})
			if err != nil {
				t.Fatalf("new redis ready index: %v", err)
			}
			if err := readyIndex.Ensure(context.Background()); err != nil {
				t.Fatalf("ensure redis ready index: %v", err)
			}
			handler, syncService, _ := newGroupAvatarTestHandlerWithStoreAndScheduler(
				t,
				runtimemedia.NewGroupAvatarService(
					redisRouter.Scene("general"),
					"http://127.0.0.1:18081",
					testChatMediaRoot,
				),
				nil,
				reliabletask.NewMongoStore(mongoDB),
				application.WithReliableGroupAvatarRuntimeIdentity(env, "chat-service-"+env),
				application.WithReliableGroupAvatarReadyIndex(readyIndex),
			)
			created := doHandlerJSON(
				t,
				handler,
				http.MethodPost,
				"/v1/chat/conversations",
				`{"type":"group","title":"ready index `+env+`","initialMemberIds":["user_test_002","user_test_003"]}`,
				"user_test_001",
				http.StatusCreated,
			)
			convID := created["_id"].(string)
			waitForConversationAvatarVersion(t, convID, 1)
			for _, userID := range []string{"user_test_001", "user_test_002", "user_test_003"} {
				waitForAvatarPatch(t, syncService, userID, convID)
			}
			waitForExactCollectionCount(t, "reliable_async_task", bson.M{
				"taskType": "chat.group_avatar.recompute",
				"status":   reliabletask.TaskStatusSucceeded,
			}, 1)
		})
	}
}

func waitForCollectionCount(t *testing.T, collection string, filter bson.M, expectedMin int64) {
	t.Helper()
	for i := 0; i < 100; i++ {
		count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), filter)
		if err != nil {
			t.Fatalf("count %s: %v", collection, err)
		}
		if count >= expectedMin {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("collection %s did not reach count %d for filter %#v", collection, expectedMin, filter)
}

func waitForExactCollectionCount(t *testing.T, collection string, filter bson.M, expected int64) {
	t.Helper()
	count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), filter)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if count != expected {
		t.Fatalf("collection %s count = %d, want %d for filter %#v", collection, count, expected, filter)
	}
}

func waitForAvatarPatch(t *testing.T, syncService *runtimesync.Service, userID string, convID string) {
	t.Helper()
	for i := 0; i < 100; i++ {
		resp, err := syncService.Pull(context.Background(), userID, 0, 20)
		if err != nil {
			t.Fatalf("Pull for %s: %v", userID, err)
		}
		for _, patch := range resp.Patches {
			if patch.Type == "conversation.avatar.updated" && patch.Payload["conversationId"] == convID {
				if strings.TrimSpace(fmt.Sprint(patch.Payload["avatarUrl"])) == "" {
					t.Fatalf("avatar patch for %s missing avatarUrl: %#v", userID, patch.Payload)
				}
				return
			}
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("user %s did not receive conversation.avatar.updated for %s", userID, convID)
}
