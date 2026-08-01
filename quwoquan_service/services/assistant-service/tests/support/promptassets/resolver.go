// Package promptassets 让测试用与生产同一份提示词资产加载器，避免测试里出现第二套话术。
package promptassets

import (
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/assets"
)

func MustResolver(t *testing.T) ports.PromptAssetResolver {
	t.Helper()
	loader, err := assets.NewDefaultPromptAssetLoader()
	if err != nil {
		t.Fatalf("build prompt asset loader: %v", err)
	}
	return loader
}
