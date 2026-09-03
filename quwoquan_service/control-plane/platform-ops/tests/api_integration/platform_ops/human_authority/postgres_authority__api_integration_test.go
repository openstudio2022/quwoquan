// spec_ref:
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-001.t1
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-001.t3
package api_integration

import (
	"context"
	"crypto/ed25519"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	authorityapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/application"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	authoritystore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/infrastructure/persistence"
	"quwoquan_service/internal/platform/testinfra"
)

func TestPostgresAppendOnlyAtomicReceiptAndCAS(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	fixture, err := testinfra.StartPostgresFixture(t.TempDir()+"/postgres", 0)
	if err != nil {
		t.Fatalf("PostgreSQL prerequisite unavailable: %v", err)
	}
	t.Cleanup(func() { _ = fixture.Close() })
	pool, err := pgxpool.New(ctx, fixture.DSN())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	store, err := authoritystore.NewPostgresStore(pool)
	if err != nil {
		t.Fatal(err)
	}
	if err = store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	_, priv, _ := ed25519.GenerateKey(nil)
	signer, _ := authorityapp.NewEd25519Signer("integration-test", priv, true)
	facade, _ := authorityapp.NewFacade(store, signer, nil)
	now := time.Date(2026, 8, 30, 2, 0, 0, 0, time.UTC)
	ids := 0
	facade.WithClock(func() time.Time { return now }).WithIDs(func() string { ids++; return time.Unix(int64(ids), 0).UTC().Format("150405.000000000") })
	unit := model.DecisionUnit{ID: "pg-unit", Stage: "integration_trusted_ci", DecisionKind: "integration_acceptance", RequiredRoles: []string{"engineering_delivery_owner"}, Scope: model.CanonicalScope{"increment": "increment-1"}, Target: "trusted-ci", Fingerprint: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Actions: []string{"integrate"}, Options: []model.DecisionOption{{OptionID: "approve", NeutralLabel: "Approve integration", UserOutcome: "Trusted integration proceeds", BusinessOutcome: "Candidate remains promotable", Cost: "Existing CI budget", TimeToEffect: "Immediate", Risk: "Bound to immutable candidate", Reversibility: "Stop before promotion", ScopeChange: "No scope change", NextStep: "Integrate candidate"}}, EvidenceExpiresAt: now.Add(time.Hour)}
	unit, err = facade.Create(ctx, authorityapp.Actor{ID: "creator"}, unit)
	if err != nil {
		t.Fatal(err)
	}
	for round := 1; round <= 2; round++ {
		request := authorityapp.SubmitRequest{Round: round, Facts: []string{"candidate checks passed"}, Impacts: []string{"integration may proceed"}}
		if round == 2 {
			request.SelectedOptionID = "approve"
		}
		unit, err = facade.Submit(ctx, authorityapp.Actor{ID: "engineer", Roles: []string{"engineering_delivery_owner"}, MFAProvenance: "verified"}, unit.ID, request)
		if err != nil {
			t.Fatal(err)
		}
		unit, err = facade.Seal(ctx, authorityapp.Actor{ID: "engineer"}, unit.ID, round)
		if err != nil {
			t.Fatal(err)
		}
	}
	unit, err = facade.Finalize(ctx, authorityapp.Actor{ID: "engineer", Roles: []string{"engineering_delivery_owner"}, MFAProvenance: "verified"}, unit.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
	if err != nil {
		t.Fatal(err)
	}
	events, err := store.Events(ctx, unit.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = model.VerifyHashChain(events); err != nil {
		t.Fatal(err)
	}
	var units, eventCount, receipts, audits, outbox int
	for _, query := range []struct {
		sql    string
		target *int
	}{{`SELECT COUNT(*) FROM human_authority_units`, &units}, {`SELECT COUNT(*) FROM human_authority_events`, &eventCount}, {`SELECT COUNT(*) FROM human_authority_receipts`, &receipts}, {`SELECT COUNT(*) FROM human_authority_audits`, &audits}, {`SELECT COUNT(*) FROM human_authority_outbox`, &outbox}} {
		if err = pool.QueryRow(ctx, query.sql).Scan(query.target); err != nil {
			t.Fatal(err)
		}
	}
	if units != 1 || receipts != 1 || eventCount != 6 || audits != 6 || outbox != 6 {
		t.Fatalf("atomic counts units=%d events=%d receipts=%d audits=%d outbox=%d", units, eventCount, receipts, audits, outbox)
	}
	input := authorityapp.TransitionInput{Fingerprint: unit.Fingerprint, Scope: unit.Scope, Action: "integrate", CommandDigest: model.Digest([]byte("command"))}
	var wg sync.WaitGroup
	errs := make(chan error, 2)
	wg.Add(2)
	go func() {
		defer wg.Done()
		_, e := facade.Consume(ctx, authorityapp.Actor{ID: "consumer"}, unit.Decision.ID, unit.Receipt.ETag, "consume-1", input)
		errs <- e
	}()
	go func() {
		defer wg.Done()
		_, e := facade.Revoke(ctx, authorityapp.Actor{ID: "revoker"}, unit.Decision.ID, unit.Receipt.ETag, "revoke-1", "stop")
		errs <- e
	}()
	wg.Wait()
	close(errs)
	success, conflict := 0, 0
	for e := range errs {
		if e == nil {
			success++
		} else if errors.Is(e, model.ErrConflict) {
			conflict++
		} else {
			t.Fatalf("race=%v", e)
		}
	}
	if success != 1 || conflict != 1 {
		t.Fatalf("winner=%d conflict=%d", success, conflict)
	}
}
