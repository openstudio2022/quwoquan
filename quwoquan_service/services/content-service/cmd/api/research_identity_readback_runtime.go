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

// researchReadbackEnvironments 与 services/content-service/environments/<env>/
// 中声明 CONTENT_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64 的环境一一对应：
// 声明该 key 的环境必须成功装配 readback（key 缺失即启动失败），
// 未声明的环境不装配，handler 对 readback 请求 fail-closed。
//
//nolint:gochecknoglobals
var researchReadbackEnvironments = map[string]bool{
	"alpha": true,
	"gamma": true,
}

func buildResearchReleaseReadback(
	appEnv string,
	releases postapp.ResearchReleaseBindingReader,
) (*postapp.ResearchReleaseReadbackQueryFacet, error) {
	if !researchReadbackEnvironments[strings.TrimSpace(appEnv)] {
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
