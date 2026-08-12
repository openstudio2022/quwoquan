package post

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/auth/researchidentity"
)

var (
	ErrResearchIdentityInvalid    = errors.New("research identity attestation is invalid")
	ErrResearchReleaseUnavailable = errors.New("research release binding is unavailable")
	ErrResearchReleaseNotResearch = errors.New("active release is not research-only")
)

type ResearchReleaseBinding struct {
	ReleaseID      string
	ManifestDigest string
}

type ResearchReleaseBindingReader interface {
	ReadActiveResearchRelease(context.Context) (ResearchReleaseBinding, error)
}

type ResearchIdentityAttestationVerifier interface {
	Verify(
		accountID string,
		attestation string,
		now time.Time,
	) (researchidentity.VerifiedAttestation, error)
}

type ResearchReleaseReadbackView struct {
	ReleaseID            string `json:"releaseId"`
	ManifestDigest       string `json:"manifestDigest"`
	SubjectHash          string `json:"subjectHash"`
	AttestationIDHash    string `json:"attestationIdHash"`
	SignatureVerified    bool   `json:"signatureVerified"`
	ResearchBadgeVisible bool   `json:"researchBadgeVisible"`
}

type ResearchReleaseReadbackQueryFacet struct {
	verifier ResearchIdentityAttestationVerifier
	releases ResearchReleaseBindingReader
	now      func() time.Time
}

func NewResearchReleaseReadbackQueryFacet(
	verifier ResearchIdentityAttestationVerifier,
	releases ResearchReleaseBindingReader,
) (*ResearchReleaseReadbackQueryFacet, error) {
	if verifier == nil || releases == nil {
		return nil, ErrResearchReleaseUnavailable
	}
	return &ResearchReleaseReadbackQueryFacet{
		verifier: verifier,
		releases: releases,
		now:      time.Now,
	}, nil
}

func (facet *ResearchReleaseReadbackQueryFacet) GetResearchReleaseReadback(
	ctx context.Context,
	accountID string,
	attestation string,
) (ResearchReleaseReadbackView, error) {
	accountID = strings.TrimSpace(accountID)
	attestation = strings.TrimSpace(attestation)
	if facet == nil || facet.verifier == nil || facet.releases == nil {
		return ResearchReleaseReadbackView{}, ErrResearchReleaseUnavailable
	}
	if accountID == "" || attestation == "" {
		return ResearchReleaseReadbackView{}, ErrResearchIdentityInvalid
	}
	verified, err := facet.verifier.Verify(accountID, attestation, facet.now().UTC())
	if err != nil {
		return ResearchReleaseReadbackView{}, fmt.Errorf("%w: %v", ErrResearchIdentityInvalid, err)
	}
	binding, err := facet.releases.ReadActiveResearchRelease(ctx)
	if err != nil {
		return ResearchReleaseReadbackView{}, err
	}
	if strings.TrimSpace(binding.ReleaseID) == "" ||
		strings.TrimSpace(binding.ManifestDigest) == "" {
		return ResearchReleaseReadbackView{}, ErrResearchReleaseUnavailable
	}
	return ResearchReleaseReadbackView{
		ReleaseID:            strings.TrimSpace(binding.ReleaseID),
		ManifestDigest:       strings.TrimSpace(binding.ManifestDigest),
		SubjectHash:          verified.SubjectHash,
		AttestationIDHash:    verified.AttestationIDHash,
		SignatureVerified:    true,
		ResearchBadgeVisible: true,
	}, nil
}
