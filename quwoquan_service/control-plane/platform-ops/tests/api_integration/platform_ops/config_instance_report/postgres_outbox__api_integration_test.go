package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	reporthttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/adapters/inbound/http"
	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	reportstore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/persistence"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/pgoutbox"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
)

func TestConfigInstanceReportRealPostgresAtomicOutbox(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	fixture, err := testinfra.StartPostgresFixture(t.TempDir()+"/postgres", 0)
	if err != nil {
		t.Fatalf("start embedded PostgreSQL: %v", err)
	}
	t.Cleanup(func() { _ = fixture.Close() })
	pool, err := pgxpool.New(ctx, fixture.DSN())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	store, err := controlplanepersistence.NewPostgresStore(pool, "platform-ops")
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	stateStore, err := reportstore.NewStateStore(store, store)
	if err != nil {
		t.Fatal(err)
	}
	desired := reportapp.DesiredHashReaderFunc(func(
		context.Context,
		string,
		string,
	) (string, error) {
		return "desired-real-postgres", nil
	})
	const candidate = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	handler, err := reporthttp.NewHandler(
		reportapp.NewCommandFacade(stateStore, desired, nil),
		reportapp.NewQueryFacade(stateStore),
		candidate,
	)
	if err != nil {
		t.Fatal(err)
	}
	body := `{"environment":"gamma","cluster":"gamma-control-a","service":"content-service","releaseManifestDigest":"` + candidate + `","effectiveHash":"desired-real-postgres","source":"release-package"}`
	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/control-plane/platform/configs/instances/content-service-gamma-control-a-0:report",
			bytes.NewBufferString(body),
		)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "service:content-service@gamma"},
		}))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("attempt=%d status=%d body=%s", attempt, response.Code, response.Body.String())
		}
	}
	var documents, workflows, audits, receipts, outbox int
	queries := []struct {
		query string
		value *int
	}{
		{`SELECT COUNT(*) FROM control_plane_documents WHERE scope='platform-ops' AND namespace='config_instance_reports'`, &documents},
		{`SELECT COUNT(*) FROM control_plane_workflows WHERE scope='platform-ops' AND object_type='config_instance_report'`, &workflows},
		{`SELECT COUNT(*) FROM control_plane_audits WHERE scope='platform-ops' AND object_type='config_instance_report'`, &audits},
		{`SELECT COUNT(*) FROM control_plane_mutation_receipts WHERE scope='platform-ops' AND object_type='config_instance_report'`, &receipts},
		{`SELECT COUNT(*) FROM platform_control_plane_outbox WHERE event_type='ConfigInstanceReported'`, &outbox},
	}
	for _, query := range queries {
		if err := pool.QueryRow(ctx, query.query).Scan(query.value); err != nil {
			t.Fatal(err)
		}
	}
	if documents != 1 || workflows != 1 || audits != 1 || receipts != 1 || outbox != 1 {
		t.Fatalf(
			"atomic packet documents=%d workflows=%d audits=%d receipts=%d outbox=%d",
			documents, workflows, audits, receipts, outbox,
		)
	}
	publisher := &capturingPublisher{}
	dispatcher, err := pgoutbox.NewDispatcher(pool, publisher, "platform_control_plane_outbox")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := dispatcher.DispatchOnce(ctx); err != nil {
		t.Fatal(err)
	}
	if publisher.Count() != 1 {
		t.Fatalf("published events=%d", publisher.Count())
	}
}

type capturingPublisher struct {
	mu     sync.Mutex
	events []runtimemessaging.DomainEvent
}

func (publisher *capturingPublisher) Publish(
	_ context.Context,
	event runtimemessaging.DomainEvent,
) error {
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	publisher.events = append(publisher.events, event)
	return nil
}

func (publisher *capturingPublisher) Count() int {
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	return len(publisher.events)
}
