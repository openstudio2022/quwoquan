package application

import (
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

const (
	PlatformIOS     = "ios"
	PlatformAndroid = "android"
)

var (
	ErrInvalidVersionQuery = errors.New("app release version query is invalid")
	ErrReleaseUnavailable  = errors.New("app release is unavailable")
)

type Release struct {
	LatestVersion               string
	LatestBuild                 string
	UpdateURL                   string
	RecoveryURL                 string
	APKURL                      string
	APKHostAllowlist            []string
	APKPackageName              string
	APKSHA256                   string
	APKSizeBytes                int64
	APKSigningCertificateSHA256 string
}

type Catalog struct {
	PublicOrigin string
	IOS          Release
	Android      Release
}

type VersionQuery struct {
	Platform    string
	AppVersion  string
	BuildNumber string
}

type VersionResult struct {
	LatestVersion string `json:"latestVersion"`
	LatestBuild   string `json:"latestBuild"`
	UpdateURL     string `json:"updateUrl"`
	RecoveryURL   string `json:"recoveryUrl"`
}

type Service struct {
	catalog Catalog
}

func NewService(catalog Catalog) (*Service, error) {
	catalog.PublicOrigin = strings.TrimRight(strings.TrimSpace(catalog.PublicOrigin), "/")
	if err := validateHTTPSURL(catalog.PublicOrigin, nil); err != nil {
		return nil, fmt.Errorf("public origin: %w", err)
	}
	if err := validateRelease(PlatformIOS, catalog.IOS); err != nil {
		return nil, err
	}
	if err := validateRelease(PlatformAndroid, catalog.Android); err != nil {
		return nil, err
	}
	return &Service{catalog: catalog}, nil
}

func (s *Service) Version(query VersionQuery) (VersionResult, error) {
	query.Platform = NormalizePlatform(query.Platform)
	query.AppVersion = strings.TrimSpace(query.AppVersion)
	query.BuildNumber = strings.TrimSpace(query.BuildNumber)
	if query.Platform == "" || query.AppVersion == "" || len(query.AppVersion) > 32 {
		return VersionResult{}, ErrInvalidVersionQuery
	}
	if !isPositiveDecimal(query.BuildNumber) {
		return VersionResult{}, ErrInvalidVersionQuery
	}
	release, ok := s.Release(query.Platform)
	if !ok {
		return VersionResult{}, ErrReleaseUnavailable
	}
	return VersionResult{
		LatestVersion: release.LatestVersion,
		LatestBuild:   release.LatestBuild,
		UpdateURL:     release.UpdateURL,
		RecoveryURL:   release.RecoveryURL,
	}, nil
}

func (s *Service) Release(platform string) (Release, bool) {
	switch NormalizePlatform(platform) {
	case PlatformIOS:
		return s.catalog.IOS, true
	case PlatformAndroid:
		return s.catalog.Android, true
	default:
		return Release{}, false
	}
}

func (s *Service) PublicOrigin() string { return s.catalog.PublicOrigin }

func NormalizePlatform(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "ios", "iphone", "ipad":
		return PlatformIOS
	case "android", "harmony", "harmonyos", "openharmony":
		return PlatformAndroid
	default:
		return ""
	}
}

func DetectPlatform(userAgent string) string {
	ua := strings.ToLower(userAgent)
	switch {
	case strings.Contains(ua, "iphone"), strings.Contains(ua, "ipad"), strings.Contains(ua, "ipod"):
		return PlatformIOS
	case strings.Contains(ua, "android"), strings.Contains(ua, "harmony"), strings.Contains(ua, "openharmony"):
		return PlatformAndroid
	default:
		return ""
	}
}

func CompareBuild(left, right string) (int, error) {
	if !isPositiveDecimal(left) || !isPositiveDecimal(right) {
		return 0, ErrInvalidVersionQuery
	}
	l, _ := strconv.ParseUint(left, 10, 64)
	r, _ := strconv.ParseUint(right, 10, 64)
	switch {
	case l < r:
		return -1, nil
	case l > r:
		return 1, nil
	default:
		return 0, nil
	}
}

func validateRelease(platform string, release Release) error {
	release.LatestVersion = strings.TrimSpace(release.LatestVersion)
	release.LatestBuild = strings.TrimSpace(release.LatestBuild)
	if release.LatestVersion == "" || !isPositiveDecimal(release.LatestBuild) {
		return fmt.Errorf("%s release version/build is invalid", platform)
	}
	if err := validateHTTPSURL(release.RecoveryURL, nil); err != nil {
		return fmt.Errorf("%s recovery url: %w", platform, err)
	}
	if platform == PlatformIOS {
		if err := validateHTTPSURL(release.UpdateURL, []string{"apps.apple.com"}); err != nil {
			return fmt.Errorf("ios app store url: %w", err)
		}
		return nil
	}
	if err := validateHTTPSURL(release.UpdateURL, nil); err != nil {
		return fmt.Errorf("android update url: %w", err)
	}
	if err := validateHTTPSURL(release.APKURL, release.APKHostAllowlist); err != nil {
		return fmt.Errorf("android apk url: %w", err)
	}
	if strings.TrimSpace(release.APKPackageName) == "" ||
		!isSHA256(release.APKSHA256) ||
		!isSHA256(release.APKSigningCertificateSHA256) ||
		release.APKSizeBytes <= 0 {
		return errors.New("android apk release proof is incomplete")
	}
	return nil
}

func validateHTTPSURL(raw string, allowedHosts []string) error {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil {
		return errors.New("must be an absolute https url")
	}
	if len(allowedHosts) == 0 {
		return nil
	}
	host := strings.ToLower(parsed.Hostname())
	for _, candidate := range allowedHosts {
		candidate = strings.ToLower(strings.TrimSpace(candidate))
		if host == candidate {
			return nil
		}
	}
	return errors.New("host is not in the allowlist")
}

func isPositiveDecimal(raw string) bool {
	if raw == "" || len(raw) > 18 {
		return false
	}
	for _, char := range raw {
		if char < '0' || char > '9' {
			return false
		}
	}
	value, err := strconv.ParseUint(raw, 10, 64)
	return err == nil && value > 0
}

func isSHA256(raw string) bool {
	raw = strings.TrimSpace(raw)
	if len(raw) != 64 {
		return false
	}
	for _, char := range raw {
		if !((char >= '0' && char <= '9') || (char >= 'a' && char <= 'f') || (char >= 'A' && char <= 'F')) {
			return false
		}
	}
	return true
}
