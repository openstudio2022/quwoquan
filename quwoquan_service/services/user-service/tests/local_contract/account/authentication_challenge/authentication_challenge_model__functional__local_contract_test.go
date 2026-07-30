package local_contract

import (
	"testing"
	"time"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

func TestAuthenticationChallengeVerificationStateMachine(t *testing.T) {
	t.Parallel()

	createdAt := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	challenge := newAuthenticationChallenge(t, createdAt, createdAt.Add(5*time.Minute))

	mismatch, err := challenge.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-wrong-1",
		Matched:               false,
		AttemptedAt:           createdAt.Add(time.Minute),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("第一次错误验证: %v", err)
	}
	if mismatch.Outcome != challengemodel.VerificationMismatch ||
		mismatch.Aggregate.Snapshot().Status != challengemodel.StatusPending ||
		mismatch.Aggregate.Snapshot().AttemptCount != 1 {
		t.Fatalf("错误验证应保持 pending 并累加次数: %+v", mismatch)
	}

	success, err := mismatch.Aggregate.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-correct",
		Matched:               true,
		AttemptedAt:           createdAt.Add(2 * time.Minute),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("正确验证: %v", err)
	}
	snapshot := success.Aggregate.Snapshot()
	if success.Outcome != challengemodel.VerificationSucceeded ||
		snapshot.Status != challengemodel.StatusCompleted ||
		snapshot.CompletedAt == nil {
		t.Fatalf("正确验证应进入 completed: %+v", success)
	}

	replayed, err := success.Aggregate.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-correct",
		Matched:               true,
		AttemptedAt:           createdAt.Add(10 * time.Minute),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("相同凭据重放: %v", err)
	}
	if replayed.Outcome != challengemodel.VerificationReplayed ||
		replayed.Changed ||
		replayed.Aggregate.Snapshot().Version != snapshot.Version {
		t.Fatalf("completed 后相同凭据应返回原结果且不推进版本: %+v", replayed)
	}

	different, err := success.Aggregate.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-different",
		Matched:               false,
		AttemptedAt:           createdAt.Add(3 * time.Minute),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("不同凭据重放判定: %v", err)
	}
	if different.Outcome != challengemodel.VerificationConsumed || different.Changed {
		t.Fatalf("completed 后不同凭据必须拒绝且不改状态: %+v", different)
	}
}

func TestAuthenticationChallengeLocksAtBoundedAttemptLimit(t *testing.T) {
	t.Parallel()

	createdAt := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	challenge := newAuthenticationChallenge(t, createdAt, createdAt.Add(5*time.Minute))

	for attempt := 1; attempt <= 3; attempt++ {
		transition, err := challenge.Verify(challengemodel.VerificationAttempt{
			CompletionFingerprint: "wrong-fingerprint",
			Matched:               false,
			AttemptedAt:           createdAt.Add(time.Duration(attempt) * time.Second),
			MaxAttempts:           3,
		})
		if err != nil {
			t.Fatalf("第 %d 次错误验证: %v", attempt, err)
		}
		challenge = transition.Aggregate
		if attempt < 3 && transition.Outcome != challengemodel.VerificationMismatch {
			t.Fatalf("第 %d 次应为 mismatch，得到 %s", attempt, transition.Outcome)
		}
		if attempt == 3 && transition.Outcome != challengemodel.VerificationLocked {
			t.Fatalf("第 3 次应锁定，得到 %s", transition.Outcome)
		}
	}

	locked := challenge.Snapshot()
	if locked.Status != challengemodel.StatusLocked || locked.AttemptCount != 3 {
		t.Fatalf("达到上限后状态错误: %+v", locked)
	}
	rejected, err := challenge.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-correct",
		Matched:               true,
		AttemptedAt:           createdAt.Add(time.Minute),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("锁定后的验证判定: %v", err)
	}
	if rejected.Outcome != challengemodel.VerificationLocked || rejected.Changed {
		t.Fatalf("锁定后正确凭据也必须拒绝且不改状态: %+v", rejected)
	}
}

func TestAuthenticationChallengeExpiryIsPersistableTerminalTransition(t *testing.T) {
	t.Parallel()

	createdAt := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	expiresAt := createdAt.Add(time.Minute)
	challenge := newAuthenticationChallenge(t, createdAt, expiresAt)

	expired, err := challenge.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-correct",
		Matched:               true,
		AttemptedAt:           expiresAt,
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("过期验证判定: %v", err)
	}
	if expired.Outcome != challengemodel.VerificationExpired ||
		!expired.Changed ||
		expired.Aggregate.Snapshot().Status != challengemodel.StatusExpired {
		t.Fatalf("到期验证应产生可持久化 expired 迁移: %+v", expired)
	}

	again, err := expired.Aggregate.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-correct",
		Matched:               true,
		AttemptedAt:           expiresAt.Add(time.Second),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("重复过期验证判定: %v", err)
	}
	if again.Outcome != challengemodel.VerificationExpired || again.Changed {
		t.Fatalf("expired 必须是稳定终态: %+v", again)
	}
}

func TestAuthenticationChallengeCancellationIsTerminal(t *testing.T) {
	t.Parallel()

	createdAt := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	challenge := newAuthenticationChallenge(t, createdAt, createdAt.Add(5*time.Minute))
	cancelled, err := challenge.Cancel(createdAt.Add(time.Minute))
	if err != nil {
		t.Fatalf("取消 challenge: %v", err)
	}
	if !cancelled.Changed ||
		cancelled.Aggregate.Snapshot().Status != challengemodel.StatusCancelled {
		t.Fatalf("pending 应迁移到 cancelled: %+v", cancelled)
	}

	rejected, err := cancelled.Aggregate.Verify(challengemodel.VerificationAttempt{
		CompletionFingerprint: "fingerprint-correct",
		Matched:               true,
		AttemptedAt:           createdAt.Add(2 * time.Minute),
		MaxAttempts:           3,
	})
	if err != nil {
		t.Fatalf("取消后验证判定: %v", err)
	}
	if rejected.Outcome != challengemodel.VerificationCancelled || rejected.Changed {
		t.Fatalf("cancelled 必须拒绝验证且保持终态: %+v", rejected)
	}

	replayedCancel, err := cancelled.Aggregate.Cancel(createdAt.Add(3 * time.Minute))
	if err != nil {
		t.Fatalf("重复取消: %v", err)
	}
	if replayedCancel.Changed ||
		replayedCancel.Aggregate.Snapshot().Version !=
			cancelled.Aggregate.Snapshot().Version {
		t.Fatalf("重复取消必须是稳定 no-op: %+v", replayedCancel)
	}
}

func TestAuthenticationChallengeScopesFederatedPhoneBindingOTPToTicket(t *testing.T) {
	t.Parallel()

	createdAt := time.Date(2026, 7, 28, 12, 0, 0, 0, time.UTC)
	challenge, err := challengemodel.New(challengemodel.CreateParams{
		ID:               "challenge-social-bind",
		Purpose:          "bind_phone",
		Channel:          "sms",
		DestinationHash:  "destination-fingerprint",
		SecretRef:        "opaque-secret-reference",
		BindingTicketRef: "fbt_ticket-1",
		ExpiresAt:        createdAt.Add(5 * time.Minute),
		CreatedAt:        createdAt,
	})
	if err != nil {
		t.Fatalf("创建 ticket-scoped challenge: %v", err)
	}
	if challenge.Snapshot().BindingTicketRef != "fbt_ticket-1" {
		t.Fatalf("binding ticket ref 丢失: %+v", challenge.Snapshot())
	}

	_, err = challengemodel.New(challengemodel.CreateParams{
		ID:               "challenge-invalid-scope",
		Purpose:          "phone_login",
		Channel:          "sms",
		DestinationHash:  "destination-fingerprint",
		SecretRef:        "opaque-secret-reference",
		BindingTicketRef: "fbt_ticket-1",
		ExpiresAt:        createdAt.Add(5 * time.Minute),
		CreatedAt:        createdAt,
	})
	if err == nil {
		t.Fatal("phone_login challenge must reject a federated binding ticket ref")
	}
}

func newAuthenticationChallenge(
	t *testing.T,
	createdAt time.Time,
	expiresAt time.Time,
) challengemodel.AuthenticationChallenge {
	t.Helper()
	challenge, err := challengemodel.New(challengemodel.CreateParams{
		ID:              "challenge-1",
		AccountID:       "account-1",
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: "destination-fingerprint",
		SecretRef:       "opaque-secret-reference",
		ExpiresAt:       expiresAt,
		CreatedAt:       createdAt,
	})
	if err != nil {
		t.Fatalf("创建 challenge: %v", err)
	}
	return challenge
}
