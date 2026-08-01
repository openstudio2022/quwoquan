package orchestration

import (
	"context"
	"fmt"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

// resolveSkillPromptGuidance 返回选中技能的领域话术。资产 ID 无法解析时返回错误，绝不允许
// 把 ID 本身当作提示词正文送进模型。
func resolveSkillPromptGuidance(
	ctx context.Context,
	resolver ports.PromptAssetResolver,
	manifest skillpkg.Manifest,
) (string, error) {
	assetIDs := trimmedAssetIDs(manifest.PromptAssets)
	if len(assetIDs) == 0 {
		return "", nil
	}
	if resolver == nil {
		return "", fmt.Errorf(
			"skill %q declares prompt assets %v but no resolver is configured",
			manifest.SkillID,
			assetIDs,
		)
	}
	guidance, err := resolver.ResolvePromptAssets(ctx, assetIDs)
	if err != nil {
		return "", fmt.Errorf("resolve prompt assets for skill %q: %w", manifest.SkillID, err)
	}
	guidance = strings.TrimSpace(guidance)
	if guidance == "" {
		return "", fmt.Errorf(
			"skill %q prompt assets %v resolved to empty guidance",
			manifest.SkillID,
			assetIDs,
		)
	}
	return guidance, nil
}

func trimmedAssetIDs(assetIDs []string) []string {
	out := make([]string, 0, len(assetIDs))
	for _, assetID := range assetIDs {
		trimmed := strings.TrimSpace(assetID)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

// composePromptPolicy 把策略模板的提示词与技能领域话术拼成一份提示词，顺序固定为
// 策略在前、技能话术在后，保证同一输入得到同一提示词。
func composePromptPolicy(policyPrompt string, skillGuidance string) string {
	policyPrompt = strings.TrimSpace(policyPrompt)
	skillGuidance = strings.TrimSpace(skillGuidance)
	switch {
	case skillGuidance == "":
		return policyPrompt
	case policyPrompt == "":
		return skillGuidance
	default:
		return policyPrompt + "\n\n技能领域要求：\n" + skillGuidance
	}
}
