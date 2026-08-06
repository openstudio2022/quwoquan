// Package hostauthority provides the owner-neutral typed evidence envelope.
// Each canonical owner remains solely responsible for its role and lifecycle
// decision; this package only normalizes action semantics and evidence hashing.
package hostauthority

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"time"
)

const DefaultEvidenceTTL = 5 * time.Minute

type Query struct {
	HostSubjectKind      string
	HostSubjectID        string
	HostSubjectRef       string
	ActorPersonaID       string
	OrganizerPersonaID   string
	AuthorityEvidenceRef string
	AuthorityVersion     int64
	Action               string
}

type OwnerDecision struct {
	HostSubjectKind      string
	HostSubjectID        string
	HostSubjectRef       string
	AuthorityEvidenceRef string
	AuthorityVersion     int64
	Authorized           bool
	Revoked              bool
}

type Evidence struct {
	HostSubjectKind      string
	HostSubjectID        string
	HostSubjectRef       string
	ActorPersonaID       string
	OrganizerPersonaID   string
	AuthorityEvidenceRef string
	AuthorityVersion     int64
	AuthorityDigest      string
	ExpiresAt            time.Time
	Action               string
	Valid                bool
	Revoked              bool
}

func Issue(query Query, decision OwnerDecision, now time.Time) Evidence {
	query = normalizeQuery(query)
	decision = normalizeDecision(decision)
	now = now.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	expiresAt := now.Add(DefaultEvidenceTTL)
	valid := query.HostSubjectKind != "" &&
		query.HostSubjectID != "" &&
		query.HostSubjectRef != "" &&
		query.ActorPersonaID != "" &&
		query.OrganizerPersonaID != "" &&
		query.AuthorityEvidenceRef != "" &&
		query.AuthorityVersion > 0 &&
		validActionOrganizer(query) &&
		decision.Authorized &&
		!decision.Revoked &&
		query.HostSubjectKind == decision.HostSubjectKind &&
		query.HostSubjectID == decision.HostSubjectID &&
		query.HostSubjectRef == decision.HostSubjectRef &&
		query.AuthorityEvidenceRef == decision.AuthorityEvidenceRef &&
		query.AuthorityVersion == decision.AuthorityVersion
	evidence := Evidence{
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        query.HostSubjectID,
		HostSubjectRef:       query.HostSubjectRef,
		ActorPersonaID:       query.ActorPersonaID,
		OrganizerPersonaID:   query.OrganizerPersonaID,
		AuthorityEvidenceRef: query.AuthorityEvidenceRef,
		AuthorityVersion:     query.AuthorityVersion,
		ExpiresAt:            expiresAt,
		Action:               query.Action,
		Valid:                valid,
		Revoked:              decision.Revoked,
	}
	evidence.AuthorityDigest = digest(evidence, decision)
	return evidence
}

func validActionOrganizer(query Query) bool {
	switch query.Action {
	case "create_draft", "publish":
		return query.ActorPersonaID == query.OrganizerPersonaID
	case "assign_organizer", "transfer_organizer":
		return query.OrganizerPersonaID != ""
	default:
		return false
	}
}

func normalizeQuery(query Query) Query {
	query.HostSubjectKind = strings.TrimSpace(query.HostSubjectKind)
	query.HostSubjectID = strings.TrimSpace(query.HostSubjectID)
	query.HostSubjectRef = strings.TrimSpace(query.HostSubjectRef)
	query.ActorPersonaID = strings.TrimSpace(query.ActorPersonaID)
	query.OrganizerPersonaID = strings.TrimSpace(query.OrganizerPersonaID)
	query.AuthorityEvidenceRef = strings.TrimSpace(query.AuthorityEvidenceRef)
	query.Action = strings.TrimSpace(query.Action)
	return query
}

func normalizeDecision(decision OwnerDecision) OwnerDecision {
	decision.HostSubjectKind = strings.TrimSpace(decision.HostSubjectKind)
	decision.HostSubjectID = strings.TrimSpace(decision.HostSubjectID)
	decision.HostSubjectRef = strings.TrimSpace(decision.HostSubjectRef)
	decision.AuthorityEvidenceRef = strings.TrimSpace(decision.AuthorityEvidenceRef)
	return decision
}

func digest(evidence Evidence, decision OwnerDecision) string {
	payload, _ := json.Marshal(struct {
		Evidence Evidence
		Decision OwnerDecision
	}{Evidence: evidence, Decision: decision})
	sum := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(sum[:])
}
