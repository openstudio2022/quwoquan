package homepage

import (
	"context"
	"errors"
	"strings"
	"time"

	runtimeauthority "quwoquan_service/runtime/hostauthority"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

var ErrHostAuthoritySubjectNotFound = errors.New("EntityHomepage Host authority subject not found")

type HostAuthorityEvaluator struct {
	store HostAuthorityAggregateReader
	now   func() time.Time
}

type HostAuthorityAggregateReader interface {
	Load(context.Context, string) (*homepagemodel.Homepage, bool, error)
}

func NewHostAuthorityEvaluator(
	store HostAuthorityAggregateReader,
	now func() time.Time,
) (*HostAuthorityEvaluator, error) {
	if store == nil {
		return nil, errors.New("EntityHomepage Host authority evaluator requires aggregate Store")
	}
	if now == nil {
		now = time.Now
	}
	return &HostAuthorityEvaluator{store: store, now: now}, nil
}

func (evaluator *HostAuthorityEvaluator) Evaluate(
	ctx context.Context,
	query runtimeauthority.Query,
) (runtimeauthority.Evidence, error) {
	homepageID := strings.TrimSpace(query.HostSubjectID)
	aggregate, found, err := evaluator.store.Load(ctx, homepageID)
	if err != nil {
		return runtimeauthority.Evidence{}, err
	}
	if !found {
		return runtimeauthority.Evidence{}, ErrHostAuthoritySubjectNotFound
	}
	snapshot := aggregate.Snapshot()
	actorID := strings.TrimSpace(query.ActorPersonaID)
	authorizedActor := actorID == strings.TrimSpace(snapshot.OwnerPersonaID) ||
		containsPersona(snapshot.ManagerPersonaIDs, actorID)
	active := snapshot.Status == homepagemodel.StatusPublished &&
		strings.TrimSpace(snapshot.ClaimStatus) == "claimed"
	ref := "entity_homepage:" + homepageID
	return runtimeauthority.Issue(query, runtimeauthority.OwnerDecision{
		HostSubjectKind:      "entity_homepage",
		HostSubjectID:        homepageID,
		HostSubjectRef:       ref,
		AuthorityEvidenceRef: ref + ":authority:" + actorID,
		AuthorityVersion:     snapshot.Version,
		Authorized:           active && authorizedActor,
		Revoked:              !active,
	}, evaluator.now()), nil
}

func containsPersona(values []string, target string) bool {
	if target == "" {
		return false
	}
	for _, value := range values {
		if strings.TrimSpace(value) == target {
			return true
		}
	}
	return false
}
