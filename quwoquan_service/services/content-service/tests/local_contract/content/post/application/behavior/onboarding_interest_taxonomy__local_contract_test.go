package behavior_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/application/behavior"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

type trackingOnboardingProcessor struct {
	dedupCalls int
	hotSignals int
	seen       map[string]struct{}
}

func (p *trackingOnboardingProcessor) ProcessSignal(_ context.Context, signal rtrec.BehaviorSignal) error {
	p.hotSignals++
	return nil
}

func (p *trackingOnboardingProcessor) ProcessSignalBatch(
	_ context.Context,
	signals []rtrec.BehaviorSignal,
) error {
	p.hotSignals += len(signals)
	return nil
}

func (p *trackingOnboardingProcessor) AcceptEvent(
	_ context.Context,
	signal rtrec.BehaviorSignal,
) (bool, error) {
	p.dedupCalls++
	if p.seen == nil {
		p.seen = make(map[string]struct{})
	}
	key := signal.UserID + "|" + signal.ClientEventID
	if _, exists := p.seen[key]; exists {
		return false, nil
	}
	p.seen[key] = struct{}{}
	return true, nil
}

func (p *trackingOnboardingProcessor) HasAcceptedEvent(
	_ context.Context,
	userID, clientEventID string,
) (bool, error) {
	_, accepted := p.seen[userID+"|"+clientEventID]
	return accepted, nil
}

type trackingOnboardingEventStore struct {
	rawEvents int
}

func (s *trackingOnboardingEventStore) InsertBatch(
	_ context.Context,
	events []ports.RawBehaviorEvent,
) error {
	s.rawEvents += len(events)
	return nil
}

func (*trackingOnboardingEventStore) ListUserFootprint(
	context.Context,
	string,
	[]string,
	time.Time,
	int,
) ([]ports.RawBehaviorEvent, error) {
	return nil, nil
}

type trackingActiveLeafValidationPort struct {
	calls               int
	expectedReleaseIDs  []string
	requestedTagRefSets [][]string
	err                 error
}

func (p *trackingActiveLeafValidationPort) ValidateActiveTaxonomyLeaves(
	_ context.Context,
	expectedTaxonomyReleaseID string,
	tagRefs []string,
) error {
	p.calls++
	p.expectedReleaseIDs = append(p.expectedReleaseIDs, expectedTaxonomyReleaseID)
	p.requestedTagRefSets = append(p.requestedTagRefSets, append([]string(nil), tagRefs...))
	return p.err
}

func newOnboardingTaxonomyService(
	leafPort ActiveTaxonomyLeafValidationPort,
	processor *trackingOnboardingProcessor,
	eventStore *trackingOnboardingEventStore,
) *BehaviorService {
	return NewBehaviorService(
		processor,
		persistence.NewPostStore([]postmodel.Post{}),
		WithBehaviorEventStore(eventStore),
		WithOnboardingInterestTaxonomyValidator(CatalogBackedOnboardingInterestTaxonomy{
			Version:                  "onboarding-catalog-v1",
			TaxonomyReleaseID:        "tag-taxonomy-test-001",
			DimensionRoots:           map[string]string{"topic": "Topic", "audience": "Audience"},
			MinSelections:            1,
			MaxSelections:            4,
			DimensionMinSelections:   map[string]int{"topic": 0, "audience": 0},
			DimensionMaxSelections:   map[string]int{"topic": 2, "audience": 2},
			ActiveLeafValidationPort: leafPort,
		}),
	)
}

func validOnboardingEvent(clientEventID string) BehaviorEventInput {
	return BehaviorEventInput{
		ClientEventID:     clientEventID,
		OccurredAt:        time.Now().UTC().Format(time.RFC3339Nano),
		UserID:            "onboarding-user",
		SessionID:         "onboarding-session",
		Action:            "onboarding_interest",
		CatalogVersion:    "onboarding-catalog-v1",
		TaxonomyReleaseID: "tag-taxonomy-test-001",
		Tags:              []string{"Topic/travel"},
	}
}

func validClickEvent(clientEventID string) BehaviorEventInput {
	return BehaviorEventInput{
		ClientEventID: clientEventID,
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		UserID:        "onboarding-user",
		SessionID:     "onboarding-session",
		Action:        "click",
		ContentID:     "post-1",
	}
}

func assertOnboardingRuntimeCode(t *testing.T, err error, want string) {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error is not a runtime AppError: %T %v", err, err)
	}
	if got := appError.Code.String(); got != want {
		t.Fatalf("runtime code = %q, want %q", got, want)
	}
}

func assertNoOnboardingWrites(
	t *testing.T,
	processor *trackingOnboardingProcessor,
	eventStore *trackingOnboardingEventStore,
) {
	t.Helper()
	if processor.dedupCalls != 0 {
		t.Fatalf("taxonomy preflight must run before dedup, got %d dedup calls", processor.dedupCalls)
	}
	if processor.hotSignals != 0 {
		t.Fatalf("taxonomy rejection must not reach HotPath, got %d signals", processor.hotSignals)
	}
	if eventStore.rawEvents != 0 {
		t.Fatalf("taxonomy rejection must not write raw events, got %d", eventStore.rawEvents)
	}
}

func TestOnboardingInterestPreflightRejectsInvalidBatchWithoutWrites(t *testing.T) {
	leafPort := &trackingActiveLeafValidationPort{}
	processor := &trackingOnboardingProcessor{}
	eventStore := &trackingOnboardingEventStore{}
	service := newOnboardingTaxonomyService(leafPort, processor, eventStore)

	invalid := validOnboardingEvent("evt-onboarding-invalid-version")
	invalid.CatalogVersion = "outdated-catalog"
	err := service.ProcessBatch(context.Background(), []BehaviorEventInput{
		validClickEvent("evt-normal-before-invalid"),
		invalid,
	})
	if err == nil {
		t.Fatal("invalid onboarding catalog version must reject the complete batch")
	}
	assertOnboardingRuntimeCode(t, err, "CONTENT.USER.invalid_argument")
	if leafPort.calls != 0 {
		t.Fatalf("locally invalid batch must not call tag-service, got %d calls", leafPort.calls)
	}
	assertNoOnboardingWrites(t, processor, eventStore)
}

func TestOnboardingInterestPreflightRejectsMismatchedClientTaxonomyReleaseWithoutWrites(t *testing.T) {
	leafPort := &trackingActiveLeafValidationPort{}
	processor := &trackingOnboardingProcessor{}
	eventStore := &trackingOnboardingEventStore{}
	service := newOnboardingTaxonomyService(leafPort, processor, eventStore)

	invalid := validOnboardingEvent("evt-onboarding-stale-release")
	invalid.TaxonomyReleaseID = "tag-taxonomy-old-release"
	err := service.ProcessBatch(context.Background(), []BehaviorEventInput{invalid})
	if err == nil {
		t.Fatal("stale client taxonomy release must reject the batch")
	}
	assertOnboardingRuntimeCode(t, err, "CONTENT.USER.invalid_argument")
	if leafPort.calls != 0 {
		t.Fatalf("mismatched local release must not call tag-service, got %d calls", leafPort.calls)
	}
	assertNoOnboardingWrites(t, processor, eventStore)
}

func TestOnboardingInterestInvalidLeafRejectsBatchWithoutWrites(t *testing.T) {
	leafPort := &trackingActiveLeafValidationPort{
		err: contentgenerated.AppErrorFromInvalidArgument(
			"tag-service reported an inactive taxonomy leaf",
		),
	}
	processor := &trackingOnboardingProcessor{}
	eventStore := &trackingOnboardingEventStore{}
	service := newOnboardingTaxonomyService(leafPort, processor, eventStore)

	err := service.ProcessBatch(context.Background(), []BehaviorEventInput{
		validClickEvent("evt-normal-before-invalid-leaf"),
		validOnboardingEvent("evt-onboarding-invalid-leaf"),
	})
	if err == nil {
		t.Fatal("inactive taxonomy leaf must reject the complete batch")
	}
	assertOnboardingRuntimeCode(t, err, "CONTENT.USER.invalid_argument")
	if leafPort.calls != 1 {
		t.Fatalf("tag-service should be called once for the batch, got %d", leafPort.calls)
	}
	assertNoOnboardingWrites(t, processor, eventStore)
}

func TestOnboardingInterestDependencyFailureRejectsBatchWithoutWrites(t *testing.T) {
	leafPort := &trackingActiveLeafValidationPort{
		err: contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag-service validation unavailable",
		),
	}
	processor := &trackingOnboardingProcessor{}
	eventStore := &trackingOnboardingEventStore{}
	service := newOnboardingTaxonomyService(leafPort, processor, eventStore)

	err := service.ProcessBatch(context.Background(), []BehaviorEventInput{
		validClickEvent("evt-normal-before-dependency-failure"),
		validOnboardingEvent("evt-onboarding-dependency-failure"),
	})
	if err == nil {
		t.Fatal("taxonomy dependency failure must reject the complete batch")
	}
	assertOnboardingRuntimeCode(t, err, "CONTENT.SYSTEM.required_dependency_unavailable")
	if leafPort.calls != 1 {
		t.Fatalf("tag-service should be called once for the batch, got %d", leafPort.calls)
	}
	assertNoOnboardingWrites(t, processor, eventStore)
}

func TestOnboardingInterestBatchUsesOneValidationAndReplayDoesNotRewrite(t *testing.T) {
	leafPort := &trackingActiveLeafValidationPort{}
	processor := &trackingOnboardingProcessor{}
	eventStore := &trackingOnboardingEventStore{}
	service := newOnboardingTaxonomyService(leafPort, processor, eventStore)
	first := validOnboardingEvent("evt-onboarding-topic")
	second := validOnboardingEvent("evt-onboarding-audience")
	second.Tags = []string{"Audience/photography", "Topic/travel"}
	events := []BehaviorEventInput{first, second}

	if err := service.ProcessBatch(context.Background(), events); err != nil {
		t.Fatalf("first ProcessBatch() error = %v", err)
	}
	if leafPort.calls != 1 {
		t.Fatalf("one request batch must issue one tag validation, got %d", leafPort.calls)
	}
	if got := leafPort.expectedReleaseIDs; len(got) != 1 || got[0] != "tag-taxonomy-test-001" {
		t.Fatalf("expected taxonomy release = %#v", got)
	}
	if got := leafPort.requestedTagRefSets; len(got) != 1 || len(got[0]) != 2 ||
		got[0][0] != "Topic/travel" || got[0][1] != "Audience/photography" {
		t.Fatalf("expected request-level deduplicated tag refs, got %#v", got)
	}
	if processor.hotSignals != 2 || eventStore.rawEvents != 2 {
		t.Fatalf("first batch writes = hotPath:%d raw:%d, want 2/2", processor.hotSignals, eventStore.rawEvents)
	}

	leafPort.err = contentgenerated.AppErrorFromRequiredDependencyUnavailable(
		"tag-service is unavailable after the command committed",
	)
	if err := service.ProcessBatch(context.Background(), events); err != nil {
		t.Fatalf("idempotency replay ProcessBatch() error = %v", err)
	}
	if leafPort.calls != 1 {
		t.Fatalf("committed idempotency replay must bypass taxonomy dependency, got %d calls", leafPort.calls)
	}
	if processor.hotSignals != 2 || eventStore.rawEvents != 2 {
		t.Fatalf("idempotency replay rewrote signals: hotPath:%d raw:%d", processor.hotSignals, eventStore.rawEvents)
	}
}

func TestOnboardingInterestAbsentDoesNotCallTaxonomyPort(t *testing.T) {
	leafPort := &trackingActiveLeafValidationPort{}
	processor := &trackingOnboardingProcessor{}
	eventStore := &trackingOnboardingEventStore{}
	service := newOnboardingTaxonomyService(leafPort, processor, eventStore)

	if err := service.ProcessBatch(context.Background(), []BehaviorEventInput{
		validClickEvent("evt-no-onboarding"),
	}); err != nil {
		t.Fatalf("ProcessBatch() error = %v", err)
	}
	if leafPort.calls != 0 {
		t.Fatalf("batch without onboarding_interest must not call tag-service, got %d", leafPort.calls)
	}
}
