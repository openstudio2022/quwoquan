// Package model defines the User-owned AccountAppealIntake aggregate.
package model

import (
	"errors"
	"fmt"
	"strings"
	"time"

	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
)

var (
	ErrInvalidIntake   = errors.New("account appeal intake is invalid")
	ErrAccountMismatch = errors.New("account appeal intake account mismatch")
	ErrAlreadyClaimed  = errors.New("account appeal intake already claimed")
)

type Status string

const (
	StatusSubmitted Status = "submitted"
	StatusClaimed   Status = "claimed"
)

func (status Status) Valid() bool {
	return status == StatusSubmitted || status == StatusClaimed
}

// State is the private persistence representation. AccountID and AuthEpoch are
// identity/security facts and must never be returned by the public submission
// operation.
type State struct {
	IntakeRef           string
	AccountID           string
	SuspensionAuthEpoch int64
	Status              Status
	SubmittedAt         time.Time
	ClaimedCaseID       string
	ClaimedAt           *time.Time
	DeleteAfter         time.Time
	Version             int64
}

type CreateParams struct {
	IntakeRef           string
	AccountID           string
	SuspensionAuthEpoch int64
	SubmittedAt         time.Time
	DeleteAfter         time.Time
}

type AccountAppealIntake struct {
	state State
}

func NewSubmitted(params CreateParams) (AccountAppealIntake, error) {
	return Restore(State{
		IntakeRef:           params.IntakeRef,
		AccountID:           params.AccountID,
		SuspensionAuthEpoch: params.SuspensionAuthEpoch,
		Status:              StatusSubmitted,
		SubmittedAt:         params.SubmittedAt,
		DeleteAfter:         params.DeleteAfter,
		Version:             1,
	})
}

func Restore(state State) (AccountAppealIntake, error) {
	state.IntakeRef = strings.TrimSpace(state.IntakeRef)
	state.AccountID = strings.TrimSpace(state.AccountID)
	state.ClaimedCaseID = strings.TrimSpace(state.ClaimedCaseID)
	state.SubmittedAt = state.SubmittedAt.UTC()
	state.DeleteAfter = state.DeleteAfter.UTC()
	state.ClaimedAt = cloneTime(state.ClaimedAt)
	if err := validateState(state); err != nil {
		return AccountAppealIntake{}, err
	}
	return AccountAppealIntake{state: state}, nil
}

func (intake AccountAppealIntake) State() State {
	state := intake.state
	state.ClaimedAt = cloneTime(state.ClaimedAt)
	return state
}

func (intake AccountAppealIntake) Validate() error {
	return validateState(intake.state)
}

// Claim binds exactly one Product Ops case. Replaying the same account/case
// tuple is stable; another account or case cannot transfer the intake.
func (intake AccountAppealIntake) Claim(
	accountID string,
	caseID string,
	claimedAt time.Time,
) (next AccountAppealIntake, replayed bool, err error) {
	if err := intake.Validate(); err != nil {
		return AccountAppealIntake{}, false, err
	}
	accountID = strings.TrimSpace(accountID)
	caseID = strings.TrimSpace(caseID)
	if !CanonicalOwnerAccountID(accountID) ||
		!CanonicalAppealCaseID(caseID) || claimedAt.IsZero() {
		return AccountAppealIntake{}, false, ErrInvalidIntake
	}
	if accountID != intake.state.AccountID {
		return AccountAppealIntake{}, false, ErrAccountMismatch
	}
	if intake.state.Status == StatusClaimed {
		if intake.state.ClaimedCaseID == caseID {
			return intake, true, nil
		}
		return AccountAppealIntake{}, false, ErrAlreadyClaimed
	}
	claimedAt = claimedAt.UTC()
	if claimedAt.Before(intake.state.SubmittedAt) || !claimedAt.Before(intake.state.DeleteAfter) {
		return AccountAppealIntake{}, false, ErrInvalidIntake
	}
	state := intake.State()
	state.Status = StatusClaimed
	state.ClaimedCaseID = caseID
	state.ClaimedAt = &claimedAt
	state.Version++
	next, err = Restore(state)
	return next, false, err
}

func validateState(state State) error {
	if !CanonicalIntakeRef(state.IntakeRef) ||
		!CanonicalOwnerAccountID(state.AccountID) ||
		state.SuspensionAuthEpoch <= 0 || !state.Status.Valid() ||
		state.SubmittedAt.IsZero() || state.DeleteAfter.IsZero() ||
		!state.DeleteAfter.After(state.SubmittedAt) || state.Version <= 0 {
		return fmt.Errorf("%w: identity, lifecycle or retention fields are invalid", ErrInvalidIntake)
	}
	switch state.Status {
	case StatusSubmitted:
		if state.ClaimedCaseID != "" || state.ClaimedAt != nil {
			return fmt.Errorf("%w: submitted intake contains claim facts", ErrInvalidIntake)
		}
	case StatusClaimed:
		if !CanonicalAppealCaseID(state.ClaimedCaseID) || state.ClaimedAt == nil ||
			state.ClaimedAt.Before(state.SubmittedAt) ||
			!state.ClaimedAt.Before(state.DeleteAfter) {
			return fmt.Errorf("%w: claimed intake receipt is invalid", ErrInvalidIntake)
		}
	}
	return nil
}

// CanonicalIntakeRef accepts only references produced by randomOpaque with the
// AccountAppealIntake prefix and 24 bytes of base64url entropy.
func CanonicalIntakeRef(value string) bool {
	const prefix = "appeal_intake_"
	return strings.HasPrefix(value, prefix) && len(value) == len(prefix)+32 &&
		asciiToken(value[len(prefix):], true)
}

// CanonicalAppealCredential accepts only credentials produced by randomOpaque
// with 32 bytes of base64url entropy. Raw credentials are never persisted.
func CanonicalAppealCredential(value string) bool {
	const prefix = "appeal_credential_"
	return strings.HasPrefix(value, prefix) && len(value) == len(prefix)+43 &&
		asciiToken(value[len(prefix):], true)
}

// CanonicalOwnerAccountID delegates to the UserAccount-owned identity value
// object so AccountAppealIntake cannot create a second account ID grammar.
func CanonicalOwnerAccountID(value string) bool {
	return useridentity.IsCanonicalOwnerID(value)
}

func CanonicalAppealCaseID(value string) bool {
	const prefix = "appeal-"
	return strings.HasPrefix(value, prefix) && len(value) > len(prefix) &&
		len(value) <= 128 && asciiToken(value[len(prefix):], false)
}

func asciiToken(value string, allowUpper bool) bool {
	for _, current := range value {
		if current >= '0' && current <= '9' || current >= 'a' && current <= 'z' ||
			allowUpper && current >= 'A' && current <= 'Z' || current == '-' || current == '_' {
			continue
		}
		return false
	}
	return value != ""
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
