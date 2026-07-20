package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	sessionapp "quwoquan_service/services/user-service/internal/application/account/account_session"
	sessionports "quwoquan_service/services/user-service/internal/domain/account/account_session/ports"
)

func TestAccountSessionCommandFacetHashesEveryRefreshTokenBeforeStore(t *testing.T) {
	t.Parallel()

	store := newFakeAccountSessionStore()
	facade := sessionapp.NewAccountSessionCommandFacade(store)
	expiresAt := time.Date(2026, 8, 19, 12, 0, 0, 0, time.UTC)
	firstToken := []byte("first-refresh-secret")
	secondToken := []byte("second-refresh-secret")
	firstHash := testRefreshTokenHash(firstToken)
	secondHash := testRefreshTokenHash(secondToken)

	issued, err := facade.Issue(context.Background(), sessionapp.IssueCommand{
		AccountID:             " account-1 ",
		DeviceID:              " device-1 ",
		AuthenticationSubject: " subject-hash ",
		IdentityOrigin:        " phone ",
		RefreshToken:          firstToken,
		ExpiresAt:             expiresAt,
	})
	if err != nil {
		t.Fatalf("签发会话: %v", err)
	}
	if issued.AccountID != "account-1" ||
		issued.DeviceID != "device-1" ||
		store.lastIssuedHash != firstHash {
		t.Fatalf("签发必须规范化身份并仅传 hash: result=%+v hash=%q", issued, store.lastIssuedHash)
	}

	rotated, err := facade.Rotate(context.Background(), sessionapp.RotateCommand{
		CurrentRefreshToken: firstToken,
		NextRefreshToken:    secondToken,
		ExpiresAt:           expiresAt.Add(24 * time.Hour),
	})
	if err != nil {
		t.Fatalf("轮换会话: %v", err)
	}
	if rotated.LineageID != issued.LineageID ||
		store.lastRotatedCurrentHash != firstHash ||
		store.lastRotatedNextHash != secondHash {
		t.Fatalf(
			"轮换必须保持 lineage 且只传双 hash: issued=%+v rotated=%+v current=%q next=%q",
			issued,
			rotated,
			store.lastRotatedCurrentHash,
			store.lastRotatedNextHash,
		)
	}
	for _, plaintext := range []string{string(firstToken), string(secondToken)} {
		if store.containsStoredValue(plaintext) {
			t.Fatalf("fake store 不得接收到 refresh 明文 %q", plaintext)
		}
	}
	if got := reflect.TypeOf((*sessionapp.CommandFacet)(nil)).Elem().NumMethod(); got != 4 || got > 10 {
		t.Fatalf("AccountSession command facet 应仅暴露四个对象命令，得到 %d", got)
	}
	assertNoClientConcurrencyFields(t,
		sessionapp.IssueCommand{},
		sessionapp.RotateCommand{},
		sessionapp.LogoutCommand{},
		sessionapp.RevokeCommand{},
	)
}

func TestAccountSessionRotationReplayRevokesLineageAndLogoutIsNoop(t *testing.T) {
	t.Parallel()

	store := newFakeAccountSessionStore()
	facade := sessionapp.NewAccountSessionCommandFacade(store)
	expiresAt := time.Date(2026, 8, 19, 12, 0, 0, 0, time.UTC)
	firstToken := []byte("lineage-first-token")
	secondToken := []byte("lineage-second-token")
	replayReplacement := []byte("must-not-be-issued")

	issued, err := facade.Issue(context.Background(), sessionapp.IssueCommand{
		AccountID:             "account-1",
		DeviceID:              "device-1",
		AuthenticationSubject: "subject-hash",
		IdentityOrigin:        "phone",
		RefreshToken:          firstToken,
		ExpiresAt:             expiresAt,
	})
	if err != nil {
		t.Fatalf("签发初始会话: %v", err)
	}
	if _, err := facade.Rotate(context.Background(), sessionapp.RotateCommand{
		CurrentRefreshToken: firstToken,
		NextRefreshToken:    secondToken,
		ExpiresAt:           expiresAt.Add(24 * time.Hour),
	}); err != nil {
		t.Fatalf("首次轮换: %v", err)
	}

	_, err = facade.Rotate(context.Background(), sessionapp.RotateCommand{
		CurrentRefreshToken: firstToken,
		NextRefreshToken:    replayReplacement,
		ExpiresAt:           expiresAt.Add(48 * time.Hour),
	})
	assertAppErrorCode(t, err, generatedTokenExpiredCode)
	if got := store.activeCountForLineage(issued.LineageID); got != 0 {
		t.Fatalf("旧 token 重放必须吊销整条 lineage，仍 active=%d", got)
	}
	if store.containsStoredValue(testRefreshTokenHash(replayReplacement)) {
		t.Fatal("重放失败不得签发 replacement session")
	}

	mutationsBeforeLogout := store.mutations
	for attempt := 0; attempt < 2; attempt++ {
		if err := facade.Logout(context.Background(), sessionapp.LogoutCommand{
			RefreshToken: secondToken,
		}); err != nil {
			t.Fatalf("已吊销 token 第 %d 次 logout 应成功: %v", attempt+1, err)
		}
	}
	if store.mutations != mutationsBeforeLogout {
		t.Fatal("已吊销 token 的 logout 必须是无状态变更 no-op")
	}

	thirdToken := []byte("independent-lineage-token")
	third, err := facade.Issue(context.Background(), sessionapp.IssueCommand{
		AccountID:             "account-1",
		DeviceID:              "device-2",
		AuthenticationSubject: "subject-hash-2",
		IdentityOrigin:        "phone",
		RefreshToken:          thirdToken,
		ExpiresAt:             expiresAt,
	})
	if err != nil {
		t.Fatalf("签发独立 lineage: %v", err)
	}
	if err := facade.Revoke(context.Background(), sessionapp.RevokeCommand{
		AccountID: "account-1",
		Reason:    sessionports.RevokeReasonSecuritySalt,
	}); err != nil {
		t.Fatalf("账号安全吊销: %v", err)
	}
	if got := store.activeCountForLineage(third.LineageID); got != 0 {
		t.Fatalf("账号吊销后独立 lineage 仍 active=%d", got)
	}
	mutationsBeforeRepeatedRevoke := store.mutations
	if err := facade.Revoke(context.Background(), sessionapp.RevokeCommand{
		AccountID: "account-1",
		Reason:    sessionports.RevokeReasonSecuritySalt,
	}); err != nil {
		t.Fatalf("重复账号吊销: %v", err)
	}
	if store.mutations != mutationsBeforeRepeatedRevoke {
		t.Fatal("重复账号吊销必须是 no-op")
	}
}

func TestAccountSessionFacadeMapsStoreErrorsToGeneratedUserErrors(t *testing.T) {
	t.Parallel()

	store := newFakeAccountSessionStore()
	facade := sessionapp.NewAccountSessionCommandFacade(store)
	command := sessionapp.RotateCommand{
		CurrentRefreshToken: []byte("current-token"),
		NextRefreshToken:    []byte("next-token"),
		ExpiresAt:           time.Date(2026, 8, 19, 12, 0, 0, 0, time.UTC),
	}
	for _, testCase := range []struct {
		name     string
		storeErr error
		wantCode string
	}{
		{name: "not found", storeErr: sessionports.ErrSessionNotFound, wantCode: generatedUnauthorizedCode},
		{name: "revoked", storeErr: sessionports.ErrSessionRevoked, wantCode: generatedUnauthorizedCode},
		{name: "expired", storeErr: sessionports.ErrSessionExpired, wantCode: generatedTokenExpiredCode},
		{name: "replayed", storeErr: sessionports.ErrSessionReplayed, wantCode: generatedTokenExpiredCode},
		{name: "storage", storeErr: errors.New("database unavailable"), wantCode: generatedInternalErrorCode},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store.rotateError = testCase.storeErr
			_, err := facade.Rotate(context.Background(), command)
			assertAppErrorCode(t, err, testCase.wantCode)
		})
	}

	store.rotateError = nil
	store.revokeByError = sessionports.ErrSessionRevoked
	if err := facade.Logout(context.Background(), sessionapp.LogoutCommand{
		RefreshToken: []byte("already-revoked"),
	}); err != nil {
		t.Fatalf("store 返回 revoked 时 logout 也必须吸收为 no-op: %v", err)
	}
	store.revokeByError = sessionports.ErrSessionNotFound
	if err := facade.Logout(context.Background(), sessionapp.LogoutCommand{
		RefreshToken: []byte("unknown-token"),
	}); err != nil {
		t.Fatalf("store 返回 not found 时 logout 不得泄露 token 存在性: %v", err)
	}
	store.revokeByError = errors.New("database unavailable")
	err := facade.Logout(context.Background(), sessionapp.LogoutCommand{
		RefreshToken: []byte("valid-shape-token"),
	})
	assertAppErrorCode(t, err, generatedInternalErrorCode)
}

const (
	generatedUnauthorizedCode  = "USER.USER.unauthorized"
	generatedTokenExpiredCode  = "USER.AUTH.token_expired"
	generatedInternalErrorCode = "USER.SYSTEM.internal_error"
)

func assertAppErrorCode(t *testing.T, err error, want string) {
	t.Helper()
	if err == nil {
		t.Fatalf("期望 generated user error %s，实际 nil", want)
	}
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("期望 *runtimeerrors.AppError，实际 %T: %v", err, err)
	}
	if got := appErr.Code.String(); got != want {
		t.Fatalf("generated user error code=%s，期望 %s", got, want)
	}
}

func assertNoClientConcurrencyFields(t *testing.T, commands ...any) {
	t.Helper()
	for _, command := range commands {
		commandType := reflect.TypeOf(command)
		for index := 0; index < commandType.NumField(); index++ {
			name := strings.ToLower(commandType.Field(index).Name)
			if strings.Contains(name, "ifmatch") ||
				strings.Contains(name, "idempotency") {
				t.Fatalf("%s 不得暴露客户端并发/幂等字段 %s", commandType, name)
			}
		}
	}
}

func testRefreshTokenHash(token []byte) string {
	digest := sha256.Sum256(token)
	return hex.EncodeToString(digest[:])
}

type fakeAccountSessionStatus string

const (
	fakeSessionActive  fakeAccountSessionStatus = "active"
	fakeSessionRotated fakeAccountSessionStatus = "rotated"
	fakeSessionRevoked fakeAccountSessionStatus = "revoked"
)

type fakeAccountSessionRecord struct {
	session sessionports.IssuedSession
	hash    string
	status  fakeAccountSessionStatus
}

type fakeAccountSessionStore struct {
	records                map[string]*fakeAccountSessionRecord
	nextID                 int
	mutations              int
	lastIssuedHash         string
	lastRotatedCurrentHash string
	lastRotatedNextHash    string
	rotateError            error
	revokeByError          error
}

func newFakeAccountSessionStore() *fakeAccountSessionStore {
	return &fakeAccountSessionStore{
		records: make(map[string]*fakeAccountSessionRecord),
	}
}

func (store *fakeAccountSessionStore) IssueSession(
	_ context.Context,
	accountID string,
	deviceID string,
	_ string,
	_ string,
	refreshTokenHash string,
	expiresAt time.Time,
) (sessionports.IssuedSession, error) {
	store.nextID++
	store.lastIssuedHash = refreshTokenHash
	issued := sessionports.IssuedSession{
		SessionID: fmt.Sprintf("session-%d", store.nextID),
		AccountID: accountID,
		DeviceID:  deviceID,
		LineageID: fmt.Sprintf("lineage-%d", store.nextID),
		ExpiresAt: expiresAt,
	}
	store.records[refreshTokenHash] = &fakeAccountSessionRecord{
		session: issued,
		hash:    refreshTokenHash,
		status:  fakeSessionActive,
	}
	store.mutations++
	return issued, nil
}

func (store *fakeAccountSessionStore) RotateSession(
	_ context.Context,
	currentTokenHash string,
	nextTokenHash string,
	expiresAt time.Time,
) (sessionports.IssuedSession, error) {
	store.lastRotatedCurrentHash = currentTokenHash
	store.lastRotatedNextHash = nextTokenHash
	if store.rotateError != nil {
		return sessionports.IssuedSession{}, store.rotateError
	}
	current, found := store.records[currentTokenHash]
	if !found {
		return sessionports.IssuedSession{}, sessionports.ErrSessionNotFound
	}
	switch current.status {
	case fakeSessionRotated:
		for _, record := range store.records {
			if record.session.LineageID == current.session.LineageID &&
				record.status != fakeSessionRevoked {
				record.status = fakeSessionRevoked
				store.mutations++
			}
		}
		return sessionports.IssuedSession{}, sessionports.ErrSessionReplayed
	case fakeSessionRevoked:
		return sessionports.IssuedSession{}, sessionports.ErrSessionRevoked
	case fakeSessionActive:
	default:
		return sessionports.IssuedSession{}, sessionports.ErrSessionExpired
	}
	current.status = fakeSessionRotated
	store.mutations++
	store.nextID++
	issued := sessionports.IssuedSession{
		SessionID: fmt.Sprintf("session-%d", store.nextID),
		AccountID: current.session.AccountID,
		DeviceID:  current.session.DeviceID,
		LineageID: current.session.LineageID,
		ExpiresAt: expiresAt,
	}
	store.records[nextTokenHash] = &fakeAccountSessionRecord{
		session: issued,
		hash:    nextTokenHash,
		status:  fakeSessionActive,
	}
	store.mutations++
	return issued, nil
}

func (store *fakeAccountSessionStore) RevokeByTokenHash(
	_ context.Context,
	refreshTokenHash string,
	_ string,
) error {
	if store.revokeByError != nil {
		return store.revokeByError
	}
	record, found := store.records[refreshTokenHash]
	if !found || record.status == fakeSessionRevoked {
		return nil
	}
	record.status = fakeSessionRevoked
	store.mutations++
	return nil
}

func (store *fakeAccountSessionStore) RevokeAllForAccount(
	_ context.Context,
	accountID string,
	_ string,
) error {
	for _, record := range store.records {
		if record.session.AccountID == accountID &&
			record.status != fakeSessionRevoked {
			record.status = fakeSessionRevoked
			store.mutations++
		}
	}
	return nil
}

func (store *fakeAccountSessionStore) containsStoredValue(value string) bool {
	for hash, record := range store.records {
		if hash == value || record.hash == value {
			return true
		}
	}
	return false
}

func (store *fakeAccountSessionStore) activeCountForLineage(lineageID string) int {
	count := 0
	for _, record := range store.records {
		if record.session.LineageID == lineageID &&
			record.status == fakeSessionActive {
			count++
		}
	}
	return count
}

var _ sessionports.AccountSessionStore = (*fakeAccountSessionStore)(nil)
