package testinfra

import (
	"context"
	"fmt"
)

type FakeModelProvider struct {
	responses []string
	calls     []string
}

func NewFakeModelProvider(responses ...string) *FakeModelProvider {
	return &FakeModelProvider{responses: responses}
}

func (p *FakeModelProvider) Complete(_ context.Context, prompt string) (string, error) {
	p.calls = append(p.calls, prompt)
	if len(p.responses) == 0 {
		return "", fmt.Errorf("testinfra: fake model provider has no response")
	}
	response := p.responses[0]
	p.responses = p.responses[1:]
	return response, nil
}

func (p *FakeModelProvider) Calls() []string {
	calls := make([]string, len(p.calls))
	copy(calls, p.calls)
	return calls
}
