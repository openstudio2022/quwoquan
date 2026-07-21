package api_integration

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

	"quwoquan_service/internal/platform/reliabletaskmongo"
	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/runtime/operation"
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
	*reliabletaskmongo.Store
	mu       sync.Mutex
	failures int
}

type completeNotificationFailOnceStore struct {
	*reliabletaskmongo.Store
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
	return s.Store.CompleteTask(ctx, taskID, leaseToken)
}

func (s *completeNotificationFailOnceStore) CompleteNotification(ctx context.Context, notificationID string, leaseToken string) error {
	s.mu.Lock()
	if s.failures > 0 {
		s.failures--
		s.mu.Unlock()
		return errors.New("injected notification ack failure")
	}
	s.mu.Unlock()
	return s.Store.CompleteNotification(ctx, notificationID, leaseToken)
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
	return newGroupAvatarTestHandlerWithStore(t, media, syncPublisher, reliabletaskmongo.New(mongoDB))
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
	chatStorage := chatStoragePorts(chatStore)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	userSyncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	if syncPublisher == nil {
		syncPublisher = userSyncService
	}
	eventPublisher := mq.NewEventPublisher(
		redisRouter.Scene("realtime"),
		redisRouter.Scene("general"),
		mq.NewMemberRecipientResolver(func(ctx context.Context, conversationID string) ([]string, error) {
			members, err := chatStore.ListMembers(
				ctx,
				conversationID,
				application.ListMembersQuery{Limit: 512, Sort: application.MemberListSortJoinedAsc},
			)
			if err != nil {
				return nil, err
			}
			ids := make([]string, 0, len(members))
			for _, member := range members {
				ids = append(ids, member.UserId)
			}
			return ids, nil
		}),
	)
	catalog, err := reliabletask.LoadCatalog(testReliableTaskCatalogPath())
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
		chatStorage,
		eventPublisher,
		media,
		syncPublisher,
		nil,
		schedulerOpts...,
	)
	schedulerCtx, cancel := context.WithCancel(context.Background())
	if err := scheduler.Start(schedulerCtx); err != nil {
		cancel()
		t.Fatalf("start reliable group avatar scheduler: %v", err)
	}
	t.Cleanup(func() {
		cancel()
		waitCtx, waitCancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer waitCancel()
		if err := scheduler.WaitForStop(waitCtx); err != nil {
			t.Errorf("wait reliable group avatar scheduler stop: %v", err)
		}
	})
	profiles := testProfileResolver{}
	conversationSvc := application.NewConversationService(
		chatStorage,
		convCache,
		eventPublisher,
		profiles,
		application.AllowRelationshipGateForTest(),
		media,
		syncPublisher,
		scheduler,
	)
	memberSvc := application.NewMemberService(
		chatStorage,
		convCache,
		eventPublisher,
		profiles,
		media,
		syncPublisher,
		scheduler,
		application.WithRelationshipGate(application.AllowRelationshipGateForTest()),
	)
	messageSvc := application.NewMessageService(
		chatStorage,
		convCache,
		eventPublisher,
		application.AllowRelationshipGateForTest(),
		testMediaAssetDeliveryReader{},
	)
	inboxSvc := application.NewInboxService(chatStorage)
	return chathttp.NewChatHandler(
		conversationSvc,
		messageSvc,
		memberSvc,
		inboxSvc,
		userSyncService,
	).Routes(), userSyncService, scheduler
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
	if method != http.MethodGet && method != http.MethodHead {
		req = commandOperationContext(req, path, userID)
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != expectedStatus {
		t.Fatalf("%s %s: expected %d, got %d: %s", method, path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return result
}

func TestGroupAvatar_CreateConversationReturnsCreatorAvatarBeforeAsyncAvatarReady(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, syncService := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 500 * time.Millisecond}, nil)
	start := time.Now()
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"async create failure"}`,
		"user_test_001",
		http.StatusCreated,
	)
	if elapsed := time.Since(start); elapsed >= 400*time.Millisecond {
		t.Fatalf("expected create conversation to return before async recompute, elapsed=%s", elapsed)
	}
	if got, want := strings.TrimSpace(created["avatarUrl"].(string)), "https://test.avatar/user_test_001"; got != want {
		t.Fatalf("expected creator avatar url on create, got %q want %q", got, want)
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

func TestGroupAvatar_DeprecatedMemberAvatarURLFallsBackToCreatorAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, _ := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 250 * time.Millisecond}, nil)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"stale polluted avatar","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	conv, err := chatStore.FindConversationByID(context.Background(), convID)
	if err != nil {
		t.Fatalf("find conversation: %v", err)
	}
	conv.AvatarUrl = "https://test.avatar/user_test_002"
	conv.GroupAvatarAssetId = ""
	conv.GroupAvatarVersion = 0
	conv.GroupAvatarSourceHash = ""
	if err := chatStore.UpdateConversation(context.Background(), convID, conv); err != nil {
		t.Fatalf("update polluted conversation: %v", err)
	}

	detail := doHandlerJSON(
		t,
		handler,
		http.MethodGet,
		"/chat/conversations/"+convID,
		"",
		"user_test_001",
		http.StatusOK,
	)
	if got, want := strings.TrimSpace(detail["avatarUrl"].(string)), "https://test.avatar/user_test_001"; got != want {
		t.Fatalf("expected creator avatar fallback, got %q want %q", got, want)
	}
	inbox := doHandlerJSON(
		t,
		handler,
		http.MethodGet,
		"/chat/inbox?limit=20",
		"",
		"user_test_002",
		http.StatusOK,
	)
	row := findInboxRow(t, inbox["items"], convID)
	if got, want := strings.TrimSpace(row["avatarUrl"].(string)), "https://test.avatar/user_test_001"; got != want {
		t.Fatalf("expected creator avatar fallback in inbox, got %q want %q", got, want)
	}
}

func TestGroupAvatar_RecomputeCoalescesEarlyMemberAdds(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	assetizer := &countingGroupAvatarAssetizer{
		delegate: newGroupAvatarMediaForContractTest(),
	}
	handler, _ := newGroupAvatarTestHandlerWithStore(
		t,
		assetizer,
		nil,
		reliabletaskmongo.New(mongoDB),
		application.WithReliableGroupAvatarDelay(300*time.Millisecond),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"coalesce early joins"}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_003"]}`,
		"user_test_001",
		http.StatusOK,
	)

	waitForConversationAvatarVersionFromBackground(t, convID, 1)
	time.Sleep(700 * time.Millisecond)
	if got := assetizer.Calls(); got != 1 {
		t.Fatalf("expected early create/add recomputes to coalesce into one render, got %d", got)
	}
}

func TestGroupAvatar_AddMembersFailureDoesNotBlockOrCorruptExistingAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"async add failure","initialMemberIds":["user_test_002"]}`)
	convID := conv["id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	_, before := doGet(t, "/chat/conversations/"+convID, "user_test_001")
	beforeVersion := int(before["groupAvatarVersion"].(float64))
	beforeURL := before["avatarUrl"].(string)
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	handler, _ := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 500 * time.Millisecond}, nil)
	start := time.Now()
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_003"]}`,
		"user_test_001",
		http.StatusOK,
	)
	elapsed := time.Since(start)
	if elapsed >= 400*time.Millisecond {
		t.Fatalf("expected add members to return before async recompute, elapsed=%s", elapsed)
	}

	time.Sleep(900 * time.Millisecond)
	_, after := doGet(t, "/chat/conversations/"+convID, "user_test_001")
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
	convID := conv["id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	_, before := doGet(t, "/chat/conversations/"+convID, "user_test_001")
	beforeVersion := int(before["groupAvatarVersion"].(float64))
	beforeURL := before["avatarUrl"].(string)
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	handler, _ := newGroupAvatarTestHandler(t, delayedFailingGroupAvatarAssetizer{delay: 500 * time.Millisecond}, nil)
	start := time.Now()
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/chat/conversations/"+convID+"/members/user_test_003",
		"",
		"user_test_001",
		http.StatusOK,
	)
	elapsed := time.Since(start)
	if elapsed >= 400*time.Millisecond {
		t.Fatalf("expected remove member to return before async recompute, elapsed=%s", elapsed)
	}

	time.Sleep(900 * time.Millisecond)
	_, after := doGet(t, "/chat/conversations/"+convID, "user_test_001")
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
		delegate: newGroupAvatarMediaForContractTest(),
	}
	handler, _ := newGroupAvatarTestHandler(t, assetizer, nil)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"retry until success"}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
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
		newGroupAvatarMediaForContractTest(),
		flakyPublisher,
	)

	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"patch retry","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)

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
		newGroupAvatarMediaForContractTest(),
		nil,
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"reliable e2e","initialMemberIds":["user_test_002","user_test_003"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)

	waitForCollectionCount(t, "reliable_task_outbox", bson.M{
		"taskType":    "chat.group_avatar.recompute",
		"aggregateId": convID,
	}, 1)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
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
		Store:    reliabletaskmongo.New(mongoDB),
		failures: 1,
	}
	handler, syncService := newGroupAvatarTestHandlerWithStore(
		t,
		newGroupAvatarMediaForContractTest(),
		nil,
		store,
		application.WithReliableGroupAvatarLeaseTTL(80*time.Millisecond),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"ack replay","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
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
		Store:    reliabletaskmongo.New(mongoDB),
		failures: 1,
	}
	handler, syncService := newGroupAvatarTestHandlerWithStore(
		t,
		newGroupAvatarMediaForContractTest(),
		nil,
		store,
		application.WithReliableGroupAvatarLeaseTTL(80*time.Millisecond),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"notification ack replay","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
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

func TestGroupAvatar_DissolveConversationStopsPendingAvatarNotificationFanout(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	delegateSync := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	flakySync := &flakyUserSyncPublisher{
		failuresLeft: map[string]int{
			"user_test_002": 100,
		},
		delegate: delegateSync,
	}
	handler, _, _ := newGroupAvatarTestHandlerWithStoreAndScheduler(
		t,
		newGroupAvatarMediaForContractTest(),
		flakySync,
		reliabletaskmongo.New(mongoDB),
		application.WithReliableGroupAvatarLeaseTTL(80*time.Millisecond),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"dissolve stops avatar fanout","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_003"]}`,
		"user_test_001",
		http.StatusOK,
	)
	waitForCollectionCount(t, "notification_outbox", bson.M{
		"eventType":   "conversation.avatar.updated",
		"aggregateId": convID,
		"status":      reliabletask.NotificationStatusRetryWait,
	}, 1)
	if code, _ := doDelete(t, "/chat/conversations/"+convID, "user_test_001"); code != http.StatusOK {
		t.Fatalf("expected dissolve status 200, got %d", code)
	}
	waitForCollectionCount(t, "notification_outbox", bson.M{
		"eventType":   "conversation.avatar.updated",
		"aggregateId": convID,
		"status":      reliabletask.NotificationStatusSucceeded,
	}, 1)

	resp, err := delegateSync.Pull(context.Background(), "user_test_002", 0, 20)
	if err != nil {
		t.Fatalf("Pull user_test_002: %v", err)
	}
	for _, patch := range resp.Patches {
		if patch.Type == "conversation.avatar.updated" && patch.Payload["conversationId"] == convID {
			t.Fatalf("expected dissolved conversation %s to stop pending avatar fanout", convID)
		}
	}
}

func TestGroupAvatar_SourceHashReplayRecreatesMissingNotification(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, syncService, scheduler := newGroupAvatarTestHandlerWithStoreAndScheduler(
		t,
		newGroupAvatarMediaForContractTest(),
		nil,
		reliabletaskmongo.New(mongoDB),
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"notification compensation","initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
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
		chatStoragePorts(chatStore),
		convCache,
		eventPublisherForContractTest(),
		testProfileResolver{},
		application.AllowRelationshipGateForTest(),
		nil,
		nil,
		failingGroupAvatarScheduler{},
	)
	_, err := conversationSvc.CreateConversation(commandOperationTestContext(), application.CreateConversationRequest{
		Type:      "group",
		Title:     "rollback create",
		CreatorId: "user_test_001",
	})
	if err == nil {
		t.Fatal("expected create conversation to fail when outbox write fails")
	}
	waitForExactCollectionCount(t, "conversations", bson.M{"title": "rollback create"}, 0)
	waitForExactCollectionCount(t, "conversation_memberships", bson.M{"userId": "user_test_001"}, 0)
	waitForExactCollectionCount(t, "reliable_task_outbox", bson.M{"taskType": "chat.group_avatar.recompute"}, 0)
}

func TestGroupAvatar_AddMembersRollsBackWhenOutboxFails(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(t, `{"type":"group","title":"rollback add"}`)
	convID := created["id"].(string)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	memberSvc := application.NewMemberService(
		chatStoragePorts(chatStore),
		convCache,
		eventPublisherForContractTest(),
		testProfileResolver{},
		nil,
		nil,
		failingGroupAvatarScheduler{},
	)
	err := memberSvc.AddMembers(commandOperationTestContext(), application.AddMembersRequest{
		ConversationId: convID,
		UserIds:        []string{"user_test_009"},
		InvitedBy:      "user_test_001",
	})
	if err == nil {
		t.Fatal("expected add members to fail when outbox write fails")
	}
	waitForExactCollectionCount(t, "conversation_memberships", bson.M{
		"conversationId": convID,
		"userId":         "user_test_009",
	}, 0)
}

func TestGroupAvatar_RemoveMemberRollsBackWhenOutboxFails(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(t, `{"type":"group","title":"rollback remove","initialMemberIds":["user_test_002"]}`)
	convID := created["id"].(string)
	waitForConversationAvatarVersion(t, convID, 1)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(redisRouter.Scene("general"))
	memberSvc := application.NewMemberService(
		chatStoragePorts(chatStore),
		convCache,
		eventPublisherForContractTest(),
		testProfileResolver{},
		nil,
		nil,
		failingGroupAvatarScheduler{},
	)
	removeCtx := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "api_integration.remove_member_rollback",
		IdempotencyKey: "group-avatar-remove-rollback-1",
		Actor: operation.ActorContext{
			AccountID: "user_test_001",
			PersonaID: "user_test_001",
		},
	})
	err := memberSvc.RemoveMember(removeCtx, application.RemoveMemberRequest{
		ConversationId: convID,
		UserId:         "user_test_002",
		OperatorId:     "user_test_001",
	})
	if err == nil {
		t.Fatal("expected remove member to fail when outbox write fails")
	}
	waitForExactCollectionCount(t, "conversation_memberships", bson.M{
		"conversationId": convID,
		"userId":         "user_test_002",
	}, 1)
}

func TestGroupAvatar_AddRemoveStormUsesLatestTopNineSourceHash(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, _ := newGroupAvatarTestHandler(
		t,
		newGroupAvatarMediaForContractTest(),
		nil,
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"add remove storm","initialMemberIds":["user_test_002","user_test_003","user_test_004","user_test_005","user_test_006","user_test_007","user_test_008","user_test_009","user_test_010"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_011","user_test_012","user_test_013","user_test_014"]}`,
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/chat/conversations/"+convID+"/members/user_test_003",
		"",
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_015"]}`,
		"user_test_001",
		http.StatusOK,
	)
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/chat/conversations/"+convID+"/members/user_test_002",
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
		members, err := chatStore.ListMembers(context.Background(), convID, application.ListMembersQuery{
			Limit: 200,
			Sort:  application.MemberListSortJoinedAsc,
		})
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

func TestGroupAvatar_MemberChangesFanoutSameAvatarToCurrentMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	handler, syncService := newGroupAvatarTestHandler(
		t,
		newGroupAvatarMediaForContractTest(),
		nil,
	)
	created := doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations",
		`{"type":"group","title":"member fanout consistency","initialMemberIds":["user_test_002","user_test_003"]}`,
		"user_test_001",
		http.StatusCreated,
	)
	convID := created["id"].(string)
	waitForConversationAvatarVersionFromBackground(t, convID, 1)
	for _, userID := range []string{"user_test_001", "user_test_002", "user_test_003"} {
		waitForAvatarPatch(t, syncService, userID, convID)
	}

	beforeAddSeq := map[string]int64{}
	for _, userID := range []string{"user_test_001", "user_test_002", "user_test_003", "user_test_004"} {
		beforeAddSeq[userID] = latestSyncSeq(t, syncService, userID)
	}
	doHandlerJSON(
		t,
		handler,
		http.MethodPost,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_test_004"]}`,
		"user_test_001",
		http.StatusOK,
	)
	waitForConversationAvatarVersionFromBackground(t, convID, 2)
	addDetail := doHandlerJSON(
		t,
		handler,
		http.MethodGet,
		"/chat/conversations/"+convID,
		"",
		"user_test_001",
		http.StatusOK,
	)
	addURL := strings.TrimSpace(addDetail["avatarUrl"].(string))
	addVersion := int(addDetail["groupAvatarVersion"].(float64))
	if !strings.Contains(addURL, "/media/avatar/s/conversation/"+convID+"/") {
		t.Fatalf("expected derived group avatar url after add, got %q", addURL)
	}
	for _, userID := range []string{"user_test_001", "user_test_002", "user_test_003", "user_test_004"} {
		patch := waitForAvatarPatchAfter(t, syncService, userID, beforeAddSeq[userID], convID)
		if got := strings.TrimSpace(fmt.Sprint(patch.Payload["avatarUrl"])); got != addURL {
			t.Fatalf("user %s patch avatarUrl = %q want %q", userID, got, addURL)
		}
		if got := patchIntValue(patch.Payload["groupAvatarVersion"]); got != addVersion {
			t.Fatalf("user %s patch version = %d want %d", userID, got, addVersion)
		}
		inbox := doHandlerJSON(t, handler, http.MethodGet, "/chat/inbox?limit=20", "", userID, http.StatusOK)
		row := findInboxRow(t, inbox["items"], convID)
		if got := strings.TrimSpace(row["avatarUrl"].(string)); got != addURL {
			t.Fatalf("user %s inbox avatarUrl = %q want %q", userID, got, addURL)
		}
	}

	beforeRemoveSeq := map[string]int64{}
	for _, userID := range []string{"user_test_001", "user_test_002", "user_test_004"} {
		beforeRemoveSeq[userID] = latestSyncSeq(t, syncService, userID)
	}
	doHandlerJSON(
		t,
		handler,
		http.MethodDelete,
		"/chat/conversations/"+convID+"/members/user_test_003",
		"",
		"user_test_001",
		http.StatusOK,
	)
	waitForConversationAvatarVersionFromBackground(t, convID, addVersion+1)
	removeDetail := doHandlerJSON(
		t,
		handler,
		http.MethodGet,
		"/chat/conversations/"+convID,
		"",
		"user_test_001",
		http.StatusOK,
	)
	removeURL := strings.TrimSpace(removeDetail["avatarUrl"].(string))
	removeVersion := int(removeDetail["groupAvatarVersion"].(float64))
	if removeURL == addURL {
		t.Fatalf("expected new derived group avatar url after remove, got unchanged %q", removeURL)
	}
	for _, userID := range []string{"user_test_001", "user_test_002", "user_test_004"} {
		patch := waitForAvatarPatchAfter(t, syncService, userID, beforeRemoveSeq[userID], convID)
		if got := strings.TrimSpace(fmt.Sprint(patch.Payload["avatarUrl"])); got != removeURL {
			t.Fatalf("user %s remove patch avatarUrl = %q want %q", userID, got, removeURL)
		}
		if got := patchIntValue(patch.Payload["groupAvatarVersion"]); got != removeVersion {
			t.Fatalf("user %s remove patch version = %d want %d", userID, got, removeVersion)
		}
	}
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
				newGroupAvatarMediaForContractTest(),
				nil,
				reliabletaskmongo.New(mongoDB),
				application.WithReliableGroupAvatarRuntimeIdentity(env, "chat-service-"+env),
				application.WithReliableGroupAvatarReadyIndex(readyIndex),
			)
			created := doHandlerJSON(
				t,
				handler,
				http.MethodPost,
				"/chat/conversations",
				`{"type":"group","title":"ready index `+env+`","initialMemberIds":["user_test_002","user_test_003"]}`,
				"user_test_001",
				http.StatusCreated,
			)
			convID := created["id"].(string)
			waitForConversationAvatarVersionFromBackground(t, convID, 1)
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

func waitForAvatarPatchAfter(
	t *testing.T,
	syncService *runtimesync.Service,
	userID string,
	afterSeq int64,
	convID string,
) runtimesync.Patch {
	t.Helper()
	for i := 0; i < 100; i++ {
		resp, err := syncService.Pull(context.Background(), userID, afterSeq, 50)
		if err != nil {
			t.Fatalf("Pull for %s: %v", userID, err)
		}
		for _, patch := range resp.Patches {
			if patch.Type == "conversation.avatar.updated" && patch.Payload["conversationId"] == convID {
				if strings.TrimSpace(fmt.Sprint(patch.Payload["avatarUrl"])) == "" {
					t.Fatalf("avatar patch for %s missing avatarUrl: %#v", userID, patch.Payload)
				}
				return patch
			}
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("user %s did not receive conversation.avatar.updated for %s after seq %d", userID, convID, afterSeq)
	return runtimesync.Patch{}
}

func findInboxRow(t *testing.T, raw any, convID string) map[string]any {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("inbox items is not list: %#v", raw)
	}
	for _, item := range items {
		row, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if row["conversationId"] == convID || row["id"] == convID {
			return row
		}
	}
	t.Fatalf("conversation %s not found in inbox: %#v", convID, items)
	return nil
}

func patchIntValue(raw any) int {
	switch value := raw.(type) {
	case int:
		return value
	case int64:
		return int(value)
	case float64:
		return int(value)
	case json.Number:
		parsed, _ := value.Int64()
		return int(parsed)
	default:
		return 0
	}
}
