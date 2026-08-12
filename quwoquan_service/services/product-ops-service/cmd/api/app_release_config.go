package main

import (
	"strings"

	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
)

func buildAppReleaseService(cfg config) (*apprelease.Service, error) {
	publicOrigin := strings.TrimRight(strings.TrimSpace(cfg.AppRelease.PublicOrigin), "/")
	return apprelease.NewService(apprelease.Catalog{
		PublicOrigin: publicOrigin,
		IOS: apprelease.Release{
			LatestVersion:           cfg.AppRelease.IOS.LatestVersion,
			LatestBuild:             cfg.AppRelease.IOS.LatestBuild,
			MinimumSupportedVersion: cfg.AppRelease.IOS.MinimumSupportedVersion,
			MinimumSupportedBuild:   cfg.AppRelease.IOS.MinimumSupportedBuild,
			UpdateURL:               cfg.AppRelease.IOS.UpdateURL,
			RecoveryURL:             cfg.AppRelease.IOS.RecoveryURL,
		},
		Android: apprelease.Release{
			LatestVersion:               cfg.AppRelease.Android.LatestVersion,
			LatestBuild:                 cfg.AppRelease.Android.LatestBuild,
			MinimumSupportedVersion:     cfg.AppRelease.Android.MinimumSupportedVersion,
			MinimumSupportedBuild:       cfg.AppRelease.Android.MinimumSupportedBuild,
			UpdateURL:                   cfg.AppRelease.Android.UpdateURL,
			RecoveryURL:                 cfg.AppRelease.Android.RecoveryURL,
			APKURL:                      cfg.AppRelease.Android.APKURL,
			APKHostAllowlist:            cfg.AppRelease.Android.APKHostAllowlist,
			APKPackageName:              cfg.AppRelease.Android.APKPackageName,
			APKSHA256:                   cfg.AppRelease.Android.APKSHA256,
			APKSizeBytes:                cfg.AppRelease.Android.APKSizeBytes,
			APKSigningCertificateSHA256: cfg.AppRelease.Android.APKSigningCertificateSHA256,
			MinAndroidVersion:           cfg.AppRelease.Android.MinAndroidVersion,
		},
		Web: apprelease.Release{
			LatestVersion:           cfg.AppRelease.Web.LatestVersion,
			LatestBuild:             cfg.AppRelease.Web.LatestBuild,
			MinimumSupportedVersion: cfg.AppRelease.Web.MinimumSupportedVersion,
			MinimumSupportedBuild:   cfg.AppRelease.Web.MinimumSupportedBuild,
			UpdateURL:               cfg.AppRelease.Web.UpdateURL,
			RecoveryURL:             cfg.AppRelease.Web.RecoveryURL,
		},
	})
}
