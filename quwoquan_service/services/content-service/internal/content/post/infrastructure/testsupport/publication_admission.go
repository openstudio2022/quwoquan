package testsupport

import (
	"context"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type AllowPublicationRateGate struct{}

func (AllowPublicationRateGate) AdmitPublication(
	context.Context,
	postports.PublicationRateRequest,
) (postports.PublicationRateDecision, error) {
	return postports.PublicationRateDecision{Allowed: true}, nil
}

type FixedPublicationSafetyGate struct {
	Decision   postports.PublicationSafetyDecision
	ReasonCode string
	Err        error
}

func (g FixedPublicationSafetyGate) EvaluatePublication(
	context.Context,
	postports.PublicationSafetyRequest,
) (postports.PublicationSafetyResult, error) {
	decision := g.Decision
	if decision == "" {
		decision = postports.PublicationSafetyAllow
	}
	return postports.PublicationSafetyResult{
		Decision:   decision,
		ReasonCode: g.ReasonCode,
	}, g.Err
}

var _ postports.PublicationRateGate = AllowPublicationRateGate{}
var _ postports.PublicationSafetyGate = FixedPublicationSafetyGate{}
