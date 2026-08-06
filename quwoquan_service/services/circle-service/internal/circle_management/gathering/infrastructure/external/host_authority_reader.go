package external

import (
	"context"
	"fmt"
	"strings"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// These ports are deliberately subject-specific. Production composition must
// bind them to the generated Persona, Entity Homepage, and Circle owner
// clients; this reader does not accept a caller-supplied generic role claim.
type PersonaHostAuthorityClient interface {
	EvaluatePersonaHostAuthority(
		context.Context,
		model.HostAuthorityQuery,
	) (model.HostAuthorityEvidence, error)
}

type EntityHomepageHostAuthorityClient interface {
	EvaluateEntityHomepageHostAuthority(
		context.Context,
		model.HostAuthorityQuery,
	) (model.HostAuthorityEvidence, error)
}

type CircleHostAuthorityClient interface {
	EvaluateCircleHostAuthority(
		context.Context,
		model.HostAuthorityQuery,
	) (model.HostAuthorityEvidence, error)
}

type HostAuthorityReader struct {
	persona        PersonaHostAuthorityClient
	entityHomepage EntityHomepageHostAuthorityClient
	circle         CircleHostAuthorityClient
}

func NewHostAuthorityReader(
	persona PersonaHostAuthorityClient,
	entityHomepage EntityHomepageHostAuthorityClient,
	circle CircleHostAuthorityClient,
) *HostAuthorityReader {
	if persona == nil || entityHomepage == nil || circle == nil {
		panic("Gathering HostAuthorityReader requires all canonical owner clients")
	}
	return &HostAuthorityReader{
		persona: persona, entityHomepage: entityHomepage, circle: circle,
	}
}

func (reader *HostAuthorityReader) ReadHostAuthority(
	ctx context.Context,
	query model.HostAuthorityQuery,
) (model.HostAuthorityEvidence, error) {
	var (
		evidence model.HostAuthorityEvidence
		err      error
	)
	switch query.HostSubjectKind {
	case contract.GatheringHostSubjectKindPersona:
		evidence, err = reader.persona.EvaluatePersonaHostAuthority(ctx, query)
	case contract.GatheringHostSubjectKindEntityHomepage:
		evidence, err = reader.entityHomepage.EvaluateEntityHomepageHostAuthority(ctx, query)
	case contract.GatheringHostSubjectKindCircle:
		evidence, err = reader.circle.EvaluateCircleHostAuthority(ctx, query)
	default:
		return model.HostAuthorityEvidence{}, fmt.Errorf(
			"%w: unsupported Host subject kind %q",
			gatheringapp.ErrHostAuthorityUnavailable,
			query.HostSubjectKind,
		)
	}
	if err != nil {
		return model.HostAuthorityEvidence{}, fmt.Errorf(
			"%w: %s owner evaluation failed: %v",
			gatheringapp.ErrHostAuthorityUnavailable,
			query.HostSubjectKind,
			err,
		)
	}
	if evidence.HostSubjectKind != query.HostSubjectKind ||
		evidence.HostSubjectID != query.HostSubjectID ||
		evidence.HostReference != strings.TrimSpace(string(query.HostSubjectKind))+":"+
			strings.TrimSpace(query.HostSubjectID) ||
		evidence.ActorPersonaID != query.ActorPersonaID ||
		evidence.OrganizerPersonaID != query.OrganizerPersonaID ||
		evidence.AuthorityEvidenceRef != query.AuthorityEvidenceRef ||
		evidence.AuthorityVersion != query.AuthorityVersion ||
		evidence.Action != query.Action {
		return model.HostAuthorityEvidence{}, fmt.Errorf(
			"%w: canonical owner response identity mismatch",
			gatheringapp.ErrHostAuthorityUnavailable,
		)
	}
	if strings.TrimSpace(evidence.AuthorityDigest) == "" ||
		evidence.ExpiresAt.IsZero() {
		return model.HostAuthorityEvidence{}, fmt.Errorf(
			"%w: canonical owner response omitted digest or expiry",
			gatheringapp.ErrHostAuthorityUnavailable,
		)
	}
	return evidence, nil
}

var _ gatheringapp.HostAuthorityReader = (*HostAuthorityReader)(nil)
