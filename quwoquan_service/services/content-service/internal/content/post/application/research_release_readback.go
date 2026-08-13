package post

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/auth/researchidentity"
)

var (
	ErrResearchIdentityInvalid    = errors.New("research identity attestation is invalid")
	ErrResearchReleaseUnavailable = errors.New("research release binding is unavailable")
	ErrResearchReleaseNotResearch = errors.New("active release is not research-only")
)

// ResearchReleaseBinding is the exact object closure of the active research
// release plus every stored media URL form of those objects. The URL forms
// are evidence for the network exposure derivation; they never reach the
// readback view directly.
type ResearchReleaseBinding struct {
	ReleaseID      string
	ManifestDigest string
	PostIDs        []string
	EntityRefs     []string
	MediaAssetIDs  []string
	MediaURLForms  []string
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
	ReleaseID                 string   `json:"releaseId"`
	ManifestDigest            string   `json:"manifestDigest"`
	SubjectHash               string   `json:"subjectHash"`
	AttestationIDHash         string   `json:"attestationIdHash"`
	SignatureVerified         bool     `json:"signatureVerified"`
	ResearchBadgeVisible      bool     `json:"researchBadgeVisible"`
	PostIDs                   []string `json:"postIds"`
	EntityRefs                []string `json:"entityRefs"`
	MediaAssetIDs             []string `json:"mediaAssetIds"`
	PublicCdnDetected         bool     `json:"publicCdnDetected"`
	AnonymousMediaURLDetected bool     `json:"anonymousMediaUrlDetected"`
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
		ReleaseID:                 strings.TrimSpace(binding.ReleaseID),
		ManifestDigest:            strings.TrimSpace(binding.ManifestDigest),
		SubjectHash:               verified.SubjectHash,
		AttestationIDHash:         verified.AttestationIDHash,
		SignatureVerified:         true,
		ResearchBadgeVisible:      true,
		PostIDs:                   normalizeResearchBindingIDs(binding.PostIDs),
		EntityRefs:                normalizeResearchBindingIDs(binding.EntityRefs),
		MediaAssetIDs:             normalizeResearchBindingIDs(binding.MediaAssetIDs),
		PublicCdnDetected:         DetectPublicCDNMediaBinding(binding.MediaURLForms),
		AnonymousMediaURLDetected: DetectAnonymousMediaURL(binding.MediaURLForms),
	}, nil
}

func normalizeResearchBindingIDs(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

// publicMediaSliceMarkers are the immutable public delivery slice namespaces
// (runtime/media slice keys). A stored media URL form bound to one of them is
// served from the public CDN and is therefore anonymously reachable.
var publicMediaSliceMarkers = []string{
	"media/avatar/s/",
	"media/image/s/",
	"media/video/s/",
	"media/background/s/",
	"media/attachment/s/",
}

// DetectPublicCDNMediaBinding reports whether any stored media URL form of
// the research release is bound to a public CDN delivery slice. It inspects
// both absolute delivery URLs and relative public-slice object keys.
func DetectPublicCDNMediaBinding(urlForms []string) bool {
	for _, form := range urlForms {
		form = strings.TrimSpace(form)
		if form == "" {
			continue
		}
		path := form
		if parsed, ok := parseAbsoluteMediaURL(form); ok {
			path = parsed.EscapedPath()
		}
		normalized := strings.Trim(path, "/")
		for _, marker := range publicMediaSliceMarkers {
			if strings.HasPrefix(normalized, marker) ||
				strings.Contains(normalized, "/"+marker) {
				return true
			}
		}
	}
	return false
}

// DetectAnonymousMediaURL reports whether any stored media URL form is an
// absolute URL that can be fetched without the signed-delivery query
// parameters (sign + t) issued by runtime/media private delivery signing.
func DetectAnonymousMediaURL(urlForms []string) bool {
	for _, form := range urlForms {
		parsed, ok := parseAbsoluteMediaURL(strings.TrimSpace(form))
		if !ok {
			continue
		}
		query := parsed.Query()
		if query.Get("sign") == "" || query.Get("t") == "" {
			return true
		}
	}
	return false
}

func parseAbsoluteMediaURL(form string) (*url.URL, bool) {
	lower := strings.ToLower(form)
	if !strings.HasPrefix(lower, "http://") && !strings.HasPrefix(lower, "https://") {
		return nil, false
	}
	parsed, err := url.Parse(form)
	if err != nil || parsed.Host == "" {
		return nil, false
	}
	return parsed, true
}
