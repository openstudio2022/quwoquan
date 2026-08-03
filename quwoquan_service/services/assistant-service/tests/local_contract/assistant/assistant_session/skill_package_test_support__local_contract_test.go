package local_contract

import "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"

func testSkillPackageIdentityResolver() runruntime.SkillPackageIdentityResolver {
	return runruntime.StaticSkillPackageIdentityResolver{
		PackageID:     "assistant.session.skills",
		ReleaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
}
