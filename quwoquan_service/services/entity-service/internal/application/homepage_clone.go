package application

import "strings"

func cloneStrings(values []string) []string {
	return append([]string(nil), values...)
}

func cloneIntroductionAssets(
	values []HomepageIntroductionAsset,
) []HomepageIntroductionAsset {
	return append([]HomepageIntroductionAsset(nil), values...)
}

func coverURLFromIntroductionAssets(values []HomepageIntroductionAsset) string {
	for _, value := range values {
		if value.Role == introductionAssetRoleCover && strings.TrimSpace(value.URL) != "" {
			return strings.TrimSpace(value.URL)
		}
	}
	return ""
}
