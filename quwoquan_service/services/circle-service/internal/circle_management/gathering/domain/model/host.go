package gathering

import (
	"fmt"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

// HostAuthorityAction names the owner decision being proved. An evidence
// record is action-scoped so a read-only owner grant cannot be replayed for
// creation, publication, or organizer transfer.
type HostAuthorityAction string

const (
	HostAuthorityCreateDraft       HostAuthorityAction = "create_draft"
	HostAuthorityPublish           HostAuthorityAction = "publish"
	HostAuthorityAssignOrganizer   HostAuthorityAction = "assign_organizer"
	HostAuthorityTransferOrganizer HostAuthorityAction = "transfer_organizer"
)

// HostAuthorityQuery is sent to the canonical Persona, Entity Homepage, or
// Circle owner. Every identity and evidence field is repeated in the response
// and compared before the result is trusted.
type HostAuthorityQuery struct {
	HostSubjectKind      contract.GatheringHostSubjectKind
	HostSubjectID        string
	ActorPersonaID       string
	OrganizerPersonaID   string
	AuthorityEvidenceRef string
	AuthorityVersion     int64
	Action               HostAuthorityAction
	EvaluatedAt          time.Time
}

// HostAuthorityEvidence is a typed owner decision, not a client role claim.
// Revoked, expired, mismatched, or action-incomplete evidence always fails
// closed.
type HostAuthorityEvidence struct {
	HostSubjectKind      contract.GatheringHostSubjectKind
	HostSubjectID        string
	HostReference        string
	ActorPersonaID       string
	OrganizerPersonaID   string
	AuthorityEvidenceRef string
	AuthorityVersion     int64
	AuthorityDigest      string
	Action               HostAuthorityAction
	Valid                bool
	Revoked              bool
	ExpiresAt            time.Time
}

// AuditFact is the structured, metadata-only fact attached to the same owner
// command result/outbox transition. Evidence contents are never copied here.
type AuditFact struct {
	Operation            string
	ActorPersonaID       string
	ParticipantPersonaID string
	HostSubjectKind      contract.GatheringHostSubjectKind
	HostSubjectID        string
	AuthorityEvidenceRef string
	AuthorityVersion     int64
	RevisionID           string
	RevisionNumber       int64
	OutcomeStatus        contract.GatheringOutcomeStatus
	OccurredAt           time.Time
}

func ValidateHostAuthority(
	binding contract.HostBinding,
	query HostAuthorityQuery,
	evidence HostAuthorityEvidence,
) error {
	binding = normalizeHostBindingAuthority(binding)
	query = normalizeHostAuthorityQuery(query)
	evidence = normalizeHostAuthorityEvidence(evidence)
	if !validHostBinding(binding) || query.EvaluatedAt.IsZero() ||
		strings.TrimSpace(query.ActorPersonaID) == "" ||
		query.Action == "" {
		return fmt.Errorf("%w: incomplete Host authority request", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	if query.HostSubjectKind != binding.HostSubjectKind ||
		query.HostSubjectID != binding.HostSubjectID ||
		query.AuthorityEvidenceRef != binding.AuthorityEvidenceRef ||
		query.AuthorityVersion != binding.AuthorityVersion {
		return fmt.Errorf("%w: requested authority does not match HostBinding", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	if !evidence.Valid || evidence.Revoked ||
		evidence.HostSubjectKind != query.HostSubjectKind ||
		evidence.HostSubjectID != query.HostSubjectID ||
		evidence.HostReference != hostAuthorityReference(
			query.HostSubjectKind,
			query.HostSubjectID,
		) ||
		evidence.ActorPersonaID != query.ActorPersonaID ||
		evidence.OrganizerPersonaID != query.OrganizerPersonaID ||
		evidence.AuthorityEvidenceRef != query.AuthorityEvidenceRef ||
		evidence.AuthorityVersion != query.AuthorityVersion ||
		strings.TrimSpace(evidence.AuthorityDigest) == "" ||
		evidence.Action != query.Action {
		return fmt.Errorf("%w: owner evidence is invalid, revoked, or mismatched", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	if !binding.AuthorityExpiresAt.IsZero() && !query.EvaluatedAt.Before(binding.AuthorityExpiresAt) {
		return fmt.Errorf("%w: HostBinding authority expired", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	if !evidence.ExpiresAt.IsZero() && !query.EvaluatedAt.Before(evidence.ExpiresAt) {
		return fmt.Errorf("%w: owner evidence expired", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	return nil
}

// InitializeHostState keeps the immutable execution subject separate from the
// public Host subject. The creator receives management authority, but does not
// receive a Participation or consume a seat.
func InitializeHostState(
	createdByPersonaID string,
	binding contract.HostBinding,
	evidence HostAuthorityEvidence,
	assignedAt time.Time,
) (contract.HostBinding, []contract.OrganizerAssignment, AuditFact, error) {
	createdByPersonaID = strings.TrimSpace(createdByPersonaID)
	binding = normalizeHostBindingAuthority(binding)
	query := HostAuthorityQuery{
		HostSubjectKind:      binding.HostSubjectKind,
		HostSubjectID:        binding.HostSubjectID,
		ActorPersonaID:       createdByPersonaID,
		OrganizerPersonaID:   createdByPersonaID,
		AuthorityEvidenceRef: binding.AuthorityEvidenceRef,
		AuthorityVersion:     binding.AuthorityVersion,
		Action:               HostAuthorityCreateDraft,
		EvaluatedAt:          assignedAt.UTC(),
	}
	if err := ValidateHostAuthority(binding, query, evidence); err != nil {
		return contract.HostBinding{}, nil, AuditFact{}, err
	}
	assignments := []contract.OrganizerAssignment{{
		PersonaID:            createdByPersonaID,
		Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
		AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
		AuthorityVersion:     evidence.AuthorityVersion,
		AssignedAt:           assignedAt.UTC(),
		Version:              1,
	}}
	return binding, assignments, authorityAuditFact("CreateGatheringDraft", query, assignedAt), nil
}

func RequireOrganizer(assignments []contract.OrganizerAssignment, personaID string) error {
	personaID = strings.TrimSpace(personaID)
	for _, assignment := range assignments {
		if assignment.PersonaID == personaID && assignment.RevokedAt.IsZero() &&
			(assignment.Role == contract.GatheringOrganizerRolePrimaryOrganizer ||
				assignment.Role == contract.GatheringOrganizerRoleCoHost) {
			return nil
		}
	}
	return fmt.Errorf("%w: active OrganizerAssignment required", gatheringerrors.ErrGatheringPermissionDenied)
}

func RequirePrimaryOrganizer(assignments []contract.OrganizerAssignment, personaID string) error {
	personaID = strings.TrimSpace(personaID)
	for _, assignment := range assignments {
		if assignment.PersonaID == personaID && assignment.RevokedAt.IsZero() &&
			assignment.Role == contract.GatheringOrganizerRolePrimaryOrganizer {
			return nil
		}
	}
	return fmt.Errorf("%w: primary OrganizerAssignment required", gatheringerrors.ErrGatheringPermissionDenied)
}

func AssignCoHost(
	assignments []contract.OrganizerAssignment,
	actorPersonaID string,
	coHostPersonaID string,
	evidence HostAuthorityEvidence,
	assignedAt time.Time,
) ([]contract.OrganizerAssignment, AuditFact, error) {
	if err := RequirePrimaryOrganizer(assignments, actorPersonaID); err != nil {
		return nil, AuditFact{}, err
	}
	if err := validatePrimaryOrganizerInvariant(assignments); err != nil {
		return nil, AuditFact{}, err
	}
	coHostPersonaID = strings.TrimSpace(coHostPersonaID)
	if coHostPersonaID == "" || assignedAt.IsZero() ||
		evidence.OrganizerPersonaID != coHostPersonaID ||
		evidence.Action != HostAuthorityAssignOrganizer ||
		!validMutationAuthorityEvidence(evidence, assignedAt) {
		return nil, AuditFact{}, fmt.Errorf("%w: invalid co-host authority evidence", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	next := cloneOrganizerAssignments(assignments)
	for index := range next {
		if next[index].PersonaID != coHostPersonaID {
			continue
		}
		if next[index].RevokedAt.IsZero() {
			if next[index].Role == contract.GatheringOrganizerRolePrimaryOrganizer {
				return nil, AuditFact{}, fmt.Errorf("%w: primary organizer cannot be reassigned as co-host", gatheringerrors.ErrGatheringTransitionForbidden)
			}
			if next[index].AuthorityEvidenceRef == evidence.AuthorityEvidenceRef &&
				next[index].AuthorityVersion == evidence.AuthorityVersion {
				return next, authorityAuditFactFromEvidence("AssignGatheringCoHost", actorPersonaID, evidence, assignedAt), nil
			}
		}
		next[index] = contract.OrganizerAssignment{
			PersonaID:            coHostPersonaID,
			Role:                 contract.GatheringOrganizerRoleCoHost,
			AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
			AuthorityVersion:     evidence.AuthorityVersion,
			AssignedAt:           assignedAt.UTC(),
			Version:              next[index].Version + 1,
		}
		if err := validatePrimaryOrganizerInvariant(next); err != nil {
			return nil, AuditFact{}, err
		}
		return next, authorityAuditFactFromEvidence("AssignGatheringCoHost", actorPersonaID, evidence, assignedAt), nil
	}
	next = append(next, contract.OrganizerAssignment{
		PersonaID:            coHostPersonaID,
		Role:                 contract.GatheringOrganizerRoleCoHost,
		AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
		AuthorityVersion:     evidence.AuthorityVersion,
		AssignedAt:           assignedAt.UTC(),
		Version:              1,
	})
	if err := validatePrimaryOrganizerInvariant(next); err != nil {
		return nil, AuditFact{}, err
	}
	return next, authorityAuditFactFromEvidence("AssignGatheringCoHost", actorPersonaID, evidence, assignedAt), nil
}

func RevokeCoHost(
	assignments []contract.OrganizerAssignment,
	actorPersonaID string,
	coHostPersonaID string,
	revokedAt time.Time,
) ([]contract.OrganizerAssignment, AuditFact, error) {
	if err := RequirePrimaryOrganizer(assignments, actorPersonaID); err != nil {
		return nil, AuditFact{}, err
	}
	if err := validatePrimaryOrganizerInvariant(assignments); err != nil {
		return nil, AuditFact{}, err
	}
	coHostPersonaID = strings.TrimSpace(coHostPersonaID)
	if coHostPersonaID == "" || revokedAt.IsZero() {
		return nil, AuditFact{}, fmt.Errorf("%w: invalid co-host revocation", gatheringerrors.ErrGatheringTransitionForbidden)
	}
	next := cloneOrganizerAssignments(assignments)
	for index := range next {
		if next[index].PersonaID != coHostPersonaID || !next[index].RevokedAt.IsZero() {
			continue
		}
		if next[index].Role != contract.GatheringOrganizerRoleCoHost {
			return nil, AuditFact{}, fmt.Errorf("%w: primary organizer cannot be revoked as co-host", gatheringerrors.ErrGatheringOrganizerTransferRequired)
		}
		next[index].RevokedAt = revokedAt.UTC()
		next[index].Version++
		if err := validatePrimaryOrganizerInvariant(next); err != nil {
			return nil, AuditFact{}, err
		}
		return next, AuditFact{
			Operation:            "RevokeGatheringCoHost",
			ActorPersonaID:       strings.TrimSpace(actorPersonaID),
			ParticipantPersonaID: coHostPersonaID,
			OccurredAt:           revokedAt.UTC(),
		}, nil
	}
	return nil, AuditFact{}, fmt.Errorf("%w: active co-host assignment not found", gatheringerrors.ErrGatheringTransitionForbidden)
}

// TransferPrimaryOrganizer computes both assignment changes before returning.
// Callers persist the returned slice with the material Revision in one
// aggregate mutation, so there is never a committed state without a primary.
func TransferPrimaryOrganizer(
	assignments []contract.OrganizerAssignment,
	actorPersonaID string,
	newPrimaryPersonaID string,
	evidence HostAuthorityEvidence,
	transferredAt time.Time,
) ([]contract.OrganizerAssignment, AuditFact, error) {
	if err := RequirePrimaryOrganizer(assignments, actorPersonaID); err != nil {
		return nil, AuditFact{}, err
	}
	if err := validatePrimaryOrganizerInvariant(assignments); err != nil {
		return nil, AuditFact{}, err
	}
	newPrimaryPersonaID = strings.TrimSpace(newPrimaryPersonaID)
	if newPrimaryPersonaID == "" || transferredAt.IsZero() ||
		evidence.OrganizerPersonaID != newPrimaryPersonaID ||
		evidence.Action != HostAuthorityTransferOrganizer ||
		!validMutationAuthorityEvidence(evidence, transferredAt) {
		return nil, AuditFact{}, fmt.Errorf("%w: invalid organizer transfer evidence", gatheringerrors.ErrGatheringHostAuthorityInvalid)
	}
	if newPrimaryPersonaID == strings.TrimSpace(actorPersonaID) {
		return nil, AuditFact{}, fmt.Errorf("%w: new primary organizer must differ from current primary", gatheringerrors.ErrGatheringOrganizerTransferRequired)
	}

	next := cloneOrganizerAssignments(assignments)
	oldPrimary := -1
	newPrimary := -1
	for index := range next {
		if next[index].PersonaID == strings.TrimSpace(actorPersonaID) &&
			next[index].Role == contract.GatheringOrganizerRolePrimaryOrganizer &&
			next[index].RevokedAt.IsZero() {
			oldPrimary = index
		}
		if next[index].PersonaID == newPrimaryPersonaID {
			newPrimary = index
		}
	}
	if oldPrimary < 0 {
		return nil, AuditFact{}, fmt.Errorf("%w: active primary organizer missing", gatheringerrors.ErrGatheringOrganizerTransferRequired)
	}
	next[oldPrimary].Role = contract.GatheringOrganizerRoleCoHost
	next[oldPrimary].Version++
	if newPrimary >= 0 {
		next[newPrimary] = contract.OrganizerAssignment{
			PersonaID:            newPrimaryPersonaID,
			Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
			AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
			AuthorityVersion:     evidence.AuthorityVersion,
			AssignedAt:           transferredAt.UTC(),
			Version:              next[newPrimary].Version + 1,
		}
	} else {
		next = append(next, contract.OrganizerAssignment{
			PersonaID:            newPrimaryPersonaID,
			Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
			AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
			AuthorityVersion:     evidence.AuthorityVersion,
			AssignedAt:           transferredAt.UTC(),
			Version:              1,
		})
	}
	if err := validatePrimaryOrganizerInvariant(next); err != nil {
		return nil, AuditFact{}, err
	}
	return next, authorityAuditFactFromEvidence("TransferGatheringOrganizer", actorPersonaID, evidence, transferredAt), nil
}

func validatePrimaryOrganizerInvariant(assignments []contract.OrganizerAssignment) error {
	activePrimaries := 0
	for _, assignment := range assignments {
		if assignment.RevokedAt.IsZero() &&
			assignment.Role == contract.GatheringOrganizerRolePrimaryOrganizer {
			activePrimaries++
		}
	}
	if activePrimaries != 1 {
		return fmt.Errorf("%w: exactly one active primary organizer is required", gatheringerrors.ErrGatheringOrganizerTransferRequired)
	}
	return nil
}

func normalizeHostBindingAuthority(value contract.HostBinding) contract.HostBinding {
	value.HostSubjectID = strings.TrimSpace(value.HostSubjectID)
	value.AuthorityEvidenceRef = strings.TrimSpace(value.AuthorityEvidenceRef)
	value.AuthorityExpiresAt = hostOutcomeUTCOrZero(value.AuthorityExpiresAt)
	return value
}

func hostAuthorityReference(
	kind contract.GatheringHostSubjectKind,
	subjectID string,
) string {
	return strings.TrimSpace(string(kind)) + ":" + strings.TrimSpace(subjectID)
}

func validHostBinding(value contract.HostBinding) bool {
	switch value.HostSubjectKind {
	case contract.GatheringHostSubjectKindPersona,
		contract.GatheringHostSubjectKindEntityHomepage,
		contract.GatheringHostSubjectKindCircle:
	default:
		return false
	}
	return value.HostSubjectID != "" && value.AuthorityEvidenceRef != "" && value.AuthorityVersion > 0
}

func validMutationAuthorityEvidence(value HostAuthorityEvidence, evaluatedAt time.Time) bool {
	value = normalizeHostAuthorityEvidence(value)
	if !value.Valid || value.Revoked || value.HostSubjectID == "" ||
		value.HostReference == "" ||
		value.ActorPersonaID == "" || value.OrganizerPersonaID == "" ||
		value.AuthorityEvidenceRef == "" || value.AuthorityVersion <= 0 ||
		value.AuthorityDigest == "" {
		return false
	}
	switch value.HostSubjectKind {
	case contract.GatheringHostSubjectKindPersona,
		contract.GatheringHostSubjectKindEntityHomepage,
		contract.GatheringHostSubjectKindCircle:
	default:
		return false
	}
	return value.ExpiresAt.IsZero() || evaluatedAt.Before(value.ExpiresAt)
}

func normalizeHostAuthorityQuery(value HostAuthorityQuery) HostAuthorityQuery {
	value.HostSubjectID = strings.TrimSpace(value.HostSubjectID)
	value.ActorPersonaID = strings.TrimSpace(value.ActorPersonaID)
	value.OrganizerPersonaID = strings.TrimSpace(value.OrganizerPersonaID)
	value.AuthorityEvidenceRef = strings.TrimSpace(value.AuthorityEvidenceRef)
	value.EvaluatedAt = hostOutcomeUTCOrZero(value.EvaluatedAt)
	return value
}

func normalizeHostAuthorityEvidence(value HostAuthorityEvidence) HostAuthorityEvidence {
	value.HostSubjectID = strings.TrimSpace(value.HostSubjectID)
	value.ActorPersonaID = strings.TrimSpace(value.ActorPersonaID)
	value.OrganizerPersonaID = strings.TrimSpace(value.OrganizerPersonaID)
	value.AuthorityEvidenceRef = strings.TrimSpace(value.AuthorityEvidenceRef)
	value.AuthorityDigest = strings.TrimSpace(value.AuthorityDigest)
	value.ExpiresAt = hostOutcomeUTCOrZero(value.ExpiresAt)
	return value
}

func cloneOrganizerAssignments(value []contract.OrganizerAssignment) []contract.OrganizerAssignment {
	return append([]contract.OrganizerAssignment(nil), value...)
}

func hostOutcomeUTCOrZero(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC()
}

func authorityAuditFact(operation string, query HostAuthorityQuery, occurredAt time.Time) AuditFact {
	return AuditFact{
		Operation:            operation,
		ActorPersonaID:       query.ActorPersonaID,
		ParticipantPersonaID: query.OrganizerPersonaID,
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        query.HostSubjectID,
		AuthorityEvidenceRef: query.AuthorityEvidenceRef,
		AuthorityVersion:     query.AuthorityVersion,
		OccurredAt:           occurredAt.UTC(),
	}
}

func authorityAuditFactFromEvidence(
	operation string,
	actorPersonaID string,
	evidence HostAuthorityEvidence,
	occurredAt time.Time,
) AuditFact {
	return AuditFact{
		Operation:            operation,
		ActorPersonaID:       strings.TrimSpace(actorPersonaID),
		ParticipantPersonaID: evidence.OrganizerPersonaID,
		HostSubjectKind:      evidence.HostSubjectKind,
		HostSubjectID:        evidence.HostSubjectID,
		AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
		AuthorityVersion:     evidence.AuthorityVersion,
		OccurredAt:           occurredAt.UTC(),
	}
}
