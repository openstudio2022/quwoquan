// Package identity adapts canonical AuthenticationChallenge and
// CredentialBinding objects into AccountAppealIntake identity evidence.
package identity

import (
	"context"
	"strings"
	"time"

	challengegenerated "quwoquan_service/services/user-service/generated/account/authentication_challenge"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	credentialports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

type ChallengeVerifier struct {
	challenges  challengeapp.CommandFacet
	credentials credentialports.AggregateStore
	now         func() time.Time
}

func NewChallengeVerifier(
	challenges challengeapp.CommandFacet,
	credentials credentialports.AggregateStore,
) *ChallengeVerifier {
	if challenges == nil || credentials == nil {
		panic("AccountAppealIntake identity verifier requires challenge and credential owners")
	}
	return &ChallengeVerifier{
		challenges: challenges, credentials: credentials, now: time.Now,
	}
}

func (verifier *ChallengeVerifier) VerifyAccountAppealChallenge(
	ctx context.Context,
	phone string,
	otpCode []byte,
	challengeID string,
) (ports.IdentityChallengeEvidence, error) {
	phoneKey := credentialmodel.NormalizePhoneCredentialKey(phone)
	challengeID = strings.TrimSpace(challengeID)
	if len(phoneKey) < 5 || len(phoneKey) > 64 || challengeID == "" || len(otpCode) == 0 {
		return ports.IdentityChallengeEvidence{}, ports.ErrIdentityNotFound
	}
	result, err := verifier.challenges.VerifyChallenge(
		ctx,
		challengeapp.VerifyChallengeCommand{
			ChallengeID:     challengeID,
			Purpose:         "account_appeal",
			Channel:         "sms",
			DestinationHash: challengeapp.SMSDestinationHash(phoneKey),
			Credential:      otpCode,
		},
	)
	if err != nil {
		return ports.IdentityChallengeEvidence{}, err
	}
	snapshot := result.Challenge
	if snapshot.ID != challengeID || snapshot.Status != challengemodel.StatusCompleted ||
		snapshot.Purpose != "account_appeal" || snapshot.Channel != "sms" ||
		!verifier.now().UTC().Before(snapshot.ExpiresAt.UTC()) {
		return ports.IdentityChallengeEvidence{}, challengegenerated.AppErrorFromOtpExpired(
			"account appeal identity challenge is no longer eligible",
		)
	}
	binding, found, err := verifier.credentials.FindByTypeAndKey(
		ctx,
		credentialmodel.CredentialTypePhone,
		phoneKey,
	)
	if err != nil {
		return ports.IdentityChallengeEvidence{}, err
	}
	if !found {
		return ports.IdentityChallengeEvidence{}, ports.ErrIdentityNotFound
	}
	state := binding.State()
	if state.Status != credentialmodel.StatusActive || strings.TrimSpace(state.OwnerID) == "" {
		return ports.IdentityChallengeEvidence{}, ports.ErrIdentityNotFound
	}
	return ports.IdentityChallengeEvidence{
		ChallengeID: snapshot.ID,
		AccountID:   state.OwnerID,
		ExpiresAt:   snapshot.ExpiresAt.UTC(),
	}, nil
}

var _ ports.IdentityChallengeVerifier = (*ChallengeVerifier)(nil)
