package local_contract

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	bindingapp "quwoquan_service/services/user-service/internal/application/account/credential_binding"
	bindingmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
	bindingports "quwoquan_service/services/user-service/internal/domain/account/credential_binding/ports"
)

func TestCredentialBindingFacadeUsesUniqueConstraintForConflictAndNoop(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	store := newFakeCredentialBindingStore()
	facade := bindingapp.NewCredentialCommandFacade(
		store,
		bindingapp.WithClock(func() time.Time { return now }),
	)
	command := bindingapp.BindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypeWechat,
		CredentialKey:  "wechat-subject-ref",
		DisplayLabel:   "微信",
	}

	first, err := facade.BindVerifiedCredential(
		context.Background(),
		"account-1",
		command,
	)
	if err != nil {
		t.Fatalf("首次绑定: %v", err)
	}
	replayed, err := facade.BindVerifiedCredential(
		context.Background(),
		"account-1",
		bindingapp.BindCredentialCommand{
			CredentialType: command.CredentialType,
			CredentialKey:  command.CredentialKey,
			DisplayLabel:   "不应覆盖首次标签",
		},
	)
	if err != nil {
		t.Fatalf("同账号重复绑定: %v", err)
	}
	if !replayed.IdempotentReplay ||
		replayed.Version != first.Version ||
		replayed.DisplayLabel != first.DisplayLabel ||
		store.outboxCount() != 1 {
		t.Fatalf("同账号同凭证必须自然 no-op 且不新增 outbox: %+v", replayed)
	}

	_, err = facade.BindVerifiedCredential(
		context.Background(),
		"account-2",
		command,
	)
	if err == nil || !strings.Contains(err.Error(), "USER.AUTH.credential_conflict") {
		t.Fatalf("同一凭证跨账号必须返回 credential_conflict，得到: %v", err)
	}
	_, err = facade.BindVerifiedCredential(
		context.Background(),
		"account-1",
		bindingapp.BindCredentialCommand{
			CredentialType: bindingmodel.CredentialTypeWechat,
			CredentialKey:  "another-wechat-subject-ref",
			DisplayLabel:   "另一个微信",
		},
	)
	if err == nil || !strings.Contains(err.Error(), "USER.AUTH.credential_conflict") {
		t.Fatalf("同账号同类型不同凭证必须返回 credential_conflict，得到: %v", err)
	}
	if store.bindingCount() != 1 || store.outboxCount() != 1 {
		t.Fatal("唯一冲突不得写入 state 或 outbox")
	}
}

func TestCredentialBindingFacadeProtectsLastCredentialAndRetriesCAS(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	store := newFakeCredentialBindingStore()
	facade := bindingapp.NewCredentialCommandFacade(
		store,
		bindingapp.WithClock(func() time.Time { return now }),
	)
	ctx := credentialActorContext("account-1")

	if _, err := facade.BindVerifiedCredential(context.Background(), "account-1", bindingapp.BindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypePhone,
		CredentialKey:  "phone-hash-ref",
		DisplayLabel:   "138****0001",
	}); err != nil {
		t.Fatalf("绑定手机号: %v", err)
	}
	_, err := facade.UnbindCredential(ctx, bindingapp.UnbindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypePhone,
	})
	if err == nil || !strings.Contains(err.Error(), "USER.AUTH.last_credential") {
		t.Fatalf("唯一可恢复凭证必须受保护，得到: %v", err)
	}
	if store.mustLoad(t, "account-1", bindingmodel.CredentialTypePhone).
		Snapshot().Status != bindingmodel.StatusActive {
		t.Fatal("最后凭证保护失败后绑定必须保持 active")
	}

	if _, err := facade.BindVerifiedCredential(context.Background(), "account-1", bindingapp.BindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypeWechat,
		CredentialKey:  "wechat-subject-ref",
		DisplayLabel:   "微信",
	}); err != nil {
		t.Fatalf("绑定第二种可恢复凭证: %v", err)
	}
	store.failNextRevokeCAS()
	revoked, err := facade.UnbindCredential(ctx, bindingapp.UnbindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypeWechat,
	})
	if err != nil {
		t.Fatalf("CAS 重试后吊销第二凭证: %v", err)
	}
	if revoked.IsActive || revoked.Version != 2 || revoked.IdempotentReplay {
		t.Fatalf("吊销回执错误: %+v", revoked)
	}
	if store.revokeCommitCount() != 3 {
		t.Fatalf("最后凭证拒绝一次 + CAS 失败重试两次，commit 次数应为 3，得到 %d",
			store.revokeCommitCount())
	}
	if store.outboxCount() != 3 {
		t.Fatalf("两次 bind + 一次成功 revoke 应有 3 条 outbox，得到 %d", store.outboxCount())
	}

	replayed, err := facade.UnbindCredential(ctx, bindingapp.UnbindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypeWechat,
	})
	if err != nil {
		t.Fatalf("重复吊销: %v", err)
	}
	if !replayed.IdempotentReplay || replayed.IsActive || replayed.Version != 2 {
		t.Fatalf("revoked 重放必须 no-op: %+v", replayed)
	}
	if store.outboxCount() != 3 {
		t.Fatal("重复吊销不得新增 outbox")
	}

	_, err = facade.BindVerifiedCredential(context.Background(), "account-1", bindingapp.BindCredentialCommand{
		CredentialType: bindingmodel.CredentialTypeWechat,
		CredentialKey:  "wechat-subject-ref",
		DisplayLabel:   "微信",
	})
	if err == nil || !strings.Contains(err.Error(), "USER.AUTH.credential_conflict") {
		t.Fatalf("revoked identity 不得被重新激活，得到: %v", err)
	}
	if store.mustLoad(t, "account-1", bindingmodel.CredentialTypeWechat).
		Snapshot().Status != bindingmodel.StatusRevoked {
		t.Fatal("重绑失败后原 identity 必须保持 revoked")
	}
}

func TestCredentialBindingFacadeKeepsEventTimeMonotonicAcrossClockSkew(
	t *testing.T,
) {
	t.Parallel()

	appNow := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	databaseNow := appNow.Add(2 * time.Second)
	store := newFakeCredentialBindingStore()
	for _, seed := range []bindingmodel.BindParams{
		{
			ID:             "binding-phone",
			OwnerID:        "account-clock-skew",
			CredentialType: bindingmodel.CredentialTypePhone,
			CredentialKey:  "phone-clock-skew",
			EventID:        "event-phone-bound",
			BoundAt:        databaseNow,
		},
		{
			ID:             "binding-wechat",
			OwnerID:        "account-clock-skew",
			CredentialType: bindingmodel.CredentialTypeWechat,
			CredentialKey:  "wechat-clock-skew",
			EventID:        "event-wechat-bound",
			BoundAt:        databaseNow,
		},
	} {
		change, err := bindingmodel.Bind(seed)
		if err != nil {
			t.Fatalf("构造数据库时钟写入的绑定: %v", err)
		}
		if _, err := store.Bind(context.Background(), change); err != nil {
			t.Fatalf("写入测试绑定: %v", err)
		}
	}

	facade := bindingapp.NewCredentialCommandFacade(
		store,
		bindingapp.WithClock(func() time.Time { return appNow }),
	)
	result, err := facade.UnbindCredential(
		credentialActorContext("account-clock-skew"),
		bindingapp.UnbindCredentialCommand{
			CredentialType: bindingmodel.CredentialTypeWechat,
		},
	)
	if err != nil {
		t.Fatalf("应用时钟落后数据库时钟不应阻断合法解绑: %v", err)
	}
	if result.IsActive || result.Version != 2 {
		t.Fatalf("解绑回执错误: %+v", result)
	}
	lastEvent := store.outbox[len(store.outbox)-1]
	if !lastEvent.OccurredAt.Equal(databaseNow) {
		t.Fatalf(
			"事件时间必须以下界 %s 单调提交，得到 %s",
			databaseNow,
			lastEvent.OccurredAt,
		)
	}
}

func credentialActorContext(accountID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "CredentialBindingLocalContract",
		RequestID:   "request-" + accountID,
		TraceID:     "trace-" + accountID,
		Actor: operation.ActorContext{
			AccountID: accountID,
		},
	})
}

type fakeCredentialBindingStore struct {
	mu             sync.Mutex
	byID           map[string]bindingmodel.CredentialBinding
	byCredential   map[string]string
	byOwnerType    map[string]string
	outbox         []bindingmodel.Event
	revokeCommits  int
	failRevokeOnce bool
}

func newFakeCredentialBindingStore() *fakeCredentialBindingStore {
	return &fakeCredentialBindingStore{
		byID:         map[string]bindingmodel.CredentialBinding{},
		byCredential: map[string]string{},
		byOwnerType:  map[string]string{},
	}
}

func (store *fakeCredentialBindingStore) Bind(
	_ context.Context,
	change bindingmodel.ChangeSet,
) (bindingports.BindResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()

	state := change.Aggregate.State()
	credentialKey := fakeCredentialKey(state.CredentialType, state.CredentialKey)
	if existingID, found := store.byCredential[credentialKey]; found {
		existing := store.byID[existingID]
		existingState := existing.State()
		if existingState.OwnerID == state.OwnerID &&
			existingState.Status == bindingmodel.StatusActive {
			return bindingports.BindResult{
				Aggregate: existing,
				Replayed:  true,
			}, nil
		}
		return bindingports.BindResult{}, bindingports.ErrCredentialConflict
	}
	ownerTypeKey := fakeOwnerTypeKey(state.OwnerID, state.CredentialType)
	if _, found := store.byOwnerType[ownerTypeKey]; found {
		return bindingports.BindResult{}, bindingports.ErrCredentialConflict
	}
	store.byID[state.ID] = change.Aggregate
	store.byCredential[credentialKey] = state.ID
	store.byOwnerType[ownerTypeKey] = state.ID
	store.outbox = append(store.outbox, change.Events...)
	return bindingports.BindResult{Aggregate: change.Aggregate}, nil
}

func (store *fakeCredentialBindingStore) LoadByOwnerAndType(
	_ context.Context,
	ownerID string,
	credentialType bindingmodel.CredentialType,
) (bindingmodel.CredentialBinding, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()

	id, found := store.byOwnerType[fakeOwnerTypeKey(ownerID, credentialType)]
	if !found {
		return bindingmodel.CredentialBinding{}, false, nil
	}
	return store.byID[id], true, nil
}

func (store *fakeCredentialBindingStore) FindByTypeAndKey(
	_ context.Context,
	credentialType bindingmodel.CredentialType,
	credentialKey string,
) (bindingmodel.CredentialBinding, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()

	id, found := store.byCredential[fakeCredentialKey(
		credentialType,
		strings.TrimSpace(credentialKey),
	)]
	if !found {
		return bindingmodel.CredentialBinding{}, false, nil
	}
	return store.byID[id], true, nil
}

func (store *fakeCredentialBindingStore) MarkUsed(
	_ context.Context,
	aggregateID string,
	_ time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if _, found := store.byID[strings.TrimSpace(aggregateID)]; !found {
		return bindingports.ErrCredentialBindingNotFound
	}
	return nil
}

func (store *fakeCredentialBindingStore) ListByOwner(
	_ context.Context,
	ownerID string,
) ([]bindingmodel.CredentialBinding, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	ownerID = strings.TrimSpace(ownerID)
	items := make([]bindingmodel.CredentialBinding, 0)
	for _, candidate := range store.byID {
		if candidate.State().OwnerID == ownerID {
			items = append(items, candidate)
		}
	}
	return items, nil
}

func (store *fakeCredentialBindingStore) CommitRevoke(
	_ context.Context,
	expectedVersion int64,
	change bindingmodel.ChangeSet,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.revokeCommits++
	if store.failRevokeOnce {
		store.failRevokeOnce = false
		return bindingmodel.ErrVersionConflict
	}

	next := change.Aggregate.State()
	id, found := store.byOwnerType[fakeOwnerTypeKey(next.OwnerID, next.CredentialType)]
	if !found {
		return bindingports.ErrCredentialBindingNotFound
	}
	current := store.byID[id]
	if current.State().Version != expectedVersion ||
		next.ID != id ||
		next.Version != expectedVersion+1 {
		return bindingmodel.ErrVersionConflict
	}
	remainingRecoverable := 0
	for candidateID, candidate := range store.byID {
		state := candidate.State()
		if candidateID != id &&
			state.OwnerID == next.OwnerID &&
			state.Status == bindingmodel.StatusActive &&
			state.CredentialType.Recoverable() {
			remainingRecoverable++
		}
	}
	if remainingRecoverable == 0 {
		return bindingports.ErrLastRecoverableCredential
	}
	store.byID[id] = change.Aggregate
	store.outbox = append(store.outbox, change.Events...)
	return nil
}

func (store *fakeCredentialBindingStore) failNextRevokeCAS() {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.failRevokeOnce = true
}

func (store *fakeCredentialBindingStore) bindingCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.byID)
}

func (store *fakeCredentialBindingStore) outboxCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.outbox)
}

func (store *fakeCredentialBindingStore) revokeCommitCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.revokeCommits
}

func (store *fakeCredentialBindingStore) mustLoad(
	t *testing.T,
	ownerID string,
	credentialType bindingmodel.CredentialType,
) bindingmodel.CredentialBinding {
	t.Helper()
	binding, found, err := store.LoadByOwnerAndType(
		context.Background(),
		ownerID,
		credentialType,
	)
	if err != nil {
		t.Fatalf("读取凭证绑定: %v", err)
	}
	if !found {
		t.Fatalf("未找到 %s/%s", ownerID, credentialType)
	}
	return binding
}

func fakeCredentialKey(
	credentialType bindingmodel.CredentialType,
	credentialKey string,
) string {
	return string(credentialType) + "\x00" + credentialKey
}

func fakeOwnerTypeKey(
	ownerID string,
	credentialType bindingmodel.CredentialType,
) string {
	return ownerID + "\x00" + string(credentialType)
}

var _ bindingports.AggregateStore = (*fakeCredentialBindingStore)(nil)
