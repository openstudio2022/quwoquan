package account_session

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/auth/researchidentity"
)

// ErrResearchIdentityInvalid marks a fail-closed attestation readback: the
// attestation is missing, tampered, expired, or bound to another account.
var ErrResearchIdentityInvalid = errors.New("research identity attestation is invalid")

// ResearchSessionAttestationView is the read model of
// GetResearchSessionAttestation. It only echoes the already-presented signed
// proof; it never widens the identity beyond what the Authority verified.
type ResearchSessionAttestationView struct {
	SubjectHash   string    `json:"subjectHash"`
	AttestationID string    `json:"attestationId"`
	ExpiresAt     time.Time `json:"expiresAt"`
}

func NewUnavailableResearchSessionQueryFacade() *ResearchSessionQueryFacade {
	return &ResearchSessionQueryFacade{}
}

// ResearchSessionQueryFacade verifies a short-lived research attestation for
// the authenticated account that presents it. Verification reuses the same
// runtime Authority as issuance, so signature, TTL and subject binding cannot
// drift between the two operations.
type ResearchSessionQueryFacade struct {
	authority *researchidentity.Authority
	now       func() time.Time
}

func NewResearchSessionQueryFacade(
	attestationKey []byte,
) (*ResearchSessionQueryFacade, error) {
	authority, err := researchidentity.NewAuthority(attestationKey)
	if err != nil {
		return nil, err
	}
	return &ResearchSessionQueryFacade{
		authority: authority,
		now:       time.Now,
	}, nil
}

func (facade *ResearchSessionQueryFacade) GetResearchSessionAttestation(
	_ context.Context,
	accountID string,
	attestation string,
) (ResearchSessionAttestationView, error) {
	if facade == nil || facade.authority == nil {
		return ResearchSessionAttestationView{}, ErrResearchIdentityUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	attestation = strings.TrimSpace(attestation)
	if accountID == "" || attestation == "" {
		return ResearchSessionAttestationView{}, ErrResearchIdentityInvalid
	}
	verified, err := facade.authority.Verify(accountID, attestation, facade.now().UTC())
	if err != nil {
		return ResearchSessionAttestationView{}, fmt.Errorf(
			"%w: %v", ErrResearchIdentityInvalid, err,
		)
	}
	return ResearchSessionAttestationView{
		SubjectHash:   verified.SubjectHash,
		AttestationID: attestation,
		ExpiresAt:     verified.ExpiresAt,
	}, nil
}
