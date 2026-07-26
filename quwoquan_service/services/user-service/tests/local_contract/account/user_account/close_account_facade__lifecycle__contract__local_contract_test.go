// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-002
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

type fakeCloseStore struct {
	result   accountports.CloseResult
	err      error
	commits  int
	lastID   string
	lastTime time.Time
}

func (s *fakeCloseStore) CommitClose(
	_ context.Context,
	accountID string,
	closedAt time.Time,
) (accountports.CloseResult, error) {
	s.commits++
	s.lastID = accountID
	s.lastTime = closedAt
	return s.result, s.err
}

type fakeCloseCache struct {
	err          error
	accountIDs   []string
	phoneKeySets [][]string
}

func (c *fakeCloseCache) InvalidateClosedAccount(
	_ context.Context,
	accountID string,
	phoneCredentialKeys []string,
) error {
	c.accountIDs = append(c.accountIDs, accountID)
	c.phoneKeySets = append(
		c.phoneKeySets,
		append([]string(nil), phoneCredentialKeys...),
	)
	return c.err
}

func TestCloseAccount_FirstCloseCascades(t *testing.T) {
	closedAt := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	store := &fakeCloseStore{
		result: accountports.CloseResult{
			AlreadyClosed:       false,
			ClosedAt:            closedAt,
			PhoneCredentialKeys: []string{"+8613800000000"},
		},
	}
	cache := &fakeCloseCache{}
	facade := useraccountapp.NewCloseAccountFacade(store, cache)

	outcome, err := facade.CloseAccount(
		context.Background(),
		useraccountapp.CloseCommand{AccountID: "acct_close_1"},
	)
	if err != nil {
		t.Fatalf("close account: %v", err)
	}
	if outcome.AccountState != "closed" || outcome.IdempotentReplay {
		t.Fatalf("unexpected outcome: %+v", outcome)
	}
	if !outcome.ClosedAt.Equal(closedAt) {
		t.Fatalf("expected closedAt %v, got %v", closedAt, outcome.ClosedAt)
	}
	if store.commits != 1 || store.lastID != "acct_close_1" {
		t.Fatalf("expected one commit for account, got %+v", store)
	}
	if len(cache.accountIDs) != 1 ||
		cache.accountIDs[0] != "acct_close_1" ||
		len(cache.phoneKeySets) != 1 ||
		len(cache.phoneKeySets[0]) != 1 ||
		cache.phoneKeySets[0][0] != "+8613800000000" {
		t.Fatalf("expected closed-account cache invalidation, got %+v", cache)
	}
}

func TestCloseAccount_ReplayIsIdempotent(t *testing.T) {
	closedAt := time.Date(2026, 7, 19, 6, 0, 0, 0, time.UTC)
	store := &fakeCloseStore{
		result: accountports.CloseResult{AlreadyClosed: true, ClosedAt: closedAt},
	}
	cache := &fakeCloseCache{}
	facade := useraccountapp.NewCloseAccountFacade(store, cache)

	outcome, err := facade.CloseAccount(
		context.Background(),
		useraccountapp.CloseCommand{AccountID: "acct_close_replay"},
	)
	if err != nil {
		t.Fatalf("replay close: %v", err)
	}
	if !outcome.IdempotentReplay {
		t.Fatalf("expected idempotent replay, got %+v", outcome)
	}
	if !outcome.ClosedAt.Equal(closedAt) {
		t.Fatalf("replay must keep original closedAt, got %v", outcome.ClosedAt)
	}
	// CommitClose 自身负责事务内幂等收敛；重放仍清理可能回潮的派生缓存。
	if len(cache.accountIDs) != 1 ||
		cache.accountIDs[0] != "acct_close_replay" {
		t.Fatalf("replay must still invalidate derived cache, got %+v", cache)
	}
}

func TestCloseAccount_MissingAccountMapsToNotFound(t *testing.T) {
	store := &fakeCloseStore{err: accountports.ErrAccountNotFound}
	facade := useraccountapp.NewCloseAccountFacade(
		store,
		nil,
	)
	_, err := facade.CloseAccount(
		context.Background(),
		useraccountapp.CloseCommand{AccountID: "acct_missing"},
	)
	if err == nil {
		t.Fatal("expected not found error")
	}
	app := rterr.NormalizeError(err)
	if app.Code.Reason != "not_found" {
		t.Fatalf("expected USER not_found, got %+v", app.Code)
	}
}

func TestCloseAccount_CacheFailureDoesNotRollbackTerminalState(t *testing.T) {
	store := &fakeCloseStore{
		result: accountports.CloseResult{ClosedAt: time.Now().UTC()},
	}
	cache := &fakeCloseCache{err: errors.New("redis unavailable")}
	facade := useraccountapp.NewCloseAccountFacade(store, cache)

	outcome, err := facade.CloseAccount(
		context.Background(),
		useraccountapp.CloseCommand{AccountID: "acct_close_fail"},
	)
	if err != nil {
		t.Fatalf("cache failure must not roll back committed close: %v", err)
	}
	if outcome.AccountState != "closed" || store.commits != 1 {
		t.Fatalf("expected committed closed outcome, got %+v store=%+v", outcome, store)
	}
}

func TestCloseAccount_BlankAccountRejected(t *testing.T) {
	facade := useraccountapp.NewCloseAccountFacade(
		&fakeCloseStore{},
		nil,
	)
	if _, err := facade.CloseAccount(
		context.Background(),
		useraccountapp.CloseCommand{AccountID: "  "},
	); err == nil {
		t.Fatal("expected blank account id to be rejected")
	}
}
