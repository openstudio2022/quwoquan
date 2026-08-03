package provider

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net"
	"net/http"
	"strings"
)

// RedactingRoundTripper 把 net/http 可能携带完整 URL（APNs URL 中含设备 token）的
// transport error 收敛为无 URL 错误，再交给统一 observed middleware 记录。
type RedactingRoundTripper struct {
	Base http.RoundTripper
}

func (r RedactingRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	base := r.Base
	if base == nil {
		base = http.DefaultTransport
	}
	response, err := base.RoundTrip(request)
	if err != nil {
		return response, sanitizeHTTPError(err)
	}
	return response, nil
}

type sanitizedTransportError struct {
	timeout bool
}

func (e sanitizedTransportError) Error() string   { return "push provider transport failed" }
func (e sanitizedTransportError) Timeout() bool   { return e.timeout }
func (e sanitizedTransportError) Temporary() bool { return true }

func sanitizeHTTPError(err error) error {
	if err == nil {
		return nil
	}
	var netErr net.Error
	return sanitizedTransportError{timeout: errors.As(err, &netErr) && netErr.Timeout()}
}

func pushHTTPClient(source *http.Client) *http.Client {
	return &http.Client{
		Transport: source.Transport,
		Timeout:   source.Timeout,
		Jar:       source.Jar,
		CheckRedirect: func(
			_ *http.Request,
			_ []*http.Request,
		) error {
			return http.ErrUseLastResponse
		},
	}
}

func providerCollapseKey(deliveryKey string) string {
	normalized := strings.TrimSpace(deliveryKey)
	if len(normalized) <= 64 {
		return normalized
	}
	sum := sha256.Sum256([]byte(normalized))
	return hex.EncodeToString(sum[:])
}
