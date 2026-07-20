package main

import (
	"errors"
	"testing"
	"time"

	iplocationapp "quwoquan_service/services/content-service/internal/application/iplocation"
)

type staticIPLocationResolver struct {
	location string
}

func (r staticIPLocationResolver) Resolve(string) string {
	return r.location
}

func TestBuildCommentIPLocationResolverUsesDeterministicOnlyInAlpha(
	t *testing.T,
) {
	t.Parallel()

	cfg := config{}
	cfg.IPLocation.Provider = "deterministic"
	resolver, closeResolver, err := buildCommentIPLocationResolver(
		cfg,
		"alpha",
		nil,
	)
	if err != nil {
		t.Fatalf("build alpha resolver: %v", err)
	}
	if resolver.Resolve("1.2.3.4") != "浙江" {
		t.Fatalf("alpha deterministic resolver did not expose contract fixture")
	}
	closeResolver()

	if _, _, err := buildCommentIPLocationResolver(cfg, "prod", nil); err == nil {
		t.Fatal("production accepted deterministic IP location resolver")
	}
}

func TestBuildCommentIPLocationResolverUsesOfflineDatabasesOutsideAlpha(
	t *testing.T,
) {
	t.Parallel()

	cfg := config{}
	cfg.IPLocation.Provider = "ip2region"
	cfg.IPLocation.IPv4DatabasePath = "/geo/ip4.xdb"
	cfg.IPLocation.IPv6DatabasePath = "/geo/ip6.xdb"

	var gotV4Path string
	var gotV6Path string
	closed := false
	factory := func(v4Path, v6Path string) (
		iplocationapp.Resolver,
		func(),
		error,
	) {
		gotV4Path = v4Path
		gotV6Path = v6Path
		return staticIPLocationResolver{location: "浙江"}, func() {
			closed = true
		}, nil
	}

	resolver, closeResolver, err := buildCommentIPLocationResolver(
		cfg,
		"prod",
		factory,
	)
	if err != nil {
		t.Fatalf("build production resolver: %v", err)
	}
	if gotV4Path != cfg.IPLocation.IPv4DatabasePath ||
		gotV6Path != cfg.IPLocation.IPv6DatabasePath {
		t.Fatalf("database paths = %q/%q", gotV4Path, gotV6Path)
	}
	if resolver.Resolve("1.2.3.4") != "浙江" {
		t.Fatal("production resolver result was not returned")
	}
	closeResolver()
	if !closed {
		t.Fatal("production resolver close function was not invoked")
	}

	if _, _, err := buildCommentIPLocationResolver(cfg, "alpha", factory); err == nil {
		t.Fatal("alpha accepted production IP location resolver")
	}
}

func TestBuildCommentIPLocationResolverFailsClosedOnDatabaseError(
	t *testing.T,
) {
	t.Parallel()

	cfg := config{}
	cfg.IPLocation.Provider = "ip2region"
	factoryErr := errors.New("invalid xdb")
	_, _, err := buildCommentIPLocationResolver(
		cfg,
		"gamma",
		func(string, string) (iplocationapp.Resolver, func(), error) {
			return nil, nil, factoryErr
		},
	)
	if !errors.Is(err, factoryErr) {
		t.Fatalf("factory error = %v, want wrapped %v", err, factoryErr)
	}
}

func TestValidateIPLocationConfigRejectsMissingOrStaleProductionData(
	t *testing.T,
) {
	t.Parallel()

	now := time.Date(2026, time.July, 20, 0, 0, 0, 0, time.UTC)
	cfg := config{}
	cfg.IPLocation.Provider = "ip2region"
	cfg.IPLocation.IPv4DatabasePath = "/geo/ip4.xdb"
	cfg.IPLocation.IPv6DatabasePath = "/geo/ip6.xdb"
	cfg.IPLocation.DataVersion = "2026-07-09"
	if err := validateIPLocationConfig(cfg, "prod", now); err != nil {
		t.Fatalf("valid production config rejected: %v", err)
	}

	cfg.IPLocation.DataVersion = "2026-05-01"
	if err := validateIPLocationConfig(cfg, "prod", now); err == nil {
		t.Fatal("stale production database was accepted")
	}

	cfg.IPLocation.Provider = "deterministic"
	if err := validateIPLocationConfig(cfg, "gamma", now); err == nil {
		t.Fatal("gamma accepted deterministic provider")
	}
}
