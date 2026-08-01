package publicweb

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/netip"
	"net/url"
	"strings"

	"golang.org/x/net/idna"
)

type RejectionKind string

const (
	RejectionInvalidURL    RejectionKind = "invalid_url"
	RejectionScheme        RejectionKind = "scheme_rejected"
	RejectionCredentials   RejectionKind = "credentials_rejected"
	RejectionHost          RejectionKind = "host_rejected"
	RejectionPort          RejectionKind = "port_rejected"
	RejectionResolution    RejectionKind = "resolution_rejected"
	RejectionRedirect      RejectionKind = "redirect_rejected"
	RejectionResponse      RejectionKind = "response_rejected"
	RejectionContentType   RejectionKind = "content_type_rejected"
	RejectionContentSize   RejectionKind = "content_size_rejected"
	RejectionContentCoding RejectionKind = "content_coding_rejected"
)

type Rejection struct {
	Kind  RejectionKind
	Value string
	Cause error
}

func (r Rejection) Error() string {
	if r.Cause == nil {
		return fmt.Sprintf("public web %s: %s", r.Kind, r.Value)
	}
	return fmt.Sprintf("public web %s: %s: %v", r.Kind, r.Value, r.Cause)
}

func (r Rejection) Unwrap() error { return r.Cause }

type DNSResolver interface {
	LookupNetIP(context.Context, string, string) ([]netip.Addr, error)
}

type NetworkPolicy struct {
	resolver DNSResolver
}

func NewNetworkPolicy(resolver DNSResolver) NetworkPolicy {
	if resolver == nil {
		resolver = net.DefaultResolver
	}
	return NetworkPolicy{resolver: resolver}
}

// ResolveURL validates the URL and every address returned by DNS. The returned
// URL uses an ASCII hostname and has no fragment, so it is safe to record in the
// source ledger. Connecting code must still call ResolveHost immediately before
// dialing to close the DNS-rebinding window.
func (p NetworkPolicy) ResolveURL(ctx context.Context, raw string) (*url.URL, []netip.Addr, error) {
	target, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || target.Opaque != "" || target.Host == "" {
		return nil, nil, Rejection{Kind: RejectionInvalidURL, Value: raw, Cause: err}
	}
	if !strings.EqualFold(target.Scheme, "https") {
		return nil, nil, Rejection{Kind: RejectionScheme, Value: target.Scheme}
	}
	if target.User != nil {
		return nil, nil, Rejection{Kind: RejectionCredentials, Value: target.User.String()}
	}
	if port := target.Port(); port != "" && port != "443" {
		return nil, nil, Rejection{Kind: RejectionPort, Value: port}
	}
	host, err := canonicalHostname(target.Hostname())
	if err != nil {
		return nil, nil, err
	}
	addresses, err := p.ResolveHost(ctx, host)
	if err != nil {
		return nil, nil, err
	}
	target.Scheme = "https"
	target.User = nil
	target.Fragment = ""
	if target.Port() == "443" {
		target.Host = net.JoinHostPort(host, "443")
	} else {
		target.Host = host
	}
	return target, addresses, nil
}

func (p NetworkPolicy) ResolveHost(ctx context.Context, rawHost string) ([]netip.Addr, error) {
	host, err := canonicalHostname(rawHost)
	if err != nil {
		return nil, err
	}
	addresses, err := p.resolver.LookupNetIP(ctx, "ip", host)
	if err != nil {
		return nil, Rejection{Kind: RejectionResolution, Value: host, Cause: err}
	}
	if len(addresses) == 0 {
		return nil, Rejection{Kind: RejectionResolution, Value: host, Cause: errors.New("no address")}
	}
	result := make([]netip.Addr, 0, len(addresses))
	for _, address := range addresses {
		address = address.Unmap()
		if !isPublicAddress(address) {
			return nil, Rejection{Kind: RejectionResolution, Value: address.String()}
		}
		result = append(result, address)
	}
	return result, nil
}

func canonicalHostname(raw string) (string, error) {
	host := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(raw)), ".")
	if host == "" {
		return "", Rejection{Kind: RejectionHost, Value: raw}
	}
	if _, err := netip.ParseAddr(host); err == nil {
		return "", Rejection{Kind: RejectionHost, Value: host}
	}
	ascii, err := idna.Lookup.ToASCII(host)
	if err != nil || len(ascii) > 253 {
		return "", Rejection{Kind: RejectionHost, Value: host, Cause: err}
	}
	for _, suffix := range []string{
		"localhost", ".localhost", ".local", ".internal", ".home", ".lan",
		".test", ".invalid", ".example",
	} {
		if ascii == suffix || strings.HasSuffix(ascii, suffix) {
			return "", Rejection{Kind: RejectionHost, Value: ascii}
		}
	}
	return ascii, nil
}

func isPublicAddress(address netip.Addr) bool {
	if !address.IsValid() || !address.IsGlobalUnicast() || address.IsPrivate() ||
		address.IsLoopback() || address.IsLinkLocalUnicast() ||
		address.IsLinkLocalMulticast() || address.IsMulticast() ||
		address.IsUnspecified() {
		return false
	}
	for _, prefix := range blockedAddressPrefixes {
		if prefix.Contains(address) {
			return false
		}
	}
	return true
}

var blockedAddressPrefixes = mustPrefixes(
	"0.0.0.0/8",
	"100.64.0.0/10",
	"100.100.100.200/32",
	"168.63.129.16/32",
	"192.0.0.0/24",
	"192.0.2.0/24",
	"198.18.0.0/15",
	"198.51.100.0/24",
	"203.0.113.0/24",
	"240.0.0.0/4",
	"100::/64",
	"2001:db8::/32",
)

func mustPrefixes(values ...string) []netip.Prefix {
	result := make([]netip.Prefix, 0, len(values))
	for _, value := range values {
		result = append(result, netip.MustParsePrefix(value))
	}
	return result
}
