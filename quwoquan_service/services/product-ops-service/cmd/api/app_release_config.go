package main

import (
	"strings"

	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
)

func buildAppReleaseService(cfg config) (*apprelease.Service, error) {
	publicOrigin := strings.TrimRight(strings.TrimSpace(cfg.AppRelease.PublicOrigin), "/")
	recoveryURL := strings.TrimSpace(cfg.AppRelease.RecoveryURL)
	if recoveryURL == "" && publicOrigin != "" {
		recoveryURL = publicOrigin + "/download"
	}
	androidUpdateURL := ""
	if strings.TrimSpace(cfg.AppRelease.Android.LatestVersion) != "" ||
		strings.TrimSpace(cfg.AppRelease.Android.LatestBuild) != "" ||
		strings.TrimSpace(cfg.AppRelease.Android.APKURL) != "" {
		androidUpdateURL = publicOrigin + "/download/android"
	}
	return apprelease.NewService(apprelease.Catalog{
		PublicOrigin: publicOrigin,
		IOS: apprelease.Release{
			LatestVersion: cfg.AppRelease.IOS.LatestVersion,
			LatestBuild:   cfg.AppRelease.IOS.LatestBuild,
			UpdateURL:     cfg.AppRelease.IOS.AppStoreURL,
			RecoveryURL:   recoveryURL,
		},
		Android: apprelease.Release{
			LatestVersion:               cfg.AppRelease.Android.LatestVersion,
			LatestBuild:                 cfg.AppRelease.Android.LatestBuild,
			UpdateURL:                   androidUpdateURL,
			RecoveryURL:                 recoveryURL,
			APKURL:                      cfg.AppRelease.Android.APKURL,
			APKHostAllowlist:            cfg.AppRelease.Android.APKHostAllowlist,
			APKPackageName:              cfg.AppRelease.Android.APKPackageName,
			APKSHA256:                   cfg.AppRelease.Android.APKSHA256,
			APKSizeBytes:                cfg.AppRelease.Android.APKSizeBytes,
			APKSigningCertificateSHA256: cfg.AppRelease.Android.APKSigningCertificateSHA256,
		},
	})
}
