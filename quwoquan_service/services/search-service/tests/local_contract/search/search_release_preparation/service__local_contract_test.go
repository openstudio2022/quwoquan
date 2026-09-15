package preparation_test

import (
	"context"
	"errors"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/search-service/internal/search/search_release_preparation/application"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
// 对象级typed替身只验证状态机，不作为真实Mongo/ES证据。
type store struct {
	state      domain.State
	exists     bool
	receipts   map[string]domain.View
	digests    map[string]string
	failCommit bool
}

func (s *store) Load(context.Context, string) (domain.State, error) {
	if !s.exists {
		return domain.State{}, domain.ErrNotFound
	}
	return s.state, nil
}
func (s *store) Receipt(_ context.Context, _ string, k, d string) (domain.View, bool, error) {
	v, ok := s.receipts[k]
	if ok && s.digests[k] != d {
		return v, false, domain.ErrConflict
	}
	return v, ok, nil
}
func (s *store) Create(_ context.Context, v domain.State) error {
	if s.exists {
		return domain.ErrConflict
	}
	s.state = v
	s.exists = true
	return nil
}
func (s *store) Claim(_ context.Context, v domain.State, expected int64, now time.Time) error {
	if s.state.Version != expected {
		return domain.ErrConflict
	}
	s.state = v
	return nil
}
func (s *store) Commit(_ context.Context, v domain.State, expected int64, token, k, d string, now time.Time) error {
	if s.failCommit {
		return domain.ErrUnavailable
	}
	if s.state.Version != expected || !s.state.CanCommit(token, now) {
		return domain.ErrConflict
	}
	s.state = v
	s.receipts[k] = v.View()
	s.digests[k] = d
	return nil
}

type projection struct {
	writes int
	fail   bool
}

func (p *projection) Prepare(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) ([]string, error) {
	p.writes++
	if p.fail {
		return nil, domain.ErrUnavailable
	}
	return []string{}, nil
}
func (p *projection) Verify(_ context.Context, _ rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error) {
	if p.fail {
		return nil, domain.ErrUnavailable
	}
	rows := []rt.ReleaseQueryClassEvidence{}
	for _, class := range []string{"result", "suggest", "retrieval", "ids", "count", "facet"} {
		rows = append(rows, rt.ReleaseQueryClassEvidence{QueryClass: class, ObjectSetDigest: s.ObjectSetDigest(), DocumentsDigest: "sha256:" + strings.Repeat("d", 64)})
	}
	return rows, nil
}
func TestPreparationDurableRecoveryAndReplay(t *testing.T) {
	now := time.Date(2026, 9, 12, 0, 0, 0, 0, time.UTC)
	generation := "sha256:" + strings.Repeat("b", 64)
	release := rt.ReleaseCandidateBinding{"gamma", "qwq_data", "candidate-a", "sha256:" + strings.Repeat("a", 64)}
	snapshot := rt.CreatorSearchCandidateSnapshot{Release: release, SourceClosureDigest: generation, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	if err := snapshot.Seal(); err != nil {
		t.Fatal(err)
	}
	command := domain.Command{Binding: rt.ReleaseQueryPreparationBinding{Release: release, Slice: "creator_search", SchemaGeneration: generation, ProviderBindingGeneration: generation}, Snapshot: rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &snapshot}, IdempotencyKey: "first"}
	s := &store{receipts: map[string]domain.View{}, digests: map[string]string{}, failCommit: true}
	p := &projection{}
	svc, err := app.NewService(s, p, "gamma", generation, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	if _, err = svc.Prepare(t.Context(), command, "content-service"); !errors.Is(err, domain.ErrUnavailable) {
		t.Fatal(err)
	}
	if s.state.Status != "running" || p.writes != 1 {
		t.Fatal("provider/checkpoint failure hidden")
	}
	command.ExpectedVersion = s.state.Version
	command.IdempotencyKey = "resume"
	if _, err = svc.Prepare(t.Context(), command, "content-service"); !errors.Is(err, domain.ErrConflict) {
		t.Fatal("live execution stolen", err)
	}
	now = now.Add(31 * time.Second)
	s.failCommit = false
	view, err := svc.Prepare(t.Context(), command, "content-service")
	if err != nil {
		t.Fatal(err)
	}
	if view.Status != "completed" || view.Proof == nil {
		t.Fatal(view)
	}
	if _, err = svc.Prepare(t.Context(), command, "content-service"); err != nil {
		t.Fatal(err)
	}
	if p.writes != 2 {
		t.Fatal("receipt replay wrote provider")
	}
	p.fail = true
	if _, err = svc.Read(t.Context(), domain.Query{Binding: command.Binding, SnapshotDigest: snapshot.SnapshotDigest}); err == nil {
		t.Fatal("stale proof returned")
	}
	copySource := *command.Snapshot.Creator
	command.Snapshot.Creator = &copySource
	command.Snapshot.Creator.SourceClosureDigest = "sha256:" + strings.Repeat("c", 64)
	_ = command.Snapshot.Creator.Seal()
	command.IdempotencyKey = "drift"
	if _, err = svc.Prepare(t.Context(), command, "content-service"); !errors.Is(err, domain.ErrConflict) {
		t.Fatal("different source digest accepted", err)
	}
}
func TestExpiredExecutionCannotCommit(t *testing.T) {
	now := time.Now().UTC()
	s := domain.State{Version: 1, Status: "accepted"}
	if err := s.Claim(1, "old", now, now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	if s.CanCommit("old", now.Add(time.Second)) {
		t.Fatal("expired token accepted")
	}
	if s.CanCommit("wrong", now) {
		t.Fatal("wrong token accepted")
	}
}
