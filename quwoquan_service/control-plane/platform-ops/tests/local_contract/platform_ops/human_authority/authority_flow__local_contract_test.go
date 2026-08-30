// spec_ref:
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-001.t1
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-001.t2
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-001.t3
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-001.t4
package local_contract

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	authorityapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/application"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	authoritystore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/infrastructure/persistence"
)

var testNow = time.Date(2026, 8, 30, 2, 0, 0, 0, time.UTC)

func newFacade(t *testing.T) (*authorityapp.Facade, *authoritystore.MemoryStore, ed25519.PublicKey) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	signer, err := authorityapp.NewEd25519Signer("test-key", priv, true)
	if err != nil {
		t.Fatal(err)
	}
	store := authoritystore.NewMemoryStore()
	facade, err := authorityapp.NewFacade(store, signer, nil)
	if err != nil {
		t.Fatal(err)
	}
	counter := 0
	facade.WithClock(func() time.Time { return testNow }).WithIDs(func() string { counter++; return "id-" + time.Unix(int64(counter), 0).UTC().Format("150405") })
	return facade, store, pub
}
func option() model.DecisionOption {
	return model.DecisionOption{OptionID: "approve", NeutralLabel: "批准", UserOutcome: "候选可发布", BusinessOutcome: "进入受控灰度", Cost: "已冻结", TimeToEffect: "窗口内", Risk: "受签名与 CAS 约束", Reversibility: "可撤销", ScopeChange: "无", Unknowns: []string{}, NextStep: "consume"}
}
func baseUnit() model.DecisionUnit {
	return model.DecisionUnit{ID: "unit-1", Stage: "production_campaign", DecisionKind: "production_campaign_approval", RiskClassification: "production_critical", Scope: model.CanonicalScope{"objective": "objective-1"}, Target: "prod", Fingerprint: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Actions: []string{"promote"}, Options: []model.DecisionOption{option()}, AuthorizedRole: "engineering_delivery_owner", EvidenceExpiresAt: testNow.Add(time.Hour)}
}
func actor(id string, roles ...string) authorityapp.Actor {
	return authorityapp.Actor{ID: id, Roles: roles, MFAProvenance: "verified"}
}
func submitAll(t *testing.T, f *authorityapp.Facade, u model.DecisionUnit, round int, actors map[string]string, selectedOption string) model.DecisionUnit {
	t.Helper()
	for len(u.PendingRoles(round)) > 0 {
		role := u.PendingRoles(round)[0]
		var err error
		u, err = f.Submit(context.Background(), actor(actors[role], role), u.ID, authorityapp.SubmitRequest{Round: round, Facts: []string{"verified"}, Impacts: []string{"bounded"}, Unknowns: []string{}, SelectedOptionID: selectedOption})
		if err != nil {
			t.Fatalf("submit role=%s round=%d: %v", role, round, err)
		}
	}
	return u
}
func completeTwoRounds(t *testing.T, f *authorityapp.Facade, u model.DecisionUnit, samePrincipal bool) model.DecisionUnit {
	actors := map[string]string{}
	for _, role := range u.RequiredRoles {
		actors[role] = "actor-" + role
		if samePrincipal {
			actors[role] = "same"
		}
	}
	for round := 1; round <= 2; round++ {
		selected := ""
		if round == 2 {
			selected = "approve"
		}
		u = submitAll(t, f, u, round, actors, selected)
		var err error
		u, err = f.Seal(context.Background(), actor("sealer"), u.ID, round)
		if err != nil {
			t.Fatal(err)
		}
	}
	return u
}
func TestMetadataKeepsRouteIdentityOutOfPortalBodiesAndDeclaresListProjection(t *testing.T) {
	fieldsRaw, err := os.ReadFile("../../../../contracts/platform_ops/human_authority/fields.yaml")
	if err != nil {
		t.Fatal(err)
	}
	operationsRaw, err := os.ReadFile("../../../../contracts/platform_ops/human_authority/operations.yaml")
	if err != nil {
		t.Fatal(err)
	}
	projectionRaw, err := os.ReadFile("../../../../contracts/platform_ops/human_authority/projections/decision_unit_slice.yaml")
	if err != nil {
		t.Fatal(err)
	}

	var fieldsDocument struct {
		Types map[string]struct {
			Fields []struct {
				Name string `yaml:"name"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	if err = yaml.Unmarshal(fieldsRaw, &fieldsDocument); err != nil {
		t.Fatal(err)
	}
	for _, requestEntity := range []string{"SubmitHumanRoleEvidenceRequest", "FinalizeHumanDecisionRequest"} {
		entity, found := fieldsDocument.Types[requestEntity]
		if !found {
			t.Fatalf("request entity %s is absent", requestEntity)
		}
		fieldNames := make(map[string]struct{}, len(entity.Fields))
		for _, field := range entity.Fields {
			fieldNames[field.Name] = struct{}{}
		}
		if _, found = fieldNames["decisionUnitId"]; !found {
			t.Fatalf("%s lost route-only decisionUnitId", requestEntity)
		}
	}

	var operationsDocument struct {
		APIRoutes []struct {
			Operation       string `yaml:"operation"`
			RequestEntity   string `yaml:"request_entity"`
			RequestBodyKind string `yaml:"request_body_kind"`
			RequestBindings struct {
				Path []struct {
					Name  string `yaml:"name"`
					Field string `yaml:"field"`
				} `yaml:"path"`
			} `yaml:"request_bindings"`
		} `yaml:"api_routes"`
	}
	if err = yaml.Unmarshal(operationsRaw, &operationsDocument); err != nil {
		t.Fatal(err)
	}
	wantRequests := map[string]string{
		"SubmitHumanRoleEvidence": "SubmitHumanRoleEvidenceRequest",
		"FinalizeHumanDecision":   "FinalizeHumanDecisionRequest",
	}
	for operation, requestEntity := range wantRequests {
		found := false
		for _, route := range operationsDocument.APIRoutes {
			if route.Operation != operation {
				continue
			}
			found = true
			if route.RequestEntity != requestEntity || route.RequestBodyKind != "object" ||
				len(route.RequestBindings.Path) != 1 ||
				route.RequestBindings.Path[0].Name != "decisionUnitId" ||
				route.RequestBindings.Path[0].Field != "decisionUnitId" {
				t.Fatalf("%s route identity/body split drifted: %+v", operation, route)
			}
		}
		if !found {
			t.Fatalf("operation %s is absent", operation)
		}
	}

	var projection struct {
		ReadModel string `yaml:"read_model"`
		Fields    []struct {
			Name string `yaml:"name"`
			Type string `yaml:"type"`
		} `yaml:"fields"`
	}
	if err = yaml.Unmarshal(projectionRaw, &projection); err != nil {
		t.Fatal(err)
	}
	if projection.ReadModel != "DecisionUnitSlice" || len(projection.Fields) != 1 ||
		projection.Fields[0].Name != "items" || projection.Fields[0].Type != "[]DecisionUnit" {
		t.Fatalf("DecisionUnitSlice projection is incomplete: %+v", projection)
	}
}

func TestGeneratedContractBindingHasProvenanceAndNoDrift(t *testing.T) {
	raw, err := os.ReadFile("../../../../../../../quwoquan_ops/policies/human_agent_delivery_contract.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if err = authorityapp.VerifyGeneratedContractSHA(raw); err != nil {
		t.Fatal(err)
	}
	if model.CanonicalHumanContractSource != "quwoquan_ops/policies/human_agent_delivery_contract.yaml" {
		t.Fatal(model.CanonicalHumanContractSource)
	}
}
func TestTwoRoundsSealHardVetoSoDAndExactSignature(t *testing.T) {
	f, _, pub := newFacade(t)
	u, err := f.Create(context.Background(), actor("creator"), baseUnit())
	if err != nil {
		t.Fatal(err)
	}
	if _, err = f.Finalize(context.Background(), actor("release", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"}); !errors.Is(err, model.ErrRoundsUnsealed) {
		t.Fatalf("unsealed finalize=%v", err)
	}
	u = completeTwoRounds(t, f, u, false)
	u, err = f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
	if err != nil {
		t.Fatal(err)
	}
	if u.Receipt == nil || !u.Receipt.TestKey || u.Receipt.ReleaseEligible {
		t.Fatalf("receipt eligibility=%+v", u.Receipt)
	}
	if err = authorityapp.VerifyReceipt(pub, *u.Receipt); err != nil {
		t.Fatal(err)
	}
	attestation, err := model.DecodeExact(u.Receipt.AttestationCanonicalBytes)
	if err != nil || !model.VerifyAuthorityObjectFields(attestation, model.GeneratedAuthorityStateAttestationFields) {
		t.Fatalf("attestation fields err=%v", err)
	}
	attestationSignature, err := base64.RawStdEncoding.DecodeString(u.Receipt.AttestationSignature)
	if err != nil || !ed25519.Verify(pub, attestation, attestationSignature) {
		t.Fatal("state attestation signature invalid")
	}
	wrapper, err := json.Marshal(*u.Receipt)
	if err != nil || !model.VerifyAuthorityObjectFields(wrapper, model.GeneratedAuthorizationReceiptWrapperFields) {
		t.Fatalf("wrapper fields err=%v", err)
	}
	tampered := *u.Receipt
	tampered.PayloadDigest = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	if err = authorityapp.VerifyReceipt(pub, tampered); !errors.Is(err, model.ErrReceiptMismatch) {
		t.Fatalf("tamper=%v", err)
	}
}
func TestHardVetoAndSoDRejectWithoutReceipt(t *testing.T) {
	t.Run("hard veto", func(t *testing.T) {
		f, _, _ := newFacade(t)
		input := baseUnit()
		input.RiskClassification = ""
		input.SoDPolicy = "role-record-only"
		input.Eligibility = []model.Eligibility{{OptionID: "approve", Eligible: false, FailedHardGateIDs: []string{"veto"}}}
		u, _ := f.Create(context.Background(), actor("creator"), input)
		u = completeTwoRounds(t, f, u, false)
		_, err := f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
		if !errors.Is(err, model.ErrHardVeto) {
			t.Fatalf("err=%v", err)
		}
	})
	t.Run("same principal", func(t *testing.T) {
		f, _, _ := newFacade(t)
		u, _ := f.Create(context.Background(), actor("creator"), baseUnit())
		u = completeTwoRounds(t, f, u, true)
		_, err := f.Finalize(context.Background(), actor("same", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
		if !errors.Is(err, model.ErrSoD) {
			t.Fatalf("err=%v", err)
		}
	})
}
func TestConsumeRevokeCASBindingAndExpiry(t *testing.T) {
	f, store, _ := newFacade(t)
	u, _ := f.Create(context.Background(), actor("creator"), baseUnit())
	u = completeTwoRounds(t, f, u, false)
	u, err := f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
	if err != nil {
		t.Fatal(err)
	}
	input := authorityapp.TransitionInput{Fingerprint: u.Fingerprint, Scope: u.Scope, Action: "promote", CommandDigest: model.Digest([]byte("command"))}
	var wg sync.WaitGroup
	errs := make(chan error, 2)
	wg.Add(2)
	go func() {
		defer wg.Done()
		_, e := f.Consume(context.Background(), actor("executor"), u.Decision.ID, u.Receipt.ETag, "consume-1", input)
		errs <- e
	}()
	go func() {
		defer wg.Done()
		_, e := f.Revoke(context.Background(), actor("revoker"), u.Decision.ID, u.Receipt.ETag, "revoke-1", "stop")
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
			t.Fatalf("race err=%v", e)
		}
	}
	if success != 1 || conflict != 1 {
		t.Fatalf("success=%d conflict=%d", success, conflict)
	}
	events, err := store.Events(context.Background(), u.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = model.VerifyHashChain(events); err != nil {
		t.Fatalf("hash chain=%v", err)
	}
}
func TestCanonicalAuthorityClaimRejectsNonCanonicalActionsAndScope(t *testing.T) {
	base := model.AuthorityReceiptClaims{SchemaVersion: 1, ReceiptID: "decision-1", DecisionID: "decision-1", DecisionUnitID: "unit-1", ActorID: "actor-1", ActorAuthenticated: true, Role: "engineering_delivery_owner", Scope: model.CanonicalScope{"objective": "objective-1"}, EvidenceFingerprint: "sha256:evidence", DecisionKind: "delivery_authorization", Actions: []string{"create_objective", "observe_objective"}, IssuedAt: "2026-08-30T00:00:00Z", ExpiresAt: "2099-08-30T00:00:00Z", ProviderKind: "hosted-human-authority", ProviderVersion: "provider-v1", ProviderCommit: "sha256:" + strings.Repeat("1", 64), ContractVersion: "human-authority-wire-v1", Issuer: "https://authority.example.com"}
	if _, err := model.CanonicalAuthorityClaimBytes(base); err != nil {
		t.Fatalf("canonical claim rejected: %v", err)
	}
	for name, mutate := range map[string]func(*model.AuthorityReceiptClaims){
		"unsorted-actions": func(value *model.AuthorityReceiptClaims) {
			value.Actions = []string{"observe_objective", "create_objective"}
		},
		"duplicate-actions": func(value *model.AuthorityReceiptClaims) {
			value.Actions = []string{"create_objective", "create_objective"}
		},
		"ambiguous-scope": func(value *model.AuthorityReceiptClaims) {
			value.Scope = model.CanonicalScope{"objective": "objective-1", "increment": "increment-1"}
		},
		"unknown-scope": func(value *model.AuthorityReceiptClaims) { value.Scope = model.CanonicalScope{"target": "objective-1"} },
	} {
		t.Run(name, func(t *testing.T) {
			candidate := base
			mutate(&candidate)
			if _, err := model.CanonicalAuthorityClaimBytes(candidate); err == nil {
				t.Fatal("non-canonical claim accepted")
			}
		})
	}
}

func TestConsumeSameWinnerIsIdempotentAndDifferentWinnerConflicts(t *testing.T) {
	f, _, _ := newFacade(t)
	u, _ := f.Create(context.Background(), actor("creator"), baseUnit())
	u = completeTwoRounds(t, f, u, false)
	u, _ = f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
	input := authorityapp.TransitionInput{Fingerprint: u.Fingerprint, Scope: u.Scope, Action: "promote", CommandDigest: model.Digest([]byte("command"))}
	first, err := f.Consume(context.Background(), actor("executor"), u.Decision.ID, u.Receipt.ETag, "consume-1", input)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := f.Consume(context.Background(), actor("executor"), u.Decision.ID, u.Receipt.ETag, "consume-1", input)
	if err != nil || replay.Generation != first.Generation || replay.WinnerCommandDigest != first.WinnerCommandDigest {
		t.Fatalf("replay=%+v err=%v", replay, err)
	}
	if _, err = f.Consume(context.Background(), actor("other"), u.Decision.ID, u.Receipt.ETag, "consume-2", input); !errors.Is(err, model.ErrConflict) {
		t.Fatalf("loser=%v", err)
	}
}

func TestConsumeRejectsFingerprintScopeActionAndExpiry(t *testing.T) {
	cases := []struct {
		name    string
		input   authorityapp.TransitionInput
		advance time.Duration
		want    error
	}{{"fingerprint", authorityapp.TransitionInput{Fingerprint: "bad", Scope: model.CanonicalScope{"objective": "objective-1"}, Action: "promote", CommandDigest: model.Digest([]byte("command"))}, 0, model.ErrReceiptMismatch}, {"scope", authorityapp.TransitionInput{Fingerprint: baseUnit().Fingerprint, Scope: model.CanonicalScope{"objective": "other"}, Action: "promote", CommandDigest: model.Digest([]byte("command"))}, 0, model.ErrReceiptMismatch}, {"action", authorityapp.TransitionInput{Fingerprint: baseUnit().Fingerprint, Scope: model.CanonicalScope{"objective": "objective-1"}, Action: "delete", CommandDigest: model.Digest([]byte("command"))}, 0, model.ErrReceiptMismatch}, {"expiry", authorityapp.TransitionInput{Fingerprint: baseUnit().Fingerprint, Scope: model.CanonicalScope{"objective": "objective-1"}, Action: "promote", CommandDigest: model.Digest([]byte("command"))}, 2 * time.Minute, model.ErrReceiptExpired}}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f, _, _ := newFacade(t)
			u, _ := f.Create(context.Background(), actor("creator"), baseUnit())
			u = completeTwoRounds(t, f, u, false)
			u, _ = f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
			if tc.name == "expiry" {
				tc.advance = 2 * time.Hour
			}
			f.WithClock(func() time.Time { return testNow.Add(tc.advance) })
			_, err := f.Consume(context.Background(), actor("executor"), u.Decision.ID, u.Receipt.ETag, "consume-negative", tc.input)
			if !errors.Is(err, tc.want) {
				t.Fatalf("err=%v", err)
			}
		})
	}
}
func TestRoleMapperRejectsRequestBodyAuthority(t *testing.T) {
	mapper, err := authorityapp.NewRoleMapper(map[string][]string{"ops-release": {"release_owner"}})
	if err != nil {
		t.Fatal(err)
	}
	roles := mapper.RolesFor([]string{"untrusted-request-role", "ops-release"})
	if len(roles) != 1 || roles[0] != "release_owner" {
		t.Fatalf("roles=%v", roles)
	}
}

func TestFinalizeUsesFrozenAuthorityAndMinimumEvidenceExpiry(t *testing.T) {
	f, _, _ := newFacade(t)
	u, err := f.Create(context.Background(), actor("creator"), baseUnit())
	if err != nil {
		t.Fatal(err)
	}
	u = completeTwoRounds(t, f, u, false)
	u, err = f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve", Note: "client cannot alter target"})
	if err != nil {
		t.Fatal(err)
	}
	raw, err := model.DecodeExact(u.Receipt.CanonicalBytes)
	if err != nil {
		t.Fatal(err)
	}
	var payload model.AuthorityReceiptClaims
	if err = json.Unmarshal(raw, &payload); err != nil {
		t.Fatal(err)
	}
	if payload.DecisionUnitID != u.ID || payload.Scope["objective"] != baseUnit().Scope["objective"] || payload.EvidenceFingerprint != baseUnit().Fingerprint || !model.Contains(payload.Actions, "promote") {
		t.Fatalf("server authority drifted: %+v", payload)
	}
	if !u.Decision.ExpiresAt.Equal(testNow.Add(time.Hour)) {
		t.Fatalf("expiry=%s", u.Decision.ExpiresAt)
	}
	if u.Receipt.ReleaseEligible {
		t.Fatal("live external blocker must keep receipt release-ineligible")
	}
}
func TestFinalizeRejectsUnknownOrHardGatedOption(t *testing.T) {
	f, _, _ := newFacade(t)
	u, _ := f.Create(context.Background(), actor("creator"), baseUnit())
	u = completeTwoRounds(t, f, u, false)
	if _, err := f.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "missing"}); !errors.Is(err, model.ErrInvalid) {
		t.Fatalf("unknown=%v", err)
	}
	f2, _, _ := newFacade(t)
	gated := baseUnit()
	gated.Eligibility = []model.Eligibility{{OptionID: "approve", Eligible: false, FailedHardGateIDs: []string{"gate-1"}}}
	u, _ = f2.Create(context.Background(), actor("creator"), gated)
	u = completeTwoRounds(t, f2, u, false)
	if _, err := f2.Finalize(context.Background(), actor("actor-release_owner", "release_owner"), u.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"}); !errors.Is(err, model.ErrHardVeto) {
		t.Fatalf("gated=%v", err)
	}
}
