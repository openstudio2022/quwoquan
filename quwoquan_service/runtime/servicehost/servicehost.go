// Package servicehost owns process-level lifecycle for a composed service
// runtime.  Modules remain responsible for their own public HTTP contracts,
// data stores, configuration and telemetry identities.
package servicehost

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"sync"
	"time"
)

const (
	// CompositionIdentitySchema identifies the immutable service module closure.
	CompositionIdentitySchema = "quwoquan.service_core_composition"
	// TopologyIdentitySchema identifies the composition plus module-local config.
	TopologyIdentitySchema = "quwoquan.service_core_topology"
)

// Module is a service-owned bootstrap adapter. The host never reaches into a
// module's private implementation: it only coordinates the lifecycle exposed
// here.
//
// Bind must leave public admission closed. Ready verifies dependencies after
// workers start, and OpenAdmission is called only after every module is ready.
type Module interface {
	Name() string
	ConfigDigest() string
	ValidateConfig(context.Context) error
	PrepareMigration(context.Context) error
	Bind(context.Context) error
	Start(context.Context) error
	Ready(context.Context) error
	OpenAdmission(context.Context) error
	Shutdown(context.Context) error
}

// WaitForReadiness gives asynchronous workers a bounded startup window while
// preserving the module's exact health contract. It never turns a failed probe
// into success and always honors parent cancellation.
func WaitForReadiness(
	ctx context.Context,
	timeout time.Duration,
	interval time.Duration,
	probe func(context.Context) error,
) error {
	if timeout <= 0 || interval <= 0 || probe == nil {
		return errors.New("servicehost readiness policy is invalid")
	}
	waitCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	var lastError error
	for {
		if waitCtx.Err() != nil {
			return errors.Join(lastError, waitCtx.Err())
		}
		if err := probe(waitCtx); err == nil {
			return nil
		} else {
			if waitCtx.Err() == nil || lastError == nil {
				lastError = err
			}
		}
		select {
		case <-waitCtx.Done():
			return errors.Join(lastError, waitCtx.Err())
		case <-ticker.C:
		}
	}
}

// ModuleFactory is the only composition seam consumed by a process host.
// Name is declared separately so callers can inspect the immutable module
// closure without constructing service dependencies.
type ModuleFactory struct {
	Name string
	New  func() (Module, error)
}

// EndpointIdentity records a logical service endpoint without coupling it to
// the process-local listener used by a composed host.
type EndpointIdentity struct {
	Module string `json:"module"`
	Host   string `json:"host"`
	Port   int    `json:"port"`
}

// CompositionIdentity binds one ordered module closure. Module order is part
// of the identity because it also determines startup and reverse shutdown.
type CompositionIdentity struct {
	Schema            string             `json:"schema"`
	Profile           string             `json:"profile"`
	Modules           []string           `json:"modules"`
	Endpoints         []EndpointIdentity `json:"endpoints"`
	CompositionDigest string             `json:"compositionDigest"`
}

// ModuleConfigIdentity preserves each logical service identity after process
// composition while binding its exact configuration digest.
type ModuleConfigIdentity struct {
	Name         string `json:"name"`
	ConfigDigest string `json:"configDigest"`
}

// TopologyIdentity binds an immutable composition to module-local configs.
type TopologyIdentity struct {
	Schema            string                 `json:"schema"`
	CompositionDigest string                 `json:"compositionDigest"`
	Modules           []ModuleConfigIdentity `json:"modules"`
	TopologyDigest    string                 `json:"topologyDigest"`
}

// Composition owns an immutable, validated module factory closure.
type Composition struct {
	factories []ModuleFactory
	identity  CompositionIdentity
}

// NewComposition validates and seals an ordered module factory closure.
func NewComposition(profile string, factories ...ModuleFactory) (*Composition, error) {
	return NewCompositionWithEndpoints(profile, nil, factories...)
}

// NewCompositionWithEndpoints seals the logical endpoint topology together
// with the module closure. Multiple modules may retain the same port when
// their canonical hostnames differ.
func NewCompositionWithEndpoints(
	profile string,
	endpoints []EndpointIdentity,
	factories ...ModuleFactory,
) (*Composition, error) {
	if profile == "" {
		return nil, errors.New("servicehost composition profile must not be empty")
	}
	if len(factories) == 0 {
		return nil, errors.New("servicehost composition requires at least one module")
	}

	names := make([]string, 0, len(factories))
	seen := make(map[string]struct{}, len(factories))
	for _, factory := range factories {
		if factory.Name == "" {
			return nil, errors.New("servicehost module factory name must not be empty")
		}
		if factory.New == nil {
			return nil, fmt.Errorf(
				"servicehost module factory %q constructor must not be nil",
				factory.Name,
			)
		}
		if _, exists := seen[factory.Name]; exists {
			return nil, fmt.Errorf(
				"servicehost duplicate module factory %q",
				factory.Name,
			)
		}
		seen[factory.Name] = struct{}{}
		names = append(names, factory.Name)
	}
	sealedEndpoints := append([]EndpointIdentity{}, endpoints...)
	endpointKeys := make(map[string]struct{}, len(sealedEndpoints))
	endpointModules := make(map[string]struct{}, len(sealedEndpoints))
	for _, endpoint := range sealedEndpoints {
		if _, exists := seen[endpoint.Module]; !exists {
			return nil, fmt.Errorf(
				"servicehost endpoint module %q is not in composition",
				endpoint.Module,
			)
		}
		if endpoint.Host == "" {
			return nil, fmt.Errorf(
				"servicehost endpoint for module %q has empty host",
				endpoint.Module,
			)
		}
		if endpoint.Port < 1 || endpoint.Port > 65535 {
			return nil, fmt.Errorf(
				"servicehost endpoint for module %q has invalid port %d",
				endpoint.Module,
				endpoint.Port,
			)
		}
		key := fmt.Sprintf("%s:%d", endpoint.Host, endpoint.Port)
		if _, exists := endpointKeys[key]; exists {
			return nil, fmt.Errorf("servicehost duplicate endpoint %q", key)
		}
		if _, exists := endpointModules[endpoint.Module]; exists {
			return nil, fmt.Errorf(
				"servicehost duplicate endpoint module %q",
				endpoint.Module,
			)
		}
		endpointKeys[key] = struct{}{}
		endpointModules[endpoint.Module] = struct{}{}
	}
	if len(sealedEndpoints) > 0 && len(endpointModules) != len(factories) {
		return nil, errors.New(
			"servicehost endpoint topology must identify every module exactly once",
		)
	}
	digest, err := digestIdentity(map[string]any{
		"schema":    CompositionIdentitySchema,
		"profile":   profile,
		"modules":   names,
		"endpoints": sealedEndpoints,
	})
	if err != nil {
		return nil, fmt.Errorf("servicehost composition identity: %w", err)
	}
	return &Composition{
		factories: slices.Clone(factories),
		identity: CompositionIdentity{
			Schema:            CompositionIdentitySchema,
			Profile:           profile,
			Modules:           slices.Clone(names),
			Endpoints:         sealedEndpoints,
			CompositionDigest: digest,
		},
	}, nil
}

// Identity returns a defensive copy of the immutable composition identity.
func (composition *Composition) Identity() CompositionIdentity {
	identity := composition.identity
	identity.Modules = slices.Clone(identity.Modules)
	identity.Endpoints = slices.Clone(identity.Endpoints)
	return identity
}

// Build constructs every module in composition order and rejects a constructor
// whose runtime identity differs from its declared factory identity.
func (composition *Composition) Build(ctx context.Context) ([]Module, error) {
	modules := make([]Module, 0, len(composition.factories))
	for _, factory := range composition.factories {
		module, err := factory.New()
		if err != nil {
			return nil, errors.Join(
				fmt.Errorf("module %q construction: %w", factory.Name, err),
				shutdownModules(ctx, modules),
			)
		}
		if module == nil {
			return nil, errors.Join(
				fmt.Errorf("module %q constructor returned nil", factory.Name),
				shutdownModules(ctx, modules),
			)
		}
		if module.Name() != factory.Name {
			return nil, errors.Join(
				fmt.Errorf(
					"module factory %q returned identity %q",
					factory.Name,
					module.Name(),
				),
				shutdownModule(ctx, module),
				shutdownModules(ctx, modules),
			)
		}
		if module.ConfigDigest() == "" {
			return nil, errors.Join(
				fmt.Errorf("module %q config digest must not be empty", factory.Name),
				shutdownModule(ctx, module),
				shutdownModules(ctx, modules),
			)
		}
		modules = append(modules, module)
	}
	return modules, nil
}

// ResolveTopologyIdentity binds one built module set to its composition.
func (composition *Composition) ResolveTopologyIdentity(
	modules []Module,
) (TopologyIdentity, error) {
	if len(modules) != len(composition.identity.Modules) {
		return TopologyIdentity{}, fmt.Errorf(
			"servicehost topology has %d modules, want %d",
			len(modules),
			len(composition.identity.Modules),
		)
	}
	configs := make([]ModuleConfigIdentity, 0, len(modules))
	for _, module := range modules {
		if module == nil {
			return TopologyIdentity{}, fmt.Errorf(
				"servicehost topology contains a nil module",
			)
		}
		configs = append(configs, ModuleConfigIdentity{
			Name:         module.Name(),
			ConfigDigest: module.ConfigDigest(),
		})
	}
	return composition.ResolveDeclaredTopologyIdentity(configs)
}

// ResolveDeclaredTopologyIdentity seals package-time module config identities
// against the exact composition order used by runtime module construction.
func (composition *Composition) ResolveDeclaredTopologyIdentity(
	configs []ModuleConfigIdentity,
) (TopologyIdentity, error) {
	if len(configs) != len(composition.identity.Modules) {
		return TopologyIdentity{}, fmt.Errorf(
			"servicehost topology has %d module configs, want %d",
			len(configs),
			len(composition.identity.Modules),
		)
	}
	sealed := slices.Clone(configs)
	for index, config := range sealed {
		wantName := composition.identity.Modules[index]
		if config.Name != wantName {
			return TopologyIdentity{}, fmt.Errorf(
				"servicehost topology module %d is %q, want %q",
				index,
				config.Name,
				wantName,
			)
		}
		if strings.TrimSpace(config.ConfigDigest) == "" {
			return TopologyIdentity{}, fmt.Errorf(
				"servicehost topology module %q config digest must not be empty",
				config.Name,
			)
		}
	}
	digest, err := digestIdentity(map[string]any{
		"schema":            TopologyIdentitySchema,
		"compositionDigest": composition.identity.CompositionDigest,
		"modules":           sealed,
	})
	if err != nil {
		return TopologyIdentity{}, fmt.Errorf("servicehost topology identity: %w", err)
	}
	return TopologyIdentity{
		Schema:            TopologyIdentitySchema,
		CompositionDigest: composition.identity.CompositionDigest,
		Modules:           sealed,
		TopologyDigest:    digest,
	}, nil
}

func digestIdentity(identity map[string]any) (string, error) {
	encoded, err := json.Marshal(identity)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func shutdownModule(ctx context.Context, module Module) error {
	cleanupCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer cancel()
	return module.Shutdown(cleanupCtx)
}

func shutdownModules(ctx context.Context, modules []Module) error {
	if len(modules) == 0 {
		return nil
	}
	cleanupCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer cancel()
	var result error
	for index := len(modules) - 1; index >= 0; index-- {
		module := modules[index]
		if err := module.Shutdown(cleanupCtx); err != nil {
			result = errors.Join(
				result,
				fmt.Errorf("module %q construction cleanup: %w", module.Name(), err),
			)
		}
	}
	return result
}

// Phase records the last completed process lifecycle boundary.
type Phase string

const (
	PhaseNew       Phase = "new"
	PhaseValidated Phase = "validated"
	PhaseMigrated  Phase = "migrated"
	PhaseBound     Phase = "bound"
	PhaseStarted   Phase = "started"
	PhaseReady     Phase = "ready"
	PhaseAdmitting Phase = "admitting"
	PhaseStopping  Phase = "stopping"
	PhaseStopped   Phase = "stopped"
	PhaseFailed    Phase = "failed"
)

// ModuleStatus is a safe diagnostic projection for a module.
type ModuleStatus struct {
	Name         string
	ConfigDigest string
	Phase        Phase
}

// Supervisor coordinates an all-or-nothing composed process. It intentionally
// has no signal handling: the executable owning the process supplies its
// context and decides its exit code.
type Supervisor struct {
	modules []Module

	mu                sync.RWMutex
	phase             Phase
	status            map[string]ModuleStatus
	owned             []Module
	readinessTimeout  time.Duration
	readinessInterval time.Duration
}

// NewSupervisor rejects ambiguous module identities and configuration
// omissions before any listener or worker can be created.
func NewSupervisor(modules ...Module) (*Supervisor, error) {
	if len(modules) == 0 {
		return nil, errors.New("servicehost requires at least one module")
	}

	status := make(map[string]ModuleStatus, len(modules))
	for _, module := range modules {
		if module == nil {
			return nil, errors.New("servicehost module must not be nil")
		}
		name := module.Name()
		if name == "" {
			return nil, errors.New("servicehost module name must not be empty")
		}
		if module.ConfigDigest() == "" {
			return nil, fmt.Errorf("servicehost module %q config digest must not be empty", name)
		}
		if _, exists := status[name]; exists {
			return nil, fmt.Errorf("servicehost duplicate module %q", name)
		}
		status[name] = ModuleStatus{
			Name:         name,
			ConfigDigest: module.ConfigDigest(),
			Phase:        PhaseNew,
		}
	}

	return &Supervisor{
		modules:           slices.Clone(modules),
		phase:             PhaseNew,
		status:            status,
		owned:             slices.Clone(modules),
		readinessTimeout:  180 * time.Second,
		readinessInterval: time.Second,
	}, nil
}

// Start validates every module before migrations, binds every listener before
// workers, and opens admission only after every readiness check has passed.
// Any failure drains every bound module in reverse order and preserves the
// failing phase for diagnosis.
func (s *Supervisor) Start(ctx context.Context) error {
	s.mu.Lock()
	if s.phase != PhaseNew {
		phase := s.phase
		s.mu.Unlock()
		return fmt.Errorf("servicehost cannot start from phase %q", phase)
	}
	s.phase = PhaseNew
	for name, status := range s.status {
		status.Phase = PhaseNew
		s.status[name] = status
	}
	s.mu.Unlock()

	if err := s.runPhase(ctx, PhaseValidated, Module.ValidateConfig); err != nil {
		return s.failAndDrain(ctx, err)
	}
	if err := s.runPhase(ctx, PhaseMigrated, Module.PrepareMigration); err != nil {
		return s.failAndDrain(ctx, err)
	}
	if err := s.runBoundPhase(ctx, PhaseBound, Module.Bind); err != nil {
		return s.failAndDrain(ctx, err)
	}
	if err := s.runPhase(ctx, PhaseStarted, Module.Start); err != nil {
		return s.failAndDrain(ctx, err)
	}
	if err := WaitForReadiness(
		ctx,
		s.readinessTimeout,
		s.readinessInterval,
		s.runReadinessProbe,
	); err != nil {
		return s.failAndDrain(ctx, err)
	}
	if err := s.runPhase(ctx, PhaseAdmitting, Module.OpenAdmission); err != nil {
		return s.failAndDrain(ctx, err)
	}
	return nil
}

func (s *Supervisor) runReadinessProbe(ctx context.Context) error {
	for _, module := range s.modules {
		if err := module.Ready(ctx); err != nil {
			s.setModulePhase(module.Name(), PhaseFailed)
			return fmt.Errorf("module %q ready: %w", module.Name(), err)
		}
		s.setModulePhase(module.Name(), PhaseReady)
	}
	s.mu.Lock()
	s.phase = PhaseReady
	s.mu.Unlock()
	return nil
}

// Shutdown drains every owned module in reverse composition order, including
// modules whose validation or binding failed. A shutdown failure is returned
// to the process owner instead of being hidden behind a successful exit.
func (s *Supervisor) Shutdown(ctx context.Context) error {
	s.mu.Lock()
	if len(s.owned) == 0 {
		s.phase = PhaseStopped
		s.mu.Unlock()
		return nil
	}
	modules := slices.Clone(s.owned)
	s.phase = PhaseStopping
	s.mu.Unlock()

	var result error
	for index := len(modules) - 1; index >= 0; index-- {
		module := modules[index]
		if err := module.Shutdown(ctx); err != nil {
			result = errors.Join(result, fmt.Errorf("module %q shutdown: %w", module.Name(), err))
		}
		s.setModulePhase(module.Name(), PhaseStopped)
	}

	s.mu.Lock()
	s.owned = nil
	if result != nil {
		s.phase = PhaseFailed
	} else {
		s.phase = PhaseStopped
	}
	s.mu.Unlock()
	return result
}

// Phase returns the current aggregate process phase.
func (s *Supervisor) Phase() Phase {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.phase
}

// Status returns module state in declared composition order.
func (s *Supervisor) Status() []ModuleStatus {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]ModuleStatus, 0, len(s.modules))
	for _, module := range s.modules {
		result = append(result, s.status[module.Name()])
	}
	return result
}

func (s *Supervisor) runPhase(
	ctx context.Context,
	phase Phase,
	operation func(Module, context.Context) error,
) error {
	for _, module := range s.modules {
		if err := operation(module, ctx); err != nil {
			s.setModulePhase(module.Name(), PhaseFailed)
			return fmt.Errorf("module %q %s: %w", module.Name(), phase, err)
		}
		s.setModulePhase(module.Name(), phase)
	}
	s.mu.Lock()
	s.phase = phase
	s.mu.Unlock()
	return nil
}

func (s *Supervisor) runBoundPhase(
	ctx context.Context,
	phase Phase,
	operation func(Module, context.Context) error,
) error {
	for _, module := range s.modules {
		if err := operation(module, ctx); err != nil {
			s.setModulePhase(module.Name(), PhaseFailed)
			return fmt.Errorf("module %q %s: %w", module.Name(), phase, err)
		}
		s.setModulePhase(module.Name(), phase)
	}
	s.mu.Lock()
	s.phase = phase
	s.mu.Unlock()
	return nil
}

func (s *Supervisor) failAndDrain(ctx context.Context, cause error) error {
	s.mu.Lock()
	s.phase = PhaseFailed
	s.mu.Unlock()
	if shutdownErr := s.Shutdown(ctx); shutdownErr != nil {
		return errors.Join(cause, shutdownErr)
	}
	s.mu.Lock()
	s.phase = PhaseFailed
	s.mu.Unlock()
	return cause
}

func (s *Supervisor) setModulePhase(name string, phase Phase) {
	s.mu.Lock()
	defer s.mu.Unlock()
	status := s.status[name]
	status.Phase = phase
	s.status[name] = status
}
