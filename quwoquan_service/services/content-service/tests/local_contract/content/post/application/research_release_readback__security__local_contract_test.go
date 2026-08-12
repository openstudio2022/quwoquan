// readiness_case: get-research-release-readback-local
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package post_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/auth/researchidentity"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
)

type researchReleaseProbe struct {
	binding postapp.ResearchReleaseBinding
	err     error
}

func (probe researchReleaseProbe) ReadActiveResearchRelease(
	context.Context,
) (postapp.ResearchReleaseBinding, error) {
	return probe.binding, probe.err
}

func TestResearchReleaseReadbackBindsVerifiedAccountAndResearchRelease(
	t *testing.T,
) {
	key := []byte("research-attestation-key-32-bytes-long")
	authority, err := researchidentity.NewAuthority(key)
	if err != nil {
		t.Fatal(err)
	}
	issuedAt := time.Now().UTC().Add(-time.Minute)
	verified, token, err := authority.Issue(
		"account-1",
		issuedAt,
		issuedAt.Add(5*time.Minute),
		[]byte(strings.Repeat("n", 32)),
	)
	if err != nil {
		t.Fatal(err)
	}
	facet, err := postapp.NewResearchReleaseReadbackQueryFacet(
		authority,
		researchReleaseProbe{binding: postapp.ResearchReleaseBinding{
			ReleaseID:      "release-research-1",
			ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		}},
	)
	if err != nil {
		t.Fatal(err)
	}
	view, err := facet.GetResearchReleaseReadback(
		context.Background(),
		"account-1",
		token,
	)
	if err != nil {
		t.Fatal(err)
	}
	if view.ReleaseID != "release-research-1" ||
		view.ManifestDigest != "sha256:"+strings.Repeat("a", 64) ||
		view.SubjectHash != verified.SubjectHash ||
		view.AttestationIDHash != verified.AttestationIDHash ||
		!view.SignatureVerified || !view.ResearchBadgeVisible {
		t.Fatalf("readback not bound to verified identity/release: %+v", view)
	}
}

func TestResearchReleaseReadbackRejectsTamperExpiryAndAccountDrift(t *testing.T) {
	key := []byte("research-attestation-key-32-bytes-long")
	authority, _ := researchidentity.NewAuthority(key)
	issuedAt := time.Now().UTC().Add(-30 * time.Second)
	_, token, _ := authority.Issue(
		"account-1",
		issuedAt,
		issuedAt.Add(time.Minute),
		[]byte(strings.Repeat("n", 32)),
	)
	binding := researchReleaseProbe{binding: postapp.ResearchReleaseBinding{
		ReleaseID:      "release-research-1",
		ManifestDigest: "sha256:" + strings.Repeat("a", 64),
	}}
	for _, test := range []struct {
		name      string
		accountID string
		token     string
		now       time.Time
	}{
		{name: "tampered", accountID: "account-1", token: token + "x"},
		{name: "expired", accountID: "account-1", token: expiredToken(t, authority)},
		{name: "account drift", accountID: "account-2", token: token},
	} {
		t.Run(test.name, func(t *testing.T) {
			facet, _ := postapp.NewResearchReleaseReadbackQueryFacet(authority, binding)
			view, err := facet.GetResearchReleaseReadback(
				context.Background(), test.accountID, test.token,
			)
			if !errors.Is(err, postapp.ErrResearchIdentityInvalid) ||
				view != (postapp.ResearchReleaseReadbackView{}) {
				t.Fatalf("view=%+v err=%v", view, err)
			}
		})
	}
}

func TestResearchReleaseReadbackRejectsNonResearchRelease(t *testing.T) {
	authority, _ := researchidentity.NewAuthority(
		[]byte("research-attestation-key-32-bytes-long"),
	)
	issuedAt := time.Now().UTC().Add(-time.Minute)
	_, token, _ := authority.Issue(
		"account-1", issuedAt, issuedAt.Add(5*time.Minute), []byte(strings.Repeat("n", 32)),
	)
	facet, _ := postapp.NewResearchReleaseReadbackQueryFacet(
		authority,
		researchReleaseProbe{err: postapp.ErrResearchReleaseNotResearch},
	)
	view, err := facet.GetResearchReleaseReadback(context.Background(), "account-1", token)
	if !errors.Is(err, postapp.ErrResearchReleaseNotResearch) ||
		view != (postapp.ResearchReleaseReadbackView{}) {
		t.Fatalf("view=%+v err=%v", view, err)
	}
}

func expiredToken(
	t *testing.T,
	authority *researchidentity.Authority,
) string {
	t.Helper()
	issuedAt := time.Now().UTC().Add(-2 * time.Minute)
	_, token, err := authority.Issue(
		"account-1",
		issuedAt,
		issuedAt.Add(time.Minute),
		[]byte(strings.Repeat("e", 32)),
	)
	if err != nil {
		t.Fatal(err)
	}
	return token
}
