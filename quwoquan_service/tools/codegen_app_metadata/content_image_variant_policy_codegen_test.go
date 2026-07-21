package main

import (
	"strings"
	"testing"
)

func TestRenderContentImageVariantPolicyDartPreservesCanonicalProfiles(t *testing.T) {
	t.Parallel()

	rendered := renderContentImageVariantPolicyDart(&contentImageVariantPolicyFile{
		DerivativePolicyVersion: 1,
		Profiles: map[string]contentImageVariantProfileDef{
			"thumbnail": {
				Width: 320, Format: "webp", Quality: 80, Scene: "feed_grid",
				Processing: "image/resize,w_320/format,webp/quality,q_80",
			},
			"display": {
				Width: 960, Format: "webp", Quality: 82, Scene: "article_body",
				Processing: "image/resize,w_960/format,webp/quality,q_82",
			},
		},
	})

	for _, expected := range []string{
		"final class ContentImageVariantProfile",
		"static const int derivativePolicyVersion = 1",
		`"thumbnail": ContentImageVariantProfile(`,
		"width: 320",
		`"display": ContentImageVariantProfile(`,
		"width: 960",
		"unknown image variant profile",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated Dart missing %q:\n%s", expected, rendered)
		}
	}
}
