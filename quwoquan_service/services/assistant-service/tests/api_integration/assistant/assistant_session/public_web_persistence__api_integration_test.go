// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
package api_integration

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	publicwebpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
)

type integrationPublicWebResolver struct {
	url string
}

func (r integrationPublicWebResolver) ResolveTarget(
	_ context.Context,
	_ string,
	target publicweb.Target,
) (publicweb.ResolvedTarget, error) {
	return publicweb.ResolvedTarget{URL: r.url, Origin: string(target.Kind)}, nil
}

type integrationPublicWebFetcher struct {
	body []byte
}

func (f integrationPublicWebFetcher) Fetch(
	_ context.Context,
	request publicweb.NetworkRequest,
) (publicweb.NetworkResult, error) {
	return publicweb.NetworkResult{
		FinalURL:      request.URL,
		RedirectChain: []string{},
		ContentType:   "text/html; charset=utf-8",
		Body:          append([]byte{}, f.body...),
		FetchedAt:     time.Date(2026, 7, 31, 2, 3, 4, 0, time.UTC),
	}, nil
}

func TestPublicWebEvidenceAndBudgetSurviveWorkerRestart(t *testing.T) {
	ctx := t.Context()
	evidence := publicwebpersistence.NewMongoEvidenceStore(integrationMongoDB)
	budget := publicwebpersistence.NewMongoRunBudgetGate(
		integrationMongoDB,
		publicweb.RunBudgetLimits{MaxPages: 1, MaxBytes: 1 << 20},
	)
	if err := evidence.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	if err := budget.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	body := []byte(`<html><head><title>Canonical source</title></head><body>` +
		`<main>durable fact</main><a href="https://example.org/next">Next</a>` +
		`</body></html>`)
	service := publicweb.NewService(
		integrationPublicWebResolver{url: "https://example.org/root"},
		integrationPublicWebFetcher{body: body},
		evidence,
		budget,
		publicweb.DefaultDocumentParser(),
	)
	document, err := service.Open(ctx, publicweb.OpenRequest{
		RunID:   "run_public_web_restart",
		SkillID: "knowledge_general",
		Target: publicweb.Target{
			Kind: publicweb.TargetURL, Value: "https://example.org/root",
		},
		Method: "GET",
	})
	if err != nil {
		t.Fatalf("open public web evidence: %v", err)
	}
	if len(document.Links) != 1 || document.ArtifactRef == "" {
		t.Fatalf("document lost link or artifact lineage: %+v", document)
	}

	// Recreate both adapters to model a Worker/process restart. No in-memory
	// state is reused below.
	restartedEvidence := publicwebpersistence.NewMongoEvidenceStore(integrationMongoDB)
	restartedBudget := publicwebpersistence.NewMongoRunBudgetGate(
		integrationMongoDB,
		publicweb.RunBudgetLimits{MaxPages: 1, MaxBytes: 1 << 20},
	)
	stored, err := restartedEvidence.ReadDocument(
		ctx,
		"run_public_web_restart",
		document.DocumentID,
	)
	if err != nil || stored.ContentDigest != document.ContentDigest ||
		stored.Source.SourceID != document.Source.SourceID {
		t.Fatalf("restarted evidence read=%+v err=%v", stored, err)
	}
	link, err := restartedEvidence.LookupDocumentLink(
		ctx,
		"run_public_web_restart",
		document.Links[0].LinkID,
	)
	if err != nil || link.ParentSourceID != document.Source.SourceID ||
		link.URL != "https://example.org/next" {
		t.Fatalf("restarted link lookup=%+v err=%v", link, err)
	}
	if _, err := restartedEvidence.LookupSource(
		ctx,
		"run_other",
		document.Source.SourceID,
	); !errors.Is(err, publicweb.ErrTargetUnavailable) {
		t.Fatalf("cross-run source lookup must fail closed, got %v", err)
	}
	if _, err := restartedEvidence.ReadDocument(
		ctx,
		"run_other",
		document.DocumentID,
	); !errors.Is(err, publicweb.ErrTargetUnavailable) {
		t.Fatalf("cross-run document read must fail closed, got %v", err)
	}
	if _, err := restartedBudget.ReserveFetch(
		ctx,
		"run_public_web_restart",
		1024,
	); !errors.Is(err, publicweb.ErrBudgetExhausted) {
		t.Fatalf("restarted budget must retain used page, got %v", err)
	}

	var artifact struct {
		Artifact struct {
			Body []byte `bson:"body"`
		} `bson:"artifact"`
	}
	if err := integrationMongoDB.Collection("assistant_run_web_evidence").
		FindOne(ctx, bson.M{
			"runId":                "run_public_web_restart",
			"recordKind":           "artifact",
			"artifact.artifactRef": document.ArtifactRef,
		}).Decode(&artifact); err != nil {
		t.Fatalf("read raw artifact: %v", err)
	}
	if string(artifact.Artifact.Body) != string(body) {
		t.Fatalf("raw artifact mismatch: got=%d want=%d", len(artifact.Artifact.Body), len(body))
	}
}

func TestPublicWebSearchSourceLineageAndConcurrentBudgetCAS(t *testing.T) {
	ctx := t.Context()
	evidence := publicwebpersistence.NewMongoEvidenceStore(integrationMongoDB)
	discovered, err := evidence.RecordSearchReferences(
		ctx,
		"run_public_web_search_lineage",
		[]publicweb.SearchReference{{
			Title: "Result", URL: "https://example.net/article#section", Source: "example.net",
		}},
	)
	if err != nil || len(discovered) != 1 {
		t.Fatalf("record search source=%+v err=%v", discovered, err)
	}
	resolver := publicweb.NewLedgerTargetResolver(evidence)
	resolved, err := resolver.ResolveTarget(
		ctx,
		"run_public_web_search_lineage",
		publicweb.Target{Kind: publicweb.TargetSource, Value: discovered[0].SourceID},
	)
	if err != nil || resolved.URL != "https://example.net/article" ||
		resolved.ParentSourceID != discovered[0].SourceID || resolved.Origin != "source" {
		t.Fatalf("resolved search source=%+v err=%v", resolved, err)
	}

	gate := publicwebpersistence.NewMongoRunBudgetGate(
		integrationMongoDB,
		publicweb.RunBudgetLimits{MaxPages: 1, MaxBytes: 4096},
	)
	const contenders = 12
	var successful atomic.Int32
	start := make(chan struct{})
	var group sync.WaitGroup
	for index := 0; index < contenders; index++ {
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			reservation, reserveErr := gate.ReserveFetch(
				ctx,
				"run_public_web_budget_cas",
				512,
			)
			if reserveErr != nil {
				if !errors.Is(reserveErr, publicweb.ErrBudgetExhausted) {
					t.Errorf("unexpected reserve error: %v", reserveErr)
				}
				return
			}
			successful.Add(1)
			if commitErr := reservation.Commit(128); commitErr != nil {
				t.Errorf("commit reservation: %v", commitErr)
			}
		}()
	}
	close(start)
	group.Wait()
	if successful.Load() != 1 {
		t.Fatalf("CAS admitted %d contenders; want exactly one", successful.Load())
	}
}
