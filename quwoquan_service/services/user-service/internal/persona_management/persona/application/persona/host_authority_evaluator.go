package persona

import (
	"context"
	"errors"
	"strings"
	"time"

	runtimeauthority "quwoquan_service/runtime/hostauthority"
)

var ErrHostAuthoritySubjectNotFound = errors.New("Persona Host authority subject not found")

type HostAuthoritySnapshot struct {
	PersonaID string
	Version   int64
	Status    string
}

type HostAuthoritySnapshotReader interface {
	ReadHostAuthoritySnapshot(context.Context, string) (HostAuthoritySnapshot, bool, error)
}

type HostAuthorityEvaluator struct {
	reader HostAuthoritySnapshotReader
	now    func() time.Time
}

func NewHostAuthorityEvaluator(
	reader HostAuthoritySnapshotReader,
	now func() time.Time,
) (*HostAuthorityEvaluator, error) {
	if reader == nil {
		return nil, errors.New("Persona Host authority evaluator requires canonical reader")
	}
	if now == nil {
		now = time.Now
	}
	return &HostAuthorityEvaluator{reader: reader, now: now}, nil
}

func (evaluator *HostAuthorityEvaluator) Evaluate(
	ctx context.Context,
	query runtimeauthority.Query,
) (runtimeauthority.Evidence, error) {
	personaID := strings.TrimSpace(query.HostSubjectID)
	snapshot, found, err := evaluator.reader.ReadHostAuthoritySnapshot(ctx, personaID)
	if err != nil {
		return runtimeauthority.Evidence{}, err
	}
	if !found {
		return runtimeauthority.Evidence{}, ErrHostAuthoritySubjectNotFound
	}
	ref := "persona:" + personaID
	evidenceRef := ref + ":self"
	active := strings.TrimSpace(snapshot.Status) == "active"
	return runtimeauthority.Issue(query, runtimeauthority.OwnerDecision{
		HostSubjectKind:      "persona",
		HostSubjectID:        personaID,
		HostSubjectRef:       ref,
		AuthorityEvidenceRef: evidenceRef,
		AuthorityVersion:     snapshot.Version,
		Authorized:           active && strings.TrimSpace(query.ActorPersonaID) == personaID,
		Revoked:              !active,
	}, evaluator.now()), nil
}
