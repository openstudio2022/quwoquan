package authentication_challenge

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"

	challengeports "quwoquan_service/services/user-service/internal/domain/account/authentication_challenge/ports"
)

// OTPCredentialVerifier 以不可逆 secretRef 验证 OTP 瞬时凭据。
type OTPCredentialVerifier struct{}

func (OTPCredentialVerifier) VerifyCredential(
	_ context.Context,
	input challengeports.CredentialVerificationInput,
) (challengeports.CredentialVerificationEvidence, error) {
	secretRef := OTPSecretReference(
		input.ChallengeID,
		input.DestinationHash,
		input.Credential,
	)
	left := []byte(secretRef)
	right := []byte(input.SecretRef)
	matched := len(left) == len(right) &&
		subtle.ConstantTimeCompare(left, right) == 1
	return challengeports.CredentialVerificationEvidence{
		CompletionFingerprint: OTPCompletionFingerprint(
			input.ChallengeID,
			input.Credential,
		),
		Matched: matched,
	}, nil
}

func OTPSecretReference(
	challengeID string,
	destinationHash string,
	credential []byte,
) string {
	sum := sha256.New()
	_, _ = sum.Write([]byte(challengeID))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write([]byte(destinationHash))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write(credential)
	return hex.EncodeToString(sum.Sum(nil))
}

func OTPCompletionFingerprint(
	challengeID string,
	credential []byte,
) string {
	sum := sha256.New()
	_, _ = sum.Write([]byte(challengeID))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write(credential)
	return hex.EncodeToString(sum.Sum(nil))
}

var _ challengeports.CredentialVerifier = OTPCredentialVerifier{}
