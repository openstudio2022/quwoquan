package bootstrap

import (
	"encoding/base64"
	"errors"
	"os"
	"strings"

	"quwoquan_service/runtime/auth/researchidentity"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
)

const contentResearchIdentityKeyEnv = "CONTENT_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64"

func buildResearchReleaseReadback(
	appEnv string,
	releases postapp.ResearchReleaseBindingReader,
) (*postapp.ResearchReleaseReadbackQueryFacet, error) {
	if strings.TrimSpace(appEnv) != "alpha" {
		return nil, nil
	}
	key, err := base64.StdEncoding.DecodeString(
		strings.TrimSpace(os.Getenv(contentResearchIdentityKeyEnv)),
	)
	if err != nil || len(key) < 32 {
		return nil, errors.New("content research identity attestation key is missing or invalid")
	}
	authority, err := researchidentity.NewAuthority(key)
	if err != nil {
		return nil, err
	}
	return postapp.NewResearchReleaseReadbackQueryFacet(authority, releases)
}
