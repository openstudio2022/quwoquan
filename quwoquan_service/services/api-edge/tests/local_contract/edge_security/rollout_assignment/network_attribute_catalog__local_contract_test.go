// spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-003
package local_contract

import (
	"crypto/sha256"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/networkcatalog"
)

const validNetworkAttributeCatalog = `schema: api-edge-network-attribute-catalog/v1
entries:
  - cidr: 10.0.0.0/8
    region: cn
    carrier: carrier-wide
  - cidr: 10.1.0.0/16
    region: gd
  - cidr: 10.1.2.0/24
    carrier: chinatelecom
  - cidr: 2001:db8::/32
    region: overseas
    carrier: ipv6-carrier
`

func TestNetworkAttributeCatalogUsesIndependentLongestPrefixAndImmutableSnapshot(t *testing.T) {
	config := writeNetworkAttributeCatalog(t, validNetworkAttributeCatalog)
	resolver, err := networkcatalog.Load(config, directedNetworkPolicy("gd", "chinatelecom"))
	if err != nil {
		t.Fatal(err)
	}
	assertNetworkAttributes(t, resolver.Resolve(net.ParseIP("10.1.2.9")), "gd", "chinatelecom")
	assertNetworkAttributes(t, resolver.Resolve(net.ParseIP("10.9.0.1")), "cn", "carrier-wide")
	assertNetworkAttributes(t, resolver.Resolve(net.ParseIP("2001:db8::1")), "overseas", "ipv6-carrier")
	assertNetworkAttributes(t, resolver.Resolve(net.ParseIP("192.0.2.10")), "unknown", "unknown")

	if err := os.WriteFile(config.File, []byte(`schema: replaced`), 0o600); err != nil {
		t.Fatal(err)
	}
	assertNetworkAttributes(t, resolver.Resolve(net.ParseIP("10.1.2.9")), "gd", "chinatelecom")
}

func TestNetworkAttributeCatalogFailsClosedOnDigestSchemaAndCoverage(t *testing.T) {
	config := writeNetworkAttributeCatalog(t, validNetworkAttributeCatalog)
	config.SHA256 = "sha256:" + strings.Repeat("0", 64)
	if _, err := networkcatalog.Load(config, directedNetworkPolicy("gd", "chinatelecom")); err == nil || !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("digest mismatch was not rejected: %v", err)
	}

	config = writeNetworkAttributeCatalog(t, strings.Replace(
		validNetworkAttributeCatalog,
		"10.1.0.0/16",
		"10.1.0.1/16",
		1,
	))
	if _, err := networkcatalog.Load(config, directedNetworkPolicy("gd", "chinatelecom")); err == nil || !strings.Contains(err.Error(), "CIDR is not canonical") {
		t.Fatalf("non-canonical CIDR was not rejected: %v", err)
	}

	config = writeNetworkAttributeCatalog(t, validNetworkAttributeCatalog)
	if _, err := networkcatalog.Load(config, directedNetworkPolicy("gd", "missing-carrier")); err == nil || !strings.Contains(err.Error(), "does not cover directed rollout values") {
		t.Fatalf("missing directed value was not rejected: %v", err)
	}
}

func directedNetworkPolicy(region, carrier string) domain.Policy {
	policy := rolloutPolicy("5")
	for _, name := range []string{"canary", "5", "20", "50"} {
		stage := policy.Stages[name]
		stage.Regions = domain.Selector{Mode: "include", Values: []string{region}}
		stage.Carriers = domain.Selector{Mode: "include", Values: []string{carrier}}
		policy.Stages[name] = stage
	}
	return policy
}

func writeNetworkAttributeCatalog(
	t *testing.T,
	raw string,
) application.NetworkAttributeCatalogConfig {
	t.Helper()
	path := filepath.Join(t.TempDir(), "network_attribute_catalog.yaml")
	content := []byte(raw)
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatal(err)
	}
	return application.NetworkAttributeCatalogConfig{
		Enabled: true,
		File:    path,
		SHA256:  fmt.Sprintf("sha256:%x", sha256.Sum256(content)),
	}
}

func assertNetworkAttributes(
	t *testing.T,
	attributes application.NetworkAttributes,
	region string,
	carrier string,
) {
	t.Helper()
	if attributes.Region != region || attributes.Carrier != carrier {
		t.Fatalf("attributes=%+v want region=%q carrier=%q", attributes, region, carrier)
	}
}
