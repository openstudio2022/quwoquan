package main

import "path/filepath"

func runtimeNavigationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"runtime",
		"shell",
		"navigation",
		"generated",
		fileName,
	)
}

func runtimeErrorOutputPath(appDir, domain, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"runtime",
		"errors",
		"generated",
		domain,
		fileName,
	)
}

func runtimeTransportOutputPath(appDir, domain, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"runtime",
		"transport",
		"generated",
		domain,
		fileName,
	)
}

func runtimeTransportSharedOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"runtime",
		"transport",
		"generated",
		fileName,
	)
}

func runtimeObservabilityOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"runtime",
		"observability",
		"generated",
		fileName,
	)
}

func contentMediaAssetApplicationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"media",
		"media_asset",
		"application",
		"generated",
		fileName,
	)
}

func contentMediaUploadSessionApplicationOutputPath(
	appDir,
	fileName string,
) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"media",
		"media_upload_session",
		"application",
		"generated",
		fileName,
	)
}

func contentPostDomainOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"content",
		"post",
		"domain",
		"generated",
		fileName,
	)
}

func contentPostApplicationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"content",
		"post",
		"application",
		"generated",
		fileName,
	)
}

func contentPostPublicGeneratedOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"content",
		"post",
		"application",
		"public",
		"generated",
		fileName,
	)
}

func contentPostAdaptersOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"content",
		"post",
		"adapters",
		"generated",
		fileName,
	)
}

func contentPostPresentationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"content_service",
		"content",
		"post",
		"presentation",
		"generated",
		fileName,
	)
}

func searchIndexViewApplicationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"search_service",
		"search",
		"search_index_view",
		"application",
		"generated",
		fileName,
	)
}

func searchIndexViewPresentationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"search_service",
		"search",
		"search_index_view",
		"presentation",
		"generated",
		fileName,
	)
}

func circlePresentationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"circle_service",
		"circle_management",
		"circle",
		"presentation",
		"generated",
		fileName,
	)
}

func entityHomepagePresentationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"entity_service",
		"entity_homepage",
		"homepage",
		"application",
		"public",
		"generated",
		fileName,
	)
}

func userAccountPresentationOutputPath(appDir, fileName string) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"user_service",
		"account",
		"user_account",
		"application",
		"public",
		"generated",
		fileName,
	)
}

func recommendationFeatureProfilePresentationOutputPath(
	appDir,
	fileName string,
) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"recommendation_service",
		"recommendation",
		"recommendation_feature_profile_view",
		"presentation",
		"generated",
		fileName,
	)
}

func recommendationFeatureProfileApplicationOutputPath(
	appDir,
	fileName string,
) string {
	return filepath.Join(
		appDir,
		"lib",
		"service",
		"recommendation_service",
		"recommendation",
		"recommendation_feature_profile_view",
		"application",
		"generated",
		fileName,
	)
}
