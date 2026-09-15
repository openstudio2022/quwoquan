package domain

import (
	"context"
	"errors"
	rt "quwoquan_service/runtime/search"
	"time"
)

var (
	ErrInvalid     = errors.New("invalid preparation input")
	ErrConflict    = errors.New("preparation conflict")
	ErrNotFound    = errors.New("preparation not found")
	ErrUnavailable = errors.New("preparation unavailable")
)

type Command struct {
	Binding         rt.ReleaseQueryPreparationBinding `json:"binding"`
	Snapshot        rt.SearchReleaseCandidateSnapshot `json:"snapshot"`
	ExpectedVersion int64                             `json:"expectedVersion"`
	IdempotencyKey  string                            `json:"idempotencyKey"`
}
type Query struct {
	Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
	SnapshotDigest string                            `json:"snapshotDigest"`
}
type State struct {
	PreparationID     string                            `bson:"preparationId"`
	Binding           rt.ReleaseQueryPreparationBinding `bson:"binding"`
	Snapshot          rt.SearchReleaseCandidateSnapshot `bson:"snapshot"`
	CreatorIDs        []string                          `bson:"creatorIds"`
	ObjectIDs         []string                          `bson:"objectIds"`
	Version           int64                             `bson:"version"`
	Status            string                            `bson:"status"`
	VerifiedObjectIDs []string                          `bson:"verifiedObjectIds"`
	ExecutionToken    *string                           `bson:"executionToken"`
	LeaseUntil        *time.Time                        `bson:"leaseUntil"`
	FailureCode       *string                           `bson:"failureCode"`
	Proof             *rt.ReleaseQueryReadinessProof    `bson:"proof"`
	UpdatedAt         time.Time                         `bson:"updatedAt"`
}
type View struct {
	PreparationID  string                            `json:"preparationId" bson:"preparationId"`
	Binding        rt.ReleaseQueryPreparationBinding `json:"binding" bson:"binding"`
	SnapshotDigest string                            `json:"snapshotDigest" bson:"snapshotDigest"`
	Version        int64                             `json:"version" bson:"version"`
	Status         string                            `json:"status" bson:"status"`
	FailureCode    *string                           `json:"failureCode" bson:"failureCode"`
	Proof          *rt.ReleaseQueryReadinessProof    `json:"proof" bson:"proof"`
	UpdatedAt      time.Time                         `json:"updatedAt" bson:"updatedAt"`
}

func (s State) View() View {
	return View{s.PreparationID, s.Binding, s.Snapshot.SnapshotDigest(), s.Version, s.Status, s.FailureCode, s.Proof, s.UpdatedAt}
}
func NewState(c Command, now time.Time) State {
	s := State{PreparationID: c.Binding.ID(), Binding: c.Binding, Snapshot: c.Snapshot, Version: 1, Status: "accepted", VerifiedObjectIDs: []string{}, CreatorIDs: []string{}, ObjectIDs: []string{}, UpdatedAt: now}
	for _, p := range c.Snapshot.Identities() {
		s.ObjectIDs = append(s.ObjectIDs, p.ObjectID)
	}
	if c.Snapshot.Creator != nil {
		for _, p := range c.Snapshot.Creator.Profiles {
			s.CreatorIDs = append(s.CreatorIDs, p.CreatorID)
		}
	}
	return s
}
func (s *State) Claim(expected int64, token string, now, until time.Time) error {
	if s.Version != expected || token == "" || !until.After(now) || until.Sub(now) > 30*time.Second {
		return ErrConflict
	}
	if s.Status == "completed" || s.Status == "failed" {
		return ErrConflict
	}
	if s.Status == "running" && (s.LeaseUntil == nil || s.LeaseUntil.After(now)) {
		return ErrConflict
	}
	s.Version++
	s.Status = "running"
	s.ExecutionToken = &token
	s.LeaseUntil = &until
	s.FailureCode = nil
	s.UpdatedAt = now
	return nil
}
func (s State) CanCommit(token string, now time.Time) bool {
	return s.Status == "running" && s.ExecutionToken != nil && *s.ExecutionToken == token && s.LeaseUntil != nil && s.LeaseUntil.After(now)
}
func (s *State) Finish(proof *rt.ReleaseQueryReadinessProof, failure string, now time.Time) {
	s.Version++
	s.UpdatedAt = now
	s.ExecutionToken = nil
	s.LeaseUntil = nil
	s.Proof = proof
	if proof != nil {
		s.Status = "completed"
		s.FailureCode = nil
		return
	}
	s.FailureCode = &failure
	s.Status = "blocked"
	if failure == "source_invalid" || failure == "closure_mismatch" || failure == "projection_conflict" {
		s.Status = "failed"
	}
}

type Store interface {
	Load(context.Context, string) (State, error)
	Receipt(context.Context, string, string, string) (View, bool, error)
	Create(context.Context, State) error
	Claim(context.Context, State, int64, time.Time) error
	Commit(context.Context, State, int64, string, string, string, time.Time) error
}
type Projection interface {
	Prepare(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) ([]string, error)
	Verify(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error)
}
