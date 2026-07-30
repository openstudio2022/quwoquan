// Package application implements the AccountAppealIntake command packet.
package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"io"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	appealgenerated "quwoquan_service/services/user-service/generated/account/account_appeal_intake"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/model"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
)

type IssueCredentialCommand struct {
	Phone       string
	OTPCode     []byte
	ChallengeID string
}

type CredentialIssueResult struct {
	AppealCredential string    `json:"appealCredential"`
	ExpiresAt        time.Time `json:"expiresAt"`
}

type SubmitIntakeCommand struct {
	AppealCredential string
	IdempotencyKey   string
}

type IntakeSubmissionResult struct {
	IntakeRef        string    `json:"intakeRef"`
	SubmittedAt      time.Time `json:"submittedAt"`
	DeleteAfter      time.Time `json:"deleteAfter"`
	IdempotentReplay bool      `json:"idempotentReplay"`
}

type ClaimIntakeCommand struct {
	IntakeRef      string
	AccountID      string
	CaseID         string
	IdempotencyKey string
}

type IntakeClaimResult struct {
	IntakeRef        string    `json:"intakeRef"`
	AccountID        string    `json:"accountId"`
	CaseID           string    `json:"caseId"`
	Status           string    `json:"status"`
	ClaimedAt        time.Time `json:"claimedAt"`
	IdempotentReplay bool      `json:"idempotentReplay"`
}

type CommandFacade struct {
	store      ports.Store
	identities ports.IdentityChallengeVerifier
	metrics    ports.Metrics
	now        func() time.Time
	entropy    io.Reader
}

type Option func(*CommandFacade)

func WithClock(now func() time.Time) Option {
	return func(facade *CommandFacade) {
		if now != nil {
			facade.now = now
		}
	}
}

func WithEntropy(entropy io.Reader) Option {
	return func(facade *CommandFacade) {
		if entropy != nil {
			facade.entropy = entropy
		}
	}
}

func NewCommandFacade(
	store ports.Store,
	identities ports.IdentityChallengeVerifier,
	metrics ports.Metrics,
	options ...Option,
) *CommandFacade {
	if store == nil || identities == nil {
		panic("AccountAppealIntake requires store and identity challenge verifier")
	}
	if metrics == nil {
		metrics = noopMetrics{}
	}
	facade := &CommandFacade{
		store: store, identities: identities, metrics: metrics,
		now: time.Now, entropy: rand.Reader,
	}
	for _, option := range options {
		if option != nil {
			option(facade)
		}
	}
	return facade
}

func (facade *CommandFacade) IssueCredential(
	ctx context.Context,
	command IssueCredentialCommand,
) (CredentialIssueResult, error) {
	started := time.Now()
	outcome := "failed"
	defer func() { facade.metrics.ObserveCommand("issue_credential", outcome, time.Since(started)) }()

	phone := strings.TrimSpace(command.Phone)
	challengeID := strings.TrimSpace(command.ChallengeID)
	otpCode := append([]byte(nil), command.OTPCode...)
	defer clearBytes(otpCode)
	if phone == "" || len(phone) > 64 || challengeID == "" ||
		len(challengeID) > 128 || len(otpCode) == 0 || len(otpCode) > 32 {
		return CredentialIssueResult{}, usergenerated.AppErrorFromInvalidArgument(
			"phone, otpCode and challengeId are required",
		)
	}
	evidence, err := facade.identities.VerifyAccountAppealChallenge(
		ctx, phone, otpCode, challengeID,
	)
	if err != nil {
		return CredentialIssueResult{}, mapIdentityError(err)
	}
	now := facade.now().UTC()
	if !model.CanonicalOwnerAccountID(strings.TrimSpace(evidence.AccountID)) ||
		strings.TrimSpace(evidence.ChallengeID) != challengeID ||
		evidence.ExpiresAt.IsZero() || !now.Before(evidence.ExpiresAt.UTC()) {
		return CredentialIssueResult{}, appealgenerated.AppErrorFromAccountAppealCredentialInvalid(
			"verified identity challenge is incomplete or expired",
		)
	}
	credential, err := randomOpaque(facade.entropy, "appeal_credential_", 32)
	if err != nil {
		return CredentialIssueResult{}, usergenerated.AppErrorFromInternalError(
			"generate account appeal credential",
		)
	}
	digest := opaqueDigest(credential)
	expiresAt := now.Add(model.CredentialTTL)
	receipt, err := facade.store.IssueCredential(ctx, ports.IssueCredentialCommit{
		CredentialID:     "appeal_credential_" + digest[:24],
		CredentialDigest: digest,
		ChallengeID:      challengeID,
		AccountID:        evidence.AccountID,
		IssuedAt:         now,
		ExpiresAt:        expiresAt,
		DeleteAfter:      expiresAt.Add(model.CredentialAuditRetention),
	})
	if err != nil {
		return CredentialIssueResult{}, mapStoreError(err)
	}
	if receipt.ExpiresAt.IsZero() || !receipt.ExpiresAt.Equal(expiresAt) {
		return CredentialIssueResult{}, usergenerated.AppErrorFromInternalError(
			"account appeal credential store returned an invalid receipt",
		)
	}
	outcome = "issued"
	return CredentialIssueResult{
		AppealCredential: credential,
		ExpiresAt:        expiresAt,
	}, nil
}

func (facade *CommandFacade) SubmitIntake(
	ctx context.Context,
	command SubmitIntakeCommand,
) (IntakeSubmissionResult, error) {
	started := time.Now()
	outcome := "failed"
	defer func() { facade.metrics.ObserveCommand("submit_intake", outcome, time.Since(started)) }()

	idempotencyKey := strings.TrimSpace(command.IdempotencyKey)
	credential := strings.TrimSpace(command.AppealCredential)
	if idempotencyKey == "" || len(idempotencyKey) > 160 ||
		!model.CanonicalAppealCredential(credential) {
		return IntakeSubmissionResult{}, usergenerated.AppErrorFromInvalidArgument(
			"appealCredential and Idempotency-Key are required",
		)
	}
	credentialDigest := opaqueDigest(credential)
	intakeRef, err := randomOpaque(facade.entropy, "appeal_intake_", 24)
	if err != nil {
		return IntakeSubmissionResult{}, usergenerated.AppErrorFromInternalError(
			"generate account appeal intake reference",
		)
	}
	now := facade.now().UTC()
	result, err := facade.store.Submit(ctx, ports.SubmitCommit{
		CredentialDigest: credentialDigest,
		IntakeRef:        intakeRef,
		IdempotencyKey:   idempotencyKey,
		CommandDigest:    stableDigest("submit", credentialDigest),
		SubmittedAt:      now,
		DeleteAfter:      now.Add(model.IntakeRetention),
	})
	if err != nil {
		return IntakeSubmissionResult{}, mapStoreError(err)
	}
	state := result.Intake.State()
	outcome = "submitted"
	if result.IdempotentReplay {
		outcome = "replayed"
	}
	return IntakeSubmissionResult{
		IntakeRef: state.IntakeRef, SubmittedAt: state.SubmittedAt,
		DeleteAfter: state.DeleteAfter, IdempotentReplay: result.IdempotentReplay,
	}, nil
}

func (facade *CommandFacade) ClaimIntake(
	ctx context.Context,
	command ClaimIntakeCommand,
) (IntakeClaimResult, error) {
	started := time.Now()
	outcome := "failed"
	defer func() { facade.metrics.ObserveCommand("claim_intake", outcome, time.Since(started)) }()

	command.IntakeRef = strings.TrimSpace(command.IntakeRef)
	command.AccountID = strings.TrimSpace(command.AccountID)
	command.CaseID = strings.TrimSpace(command.CaseID)
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	if !model.CanonicalIntakeRef(command.IntakeRef) ||
		!model.CanonicalOwnerAccountID(command.AccountID) ||
		!model.CanonicalAppealCaseID(command.CaseID) ||
		command.IdempotencyKey == "" || len(command.IdempotencyKey) > 160 {
		return IntakeClaimResult{}, usergenerated.AppErrorFromInvalidArgument(
			"intakeRef, accountId, caseId and Idempotency-Key are required",
		)
	}
	result, err := facade.store.Claim(ctx, ports.ClaimCommit{
		IntakeRef: command.IntakeRef, AccountID: command.AccountID,
		CaseID: command.CaseID, IdempotencyKey: command.IdempotencyKey,
		CommandDigest: stableDigest(
			"claim", command.IntakeRef, command.AccountID, command.CaseID,
		),
		ClaimedAt: facade.now().UTC(),
	})
	if err != nil {
		return IntakeClaimResult{}, mapStoreError(err)
	}
	state := result.Intake.State()
	if state.ClaimedAt == nil {
		return IntakeClaimResult{}, usergenerated.AppErrorFromInternalError(
			"claimed account appeal intake has no claim receipt",
		)
	}
	outcome = "claimed"
	if result.IdempotentReplay {
		outcome = "replayed"
	}
	return IntakeClaimResult{
		IntakeRef: state.IntakeRef, AccountID: state.AccountID,
		CaseID: state.ClaimedCaseID, Status: string(state.Status),
		ClaimedAt: state.ClaimedAt.UTC(), IdempotentReplay: result.IdempotentReplay,
	}, nil
}

func (facade *CommandFacade) PurgeExpired(ctx context.Context) error {
	credentials, intakes, err := facade.store.PurgeExpired(ctx, facade.now().UTC())
	if err != nil {
		return err
	}
	if credentials > 0 {
		facade.metrics.AddPurged("credential", float64(credentials))
	}
	if intakes > 0 {
		facade.metrics.AddPurged("intake", float64(intakes))
	}
	return nil
}

func (facade *CommandFacade) RunRetentionPurge(
	ctx context.Context,
	interval time.Duration,
) error {
	if interval <= 0 {
		return errors.New("AccountAppealIntake purge interval must be positive")
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			started := time.Now()
			if err := facade.PurgeExpired(ctx); err != nil && ctx.Err() == nil {
				facade.metrics.ObserveCommand(
					"retention_purge", "failed", time.Since(started),
				)
				continue
			}
			facade.metrics.ObserveCommand(
				"retention_purge", "completed", time.Since(started),
			)
		}
	}
}

func mapIdentityError(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	if errors.Is(err, ports.ErrIdentityNotFound) {
		return appealgenerated.AppErrorFromAccountAppealCredentialInvalid(
			"verified phone identity is not bound to an account",
		)
	}
	return usergenerated.AppErrorFromInternalError(
		"account appeal identity verification failed",
	)
}

func mapStoreError(err error) error {
	switch {
	case errors.Is(err, ports.ErrCredentialInvalid):
		return appealgenerated.AppErrorFromAccountAppealCredentialInvalid(err.Error())
	case errors.Is(err, ports.ErrCredentialExpired):
		return appealgenerated.AppErrorFromAccountAppealCredentialExpired(err.Error())
	case errors.Is(err, ports.ErrCredentialConsumed):
		return appealgenerated.AppErrorFromAccountAppealCredentialConsumed(err.Error())
	case errors.Is(err, ports.ErrAccountNotSuspended):
		return appealgenerated.AppErrorFromAccountAppealNotSuspended(err.Error())
	case errors.Is(err, ports.ErrRateLimited):
		return appealgenerated.AppErrorFromAccountAppealRateLimited(err.Error())
	case errors.Is(err, ports.ErrIntakeNotFound):
		return appealgenerated.AppErrorFromAccountAppealIntakeNotFound(err.Error())
	case errors.Is(err, ports.ErrAccountMismatch):
		return appealgenerated.AppErrorFromAccountAppealIntakeAccountMismatch(err.Error())
	case errors.Is(err, ports.ErrIntakeClaimed):
		return appealgenerated.AppErrorFromAccountAppealIntakeClaimed(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return appealgenerated.AppErrorFromAccountAppealIdempotencyConflict(err.Error())
	default:
		return usergenerated.AppErrorFromInternalError(
			"AccountAppealIntake persistence failed",
		)
	}
}

func randomOpaque(entropy io.Reader, prefix string, size int) (string, error) {
	value := make([]byte, size)
	defer clearBytes(value)
	if _, err := io.ReadFull(entropy, value); err != nil {
		return "", err
	}
	return prefix + base64.RawURLEncoding.EncodeToString(value), nil
}

func opaqueDigest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func stableDigest(parts ...string) string {
	sum := sha256.Sum256([]byte(strings.Join(parts, "\x00")))
	return hex.EncodeToString(sum[:])
}

func clearBytes(value []byte) {
	for index := range value {
		value[index] = 0
	}
}

type noopMetrics struct{}

func (noopMetrics) ObserveCommand(string, string, time.Duration) {}
func (noopMetrics) AddPurged(string, float64)                    {}
