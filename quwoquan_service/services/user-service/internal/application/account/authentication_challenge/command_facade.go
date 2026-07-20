// Package authentication_challenge 提供 AuthenticationChallenge 对象专属、
// 强类型 command facet。
package authentication_challenge

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	challengemodel "quwoquan_service/services/user-service/internal/domain/account/authentication_challenge/model"
	challengeports "quwoquan_service/services/user-service/internal/domain/account/authentication_challenge/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const (
	defaultMaxVerificationAttempts = 5
	challengeCommitAttempts        = 3
)

type CommandFacet interface {
	CreateChallenge(context.Context, CreateChallengeCommand) (ChallengeCommandResult, error)
	VerifyChallenge(context.Context, VerifyChallengeCommand) (ChallengeCommandResult, error)
	CancelChallenge(context.Context, CancelChallengeCommand) (ChallengeCommandResult, error)
}

type AuthenticationChallengeCommandFacade struct {
	store       challengeports.AggregateStore
	verifier    challengeports.CredentialVerifier
	now         func() time.Time
	maxAttempts int
}

type Option func(*AuthenticationChallengeCommandFacade)

func WithClock(now func() time.Time) Option {
	return func(facade *AuthenticationChallengeCommandFacade) {
		if now != nil {
			facade.now = now
		}
	}
}

func WithMaxVerificationAttempts(maxAttempts int) Option {
	return func(facade *AuthenticationChallengeCommandFacade) {
		facade.maxAttempts = maxAttempts
	}
}

func NewAuthenticationChallengeCommandFacade(
	store challengeports.AggregateStore,
	verifier challengeports.CredentialVerifier,
	options ...Option,
) *AuthenticationChallengeCommandFacade {
	if store == nil {
		panic("AuthenticationChallengeCommandFacade requires an object-specific AggregateStore")
	}
	if verifier == nil {
		panic("AuthenticationChallengeCommandFacade requires a CredentialVerifier")
	}
	facade := &AuthenticationChallengeCommandFacade{
		store:       store,
		verifier:    verifier,
		now:         time.Now,
		maxAttempts: defaultMaxVerificationAttempts,
	}
	for _, option := range options {
		if option != nil {
			option(facade)
		}
	}
	if facade.maxAttempts <= 0 {
		panic("AuthenticationChallengeCommandFacade requires a positive attempt limit")
	}
	return facade
}

var _ CommandFacet = (*AuthenticationChallengeCommandFacade)(nil)

func (facade *AuthenticationChallengeCommandFacade) CreateChallenge(
	ctx context.Context,
	command CreateChallengeCommand,
) (ChallengeCommandResult, error) {
	idempotencyKey := strings.TrimSpace(command.IdempotencyKey)
	if idempotencyKey == "" || len(idempotencyKey) > 256 {
		return ChallengeCommandResult{}, generated.AppErrorFromInvalidArgument(
			"authentication challenge requires an idempotency key",
		)
	}
	aggregate, err := challengemodel.New(challengemodel.CreateParams{
		ID:              command.ID,
		AccountID:       command.AccountID,
		Purpose:         command.Purpose,
		Channel:         command.Channel,
		DestinationHash: command.DestinationHash,
		SecretRef:       command.SecretRef,
		ExpiresAt:       command.ExpiresAt,
		CreatedAt:       facade.now().UTC(),
	})
	if err != nil {
		return ChallengeCommandResult{}, mapChallengeError(err)
	}
	result, err := facade.store.Create(ctx, challengeports.CreateCommit{
		Aggregate:          aggregate,
		IdempotencyKey:     idempotencyKey,
		CommandFingerprint: creationCommandFingerprint(aggregate.Snapshot()),
	})
	if err != nil {
		return ChallengeCommandResult{}, mapChallengeError(err)
	}
	if err := result.Aggregate.Validate(); err != nil {
		return ChallengeCommandResult{}, generated.AppErrorFromInternalError(
			"authentication challenge store returned invalid state",
		)
	}
	return ChallengeCommandResult{
		Challenge:        result.Aggregate.Snapshot(),
		IdempotentReplay: result.Replayed,
	}, nil
}

func (facade *AuthenticationChallengeCommandFacade) VerifyChallenge(
	ctx context.Context,
	command VerifyChallengeCommand,
) (ChallengeCommandResult, error) {
	credential := append([]byte(nil), command.Credential...)
	defer clearBytes(credential)
	if len(credential) == 0 {
		return ChallengeCommandResult{}, generated.AppErrorFromInvalidArgument(
			"authentication challenge credential is required",
		)
	}
	lookup, err := normalizeVerificationLookup(command)
	if err != nil {
		return ChallengeCommandResult{}, err
	}

	for attempt := 0; attempt < challengeCommitAttempts; attempt++ {
		aggregate, found, loadErr := facade.load(ctx, lookup)
		if loadErr != nil {
			return ChallengeCommandResult{}, mapChallengeError(loadErr)
		}
		if !found {
			return ChallengeCommandResult{}, generated.AppErrorFromOtpExpired(
				"authentication challenge is absent",
			)
		}
		state := aggregate.State()
		evidence, verifyErr := facade.verifier.VerifyCredential(
			ctx,
			challengeports.CredentialVerificationInput{
				ChallengeID:     state.ID,
				Purpose:         state.Purpose,
				Channel:         state.Channel,
				DestinationHash: state.DestinationHash,
				SecretRef:       state.SecretRef,
				Credential:      credential,
			},
		)
		if verifyErr != nil {
			return ChallengeCommandResult{}, generated.AppErrorFromInternalError(
				"authentication challenge credential verifier failed",
			)
		}
		transition, transitionErr := aggregate.Verify(challengemodel.VerificationAttempt{
			CompletionFingerprint: evidence.CompletionFingerprint,
			Matched:               evidence.Matched,
			AttemptedAt:           facade.now().UTC(),
			MaxAttempts:           facade.maxAttempts,
		})
		if transitionErr != nil {
			return ChallengeCommandResult{}, mapChallengeError(transitionErr)
		}
		if transition.Changed {
			commitErr := facade.store.Commit(ctx, state.Version, transition.Aggregate)
			if errors.Is(commitErr, challengemodel.ErrVersionConflict) &&
				attempt+1 < challengeCommitAttempts {
				continue
			}
			if commitErr != nil {
				return ChallengeCommandResult{}, mapChallengeError(commitErr)
			}
		}
		return verificationCommandResult(transition)
	}
	panic("unreachable AuthenticationChallenge CAS retry")
}

func (facade *AuthenticationChallengeCommandFacade) CancelChallenge(
	ctx context.Context,
	command CancelChallengeCommand,
) (ChallengeCommandResult, error) {
	challengeID := strings.TrimSpace(command.ChallengeID)
	if challengeID == "" {
		return ChallengeCommandResult{}, generated.AppErrorFromInvalidArgument(
			"authentication challenge id is required",
		)
	}
	for attempt := 0; attempt < challengeCommitAttempts; attempt++ {
		aggregate, found, err := facade.store.LoadByID(ctx, challengeID)
		if err != nil {
			return ChallengeCommandResult{}, mapChallengeError(err)
		}
		if !found {
			return ChallengeCommandResult{}, generated.AppErrorFromOtpExpired(
				"authentication challenge is absent",
			)
		}
		expectedVersion := aggregate.Snapshot().Version
		mutation, err := aggregate.Cancel(facade.now().UTC())
		if err != nil {
			return ChallengeCommandResult{}, mapChallengeError(err)
		}
		if !mutation.Changed {
			return ChallengeCommandResult{
				Challenge:        aggregate.Snapshot(),
				IdempotentReplay: true,
			}, nil
		}
		err = facade.store.Commit(ctx, expectedVersion, mutation.Aggregate)
		if errors.Is(err, challengemodel.ErrVersionConflict) &&
			attempt+1 < challengeCommitAttempts {
			continue
		}
		if err != nil {
			return ChallengeCommandResult{}, mapChallengeError(err)
		}
		return ChallengeCommandResult{Challenge: mutation.Aggregate.Snapshot()}, nil
	}
	panic("unreachable AuthenticationChallenge cancellation CAS retry")
}

type verificationLookup struct {
	challengeID string
	latest      challengeports.LatestChallengeLookup
}

func normalizeVerificationLookup(
	command VerifyChallengeCommand,
) (verificationLookup, error) {
	challengeID := strings.TrimSpace(command.ChallengeID)
	purpose := strings.TrimSpace(command.Purpose)
	channel := strings.TrimSpace(command.Channel)
	destinationHash := strings.TrimSpace(command.DestinationHash)
	hasLatestLookup := purpose != "" || channel != "" || destinationHash != ""
	if challengeID != "" && hasLatestLookup {
		return verificationLookup{}, generated.AppErrorFromInvalidArgument(
			"challengeId and latest challenge lookup cannot be combined",
		)
	}
	if challengeID != "" {
		return verificationLookup{challengeID: challengeID}, nil
	}
	if purpose == "" || channel == "" || destinationHash == "" {
		return verificationLookup{}, generated.AppErrorFromInvalidArgument(
			"latest challenge lookup requires purpose, channel and destinationHash",
		)
	}
	return verificationLookup{latest: challengeports.LatestChallengeLookup{
		Purpose:         purpose,
		Channel:         channel,
		DestinationHash: destinationHash,
	}}, nil
}

func (facade *AuthenticationChallengeCommandFacade) load(
	ctx context.Context,
	lookup verificationLookup,
) (challengemodel.AuthenticationChallenge, bool, error) {
	if lookup.challengeID != "" {
		return facade.store.LoadByID(ctx, lookup.challengeID)
	}
	return facade.store.LoadLatest(ctx, lookup.latest)
}

func verificationCommandResult(
	transition challengemodel.VerificationTransition,
) (ChallengeCommandResult, error) {
	switch transition.Outcome {
	case challengemodel.VerificationSucceeded:
		return ChallengeCommandResult{Challenge: transition.Aggregate.Snapshot()}, nil
	case challengemodel.VerificationReplayed:
		return ChallengeCommandResult{
			Challenge:        transition.Aggregate.Snapshot(),
			IdempotentReplay: true,
		}, nil
	case challengemodel.VerificationMismatch:
		return ChallengeCommandResult{}, generated.AppErrorFromOtpMismatch(
			"authentication challenge credential did not match",
		)
	case challengemodel.VerificationLocked:
		return ChallengeCommandResult{}, generated.AppErrorFromOtpAttemptsExceeded(
			"authentication challenge reached the verification attempt limit",
		)
	case challengemodel.VerificationExpired, challengemodel.VerificationCancelled:
		return ChallengeCommandResult{}, generated.AppErrorFromOtpExpired(
			"authentication challenge is no longer verifiable",
		)
	case challengemodel.VerificationConsumed:
		return ChallengeCommandResult{}, generated.AppErrorFromChallengeConsumed(
			"authentication challenge completed with another credential",
		)
	default:
		return ChallengeCommandResult{}, generated.AppErrorFromInternalError(
			"authentication challenge produced an unknown verification outcome",
		)
	}
}

func mapChallengeError(err error) error {
	switch {
	case errors.Is(err, challengeports.ErrIdempotencyConflict):
		return generated.AppErrorFromInvalidArgument(
			"authentication challenge idempotency key was reused for another target",
		)
	case errors.Is(err, challengemodel.ErrInvalidChallenge):
		return generated.AppErrorFromInvalidArgument(err.Error())
	case errors.Is(err, challengemodel.ErrVersionConflict):
		return generated.AppErrorFromInternalError(
			"authentication challenge changed repeatedly during commit",
		)
	default:
		return generated.AppErrorFromInternalError(
			"authentication challenge persistence failed",
		)
	}
}

// creationCommandFingerprint 只绑定稳定的非 secret 创建范围。ID、secretRef 与
// expiresAt 可能在客户端超时重试时重新生成，不参与幂等身份；同 key 跨目标复用会拒绝。
func creationCommandFingerprint(snapshot challengemodel.Snapshot) string {
	sum := sha256.Sum256([]byte(strings.Join([]string{
		snapshot.AccountID,
		snapshot.Purpose,
		snapshot.Channel,
		snapshot.DestinationHash,
	}, "\x00")))
	return hex.EncodeToString(sum[:])
}

func clearBytes(value []byte) {
	for index := range value {
		value[index] = 0
	}
}
