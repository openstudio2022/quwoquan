package runtimegovernance

import (
	"errors"
	"net/http"
)

// ErrCircuitOpen is returned when the circuit breaker is open.
var ErrCircuitOpen = errors.New("circuit breaker open")

// CBTransport wraps an http.RoundTripper with CircuitBreaker protection.
type CBTransport struct {
	Base http.RoundTripper
	CB   *CircuitBreaker
}

func (t *CBTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if !t.CB.Allow() {
		return nil, ErrCircuitOpen
	}
	resp, err := t.Base.RoundTrip(req)
	if err != nil {
		t.CB.RecordFailure()
		return nil, err
	}
	if resp.StatusCode >= 500 {
		t.CB.RecordFailure()
	} else {
		t.CB.RecordSuccess()
	}
	return resp, nil
}

// WrapClientWithCB returns a shallow copy of client whose Transport is
// protected by the given CircuitBreaker.
func WrapClientWithCB(client *http.Client, cb *CircuitBreaker) *http.Client {
	base := client.Transport
	if base == nil {
		base = http.DefaultTransport
	}
	clone := *client
	clone.Transport = &CBTransport{Base: base, CB: cb}
	return &clone
}
