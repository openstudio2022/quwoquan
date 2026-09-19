package application

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	credentialports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

type recoveryMemoryStore struct {
	mu    sync.Mutex
	flows map[string]AccountCreationFlow
}

func newRecoveryMemoryStore() *recoveryMemoryStore {
	return &recoveryMemoryStore{flows: map[string]AccountCreationFlow{}}
}
func (s *recoveryMemoryStore) Begin(_ context.Context, candidate AccountCreationFlow) (AccountCreationFlow, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if stored, ok := s.flows[candidate.FlowID]; ok {
		if stored.IntentDigest != candidate.IntentDigest {
			return AccountCreationFlow{}, ErrAccountCreationFlowConflict
		}
		return stored, nil
	}
	candidate.CreatedAt = time.Now().UTC()
	candidate.UpdatedAt = candidate.CreatedAt
	s.flows[candidate.FlowID] = candidate
	return candidate, nil
}
func (s *recoveryMemoryStore) Load(_ context.Context, id string) (AccountCreationFlow, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	f, ok := s.flows[id]
	return f, ok, nil
}
func (s *recoveryMemoryStore) MarkStep(_ context.Context, id string, step AccountCreationStep) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	f, ok := s.flows[id]
	if !ok {
		return ErrAccountCreationFlowNotFound
	}
	switch step {
	case AccountCreationAccountCommitted:
		f.AccountCommitted = true
	case AccountCreationPersonaCommitted:
		f.PersonaCommitted = true
	case AccountCreationProfileProjected:
		f.ProfileProjected = true
	case AccountCreationCredentialBound:
		f.CredentialBound = true
	default:
		return errors.New("bad step")
	}
	f.Completed = f.AccountCommitted && f.PersonaCommitted && f.ProfileProjected && f.CredentialBound
	s.flows[id] = f
	return nil
}

func (s *recoveryMemoryStore) ReplacePersonaCandidate(_ context.Context, id, expected, next string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	flow, ok := s.flows[id]
	if !ok || flow.PersonaID != expected || flow.PersonaCommitted {
		return ErrAccountCreationCandidateStale
	}
	flow.PersonaID = next
	s.flows[id] = flow
	return nil
}

type recoveryProfileStore struct {
	profiles map[string]*usermodel.UserProfile
	creates  int
}

func (s *recoveryProfileStore) FindByID(_ context.Context, id string) (*usermodel.UserProfile, error) {
	return s.profiles[id], nil
}
func (*recoveryProfileStore) FindByNickname(context.Context, string) (*usermodel.UserProfile, error) {
	return nil, nil
}
func (*recoveryProfileStore) SearchProfiles(context.Context, string, int) ([]usermodel.UserProfile, error) {
	return nil, nil
}
func (s *recoveryProfileStore) CreateAccount(_ context.Context, c userports.UserAccountCreate) error {
	s.creates++
	s.profiles[c.UserID] = &usermodel.UserProfile{UserID: c.UserID, AccountState: c.AccountState, IdentityOrigin: c.IdentityOrigin, LogicalShard: c.LogicalShard}
	return nil
}
func (*recoveryProfileStore) PromoteRegistration(context.Context, userports.RegistrationPromotion) error {
	return nil
}

type recoveryPersonaStore struct{ personas map[string]*usermodel.Persona }

func (s *recoveryPersonaStore) FindByID(_ context.Context, id string) (*usermodel.Persona, error) {
	return s.personas[id], nil
}
func (s *recoveryPersonaStore) FindByPersonaID(_ context.Context, id string) (*usermodel.Persona, error) {
	return s.personas[id], nil
}
func (*recoveryPersonaStore) FindByUserHandle(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}
func (s *recoveryPersonaStore) FindByUserID(_ context.Context, owner string) ([]usermodel.Persona, error) {
	r := []usermodel.Persona{}
	for _, p := range s.personas {
		if p.UserID == owner {
			r = append(r, *p)
		}
	}
	return r, nil
}
func (s *recoveryPersonaStore) FindActiveByUserID(_ context.Context, owner string) (*usermodel.Persona, error) {
	for _, p := range s.personas {
		if p.UserID == owner && p.IsActive {
			return p, nil
		}
	}
	return nil, nil
}

type recoveryPersonaCommands struct {
	store    *recoveryPersonaStore
	failures int
	failure  error
	seenIDs  []string
	commits  int
}

func (c *recoveryPersonaCommands) CommitCreate(_ context.Context, p *usermodel.Persona, _ personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	c.seenIDs = append(c.seenIDs, p.PersonaID)
	if c.failures > 0 {
		c.failures--
		if c.failure != nil {
			return personaports.PersonaCommandResult{}, c.failure
		}
		return personaports.PersonaCommandResult{}, errors.New("injected Persona failure")
	}
	c.commits++
	copy := *p
	copy.Version = 1
	c.store.personas[p.PersonaID] = &copy
	return personaports.PersonaCommandResult{PersonaID: p.PersonaID, Version: 1}, nil
}
func (*recoveryPersonaCommands) CommitMutation(context.Context, *usermodel.Persona, string, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	panic("unused")
}
func (*recoveryPersonaCommands) CommitActivation(context.Context, string, string, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	panic("unused")
}

type recoveryProjector struct {
	profiles *recoveryProfileStore
	personas *recoveryPersonaStore
	calls    int
}

func (p *recoveryProjector) Project(_ context.Context, id string, _ int64) (*usermodel.UserProfile, error) {
	p.calls++
	persona := p.personas.personas[id]
	profile := p.profiles.profiles[persona.UserID]
	profile.Nickname = persona.DisplayName
	return profile, nil
}
func (*recoveryProjector) ProjectNext(context.Context) (bool, error) { return false, nil }
func (*recoveryProjector) Run(context.Context, time.Duration) error  { return nil }

type recoveryCredentialStore struct {
	byKey map[string]credentialmodel.CredentialBinding
}

func (s *recoveryCredentialStore) Bind(_ context.Context, change credentialmodel.ChangeSet) (credentialports.BindResult, error) {
	s.byKey[string(change.Aggregate.State().CredentialType)+"|"+change.Aggregate.State().CredentialKey] = change.Aggregate
	return credentialports.BindResult{Aggregate: change.Aggregate}, nil
}
func (*recoveryCredentialStore) LoadByOwnerAndType(context.Context, string, credentialmodel.CredentialType) (credentialmodel.CredentialBinding, bool, error) {
	return credentialmodel.CredentialBinding{}, false, nil
}
func (s *recoveryCredentialStore) FindByTypeAndKey(_ context.Context, t credentialmodel.CredentialType, k string) (credentialmodel.CredentialBinding, bool, error) {
	b, ok := s.byKey[string(t)+"|"+k]
	return b, ok, nil
}
func (*recoveryCredentialStore) MarkUsed(context.Context, string, time.Time) error { return nil }
func (*recoveryCredentialStore) ListByOwner(context.Context, string) ([]credentialmodel.CredentialBinding, error) {
	return nil, nil
}
func (*recoveryCredentialStore) CommitRevoke(context.Context, int64, credentialmodel.ChangeSet) error {
	return nil
}

type recoveryCredentialCommands struct {
	store *recoveryCredentialStore
	binds int
}

func (c *recoveryCredentialCommands) BindVerifiedCredential(_ context.Context, owner string, cmd credentialapp.BindCredentialCommand) (credentialapp.CommandResult, error) {
	c.binds++
	change, err := credentialmodel.Bind(credentialmodel.BindParams{ID: "credential-1", OwnerID: owner, CredentialType: cmd.CredentialType, CredentialKey: cmd.CredentialKey, DisplayLabel: cmd.DisplayLabel, EventID: "event-1", BoundAt: time.Now().UTC()})
	if err != nil {
		return credentialapp.CommandResult{}, err
	}
	r, err := c.store.Bind(context.Background(), change)
	if err != nil {
		return credentialapp.CommandResult{}, err
	}
	snap := r.Aggregate.Snapshot()
	return credentialapp.CommandResult{OwnerID: owner, CredentialType: snap.CredentialType, IsActive: snap.IsActive(), DisplayLabel: snap.DisplayLabel, Version: snap.Version}, nil
}
func (*recoveryCredentialCommands) UnbindCredential(context.Context, credentialapp.UnbindCredentialCommand) (credentialapp.CommandResult, error) {
	panic("unused")
}

func TestAuthCreationResumesAfterAccountCommittedPersonaFailure(t *testing.T) {
	ctx := context.Background()
	recovery := newRecoveryMemoryStore()
	profiles := &recoveryProfileStore{profiles: map[string]*usermodel.UserProfile{}}
	personas := &recoveryPersonaStore{personas: map[string]*usermodel.Persona{}}
	personaCommands := &recoveryPersonaCommands{store: personas, failures: 1}
	projector := &recoveryProjector{profiles: profiles, personas: personas}
	credentials := &recoveryCredentialStore{byKey: map[string]credentialmodel.CredentialBinding{}}
	credentialCommands := &recoveryCredentialCommands{store: credentials}
	service := NewAuthService(profiles, personas, credentials, nil, nil, WithCredentialCommands(credentialCommands), WithPersonaCommandPipeline(personaCommands, projector), WithAccountCreationRecoveryStore(recovery))
	_, err := service.createOwnerAccountWithIdentity(ctx, credentialmodel.CredentialTypePhone, "+8613800000000", "phone", "phone", "ph")
	if err == nil {
		t.Fatal("first call must fail at Persona step")
	}
	if profiles.creates != 1 || len(profiles.profiles) != 1 || len(personas.personas) != 0 {
		t.Fatalf("after failure accounts=%d profiles=%d personas=%d", profiles.creates, len(profiles.profiles), len(personas.personas))
	}
	flowID, _ := accountCreationFlowIdentity(credentialmodel.CredentialTypePhone, "+8613800000000", "phone")
	first, ok, _ := recovery.Load(ctx, flowID)
	if !ok || !first.AccountCommitted || first.PersonaCommitted {
		t.Fatalf("flow after failure=%+v", first)
	}
	ownerID, err := service.createOwnerAccountWithIdentity(ctx, credentialmodel.CredentialTypePhone, "+8613800000000", "phone", "phone", "ph")
	if err != nil {
		t.Fatal(err)
	}
	if ownerID != first.OwnerID || profiles.creates != 1 || len(personas.personas) != 1 || personaCommands.commits != 1 || projector.calls != 1 || credentialCommands.binds != 1 {
		t.Fatalf("owner=%s flow=%+v creates=%d personas=%d commits=%d projections=%d binds=%d", ownerID, first, profiles.creates, len(personas.personas), personaCommands.commits, projector.calls, credentialCommands.binds)
	}
	if len(personaCommands.seenIDs) != 2 || personaCommands.seenIDs[0] != first.PersonaID || personaCommands.seenIDs[1] != first.PersonaID {
		t.Fatalf("Persona identity changed across recovery: %v flow=%s", personaCommands.seenIDs, first.PersonaID)
	}
	terminal, _, _ := recovery.Load(ctx, flowID)
	if !terminal.Completed {
		t.Fatalf("terminal flow=%+v", terminal)
	}
}

func TestAuthCreationReplacesUncommittedPersonaCandidateOnIdentityConflict(t *testing.T) {
	ctx := context.Background()
	recovery := newRecoveryMemoryStore()
	profiles := &recoveryProfileStore{profiles: map[string]*usermodel.UserProfile{}}
	personas := &recoveryPersonaStore{personas: map[string]*usermodel.Persona{}}
	personaCommands := &recoveryPersonaCommands{store: personas, failures: 1, failure: personaports.ErrPersonaIdentityConflict}
	projector := &recoveryProjector{profiles: profiles, personas: personas}
	credentials := &recoveryCredentialStore{byKey: map[string]credentialmodel.CredentialBinding{}}
	credentialCommands := &recoveryCredentialCommands{store: credentials}
	service := NewAuthService(profiles, personas, credentials, nil, nil,
		WithCredentialCommands(credentialCommands), WithPersonaCommandPipeline(personaCommands, projector), WithAccountCreationRecoveryStore(recovery))
	ownerID, err := service.createOwnerAccountWithIdentity(ctx, credentialmodel.CredentialTypePhone, "+8613800000001", "phone", "phone", "ph")
	if err != nil {
		t.Fatal(err)
	}
	flowID, _ := accountCreationFlowIdentity(credentialmodel.CredentialTypePhone, "+8613800000001", "phone")
	flow, found, err := recovery.Load(ctx, flowID)
	if err != nil || !found || !flow.Completed {
		t.Fatalf("flow=%+v found=%v err=%v", flow, found, err)
	}
	if len(personaCommands.seenIDs) != 2 || personaCommands.seenIDs[0] == personaCommands.seenIDs[1] {
		t.Fatalf("identity conflict did not rotate candidate: %v", personaCommands.seenIDs)
	}
	if flow.OwnerID != ownerID || flow.PersonaID != personaCommands.seenIDs[1] {
		t.Fatalf("flow identity=%+v committed=%v", flow, personaCommands.seenIDs)
	}
	if personas.personas[flow.PersonaID] == nil || len(personas.personas) != 1 || profiles.creates != 1 {
		t.Fatalf("personas=%v account creates=%d", personas.personas, profiles.creates)
	}
}
