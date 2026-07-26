// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"context"
	"errors"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

func TestAccountSecurityTerminalEventClosesEveryAffectedSessionAndNeverRestores(
	t *testing.T,
) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 14, 0, 0, 0, time.UTC)
	store := newTerminalCallStore(
		terminalActiveSession("call-security-one", "room-security-one", "persona-closed", "peer-one"),
		terminalActiveSession("call-security-two", "room-security-two", "peer-two", "persona-closed"),
		terminalActiveSession("call-unaffected", "room-unaffected", "peer-one", "peer-two"),
	)
	cache := &terminalCallCache{}
	rooms := &terminalMediaProvider{}
	orchestrator := newTerminalOrchestrator(store, cache, rooms, now)
	securityEvent := application.AccountSecurityTerminalEvent{
		EventID:      "user-account-closed-event-1",
		AccountID:    "account-closed",
		PersonaIDs:   []string{"persona-closed", "persona-closed"},
		AccountState: "closed",
		OccurredAt:   now,
	}

	result, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		securityEvent,
	)
	if err != nil {
		t.Fatalf("ApplyAccountSecurityTerminalEvent() error = %v", err)
	}
	if result.TerminatedCalls != 2 || result.Replayed || result.RestoredIgnored {
		t.Fatalf("closure result = %#v, want two new terminal transitions", result)
	}
	for _, callID := range []string{"call-security-one", "call-security-two"} {
		session := store.call(callID)
		if session.Status != model.StatusEnded ||
			session.EndReason != model.EndReasonAccountClosed ||
			session.ParticipantCount != 0 {
			t.Fatalf("closed session %s = %#v", callID, session)
		}
		for _, participant := range session.Participants {
			if participant.Status != model.ParticipantLeft || participant.LeftAt == nil {
				t.Fatalf(
					"closed session %s left participant residual %#v",
					callID,
					participant,
				)
			}
		}
		if !cache.wasDeleted(callID) {
			t.Fatalf("closed session %s retained a cache state", callID)
		}
	}
	if affected := store.call("call-unaffected"); affected.Status != model.StatusInCall {
		t.Fatalf("unaffected session was changed to %s", affected.Status)
	}
	if !rooms.wasDeleted("room-security-one") || !rooms.wasDeleted("room-security-two") {
		t.Fatalf("affected rooms were not revoked: %#v", rooms.deletedRooms())
	}
	if rooms.wasDeleted("room-unaffected") {
		t.Fatal("unaffected media room was revoked")
	}

	commits := store.committed()
	if len(commits) != 2 {
		t.Fatalf("terminal commits = %d, want 2", len(commits))
	}
	for _, commit := range commits {
		if len(commit.Events) != 1 || commit.Events[0].EventType != "CallEnded" {
			t.Fatalf("terminal outbox commit = %#v, want one CallEnded fact", commit)
		}
		wire := string(commit.Events[0].Payload)
		if strings.Contains(wire, securityEvent.EventID) ||
			strings.Contains(wire, securityEvent.AccountID) {
			t.Fatalf("terminal CallEnded fact leaked upstream security identity: %s", wire)
		}
	}

	deletionsBeforeReplay := rooms.deleteCount()
	commitsBeforeReplay := len(commits)
	replayed, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		securityEvent,
	)
	if err != nil {
		t.Fatalf("duplicate terminal event error = %v", err)
	}
	if !replayed.Replayed || replayed.TerminatedCalls != 0 {
		t.Fatalf("duplicate closure result = %#v, want replay/no mutations", replayed)
	}
	if rooms.deleteCount() != deletionsBeforeReplay ||
		len(store.committed()) != commitsBeforeReplay {
		t.Fatal("duplicate terminal event repeated revocation or outbox commit")
	}

	restored, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		application.AccountSecurityTerminalEvent{
			EventID:      "user-restored-event-1",
			AccountID:    securityEvent.AccountID,
			PersonaIDs:   []string{"persona-closed"},
			AccountState: "active",
			AuthEpoch:    2,
			OccurredAt:   now.Add(time.Minute),
		},
	)
	if err != nil {
		t.Fatalf("UserRestored application error = %v", err)
	}
	if !restored.RestoredIgnored || !restored.Replayed {
		t.Fatalf("UserRestored result = %#v, want no-op", restored)
	}
	if session := store.call("call-security-one"); session.Status != model.StatusEnded ||
		session.EndReason != model.EndReasonAccountClosed {
		t.Fatalf("UserRestored revived old call: %#v", session)
	}
}

func TestAccountSecurityTerminalEventRetriesAfterRoomRevocationFailure(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 14, 5, 0, 0, time.UTC)
	store := newTerminalCallStore(
		terminalActiveSession("call-security-retry", "room-security-retry", "persona-suspended", "peer"),
	)
	cache := &terminalCallCache{}
	rooms := &terminalMediaProvider{failDeletes: 1}
	orchestrator := newTerminalOrchestrator(store, cache, rooms, now)
	securityEvent := application.AccountSecurityTerminalEvent{
		EventID:      "user-suspended-event-1",
		AccountID:    "account-suspended",
		PersonaIDs:   []string{"persona-suspended"},
		AccountState: "suspended",
		AuthEpoch:    3,
		OccurredAt:   now,
	}

	if _, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		securityEvent,
	); err == nil {
		t.Fatal("room revocation failure was acknowledged")
	}
	if session := store.call("call-security-retry"); session.Status != model.StatusInCall {
		t.Fatalf("failed revocation mutated session to %s", session.Status)
	}
	if len(store.committed()) != 0 {
		t.Fatal("failed revocation wrote terminal outbox fact")
	}

	retry, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		securityEvent,
	)
	if err != nil {
		t.Fatalf("retry after room revocation error = %v", err)
	}
	if retry.TerminatedCalls != 1 {
		t.Fatalf("retry result = %#v, want one closed call", retry)
	}
	if session := store.call("call-security-retry"); session.Status != model.StatusEnded ||
		session.EndReason != model.EndReasonAccountSuspended {
		t.Fatalf("retry did not close suspended account call: %#v", session)
	}
}

func TestAccountSecurityTerminalEventRevokesRoomBeforeCacheCleanupRetry(
	t *testing.T,
) {
	t.Parallel()

	now := time.Date(2026, time.July, 23, 14, 10, 0, 0, time.UTC)
	store := newTerminalCallStore(
		terminalActiveSession("call-security-cache", "room-security-cache", "persona-cache", "peer"),
	)
	cache := &terminalCallCache{failDeletes: 1}
	rooms := &terminalMediaProvider{}
	orchestrator := newTerminalOrchestrator(store, cache, rooms, now)
	securityEvent := application.AccountSecurityTerminalEvent{
		EventID:      "user-closed-cache-retry-event",
		AccountID:    "account-cache",
		PersonaIDs:   []string{"persona-cache"},
		AccountState: "closed",
		OccurredAt:   now,
	}

	if _, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		securityEvent,
	); err == nil {
		t.Fatal("cache cleanup failure was acknowledged")
	}
	if !rooms.wasDeleted("room-security-cache") {
		t.Fatal("cache failure prevented immediate media room revocation")
	}
	if session := store.call("call-security-cache"); session.Status != model.StatusInCall {
		t.Fatalf("cache failure committed terminal state unexpectedly: %#v", session)
	}

	result, err := orchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		securityEvent,
	)
	if err != nil {
		t.Fatalf("cache cleanup retry error = %v", err)
	}
	if result.TerminatedCalls != 1 ||
		!cache.wasDeleted("call-security-cache") {
		t.Fatalf("cache cleanup retry result = %#v", result)
	}
	if roomDeletes := rooms.deleteCount(); roomDeletes != 2 {
		t.Fatalf("room revocation retries = %d, want 2 idempotent deletes", roomDeletes)
	}
}

func newTerminalOrchestrator(
	store application.CallStore,
	cache application.CallStateCache,
	rooms application.MediaRoomProvider,
	now time.Time,
) *application.CallOrchestrator {
	return application.NewCallOrchestrator(
		store,
		cache,
		callsession.NewCallSessionService(),
		rooms,
		application.AllowRelationshipGateForTest(),
		application.WithClock(func() time.Time { return now }),
		application.WithCallAccountSecurityGate(
			application.AllowCallAccountSecurityForTest(),
		),
	)
}

func terminalActiveSession(id, roomID string, personaIDs ...string) *model.CallSession {
	participants := make([]model.Participant, 0, len(personaIDs))
	for index, personaID := range personaIDs {
		role := model.RoleInvitee
		if index == 0 {
			role = model.RoleInitiator
		}
		participants = append(participants, model.Participant{
			UserID:   personaID,
			Role:     role,
			Status:   model.ParticipantConnected,
			JoinedAt: terminalTimePointer(time.Date(2026, time.July, 23, 13, 0, 0, 0, time.UTC)),
		})
	}
	return &model.CallSession{
		ID:               id,
		RoomID:           roomID,
		Version:          1,
		CallType:         model.CallTypeAudio,
		Status:           model.StatusInCall,
		InitiatorID:      personaIDs[0],
		MaxParticipants:  model.MaxParticipantsGroup,
		ParticipantCount: len(participants),
		Participants:     participants,
		CreatedAt:        time.Date(2026, time.July, 23, 12, 0, 0, 0, time.UTC),
		UpdatedAt:        time.Date(2026, time.July, 23, 13, 0, 0, 0, time.UTC),
	}
}

func terminalTimePointer(value time.Time) *time.Time {
	return &value
}

type terminalCallStore struct {
	mu       sync.Mutex
	sessions map[string]*model.CallSession
	receipts map[string]application.CallCommitResult
	commits  []application.CallCommit
}

func newTerminalCallStore(sessions ...*model.CallSession) *terminalCallStore {
	store := &terminalCallStore{
		sessions: make(map[string]*model.CallSession, len(sessions)),
		receipts: make(map[string]application.CallCommitResult),
	}
	for _, session := range sessions {
		store.sessions[session.ID] = cloneCallSession(session)
	}
	return store
}

func (store *terminalCallStore) CreateCall(context.Context, *model.CallSession) error {
	return errors.New("CreateCall is not used by account security terminal closure")
}

func (store *terminalCallStore) FindCallByID(
	_ context.Context,
	id string,
) (*model.CallSession, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return cloneCallSession(store.sessions[id]), nil
}

func (store *terminalCallStore) FindActiveCallForUser(
	context.Context,
	string,
) (*model.CallSession, error) {
	return nil, errors.New("FindActiveCallForUser is not used by account security terminal closure")
}

func (store *terminalCallStore) FindActiveCallsForUsers(
	_ context.Context,
	personaIDs []string,
	limit int,
) ([]*model.CallSession, error) {
	store.mu.Lock()
	defer store.mu.Unlock()

	affected := make(map[string]struct{}, len(personaIDs))
	for _, personaID := range personaIDs {
		affected[strings.TrimSpace(personaID)] = struct{}{}
	}
	ids := make([]string, 0, len(store.sessions))
	for id := range store.sessions {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	result := make([]*model.CallSession, 0)
	for _, id := range ids {
		session := store.sessions[id]
		if session == nil || session.Status == model.StatusEnded {
			continue
		}
		for _, participant := range session.Participants {
			if _, found := affected[participant.UserID]; found {
				result = append(result, cloneCallSession(session))
				break
			}
		}
		if limit > 0 && len(result) >= limit {
			break
		}
	}
	return result, nil
}

func (store *terminalCallStore) FindOverdueRingingCalls(
	context.Context,
	time.Time,
	time.Time,
	int,
) ([]*model.CallSession, error) {
	return nil, errors.New("FindOverdueRingingCalls is not used by account security terminal closure")
}

func (store *terminalCallStore) Commit(
	_ context.Context,
	commit application.CallCommit,
) (application.CallCommitResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[commit.IdempotencyKey]; found {
		return application.CallCommitResult{
			Session:  cloneCallSession(receipt.Session),
			Replayed: true,
		}, nil
	}
	current := store.sessions[commit.Session.ID]
	if current == nil || current.Version != commit.ExpectedVersion {
		return application.CallCommitResult{}, application.ErrVersionConflict
	}
	updated := cloneCallSession(commit.Session)
	updated.Version = commit.ExpectedVersion + 1
	store.sessions[updated.ID] = updated
	result := application.CallCommitResult{Session: cloneCallSession(updated)}
	store.receipts[commit.IdempotencyKey] = result
	store.commits = append(store.commits, cloneTerminalCommit(commit))
	return result, nil
}

func (store *terminalCallStore) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	_ string,
	_ string,
) (application.CallCommitResult, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, found := store.receipts[idempotencyKey]
	if !found {
		return application.CallCommitResult{}, false, nil
	}
	return application.CallCommitResult{
		Session:  cloneCallSession(receipt.Session),
		Replayed: true,
	}, true, nil
}

func (store *terminalCallStore) RecordNoopReceipt(
	_ context.Context,
	receipt application.CallNoopReceipt,
) (application.CallCommitResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := application.CallCommitResult{Session: cloneCallSession(receipt.Session)}
	store.receipts[receipt.IdempotencyKey] = result
	return result, nil
}

func (store *terminalCallStore) ListCallsByUserID(
	context.Context,
	string,
	application.CallHistoryQuery,
) (application.CallHistoryPage, error) {
	return application.CallHistoryPage{}, errors.New(
		"ListCallsByUserID is not used by account security terminal closure",
	)
}

func (store *terminalCallStore) call(id string) *model.CallSession {
	store.mu.Lock()
	defer store.mu.Unlock()
	return cloneCallSession(store.sessions[id])
}

func (store *terminalCallStore) committed() []application.CallCommit {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]application.CallCommit, 0, len(store.commits))
	for _, commit := range store.commits {
		result = append(result, cloneTerminalCommit(commit))
	}
	return result
}

func cloneTerminalCommit(commit application.CallCommit) application.CallCommit {
	clone := commit
	clone.Session = cloneCallSession(commit.Session)
	clone.Events = append([]application.CallOutboxEvent(nil), commit.Events...)
	for index := range clone.Events {
		clone.Events[index].Payload = append([]byte(nil), clone.Events[index].Payload...)
	}
	return clone
}

type terminalCallCache struct {
	mu          sync.Mutex
	failDeletes int
	deleted     map[string]int
}

func (cache *terminalCallCache) SetCallState(
	context.Context,
	*model.CallSession,
) error {
	return nil
}

func (cache *terminalCallCache) GetCallState(
	context.Context,
	string,
) (*model.CallSession, error) {
	return nil, nil
}

func (cache *terminalCallCache) DeleteCallState(
	_ context.Context,
	callID string,
) error {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if cache.failDeletes > 0 {
		cache.failDeletes--
		return errors.New("call-state cache unavailable")
	}
	if cache.deleted == nil {
		cache.deleted = make(map[string]int)
	}
	cache.deleted[callID]++
	return nil
}

func (cache *terminalCallCache) wasDeleted(callID string) bool {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	return cache.deleted[callID] > 0
}

type terminalMediaProvider struct {
	mu          sync.Mutex
	failDeletes int
	deleted     map[string]int
}

func (*terminalMediaProvider) CreateRoom(context.Context, string, int) error {
	return errors.New("CreateRoom is not used by account security terminal closure")
}

func (provider *terminalMediaProvider) DeleteRoom(
	_ context.Context,
	roomID string,
) error {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	if provider.failDeletes > 0 {
		provider.failDeletes--
		return errors.New("media provider unavailable")
	}
	if provider.deleted == nil {
		provider.deleted = make(map[string]int)
	}
	provider.deleted[roomID]++
	return nil
}

func (*terminalMediaProvider) ListParticipants(
	context.Context,
	string,
) ([]application.RoomParticipant, error) {
	return nil, nil
}

func (*terminalMediaProvider) RemoveParticipant(
	context.Context,
	string,
	string,
) error {
	return nil
}

func (*terminalMediaProvider) IssueParticipantAccess(
	context.Context,
	string,
	string,
) (application.MediaSessionAccess, error) {
	return application.MediaSessionAccess{}, errors.New(
		"IssueParticipantAccess is not used by account security terminal closure",
	)
}

func (provider *terminalMediaProvider) wasDeleted(roomID string) bool {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	return provider.deleted[roomID] > 0
}

func (provider *terminalMediaProvider) deleteCount() int {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	count := 0
	for _, value := range provider.deleted {
		count += value
	}
	return count
}

func (provider *terminalMediaProvider) deletedRooms() map[string]int {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	result := make(map[string]int, len(provider.deleted))
	for roomID, count := range provider.deleted {
		result[roomID] = count
	}
	return result
}
