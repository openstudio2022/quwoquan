// readiness_case: get-research-release-readback-local
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package post_test

import (
	"context"
	"errors"
	"reflect"
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

func isolatedResearchBinding() postapp.ResearchReleaseBinding {
	return postapp.ResearchReleaseBinding{
		ReleaseID:      "release-research-1",
		ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		PostIDs:        []string{"post-2", "post-1", "post-1"},
		EntityRefs:     []string{"entity:scene/one", "entity:scene/two"},
		MediaAssetIDs:  []string{"asset-9", "asset-3"},
		MediaURLForms: []string{
			"https://media.internal.example/media/objects/sha256/aa/bb?sign=" +
				strings.Repeat("f", 64) + "&t=4102444800",
			"https://media.internal.example/media/processed/image/v1/one.jpg?sign=" +
				strings.Repeat("e", 64) + "&t=4102444800",
			"", " ",
		},
	}
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
		researchReleaseProbe{binding: isolatedResearchBinding()},
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
	if !reflect.DeepEqual(view.PostIDs, []string{"post-1", "post-2"}) ||
		!reflect.DeepEqual(view.EntityRefs, []string{"entity:scene/one", "entity:scene/two"}) ||
		!reflect.DeepEqual(view.MediaAssetIDs, []string{"asset-3", "asset-9"}) {
		t.Fatalf("readback did not expose the exact release binding lists: %+v", view)
	}
	if view.PublicCdnDetected || view.AnonymousMediaURLDetected {
		t.Fatalf(
			"signed-only research media must derive no public CDN and no anonymous URL: %+v",
			view,
		)
	}
}

func TestResearchReleaseReadbackDerivesNetworkExposureFromMediaURLForms(
	t *testing.T,
) {
	authority, err := researchidentity.NewAuthority(
		[]byte("research-attestation-key-32-bytes-long"),
	)
	if err != nil {
		t.Fatal(err)
	}
	issuedAt := time.Now().UTC().Add(-time.Minute)
	_, token, err := authority.Issue(
		"account-1", issuedAt, issuedAt.Add(5*time.Minute), []byte(strings.Repeat("n", 32)),
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name          string
		mediaURLForms []string
		wantPublicCDN bool
		wantAnonymous bool
	}{
		{
			name: "signed private delivery only",
			mediaURLForms: []string{
				"https://media.internal.example/media/objects/sha256/aa/bb?sign=" +
					strings.Repeat("f", 64) + "&t=4102444800",
			},
			wantPublicCDN: false,
			wantAnonymous: false,
		},
		{
			name: "public CDN slice URL is detected and is anonymous",
			mediaURLForms: []string{
				"https://cdn.example.com/media/image/s/asset/asset_001/v3/source.png",
			},
			wantPublicCDN: true,
			wantAnonymous: true,
		},
		{
			name:          "relative public slice key still binds public CDN",
			mediaURLForms: []string{"media/video/s/asset/asset_002/v1/play.mp4"},
			wantPublicCDN: true,
			wantAnonymous: false,
		},
		{
			name: "unsigned absolute URL is anonymous even off the CDN slices",
			mediaURLForms: []string{
				"https://media.internal.example/media/objects/sha256/aa/bb",
			},
			wantPublicCDN: false,
			wantAnonymous: true,
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			binding := isolatedResearchBinding()
			binding.MediaURLForms = test.mediaURLForms
			facet, err := postapp.NewResearchReleaseReadbackQueryFacet(
				authority,
				researchReleaseProbe{binding: binding},
			)
			if err != nil {
				t.Fatal(err)
			}
			view, err := facet.GetResearchReleaseReadback(
				context.Background(), "account-1", token,
			)
			if err != nil {
				t.Fatal(err)
			}
			if view.PublicCdnDetected != test.wantPublicCDN ||
				view.AnonymousMediaURLDetected != test.wantAnonymous {
				t.Fatalf(
					"exposure derivation drifted: publicCdn=%t anonymous=%t view=%+v",
					test.wantPublicCDN, test.wantAnonymous, view,
				)
			}
		})
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
	binding := researchReleaseProbe{binding: isolatedResearchBinding()}
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
				!reflect.DeepEqual(view, postapp.ResearchReleaseReadbackView{}) {
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
		!reflect.DeepEqual(view, postapp.ResearchReleaseReadbackView{}) {
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
