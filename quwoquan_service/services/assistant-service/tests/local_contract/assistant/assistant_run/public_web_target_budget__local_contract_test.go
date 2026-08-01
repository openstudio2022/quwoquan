package assistant_run_test

import (
	"context"
	"errors"
	"testing"

	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
)

type referenceLookupStub struct{}

func (referenceLookupStub) LookupSource(
	_ context.Context,
	runID string,
	sourceID string,
) (publicweb.StoredSource, error) {
	if runID != "run_1" || sourceID != "src_1" {
		return publicweb.StoredSource{}, errors.New("not owned by run")
	}
	return publicweb.StoredSource{
		SourceID:      sourceID,
		NormalizedURL: "https://source.example.org/article",
	}, nil
}

func (referenceLookupStub) LookupDocumentLink(
	_ context.Context,
	runID string,
	linkID string,
) (publicweb.StoredDocumentLink, error) {
	if runID != "run_1" || linkID != "link_1" {
		return publicweb.StoredDocumentLink{}, errors.New("not owned by run")
	}
	return publicweb.StoredDocumentLink{
		LinkID:         linkID,
		URL:            "https://child.example.org/detail",
		ParentSourceID: "src_parent",
	}, nil
}

func TestLedgerTargetResolverNeverTrustsModelSuppliedLineage(t *testing.T) {
	resolver := publicweb.NewLedgerTargetResolver(referenceLookupStub{})
	tests := []struct {
		name       string
		target     publicweb.Target
		wantURL    string
		wantOrigin string
		wantParent string
	}{
		{
			name:       "direct url",
			target:     publicweb.Target{Kind: publicweb.TargetURL, Value: "https://direct.example.org"},
			wantURL:    "https://direct.example.org",
			wantOrigin: "url",
		},
		{
			name:       "source identifier",
			target:     publicweb.Target{Kind: publicweb.TargetSource, Value: "src_1"},
			wantURL:    "https://source.example.org/article",
			wantOrigin: "source",
			wantParent: "src_1",
		},
		{
			name:       "document link identifier",
			target:     publicweb.Target{Kind: publicweb.TargetDocumentLink, Value: "link_1"},
			wantURL:    "https://child.example.org/detail",
			wantOrigin: "document_link",
			wantParent: "src_parent",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			resolved, err := resolver.ResolveTarget(context.Background(), "run_1", test.target)
			if err != nil {
				t.Fatalf("ResolveTarget() error = %v", err)
			}
			if resolved.URL != test.wantURL || resolved.Origin != test.wantOrigin || resolved.ParentSourceID != test.wantParent {
				t.Fatalf("resolved = %#v", resolved)
			}
		})
	}
	if _, err := resolver.ResolveTarget(
		context.Background(),
		"run_1",
		publicweb.Target{Kind: publicweb.TargetDocumentLink, Value: "https://forged.example.org"},
	); err == nil {
		t.Fatal("forged document link identifier was accepted")
	}
}

func TestRunBudgetGateAccountsConcurrentReservationsAndCommittedBytes(t *testing.T) {
	gate := publicweb.NewRunBudgetGate(publicweb.RunBudgetLimits{
		MaxPages: 2,
		MaxBytes: 10,
	})
	first, err := gate.ReserveFetch(context.Background(), "run_1", 8)
	if err != nil {
		t.Fatalf("first ReserveFetch() error = %v", err)
	}
	second, err := gate.ReserveFetch(context.Background(), "run_1", 8)
	if err != nil {
		t.Fatalf("second ReserveFetch() error = %v", err)
	}
	if second.AllowedBytes() != 2 {
		t.Fatalf("second AllowedBytes() = %d, want 2", second.AllowedBytes())
	}
	if _, err := gate.ReserveFetch(context.Background(), "run_1", 1); !errors.Is(err, publicweb.ErrBudgetExhausted) {
		t.Fatalf("third ReserveFetch() error = %v", err)
	}
	if err := first.Commit(4); err != nil {
		t.Fatalf("first Commit() error = %v", err)
	}
	second.Release()
	snapshot := gate.Snapshot("run_1")
	if snapshot.UsedPages != 1 || snapshot.UsedBytes != 4 || snapshot.ReservedPage != 0 || snapshot.ReservedByte != 0 {
		t.Fatalf("snapshot = %#v", snapshot)
	}
	third, err := gate.ReserveFetch(context.Background(), "run_1", 9)
	if err != nil {
		t.Fatalf("third ReserveFetch() after release error = %v", err)
	}
	if third.AllowedBytes() != 6 {
		t.Fatalf("third AllowedBytes() = %d, want 6", third.AllowedBytes())
	}
	if err := third.Commit(7); !errors.Is(err, publicweb.ErrBudgetExhausted) {
		t.Fatalf("oversized Commit() error = %v", err)
	}
	third.Release()
}
