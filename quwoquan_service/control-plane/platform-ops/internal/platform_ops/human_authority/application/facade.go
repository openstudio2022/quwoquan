package application

import (
	"context"
	"crypto/ed25519"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/ports"
)

type Actor struct {
	ID            string
	Roles         []string
	Scopes        []string
	MFAProvenance string
}
type RoleMapper struct{ groups map[string][]string }

func NewRoleMapper(groups map[string][]string) (*RoleMapper, error) {
	copied := map[string][]string{}
	for group, roles := range groups {
		group = strings.TrimSpace(group)
		if group == "" {
			return nil, model.ErrInvalid
		}
		for _, role := range roles {
			if !model.ValidRole(role) {
				return nil, model.ErrInvalid
			}
		}
		copied[group] = append([]string(nil), roles...)
	}
	return &RoleMapper{groups: copied}, nil
}
func (m *RoleMapper) RolesFor(groups []string) []string {
	out := []string{}
	for _, group := range groups {
		out = append(out, m.groups[strings.TrimSpace(group)]...)
	}
	unique := map[string]struct{}{}
	result := []string{}
	for _, role := range out {
		if _, ok := unique[role]; !ok {
			unique[role] = struct{}{}
			result = append(result, role)
		}
	}
	return result
}

type SubmitRequest struct {
	Round            int      `json:"round"`
	Facts            []string `json:"facts"`
	Impacts          []string `json:"impacts"`
	Unknowns         []string `json:"unknowns"`
	SelectedOptionID string   `json:"selectedOptionId,omitempty"`
}

type SigningPublicKey struct {
	KeyID           string `json:"keyId"`
	Algorithm       string `json:"algorithm"`
	PublicKey       string `json:"publicKey"`
	ReleaseEligible bool   `json:"releaseEligible"`
	ExternalBlocker string `json:"externalBlocker,omitempty"`
}

type GitHubMapping struct {
	Repository   string
	Environment  string
	DecisionKind string
	Scope        string
}
type ProviderIdentity struct {
	Issuer          string
	ProviderKind    string
	ProviderVersion string
	ProviderCommit  string
	ContractVersion string
}

type Facade struct {
	store          ports.Store
	signer         ports.Signer
	provider       ProviderIdentity
	now            func() time.Time
	ids            func() string
	githubMappings []GitHubMapping
}

func NewFacade(store ports.Store, signer ports.Signer, mappings []GitHubMapping) (*Facade, error) {
	return NewFacadeWithProvider(store, signer, mappings, ProviderIdentity{Issuer: "https://authority.test", ProviderKind: "hosted-human-authority", ProviderVersion: "test", ProviderCommit: "sha256:" + strings.Repeat("0", 64), ContractVersion: "human-authority-wire-v1"})
}

func NewFacadeWithProvider(store ports.Store, signer ports.Signer, mappings []GitHubMapping, provider ProviderIdentity) (*Facade, error) {
	if store == nil || signer == nil {
		return nil, errors.New("human authority facade requires store and signer")
	}
	if strings.TrimSpace(provider.Issuer) == "" || strings.TrimSpace(provider.ProviderKind) == "" || strings.TrimSpace(provider.ProviderVersion) == "" || strings.TrimSpace(provider.ContractVersion) == "" || !isCanonicalDigest(provider.ProviderCommit) {
		return nil, errors.New("human authority provider identity is invalid")
	}
	for _, m := range mappings {
		if strings.TrimSpace(m.Repository) == "" || strings.TrimSpace(m.Environment) == "" || !model.ValidDecisionKind(m.DecisionKind) || strings.TrimSpace(m.Scope) == "" {
			return nil, model.ErrInvalid
		}
	}
	return &Facade{store: store, signer: signer, provider: provider, now: func() time.Time { return time.Now().UTC() }, ids: func() string { return uuid.NewString() }, githubMappings: append([]GitHubMapping(nil), mappings...)}, nil
}
func (f *Facade) WithClock(now func() time.Time) *Facade { f.now = now; return f }
func (f *Facade) WithIDs(ids func() string) *Facade      { f.ids = ids; return f }

func (f *Facade) Create(ctx context.Context, actor Actor, input model.DecisionUnit) (model.DecisionUnit, error) {
	if strings.TrimSpace(input.ID) == "" {
		input.ID = f.ids()
	}
	input.CreatedAt = f.now()
	unit, err := model.NewDecisionUnit(input)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	event, err := model.NewEvent(unit.ID, f.ids(), "DecisionUnitCreated", actor.ID, 1, "", unit, unit.CreatedAt)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	unit.LastSequence = 1
	unit.LastHash = event.Hash
	if err = f.store.Create(ctx, ports.CommitPacket{Unit: unit, Events: []model.Event{event}, AuditAction: "decision_unit_created", AuditActor: actor.ID, OutboxType: "HumanDecisionUnitCreated", OutboxPayload: map[string]any{"decisionUnitId": unit.ID, "decisionKind": unit.DecisionKind}}); err != nil {
		return model.DecisionUnit{}, err
	}
	return unit, nil
}
func (f *Facade) Submit(ctx context.Context, actor Actor, unitID string, request SubmitRequest) (model.DecisionUnit, error) {
	unit, err := f.store.Load(ctx, unitID)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	round := unit.CurrentRound()
	if request.Round != round || round == 0 {
		return model.DecisionUnit{}, model.ErrConflict
	}
	pending := unit.PendingRoles(round)
	matched := []string{}
	for _, role := range pending {
		if model.Contains(actor.Roles, role) {
			matched = append(matched, role)
		}
	}
	if len(matched) != 1 {
		return model.DecisionUnit{}, model.ErrWrongRole
	}
	expiresAt := unit.EvidenceExpiresAt
	evidence := struct {
		DecisionUnitID     string   `json:"decisionUnitId"`
		Role               string   `json:"role"`
		ActorID            string   `json:"actorId"`
		ActorAuthenticated bool     `json:"actorAuthenticated"`
		Round              int      `json:"round"`
		Facts              []string `json:"facts"`
		Impacts            []string `json:"impacts"`
		Unknowns           []string `json:"unknowns"`
		SelectedOptionID   string   `json:"selectedOptionId,omitempty"`
		EvidenceExpiresAt  string   `json:"evidenceExpiresAt"`
	}{unit.ID, matched[0], actor.ID, true, round, normalizedStrings(request.Facts), normalizedStrings(request.Impacts), normalizedStrings(request.Unknowns), strings.TrimSpace(request.SelectedOptionID), expiresAt.UTC().Format(time.RFC3339Nano)}
	exact, err := json.Marshal(evidence)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	submission := model.RoleSubmission{Role: matched[0], ActorID: actor.ID, Round: round, Facts: evidence.Facts, Impacts: evidence.Impacts, Unknowns: evidence.Unknowns, SelectedOptionID: evidence.SelectedOptionID, CanonicalEvidence: model.EncodeExact(exact), EvidenceDigest: model.Digest(exact), Passed: true, SubmittedAt: f.now().UTC(), EvidenceExpiresAt: expiresAt, MFAProvenance: actor.MFAProvenance}
	return f.submitCanonical(ctx, actor, unit, submission)
}

func (f *Facade) submitCanonical(ctx context.Context, actor Actor, unit model.DecisionUnit, s model.RoleSubmission) (model.DecisionUnit, error) {
	s.SubmissionID = f.ids()
	if err := unit.ValidateSubmission(s, f.now()); err != nil {
		return model.DecisionUnit{}, err
	}
	unit.Submissions = append(unit.Submissions, s)
	event, err := model.NewEvent(unit.ID, f.ids(), "RoleSubmissionRecorded", actor.ID, unit.LastSequence+1, unit.LastHash, s, f.now())
	if err != nil {
		return model.DecisionUnit{}, err
	}
	unit.LastSequence = event.Sequence
	unit.LastHash = event.Hash
	if err = f.store.Append(ctx, event.Sequence-1, ports.CommitPacket{Unit: unit, Events: []model.Event{event}, AuditAction: "role_submission_recorded", AuditActor: actor.ID, OutboxType: "HumanRoleSubmissionRecorded", OutboxPayload: map[string]any{"decisionUnitId": unit.ID, "role": s.Role, "round": s.Round}}); err != nil {
		return model.DecisionUnit{}, err
	}
	return unit, nil
}
func (f *Facade) Seal(ctx context.Context, actor Actor, unitID string, round int) (model.DecisionUnit, error) {
	unit, err := f.store.Load(ctx, unitID)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	if err = unit.CanSeal(round); err != nil {
		return model.DecisionUnit{}, err
	}
	unit.SealedRounds = append(unit.SealedRounds, round)
	event, err := model.NewEvent(unit.ID, f.ids(), "RoundSealed", actor.ID, unit.LastSequence+1, unit.LastHash, map[string]any{"round": round}, f.now())
	if err != nil {
		return model.DecisionUnit{}, err
	}
	unit.LastSequence = event.Sequence
	unit.LastHash = event.Hash
	if err = f.store.Append(ctx, event.Sequence-1, ports.CommitPacket{Unit: unit, Events: []model.Event{event}, AuditAction: "round_sealed", AuditActor: actor.ID, OutboxType: "HumanDecisionRoundSealed", OutboxPayload: map[string]any{"decisionUnitId": unit.ID, "round": round}}); err != nil {
		return model.DecisionUnit{}, err
	}
	return unit, nil
}

type FinalizeInput struct {
	SelectedOptionID string `json:"selectedOptionId"`
	Note             string `json:"note,omitempty"`
}

func (f *Facade) Finalize(ctx context.Context, actor Actor, unitID string, input FinalizeInput) (model.DecisionUnit, error) {
	unit, err := f.store.Load(ctx, unitID)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	now := f.now().UTC()
	if !model.Contains(actor.Roles, unit.AccountableRole) {
		return model.DecisionUnit{}, model.ErrWrongRole
	}
	if err = unit.CanFinalize(actor.ID, now); err != nil {
		return model.DecisionUnit{}, err
	}
	selected := strings.TrimSpace(input.SelectedOptionID)
	if !unit.HasOption(selected) {
		return model.DecisionUnit{}, model.ErrInvalid
	}
	eligibility, found := unit.EligibilityFor(selected)
	if !found || !eligibility.Eligible || len(eligibility.FailedHardGateIDs) != 0 {
		return model.DecisionUnit{}, model.ErrHardVeto
	}
	expiresAt := unit.EvidenceExpiresAt
	for _, submission := range unit.Submissions {
		if submission.EvidenceExpiresAt.Before(expiresAt) {
			expiresAt = submission.EvidenceExpiresAt
		}
	}
	if !expiresAt.After(now) {
		return model.DecisionUnit{}, model.ErrEvidenceExpired
	}
	decision := model.DecisionRecord{ID: f.ids(), SelectedOptionID: selected, ActorID: actor.ID, RecordedAt: now, ExpiresAt: expiresAt.UTC()}
	claims := model.AuthorityReceiptClaims{SchemaVersion: 1, ReceiptID: decision.ID, DecisionID: decision.ID, DecisionUnitID: unit.ID, ActorID: actor.ID, ActorAuthenticated: true, Role: unit.AccountableRole, Scope: unit.Scope, EvidenceFingerprint: unit.Fingerprint, DecisionKind: unit.DecisionKind, Actions: unit.Actions, IssuedAt: now.Format(time.RFC3339Nano), ExpiresAt: expiresAt.UTC().Format(time.RFC3339Nano), ProviderKind: f.provider.ProviderKind, ProviderVersion: f.provider.ProviderVersion, ProviderCommit: f.provider.ProviderCommit, ContractVersion: f.provider.ContractVersion, Issuer: f.provider.Issuer, NativeProtection: false, ReleaseEligible: false, TestKey: f.signer.TestKey()}
	exact, err := model.CanonicalAuthorityClaimBytes(claims)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	signature, err := f.signer.Sign(exact)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	receipt := model.AuthorizationReceipt{SchemaVersion: 1, CanonicalBytes: model.EncodeExact(exact), PayloadDigest: model.Digest(exact), SignatureAlgorithm: "ed25519", KeyID: f.signer.KeyID(), Signature: base64.RawStdEncoding.EncodeToString(signature), ReceiptID: decision.ID, DecisionID: decision.ID, DecisionUnitID: unit.ID, State: model.ReceiptAvailable, PreviousGeneration: 0, Generation: 1, ETag: model.ReceiptETag(decision.ID, 1), ChainCommit: unit.LastHash, ProviderKind: f.provider.ProviderKind, ProviderVersion: f.provider.ProviderVersion, ProviderCommit: f.provider.ProviderCommit, ContractVersion: f.provider.ContractVersion, Issuer: f.provider.Issuer, IssuedAt: now, ExpiresAt: expiresAt.UTC(), TestKey: f.signer.TestKey(), ReleaseEligible: false}
	unit.Decision, unit.Receipt = &decision, &receipt
	event, err := model.NewEvent(unit.ID, f.ids(), "DecisionFinalized", actor.ID, unit.LastSequence+1, unit.LastHash, map[string]any{"decisionId": decision.ID, "receiptDigest": receipt.PayloadDigest}, now)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	unit.LastSequence, unit.LastHash = event.Sequence, event.Hash
	receipt.ChainCommit = event.Hash
	if err = f.signReceiptState(&receipt); err != nil {
		return model.DecisionUnit{}, err
	}
	unit.Receipt = &receipt
	if err = f.store.Append(ctx, event.Sequence-1, ports.CommitPacket{Unit: unit, Events: []model.Event{event}, AuditAction: "decision_finalized", AuditActor: actor.ID, Receipt: &receipt, OutboxType: "HumanDecisionFinalized", OutboxPayload: map[string]any{"decisionUnitId": unit.ID, "decisionId": decision.ID, "receiptDigest": receipt.PayloadDigest}}); err != nil {
		return model.DecisionUnit{}, err
	}
	return unit, nil
}
func (f *Facade) Read(ctx context.Context, actor Actor, id string) (model.DecisionUnit, error) {
	unit, err := f.store.Load(ctx, id)
	if err != nil {
		return model.DecisionUnit{}, err
	}
	if !visibleTo(unit, actor) {
		return model.DecisionUnit{}, model.ErrWrongRole
	}
	return projectForActor(unit, actor), nil
}
func (f *Facade) List(ctx context.Context, actor Actor) ([]model.DecisionUnit, error) {
	units, err := f.store.List(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]model.DecisionUnit, 0, len(units))
	for _, unit := range units {
		if visibleTo(unit, actor) {
			out = append(out, projectForActor(unit, actor))
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.Before(out[j].CreatedAt) })
	return out, nil
}
func visibleTo(unit model.DecisionUnit, actor Actor) bool {
	if len(actor.Roles) == 0 {
		return false
	}
	for _, role := range unit.RequiredRoles {
		if model.Contains(actor.Roles, role) {
			return true
		}
	}
	return false
}
func projectForActor(unit model.DecisionUnit, actor Actor) model.DecisionUnit {
	projected := unit
	projected.Submissions = nil
	for _, submission := range unit.Submissions {
		if model.Contains(actor.Roles, submission.Role) {
			projected.Submissions = append(projected.Submissions, submission)
		}
	}
	if !unit.RoundSealed(1) {
		projected.Options = nil
		projected.Eligibility = nil
	}
	return projected
}
func (f *Facade) Receipt(ctx context.Context, decisionID string) (model.AuthorizationReceipt, error) {
	receipt, err := f.store.Receipt(ctx, decisionID)
	if err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if err = f.hydrateAndSignReceipt(&receipt); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	return receipt, nil
}
func (f *Facade) PublicKey(keyID string) (SigningPublicKey, error) {
	if strings.TrimSpace(keyID) != f.signer.KeyID() {
		return SigningPublicKey{}, model.ErrNotFound
	}
	return SigningPublicKey{KeyID: f.signer.KeyID(), Algorithm: "Ed25519", PublicKey: base64.RawStdEncoding.EncodeToString(f.signer.PublicKey()), ReleaseEligible: false, ExternalBlocker: "HOSTED_HUMAN_AUTHORITY_LIVE_EVIDENCE"}, nil
}
func (f *Facade) Idempotency(ctx context.Context, operation, key string) (ports.IdempotencyRecord, bool, error) {
	return f.store.Idempotency(ctx, operation, key)
}
func (f *Facade) SaveIdempotency(ctx context.Context, record ports.IdempotencyRecord) error {
	return f.store.SaveIdempotency(ctx, record)
}
func (f *Facade) Outbox(ctx context.Context, limit int) ([]ports.OutboxRecord, error) {
	return f.store.Outbox(ctx, limit)
}
func (f *Facade) Events(ctx context.Context, id string) ([]model.Event, error) {
	return f.store.Events(ctx, id)
}

type TransitionInput struct {
	Fingerprint   string               `json:"fingerprint"`
	Scope         model.CanonicalScope `json:"scope"`
	Action        string               `json:"action"`
	CommandDigest string               `json:"commandDigest"`
}

func (f *Facade) Consume(ctx context.Context, actor Actor, decisionID, expectedETag, idempotencyKey string, input TransitionInput) (model.AuthorizationReceipt, error) {
	receipt, err := f.store.TransitionReceipt(ctx, decisionID, model.ReceiptAvailable, model.ReceiptConsumed, expectedETag, idempotencyKey, input.CommandDigest, actor.ID, input.Fingerprint, input.Scope, input.Action, f.now(), "")
	if err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if err = f.hydrateAndSignReceipt(&receipt); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	return receipt, nil
}
func (f *Facade) Revoke(ctx context.Context, actor Actor, decisionID, expectedETag, idempotencyKey, reason string) (model.AuthorizationReceipt, error) {
	reason = strings.TrimSpace(reason)
	if reason == "" {
		return model.AuthorizationReceipt{}, model.ErrInvalid
	}
	receipt, err := f.store.TransitionReceipt(ctx, decisionID, model.ReceiptAvailable, model.ReceiptRevoked, expectedETag, idempotencyKey, model.Digest([]byte(reason)), actor.ID, "", nil, "", f.now(), reason)
	if err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if err = f.hydrateAndSignReceipt(&receipt); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	return receipt, nil
}
func VerifyReceipt(publicKey ed25519.PublicKey, receipt model.AuthorizationReceipt) error {
	exact, err := model.DecodeExact(receipt.CanonicalBytes)
	if err != nil {
		return model.ErrInvalid
	}
	if subtle.ConstantTimeCompare([]byte(model.Digest(exact)), []byte(receipt.PayloadDigest)) != 1 {
		return model.ErrReceiptMismatch
	}
	sig, err := base64.RawStdEncoding.DecodeString(receipt.Signature)
	if err != nil || !ed25519.Verify(publicKey, exact, sig) {
		return model.ErrReceiptMismatch
	}
	return nil
}

func (f *Facade) GitHubMapping(repository, environment string) (GitHubMapping, bool) {
	for _, m := range f.githubMappings {
		if m.Repository == repository && m.Environment == environment {
			return m, true
		}
	}
	return GitHubMapping{}, false
}
func (f *Facade) RecordGitHub(ctx context.Context, approval model.GitHubApproval) (model.GitHubApproval, bool, error) {
	if approval.NativeProtection {
		return model.GitHubApproval{}, false, model.ErrInvalid
	}
	mapping, ok := f.GitHubMapping(approval.Repository, approval.Environment)
	if !ok {
		return model.GitHubApproval{}, false, model.ErrInvalid
	}
	approval.MappedDecisionKind = mapping.DecisionKind
	approval.MappedScope = mapping.Scope
	return f.store.RecordGitHub(ctx, approval)
}
func ScopeAllowed(grants []string, required string) bool { return model.Contains(grants, required) }
func VerifyGeneratedContractSHA(source []byte) error {
	if model.Digest(source) != model.CanonicalHumanContractSHA256 {
		return fmt.Errorf("canonical Human contract drift: generated=%s actual=%s", model.CanonicalHumanContractSHA256, model.Digest(source))
	}
	return nil
}

func normalizedStrings(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			out = append(out, value)
		}
	}
	return out
}

func (f *Facade) hydrateAndSignReceipt(receipt *model.AuthorizationReceipt) error {
	exact, err := model.DecodeExact(receipt.CanonicalBytes)
	if err != nil {
		return model.ErrReceiptMismatch
	}
	var claims model.AuthorityReceiptClaims
	if err = json.Unmarshal(exact, &claims); err != nil {
		return model.ErrReceiptMismatch
	}
	if claims.ReceiptID != receipt.DecisionID || !model.VerifyAuthorityObjectFields(exact, model.GeneratedAuthorityReceiptClaimFields) || model.Digest(exact) != receipt.PayloadDigest {
		return model.ErrReceiptMismatch
	}
	receipt.SchemaVersion = 1
	receipt.ReceiptID = claims.ReceiptID
	receipt.DecisionUnitID = claims.DecisionUnitID
	receipt.SignatureAlgorithm = "ed25519"
	receipt.ProviderKind = claims.ProviderKind
	receipt.ProviderVersion = claims.ProviderVersion
	receipt.ProviderCommit = claims.ProviderCommit
	receipt.ContractVersion = claims.ContractVersion
	receipt.Issuer = claims.Issuer
	receipt.ETag = model.ReceiptETag(receipt.ReceiptID, receipt.Generation)
	return f.signReceiptState(receipt)
}
func (f *Facade) signReceiptState(receipt *model.AuthorizationReceipt) error {
	attestation := model.AuthorityStateAttestation{SchemaVersion: 1, ReceiptID: receipt.ReceiptID, DecisionID: receipt.DecisionID, DecisionUnitID: receipt.DecisionUnitID, PayloadDigest: receipt.PayloadDigest, State: receipt.State, PreviousGeneration: receipt.PreviousGeneration, Generation: receipt.Generation, ETag: receipt.ETag, WinnerIdempotencyKey: receipt.WinnerIdempotencyKey, WinnerCommandDigest: receipt.WinnerCommandDigest, StateActorID: receipt.StateActor, StateAt: receipt.StateAt, ChainCommit: receipt.ChainCommit, ProviderKind: receipt.ProviderKind, ProviderVersion: receipt.ProviderVersion, ProviderCommit: receipt.ProviderCommit, ContractVersion: receipt.ContractVersion, Issuer: receipt.Issuer}
	exact, err := model.CanonicalStateAttestationBytes(attestation)
	if err != nil {
		return err
	}
	signature, err := f.signer.Sign(exact)
	if err != nil {
		return err
	}
	receipt.AttestationCanonicalBytes = model.EncodeExact(exact)
	receipt.AttestationDigest = model.Digest(exact)
	receipt.AttestationSignature = base64.RawStdEncoding.EncodeToString(signature)
	return nil
}
func isCanonicalDigest(value string) bool {
	if len(value) != 71 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, character := range value[7:] {
		if !(character >= '0' && character <= '9') && !(character >= 'a' && character <= 'f') {
			return false
		}
	}
	return true
}
