package application

import (
	"context"
	"errors"
	"strings"
	"time"

	runtimeauthority "quwoquan_service/runtime/hostauthority"
	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
)

var ErrHostAuthoritySubjectNotFound = errors.New("Circle Host authority subject not found")

type MembershipAuthorityReader interface {
	LoadByIdentity(
		context.Context,
		string,
		string,
	) (membershipmodel.CircleMembership, bool, error)
}

type CircleAuthorityReader interface {
	Load(context.Context, string) (circlemodel.Circle, bool, error)
}

type HostAuthorityEvaluator struct {
	circles     CircleAuthorityReader
	memberships MembershipAuthorityReader
	now         func() time.Time
}

func NewHostAuthorityEvaluator(
	circles CircleAuthorityReader,
	memberships MembershipAuthorityReader,
	now func() time.Time,
) (*HostAuthorityEvaluator, error) {
	if circles == nil || memberships == nil {
		return nil, errors.New("Circle Host authority evaluator requires aggregate and membership Stores")
	}
	if now == nil {
		now = time.Now
	}
	return &HostAuthorityEvaluator{
		circles: circles, memberships: memberships, now: now,
	}, nil
}

func (evaluator *HostAuthorityEvaluator) Evaluate(
	ctx context.Context,
	query runtimeauthority.Query,
) (runtimeauthority.Evidence, error) {
	circleID := strings.TrimSpace(query.HostSubjectID)
	circle, found, err := evaluator.circles.Load(ctx, circleID)
	if err != nil {
		return runtimeauthority.Evidence{}, err
	}
	if !found {
		return runtimeauthority.Evidence{}, ErrHostAuthoritySubjectNotFound
	}
	actorID := strings.TrimSpace(query.ActorPersonaID)
	activeCircle := circle.Status == circlemodel.CircleStatusActive
	authorized := activeCircle && strings.TrimSpace(circle.OwnerID) == actorID
	revoked := !activeCircle
	authorityVersion := circle.Version
	if !authorized {
		membership, membershipFound, membershipErr :=
			evaluator.memberships.LoadByIdentity(ctx, circleID, actorID)
		if membershipErr != nil {
			return runtimeauthority.Evidence{}, membershipErr
		}
		if membershipFound {
			activeAdmin := membership.State == membershipmodel.CircleMembershipStateActive &&
				membership.Role == membershipmodel.CircleMemberRoleAdmin
			authorized = activeCircle && activeAdmin
			revoked = revoked || !activeAdmin
			authorityVersion = membership.Version
		}
	}
	ref := "circle:" + circleID
	return runtimeauthority.Issue(query, runtimeauthority.OwnerDecision{
		HostSubjectKind:      "circle",
		HostSubjectID:        circleID,
		HostSubjectRef:       ref,
		AuthorityEvidenceRef: ref + ":authority:" + actorID,
		AuthorityVersion:     authorityVersion,
		Authorized:           authorized,
		Revoked:              revoked,
	}, evaluator.now()), nil
}
