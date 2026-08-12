package networkcatalog

import (
	"bytes"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"net"
	"net/netip"
	"os"
	"regexp"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
)

const catalogSchema = "api-edge-network-attribute-catalog/v1"

var (
	sha256ReferencePattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	attributeValuePattern  = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]{0,31}$`)
)

type catalogDocument struct {
	Schema  string         `yaml:"schema"`
	Entries []catalogEntry `yaml:"entries"`
}

type catalogEntry struct {
	CIDR    string `yaml:"cidr"`
	Region  string `yaml:"region,omitempty"`
	Carrier string `yaml:"carrier,omitempty"`
}

type resolvedEntry struct {
	prefix  netip.Prefix
	region  string
	carrier string
}

// Resolver is an immutable in-memory snapshot of the release-bound catalog.
// It never reloads the file and never performs a network lookup.
type Resolver struct {
	entries []resolvedEntry
}

var _ application.NetworkAttributeResolver = (*Resolver)(nil)

func Load(
	config application.NetworkAttributeCatalogConfig,
	policy domain.Policy,
) (*Resolver, error) {
	if !config.Enabled {
		if policy.RequiresNetworkAttributeCatalog() {
			return nil, errors.New("directed region or carrier rollout requires the network attribute catalog")
		}
		return nil, nil
	}
	config.File = strings.TrimSpace(config.File)
	config.SHA256 = strings.ToLower(strings.TrimSpace(config.SHA256))
	if config.File == "" || !sha256ReferencePattern.MatchString(config.SHA256) {
		return nil, errors.New("network attribute catalog file and canonical SHA-256 are required")
	}
	raw, err := os.ReadFile(config.File)
	if err != nil {
		return nil, fmt.Errorf("read network attribute catalog: %w", err)
	}
	actualDigest := fmt.Sprintf("sha256:%x", sha256.Sum256(raw))
	if actualDigest != config.SHA256 {
		return nil, fmt.Errorf("network attribute catalog digest mismatch: got %s", actualDigest)
	}
	document, err := decodeCatalog(raw)
	if err != nil {
		return nil, err
	}
	resolver, regions, carriers, err := buildResolver(document)
	if err != nil {
		return nil, err
	}
	if err := validatePolicyCoverage(policy, regions, carriers); err != nil {
		return nil, err
	}
	return resolver, nil
}

func (resolver *Resolver) Resolve(clientIP net.IP) application.NetworkAttributes {
	attributes := application.NetworkAttributes{Region: "unknown", Carrier: "unknown"}
	if resolver == nil {
		return attributes
	}
	address, ok := netip.AddrFromSlice(clientIP)
	if !ok {
		return attributes
	}
	address = address.Unmap()
	for _, entry := range resolver.entries {
		if !entry.prefix.Contains(address) {
			continue
		}
		if attributes.Region == "unknown" && entry.region != "" {
			attributes.Region = entry.region
		}
		if attributes.Carrier == "unknown" && entry.carrier != "" {
			attributes.Carrier = entry.carrier
		}
		if attributes.Region != "unknown" && attributes.Carrier != "unknown" {
			break
		}
	}
	return attributes
}

func decodeCatalog(raw []byte) (catalogDocument, error) {
	decoder := yaml.NewDecoder(bytes.NewReader(raw))
	decoder.KnownFields(true)
	var document catalogDocument
	if err := decoder.Decode(&document); err != nil {
		return catalogDocument{}, fmt.Errorf("decode network attribute catalog: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return catalogDocument{}, errors.New("network attribute catalog contains multiple YAML documents")
		}
		return catalogDocument{}, fmt.Errorf("decode trailing network attribute catalog: %w", err)
	}
	if strings.TrimSpace(document.Schema) != catalogSchema {
		return catalogDocument{}, fmt.Errorf("network attribute catalog schema must equal %q", catalogSchema)
	}
	if len(document.Entries) == 0 || len(document.Entries) > 100000 {
		return catalogDocument{}, errors.New("network attribute catalog entries must contain 1..100000 items")
	}
	return document, nil
}

func buildResolver(
	document catalogDocument,
) (*Resolver, map[string]struct{}, map[string]struct{}, error) {
	entries := make([]resolvedEntry, 0, len(document.Entries))
	regions := make(map[string]struct{})
	carriers := make(map[string]struct{})
	prefixes := make(map[string]struct{}, len(document.Entries))
	for index, raw := range document.Entries {
		prefixText := strings.TrimSpace(raw.CIDR)
		prefix, err := netip.ParsePrefix(prefixText)
		if err != nil || prefix.Masked().String() != prefixText {
			return nil, nil, nil, fmt.Errorf("network attribute catalog entry %d CIDR is not canonical", index)
		}
		prefix = prefix.Masked()
		prefixKey := prefix.String()
		if _, exists := prefixes[prefixKey]; exists {
			return nil, nil, nil, fmt.Errorf("network attribute catalog CIDR %s is duplicated", prefixKey)
		}
		prefixes[prefixKey] = struct{}{}
		region, err := normalizeAttribute(raw.Region)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("network attribute catalog entry %d region: %w", index, err)
		}
		carrier, err := normalizeAttribute(raw.Carrier)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("network attribute catalog entry %d carrier: %w", index, err)
		}
		if region == "" && carrier == "" {
			return nil, nil, nil, fmt.Errorf("network attribute catalog entry %d has no attributes", index)
		}
		if region != "" {
			regions[region] = struct{}{}
		}
		if carrier != "" {
			carriers[carrier] = struct{}{}
		}
		entries = append(entries, resolvedEntry{prefix: prefix, region: region, carrier: carrier})
	}
	sort.Slice(entries, func(left, right int) bool {
		if entries[left].prefix.Bits() != entries[right].prefix.Bits() {
			return entries[left].prefix.Bits() > entries[right].prefix.Bits()
		}
		return entries[left].prefix.String() < entries[right].prefix.String()
	})
	return &Resolver{entries: entries}, regions, carriers, nil
}

func normalizeAttribute(value string) (string, error) {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return "", nil
	}
	if value == "unknown" || !attributeValuePattern.MatchString(value) {
		return "", errors.New("value must be a canonical non-unknown label")
	}
	return value, nil
}

func validatePolicyCoverage(
	policy domain.Policy,
	regions map[string]struct{},
	carriers map[string]struct{},
) error {
	missingRegions := missingDirectedValues(policy, true, regions)
	missingCarriers := missingDirectedValues(policy, false, carriers)
	if len(missingRegions) != 0 || len(missingCarriers) != 0 {
		return fmt.Errorf(
			"network attribute catalog does not cover directed rollout values: regions=%v carriers=%v",
			missingRegions,
			missingCarriers,
		)
	}
	return nil
}

func missingDirectedValues(
	policy domain.Policy,
	regions bool,
	available map[string]struct{},
) []string {
	missing := make(map[string]struct{})
	for _, stage := range policy.Stages {
		selector := stage.Carriers
		if regions {
			selector = stage.Regions
		}
		if selector.Mode != "include" {
			continue
		}
		for _, raw := range selector.Values {
			value := strings.ToLower(strings.TrimSpace(raw))
			if value == "unknown" {
				continue
			}
			if _, exists := available[value]; !exists {
				missing[value] = struct{}{}
			}
		}
	}
	values := make([]string, 0, len(missing))
	for value := range missing {
		values = append(values, value)
	}
	sort.Strings(values)
	return values
}
