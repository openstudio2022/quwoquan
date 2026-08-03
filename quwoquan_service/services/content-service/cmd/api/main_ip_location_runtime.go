package main

import (
	"fmt"
	"strings"
	"time"

	iplocationapp "quwoquan_service/services/content-service/internal/content/comment/application/iplocation"
	iplocationinfra "quwoquan_service/services/content-service/internal/content/comment/infrastructure/iplocation"
)

type ipLocationResolverFactory func(
	ipv4DatabasePath string,
	ipv6DatabasePath string,
) (iplocationapp.Resolver, func(), error)

func newIP2RegionResolver(
	ipv4DatabasePath string,
	ipv6DatabasePath string,
) (iplocationapp.Resolver, func(), error) {
	resolver, err := iplocationinfra.NewIP2RegionResolver(
		ipv4DatabasePath,
		ipv6DatabasePath,
	)
	if err != nil {
		return nil, nil, err
	}
	return resolver, resolver.Close, nil
}

func buildCommentIPLocationResolver(
	cfg config,
	appEnv string,
	factory ipLocationResolverFactory,
) (iplocationapp.Resolver, func(), error) {
	provider := strings.ToLower(strings.TrimSpace(cfg.IPLocation.Provider))
	switch provider {
	case "deterministic":
		if appEnv != "alpha" {
			return nil, nil, fmt.Errorf(
				"ip_location.provider=deterministic is forbidden in APP_ENV=%s",
				appEnv,
			)
		}
		return iplocationapp.NewDeterministicProvinceResolver(), func() {}, nil
	case "ip2region":
		if appEnv == "alpha" {
			return nil, nil, fmt.Errorf(
				"ip_location.provider=ip2region is forbidden in APP_ENV=alpha",
			)
		}
		if factory == nil {
			return nil, nil, fmt.Errorf("ip2region resolver factory is required")
		}
		resolver, closeResolver, err := factory(
			cfg.IPLocation.IPv4DatabasePath,
			cfg.IPLocation.IPv6DatabasePath,
		)
		if err != nil {
			return nil, nil, fmt.Errorf("load ip2region databases: %w", err)
		}
		if resolver == nil || closeResolver == nil {
			return nil, nil, fmt.Errorf("ip2region resolver factory returned nil")
		}
		if versionDate, parseErr := time.Parse(
			"2006-01-02",
			strings.TrimSpace(cfg.IPLocation.DataVersion),
		); parseErr == nil {
			iplocationinfra.ObserveDataVersion(versionDate, time.Now().UTC())
		}
		return resolver, closeResolver, nil
	default:
		return nil, nil, fmt.Errorf(
			"unsupported ip_location.provider %q",
			cfg.IPLocation.Provider,
		)
	}
}
