package servicehost

import (
	"context"
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"testing"
	"time"
)

const (
	firstConfigDigest  = "sha256:a7937b64b8caa58f03721bb6bacf5c78cb235febe0e70b1b84cd99541461a08e" // sha256("first")
	secondConfigDigest = "sha256:16367aacb67a4a017c8da8ab95682ccb390863780f7114dda0a0e0c55644c7c4" // sha256("second")
	edgeConfigDigest   = "sha256:a1cb100f57e971cacf269e7c26e4630a25a8e9d4bdd35e32df1a80b66b896254" // sha256("edge")
	searchConfigDigest = "sha256:2419329067823cab5b4e5ac5dd18a6abf1f57f45e753f5fc934292f3085a3717" // sha256("search")
)

type testModule struct {
	name   string
	digest string
	log    *[]string
	fail   map[string]error
}

func (m *testModule) Name() string         { return m.name }
func (m *testModule) ConfigDigest() string { return m.digest }

func (m *testModule) ValidateConfig(context.Context) error {
	return m.record("validate")
}

func (m *testModule) PrepareMigration(context.Context) error {
	return m.record("migrate")
}

func (m *testModule) Bind(context.Context) error {
	return m.record("bind")
}

func (m *testModule) Start(context.Context) error {
	return m.record("start")
}

func (m *testModule) Ready(context.Context) error {
	return m.record("ready")
}

func (m *testModule) OpenAdmission(context.Context) error {
	return m.record("admit")
}

func (m *testModule) Shutdown(context.Context) error {
	return m.record("shutdown")
}

func (m *testModule) record(operation string) error {
	*m.log = append(*m.log, m.name+":"+operation)
	return m.fail[operation]
}

func TestSupervisorStartsEveryModuleBeforeOpeningAdmission(t *testing.T) {
	t.Parallel()

	var calls []string
	first := &testModule{name: "api-edge", digest: firstConfigDigest, log: &calls}
	second := &testModule{name: "search-service", digest: secondConfigDigest, log: &calls}
	supervisor, err := NewSupervisor(first, second)
	if err != nil {
		t.Fatalf("NewSupervisor() error = %v", err)
	}

	if err := supervisor.Start(context.Background()); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	want := []string{
		"api-edge:validate",
		"search-service:validate",
		"api-edge:migrate",
		"search-service:migrate",
		"api-edge:bind",
		"search-service:bind",
		"api-edge:start",
		"search-service:start",
		"api-edge:ready",
		"search-service:ready",
		"api-edge:admit",
		"search-service:admit",
	}
	if !slices.Equal(calls, want) {
		t.Fatalf("calls = %#v, want %#v", calls, want)
	}
	if got := supervisor.Phase(); got != PhaseAdmitting {
		t.Fatalf("Phase() = %q, want %q", got, PhaseAdmitting)
	}
	for _, status := range supervisor.Status() {
		if status.Phase != PhaseAdmitting {
			t.Fatalf("module %q phase = %q, want %q", status.Name, status.Phase, PhaseAdmitting)
		}
	}
}

func TestSupervisorFailureDrainsBoundModulesInReverseOrder(t *testing.T) {
	t.Parallel()

	var calls []string
	first := &testModule{name: "api-edge", digest: firstConfigDigest, log: &calls}
	second := &testModule{
		name:   "search-service",
		digest: secondConfigDigest,
		log:    &calls,
		fail:   map[string]error{"ready": errors.New("elasticsearch unavailable")},
	}
	supervisor, err := NewSupervisor(first, second)
	if err != nil {
		t.Fatalf("NewSupervisor() error = %v", err)
	}
	supervisor.readinessTimeout = 5 * time.Millisecond
	supervisor.readinessInterval = 10 * time.Millisecond

	err = supervisor.Start(context.Background())
	if err == nil ||
		!strings.Contains(
			err.Error(),
			"module \"search-service\" ready: elasticsearch unavailable",
		) ||
		!errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Start() error = %v", err)
	}

	wantPrefix := []string{
		"api-edge:validate",
		"search-service:validate",
		"api-edge:migrate",
		"search-service:migrate",
		"api-edge:bind",
		"search-service:bind",
		"api-edge:start",
		"search-service:start",
	}
	if len(calls) < len(wantPrefix)+4 ||
		!slices.Equal(calls[:len(wantPrefix)], wantPrefix) ||
		!slices.Equal(
			calls[len(calls)-2:],
			[]string{"search-service:shutdown", "api-edge:shutdown"},
		) {
		t.Fatalf("calls = %#v, want startup prefix and reverse shutdown", calls)
	}
	for _, call := range calls[len(wantPrefix) : len(calls)-2] {
		if call != "api-edge:ready" && call != "search-service:ready" {
			t.Fatalf("unexpected readiness-window call %q in %#v", call, calls)
		}
	}
	if got := supervisor.Phase(); got != PhaseFailed {
		t.Fatalf("Phase() = %q, want %q", got, PhaseFailed)
	}
}

func TestSupervisorValidationFailureDrainsEveryConstructedModule(t *testing.T) {
	t.Parallel()

	var calls []string
	first := &testModule{
		name:   "user-service",
		digest: userConfigDigest,
		log:    &calls,
		fail:   map[string]error{"validate": errors.New("config unavailable")},
	}
	second := &testModule{
		name:   "api-edge",
		digest: edgeConfigDigest,
		log:    &calls,
	}
	supervisor, err := NewSupervisor(first, second)
	if err != nil {
		t.Fatalf("NewSupervisor() error = %v", err)
	}

	err = supervisor.Start(context.Background())
	if err == nil {
		t.Fatal("Start() error = nil, want validation error")
	}
	want := []string{
		"user-service:validate",
		"api-edge:shutdown",
		"user-service:shutdown",
	}
	if !slices.Equal(calls, want) {
		t.Fatalf("calls = %#v, want %#v", calls, want)
	}
}

func TestSupervisorRejectsAmbiguousComposition(t *testing.T) {
	t.Parallel()

	var calls []string
	module := &testModule{name: "api-edge", digest: firstConfigDigest, log: &calls}
	if _, err := NewSupervisor(module, module); err == nil {
		t.Fatal("NewSupervisor() accepted duplicate module")
	}
	if _, err := NewSupervisor(&testModule{name: "missing-digest", log: &calls}); err == nil {
		t.Fatal("NewSupervisor() accepted missing config digest")
	}
}

func TestCompositionIdentityAndTopologyAreImmutable(t *testing.T) {
	t.Parallel()

	var calls []string
	factories := []ModuleFactory{
		{
			Name: "api-edge",
			New: func() (Module, error) {
				return &testModule{
					name: "api-edge", digest: edgeConfigDigest, log: &calls,
				}, nil
			},
		},
		{
			Name: "search-service",
			New: func() (Module, error) {
				return &testModule{
					name: "search-service", digest: searchConfigDigest, log: &calls,
				}, nil
			},
		},
	}
	composition, err := NewComposition("service-core", factories...)
	if err != nil {
		t.Fatalf("NewComposition() error = %v", err)
	}
	identity := composition.Identity()
	const wantCompositionDigest = "sha256:a7a3ae027446b1454c917c5f374bad343e297ce6779c8fe20701a961972b8b87"
	if identity.CompositionDigest != wantCompositionDigest {
		t.Fatalf(
			"CompositionDigest = %q, want %q",
			identity.CompositionDigest,
			wantCompositionDigest,
		)
	}
	identity.Modules[0] = "mutated"
	if got := composition.Identity().Modules[0]; got != "api-edge" {
		t.Fatalf("composition identity was mutable: %q", got)
	}

	modules, err := composition.Build(context.Background())
	if err != nil {
		t.Fatalf("Build() error = %v", err)
	}
	topology, err := composition.ResolveTopologyIdentity(modules)
	if err != nil {
		t.Fatalf("ResolveTopologyIdentity() error = %v", err)
	}
	const wantTopologyDigest = "sha256:070cb8604867a687847e9797830d4c05dff9d59fb8e3e4053d631af7e502e75b"
	if topology.TopologyDigest != wantTopologyDigest {
		encoded, _ := json.Marshal(topology)
		t.Fatalf(
			"TopologyDigest = %q, want %q; topology=%s",
			topology.TopologyDigest,
			wantTopologyDigest,
			encoded,
		)
	}
}

func TestCompositionRejectsFactoryIdentityDriftAndDrains(t *testing.T) {
	t.Parallel()

	var calls []string
	composition, err := NewComposition(
		"service-core",
		ModuleFactory{
			Name: "api-edge",
			New: func() (Module, error) {
				return &testModule{
					name: "api-edge", digest: edgeConfigDigest, log: &calls,
				}, nil
			},
		},
		ModuleFactory{
			Name: "search-service",
			New: func() (Module, error) {
				return &testModule{
					name: "wrong-service", digest: searchConfigDigest, log: &calls,
				}, nil
			},
		},
	)
	if err != nil {
		t.Fatalf("NewComposition() error = %v", err)
	}
	_, err = composition.Build(context.Background())
	if err == nil || err.Error() != `module factory "search-service" returned identity "wrong-service"` {
		t.Fatalf("Build() error = %v", err)
	}
	want := []string{"wrong-service:shutdown", "api-edge:shutdown"}
	if !slices.Equal(calls, want) {
		t.Fatalf("calls = %#v, want %#v", calls, want)
	}
}

func TestChainCleanupCapturesEachPreviousCallback(t *testing.T) {
	calls := []string{}
	cleanup := func() { calls = append(calls, "base") }
	cleanup = ChainCleanup(cleanup, func() { calls = append(calls, "first") })
	cleanup = ChainCleanup(cleanup, func() { calls = append(calls, "second") })

	cleanup()

	want := []string{"second", "first", "base"}
	if !slices.Equal(calls, want) {
		t.Fatalf("calls = %#v, want %#v", calls, want)
	}
}

func TestWaitForReadinessRetriesWithoutWeakeningProbe(t *testing.T) {
	attempts := 0
	err := WaitForReadiness(
		t.Context(),
		100*time.Millisecond,
		time.Millisecond,
		func(context.Context) error {
			attempts++
			if attempts < 3 {
				return errors.New("worker has not completed its first poll")
			}
			return nil
		},
	)
	if err != nil {
		t.Fatalf("WaitForReadiness() error = %v", err)
	}
	if attempts != 3 {
		t.Fatalf("attempts = %d, want 3", attempts)
	}
}

func TestWaitForReadinessFailsClosedAtDeadline(t *testing.T) {
	err := WaitForReadiness(
		t.Context(),
		5*time.Millisecond,
		time.Millisecond,
		func(context.Context) error {
			return errors.New("dependency unavailable")
		},
	)
	if err == nil ||
		!strings.Contains(err.Error(), "dependency unavailable") ||
		!errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("WaitForReadiness() error = %v", err)
	}
}
