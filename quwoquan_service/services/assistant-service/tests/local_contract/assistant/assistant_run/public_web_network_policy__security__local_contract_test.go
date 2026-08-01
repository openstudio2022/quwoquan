// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"crypto/tls"
	"errors"
	"io"
	"net"
	"net/http"
	"net/netip"
	"strings"
	"testing"

	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
)

type staticDNSResolver map[string][]netip.Addr

func (r staticDNSResolver) LookupNetIP(
	_ context.Context,
	_ string,
	host string,
) ([]netip.Addr, error) {
	addresses, ok := r[host]
	if !ok {
		return nil, errors.New("not found")
	}
	return append([]netip.Addr{}, addresses...), nil
}

func TestPublicWebNetworkPolicyAcceptsOnlyPublicHTTPSTargets(t *testing.T) {
	policy := publicweb.NewNetworkPolicy(staticDNSResolver{
		"public.example.org": {netip.MustParseAddr("93.184.216.34")},
	})
	target, addresses, err := policy.ResolveURL(
		context.Background(),
		"https://Public.Example.Org:443/path?q=1#fragment",
	)
	if err != nil {
		t.Fatalf("ResolveURL() error = %v", err)
	}
	if got, want := target.String(), "https://public.example.org:443/path?q=1"; got != want {
		t.Fatalf("normalized URL = %q, want %q", got, want)
	}
	if len(addresses) != 1 || addresses[0].String() != "93.184.216.34" {
		t.Fatalf("addresses = %#v", addresses)
	}
}

func TestPublicWebNetworkPolicyRejectsProtocolCredentialsPortAndLiteralIP(t *testing.T) {
	policy := publicweb.NewNetworkPolicy(staticDNSResolver{})
	values := []string{
		"http://public.example.org",
		"file:///etc/passwd",
		"https://user:secret@public.example.org",
		"https://public.example.org:8443",
		"https://127.0.0.1/",
		"https://[::1]/",
		"https://metadata.google.internal/",
		"https://service.local/",
	}
	for _, value := range values {
		t.Run(value, func(t *testing.T) {
			if _, _, err := policy.ResolveURL(context.Background(), value); err == nil {
				t.Fatalf("ResolveURL(%q) unexpectedly succeeded", value)
			}
		})
	}
}

func TestPublicWebNetworkPolicyRejectsAnyNonPublicDNSAnswer(t *testing.T) {
	blocked := []string{
		"127.0.0.1",
		"10.0.0.1",
		"172.16.0.1",
		"192.168.1.1",
		"169.254.169.254",
		"100.100.100.200",
		"168.63.129.16",
		"100.64.0.1",
		"198.18.0.1",
		"192.0.2.1",
		"::1",
		"fc00::1",
		"fe80::1",
		"2001:db8::1",
	}
	for _, address := range blocked {
		t.Run(address, func(t *testing.T) {
			policy := publicweb.NewNetworkPolicy(staticDNSResolver{
				"rebind.example.org": {
					netip.MustParseAddr("93.184.216.34"),
					netip.MustParseAddr(address),
				},
			})
			if _, _, err := policy.ResolveURL(
				context.Background(),
				"https://rebind.example.org",
			); err == nil {
				t.Fatalf("mixed DNS answer containing %s was accepted", address)
			}
		})
	}
}

type recordingDialer struct{ addresses []string }

func (d *recordingDialer) DialContext(
	_ context.Context,
	_ string,
	address string,
) (net.Conn, error) {
	d.addresses = append(d.addresses, address)
	return nil, errors.New("stop after address assertion")
}

func TestSecureTransportPinsDialToRevalidatedPublicAddress(t *testing.T) {
	policy := publicweb.NewNetworkPolicy(staticDNSResolver{
		"public.example.org": {netip.MustParseAddr("93.184.216.34")},
	})
	dialer := &recordingDialer{}
	transport := publicweb.NewSecureTransport(policy, dialer)
	_, err := transport.DialContext(
		context.Background(),
		"tcp",
		"public.example.org:443",
	)
	if err == nil {
		t.Fatal("DialContext() unexpectedly succeeded")
	}
	if got, want := strings.Join(dialer.addresses, ","), "93.184.216.34:443"; got != want {
		t.Fatalf("dialed %q, want %q", got, want)
	}
}

type rebindingDNSResolver struct{ calls int }

func (r *rebindingDNSResolver) LookupNetIP(
	_ context.Context,
	_ string,
	_ string,
) ([]netip.Addr, error) {
	r.calls++
	if r.calls == 1 {
		return []netip.Addr{netip.MustParseAddr("93.184.216.34")}, nil
	}
	return []netip.Addr{netip.MustParseAddr("169.254.169.254")}, nil
}

func TestSecureTransportRejectsDNSRebindingAtFinalDial(t *testing.T) {
	resolver := &rebindingDNSResolver{}
	policy := publicweb.NewNetworkPolicy(resolver)
	if _, _, err := policy.ResolveURL(
		context.Background(),
		"https://rebind.example.org",
	); err != nil {
		t.Fatalf("initial public DNS resolution failed: %v", err)
	}
	dialer := &recordingDialer{}
	transport := publicweb.NewSecureTransport(policy, dialer)
	if _, err := transport.DialContext(
		context.Background(),
		"tcp",
		"rebind.example.org:443",
	); err == nil {
		t.Fatal("private rebinding answer reached the dialer")
	}
	if len(dialer.addresses) != 0 || resolver.calls != 2 {
		t.Fatalf("rebind calls=%d dialed=%v", resolver.calls, dialer.addresses)
	}
}

func TestSecureTransportCannotDisableTLSVerificationOrAttachClientCertificate(t *testing.T) {
	policy := publicweb.NewNetworkPolicy(staticDNSResolver{
		"public.example.org": {netip.MustParseAddr("93.184.216.34")},
	})
	transport := publicweb.NewSecureTransportWithTLS(
		policy,
		&recordingDialer{},
		&tls.Config{
			InsecureSkipVerify: true,
			Certificates:       []tls.Certificate{{}},
		},
	)
	if transport.TLSClientConfig.InsecureSkipVerify ||
		len(transport.TLSClientConfig.Certificates) != 0 ||
		transport.TLSClientConfig.MinVersion < tls.VersionTLS12 {
		t.Fatalf("unsafe TLS client config survived: %#v", transport.TLSClientConfig)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

func TestPublicWebFetcherStripsCredentialsAndRevalidatesRedirects(t *testing.T) {
	policy := publicweb.NewNetworkPolicy(staticDNSResolver{
		"first.example.org":  {netip.MustParseAddr("93.184.216.34")},
		"second.example.org": {netip.MustParseAddr("8.8.8.8")},
	})
	requestCount := 0
	client := &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		requestCount++
		if request.Header.Get("Authorization") != "" || request.Header.Get("Cookie") != "" || request.Header.Get("Referer") != "" {
			t.Fatalf("unsafe headers escaped: %#v", request.Header)
		}
		if request.Header.Get("Accept-Encoding") != "identity" {
			t.Fatalf("Accept-Encoding = %q", request.Header.Get("Accept-Encoding"))
		}
		if requestCount == 1 {
			return responseFor(request, http.StatusFound, "", map[string]string{
				"Location": "https://second.example.org/final",
			}), nil
		}
		return responseFor(request, http.StatusOK, "verified body", map[string]string{
			"Content-Type": "text/plain; charset=utf-8",
		}), nil
	})}
	fetcher := publicweb.NewFetcherWithClient(policy, client, publicweb.DefaultFetchLimits())
	result, err := fetcher.Fetch(context.Background(), application.NetworkRequest{
		URL:    "https://first.example.org/start",
		Method: http.MethodGet,
	})
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if got, want := result.FinalURL, "https://second.example.org/final"; got != want {
		t.Fatalf("FinalURL = %q, want %q", got, want)
	}
	if len(result.RedirectChain) != 1 || result.RedirectChain[0] != result.FinalURL {
		t.Fatalf("RedirectChain = %#v", result.RedirectChain)
	}
}

func TestPublicWebFetcherRejectsRedirectEscapeAndUnboundedContent(t *testing.T) {
	tests := []struct {
		name       string
		location   string
		body       string
		headers    map[string]string
		maxBytes   int64
		wantReject publicweb.RejectionKind
	}{
		{
			name:       "redirect to private address",
			location:   "https://private.example.org/metadata",
			wantReject: publicweb.RejectionResolution,
		},
		{
			name:       "unsupported media",
			body:       "binary",
			headers:    map[string]string{"Content-Type": "application/octet-stream"},
			wantReject: publicweb.RejectionContentType,
		},
		{
			name:       "compressed response",
			body:       "compressed",
			headers:    map[string]string{"Content-Type": "text/plain", "Content-Encoding": "gzip"},
			wantReject: publicweb.RejectionContentCoding,
		},
		{
			name:       "response over run budget",
			body:       "too large",
			headers:    map[string]string{"Content-Type": "text/plain"},
			maxBytes:   3,
			wantReject: publicweb.RejectionContentSize,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			policy := publicweb.NewNetworkPolicy(staticDNSResolver{
				"public.example.org":  {netip.MustParseAddr("93.184.216.34")},
				"private.example.org": {netip.MustParseAddr("169.254.169.254")},
			})
			client := &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
				if test.location != "" {
					return responseFor(request, http.StatusFound, "", map[string]string{"Location": test.location}), nil
				}
				return responseFor(request, http.StatusOK, test.body, test.headers), nil
			})}
			fetcher := publicweb.NewFetcherWithClient(policy, client, publicweb.DefaultFetchLimits())
			_, err := fetcher.Fetch(context.Background(), application.NetworkRequest{
				URL:      "https://public.example.org/start",
				MaxBytes: test.maxBytes,
			})
			var rejection publicweb.Rejection
			if !errors.As(err, &rejection) || rejection.Kind != test.wantReject {
				t.Fatalf("Fetch() error = %v, want rejection %s", err, test.wantReject)
			}
		})
	}
}

func responseFor(
	request *http.Request,
	status int,
	body string,
	headers map[string]string,
) *http.Response {
	header := make(http.Header)
	for key, value := range headers {
		header.Set(key, value)
	}
	return &http.Response{
		StatusCode:    status,
		Status:        http.StatusText(status),
		Header:        header,
		Body:          io.NopCloser(strings.NewReader(body)),
		ContentLength: int64(len(body)),
		Request:       request,
	}
}
