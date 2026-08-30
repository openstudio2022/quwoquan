package model

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalid         = errors.New("human authority: invalid")
	ErrNotFound        = errors.New("human authority: not found")
	ErrConflict        = errors.New("human authority: conflict")
	ErrWrongRole       = errors.New("human authority: wrong role")
	ErrRoundsUnsealed  = errors.New("human authority: both rounds must be sealed")
	ErrHardVeto        = errors.New("human authority: hard veto failed")
	ErrSoD             = errors.New("human authority: separation of duties failed")
	ErrEvidenceExpired = errors.New("human authority: evidence expired")
	ErrReceiptExpired  = errors.New("human authority: receipt expired")
	ErrReceiptMismatch = errors.New("human authority: receipt binding mismatch")
)

const (
	ReceiptAvailable = "available"
	ReceiptConsumed  = "consumed"
	ReceiptRevoked   = "revoked"
)

type DecisionOption struct {
	OptionID        string   `json:"optionId"`
	NeutralLabel    string   `json:"neutralLabel"`
	UserOutcome     string   `json:"userOutcome"`
	BusinessOutcome string   `json:"businessOutcome"`
	Cost            string   `json:"cost"`
	TimeToEffect    string   `json:"timeToEffect"`
	Risk            string   `json:"risk"`
	Reversibility   string   `json:"reversibility"`
	ScopeChange     string   `json:"scopeChange"`
	Unknowns        []string `json:"unknowns"`
	NextStep        string   `json:"nextStep"`
}

type DecisionUnit struct {
	ID                 string                `json:"decisionUnitId"`
	Stage              string                `json:"stage"`
	DecisionKind       string                `json:"decisionKind"`
	RequiredRoles      []string              `json:"requiredRoles"`
	HardVetoRoles      []string              `json:"hardVetoRoles"`
	AccountableRole    string                `json:"accountableRole"`
	AuthorizedRole     string                `json:"authorizedRole"`
	SoDPolicy          string                `json:"sodPolicy"`
	RiskClassification string                `json:"riskClassification,omitempty"`
	Scope              CanonicalScope        `json:"scope"`
	Target             string                `json:"target"`
	Fingerprint        string                `json:"fingerprint"`
	Actions            []string              `json:"actions"`
	Options            []DecisionOption      `json:"options"`
	EvidenceExpiresAt  time.Time             `json:"evidenceExpiresAt"`
	CreatedAt          time.Time             `json:"createdAt"`
	SealedRounds       []int                 `json:"sealedRounds"`
	Submissions        []RoleSubmission      `json:"submissions"`
	Eligibility        []Eligibility         `json:"eligibility,omitempty"`
	Decision           *DecisionRecord       `json:"decision,omitempty"`
	Receipt            *AuthorizationReceipt `json:"receipt,omitempty"`
	LastSequence       int64                 `json:"lastSequence"`
	LastHash           string                `json:"lastHash"`
}

type RoleSubmission struct {
	SubmissionID      string    `json:"submissionId"`
	Role              string    `json:"role"`
	ActorID           string    `json:"actorId"`
	Round             int       `json:"round"`
	Facts             []string  `json:"facts"`
	Impacts           []string  `json:"impacts"`
	Unknowns          []string  `json:"unknowns"`
	SelectedOptionID  string    `json:"selectedOptionId,omitempty"`
	CanonicalEvidence string    `json:"canonicalEvidenceBytes"`
	EvidenceDigest    string    `json:"evidenceDigest"`
	Passed            bool      `json:"passed"`
	SubmittedAt       time.Time `json:"submittedAt"`
	EvidenceExpiresAt time.Time `json:"evidenceExpiresAt"`
	MFAProvenance     string    `json:"mfaProvenance"`
}

type Eligibility struct {
	OptionID          string   `json:"optionId"`
	Eligible          bool     `json:"eligible"`
	FailedHardGateIDs []string `json:"failedHardGateIds"`
}

type DecisionRecord struct {
	ID               string    `json:"decisionId"`
	SelectedOptionID string    `json:"selectedOptionId"`
	ActorID          string    `json:"actorId"`
	RecordedAt       time.Time `json:"recordedAt"`
	ExpiresAt        time.Time `json:"expiresAt"`
}

type CanonicalScope map[string]string

type AuthorityReceiptClaims struct {
	SchemaVersion       int            `json:"schemaVersion"`
	ReceiptID           string         `json:"receiptId"`
	DecisionID          string         `json:"decisionId"`
	DecisionUnitID      string         `json:"decisionUnitId"`
	ActorID             string         `json:"actorId"`
	ActorAuthenticated  bool           `json:"actorAuthenticated"`
	Role                string         `json:"role"`
	Scope               CanonicalScope `json:"scope"`
	EvidenceFingerprint string         `json:"evidenceFingerprint"`
	DecisionKind        string         `json:"decisionKind"`
	Actions             []string       `json:"actions"`
	IssuedAt            string         `json:"issuedAt"`
	ExpiresAt           string         `json:"expiresAt"`
	ProviderKind        string         `json:"providerKind"`
	ProviderVersion     string         `json:"providerVersion"`
	ProviderCommit      string         `json:"providerCommit"`
	ContractVersion     string         `json:"contractVersion"`
	Issuer              string         `json:"issuer"`
	NativeProtection    bool           `json:"nativeProtection"`
	ReleaseEligible     bool           `json:"releaseEligible"`
	TestKey             bool           `json:"testKey"`
}

type AuthorityStateAttestation struct {
	SchemaVersion        int    `json:"schemaVersion"`
	ReceiptID            string `json:"receiptId"`
	DecisionID           string `json:"decisionId"`
	DecisionUnitID       string `json:"decisionUnitId"`
	PayloadDigest        string `json:"payloadDigest"`
	State                string `json:"state"`
	PreviousGeneration   int64  `json:"previousGeneration"`
	Generation           int64  `json:"generation"`
	ETag                 string `json:"etag"`
	WinnerIdempotencyKey string `json:"winnerIdempotencyKey"`
	WinnerCommandDigest  string `json:"winnerCommandDigest"`
	StateActorID         string `json:"stateActorId"`
	StateAt              string `json:"stateAt"`
	ChainCommit          string `json:"chainCommit"`
	ProviderKind         string `json:"providerKind"`
	ProviderVersion      string `json:"providerVersion"`
	ProviderCommit       string `json:"providerCommit"`
	ContractVersion      string `json:"contractVersion"`
	Issuer               string `json:"issuer"`
}

type AuthorizationReceipt struct {
	SchemaVersion             int       `json:"schemaVersion"`
	CanonicalBytes            string    `json:"canonicalBytes"`
	PayloadDigest             string    `json:"payloadDigest"`
	SignatureAlgorithm        string    `json:"signatureAlgorithm"`
	KeyID                     string    `json:"keyId"`
	Signature                 string    `json:"signature"`
	AttestationCanonicalBytes string    `json:"attestationCanonicalBytes"`
	AttestationDigest         string    `json:"attestationDigest"`
	AttestationSignature      string    `json:"attestationSignature"`
	ReceiptID                 string    `json:"receiptId"`
	DecisionID                string    `json:"decisionId"`
	DecisionUnitID            string    `json:"decisionUnitId"`
	State                     string    `json:"state"`
	PreviousGeneration        int64     `json:"previousGeneration"`
	Generation                int64     `json:"generation"`
	ETag                      string    `json:"etag"`
	WinnerIdempotencyKey      string    `json:"winnerIdempotencyKey"`
	WinnerCommandDigest       string    `json:"winnerCommandDigest"`
	StateActor                string    `json:"stateActorId"`
	StateAt                   string    `json:"stateAt"`
	ChainCommit               string    `json:"chainCommit"`
	ProviderKind              string    `json:"providerKind"`
	ProviderVersion           string    `json:"providerVersion"`
	ProviderCommit            string    `json:"providerCommit"`
	ContractVersion           string    `json:"contractVersion"`
	Issuer                    string    `json:"issuer"`
	ReleaseEligible           bool      `json:"releaseEligible"`
	TestKey                   bool      `json:"testKey"`
	IssuedAt                  time.Time `json:"-"`
	ExpiresAt                 time.Time `json:"-"`
}

type Event struct {
	EventID      string    `json:"eventId"`
	UnitID       string    `json:"decisionUnitId"`
	Sequence     int64     `json:"sequence"`
	Type         string    `json:"type"`
	ActorID      string    `json:"actorId"`
	Payload      []byte    `json:"payload"`
	PreviousHash string    `json:"previousHash"`
	Hash         string    `json:"hash"`
	OccurredAt   time.Time `json:"occurredAt"`
}

type GitHubApproval struct {
	DeliveryID         string    `json:"deliveryId"`
	PayloadDigest      string    `json:"payloadDigest"`
	InstallationID     int64     `json:"installationId"`
	Repository         string    `json:"repository"`
	RunID              int64     `json:"runId"`
	RunAttempt         int64     `json:"runAttempt"`
	HeadSHA            string    `json:"headSha"`
	CandidateDigest    string    `json:"candidateDigest"`
	Environment        string    `json:"environment"`
	Event              string    `json:"event"`
	Action             string    `json:"action"`
	Requested          bool      `json:"requested"`
	Approved           bool      `json:"approved"`
	NativeProtection   bool      `json:"nativeProtection"`
	MappedDecisionKind string    `json:"mappedDecisionKind,omitempty"`
	MappedScope        string    `json:"mappedScope,omitempty"`
	ActorID            string    `json:"actorId,omitempty"`
	OccurredAt         time.Time `json:"occurredAt"`
}

func Contains(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func ValidRole(value string) bool         { return Contains(GeneratedHumanAuthorityRoles, value) }
func ValidDecisionKind(value string) bool { return Contains(GeneratedDecisionKinds, value) }
func ValidSoD(value string) bool          { return Contains(GeneratedSoDPolicies, value) }
func ValidResponsibility(value string) bool {
	return Contains(GeneratedDecisionUnitResponsibilities, value)
}

func RouterRule(stage, kind string) (GeneratedRouterRule, bool) {
	for _, rule := range GeneratedRouterRules {
		if rule.Stage == stage && rule.DecisionKind == kind {
			return rule, true
		}
	}
	return GeneratedRouterRule{}, false
}

func NewDecisionUnit(unit DecisionUnit) (DecisionUnit, error) {
	unit.ID, unit.Stage, unit.DecisionKind = strings.TrimSpace(unit.ID), strings.TrimSpace(unit.Stage), strings.TrimSpace(unit.DecisionKind)
	if !validCanonicalScope(unit.Scope) {
		return DecisionUnit{}, ErrInvalid
	}
	unit.Target, unit.Fingerprint = strings.TrimSpace(unit.Target), strings.TrimSpace(unit.Fingerprint)
	if unit.ID == "" || len(unit.Scope) == 0 || unit.Target == "" || unit.Fingerprint == "" || !ValidDecisionKind(unit.DecisionKind) || unit.EvidenceExpiresAt.IsZero() {
		return DecisionUnit{}, ErrInvalid
	}
	rule, found := RouterRule(unit.Stage, unit.DecisionKind)
	if !found {
		return DecisionUnit{}, ErrInvalid
	}
	unit.AccountableRole = rule.AccountableRole
	unit.HardVetoRoles = append([]string(nil), rule.HardVetoRoles...)
	if unit.SoDPolicy == "" {
		unit.SoDPolicy = GeneratedDefaultSoDPolicy
	}
	if policy := GeneratedRiskSoDPolicies[strings.TrimSpace(unit.RiskClassification)]; policy != "" {
		unit.SoDPolicy = policy
	}
	if !ValidSoD(unit.SoDPolicy) {
		return DecisionUnit{}, ErrInvalid
	}
	roles := append([]string(nil), unit.RequiredRoles...)
	roles = append(roles, unit.HardVetoRoles...)
	if unit.AccountableRole != "" {
		roles = append(roles, unit.AccountableRole)
	}
	if unit.AuthorizedRole != "" {
		roles = append(roles, unit.AuthorizedRole)
	}
	unit.RequiredRoles = uniqueSorted(roles)
	for _, role := range unit.RequiredRoles {
		if !ValidRole(role) {
			return DecisionUnit{}, ErrInvalid
		}
	}
	unit.Actions = uniqueSorted(unit.Actions)
	if len(unit.Actions) == 0 || len(unit.Options) == 0 {
		return DecisionUnit{}, ErrInvalid
	}
	seenOptions := map[string]struct{}{}
	for index := range unit.Options {
		option := &unit.Options[index]
		option.OptionID = strings.TrimSpace(option.OptionID)
		if option.OptionID == "" || strings.TrimSpace(option.NeutralLabel) == "" || strings.TrimSpace(option.UserOutcome) == "" || strings.TrimSpace(option.BusinessOutcome) == "" || strings.TrimSpace(option.Cost) == "" || strings.TrimSpace(option.TimeToEffect) == "" || strings.TrimSpace(option.Risk) == "" || strings.TrimSpace(option.Reversibility) == "" || strings.TrimSpace(option.ScopeChange) == "" || strings.TrimSpace(option.NextStep) == "" {
			return DecisionUnit{}, ErrInvalid
		}
		if _, duplicated := seenOptions[option.OptionID]; duplicated {
			return DecisionUnit{}, ErrInvalid
		}
		seenOptions[option.OptionID] = struct{}{}
	}
	if len(unit.Eligibility) == 0 {
		unit.Eligibility = make([]Eligibility, 0, len(unit.Options))
		for _, option := range unit.Options {
			unit.Eligibility = append(unit.Eligibility, Eligibility{OptionID: option.OptionID, Eligible: true})
		}
	}
	unit.CreatedAt = unit.CreatedAt.UTC()
	unit.EvidenceExpiresAt = unit.EvidenceExpiresAt.UTC()
	unit.SealedRounds, unit.Submissions = nil, nil
	return unit, nil
}

func (u DecisionUnit) RoundSealed(round int) bool {
	for _, v := range u.SealedRounds {
		if v == round {
			return true
		}
	}
	return false
}

func (u DecisionUnit) ValidateSubmission(s RoleSubmission, now time.Time) error {
	if !ValidRole(s.Role) || !Contains(u.RequiredRoles, s.Role) || strings.TrimSpace(s.ActorID) == "" || (s.Round != 1 && s.Round != 2) || !canonicalDigest(s.EvidenceDigest) || strings.TrimSpace(s.CanonicalEvidence) == "" {
		return ErrInvalid
	}
	if u.RoundSealed(s.Round) {
		return ErrConflict
	}
	if now.After(u.EvidenceExpiresAt) || now.After(s.EvidenceExpiresAt) {
		return ErrEvidenceExpired
	}
	if s.Round == 1 && s.SelectedOptionID != "" {
		return ErrInvalid
	}
	if s.Round == 2 && s.SelectedOptionID != "" && !u.HasOption(s.SelectedOptionID) {
		return ErrInvalid
	}
	for _, existing := range u.Submissions {
		if existing.Round == s.Round && existing.Role == s.Role {
			return ErrConflict
		}
	}
	return nil
}

func (u DecisionUnit) HasOption(optionID string) bool {
	optionID = strings.TrimSpace(optionID)
	for _, option := range u.Options {
		if option.OptionID == optionID {
			return true
		}
	}
	return false
}

func (u DecisionUnit) EligibilityFor(optionID string) (Eligibility, bool) {
	for _, eligibility := range u.Eligibility {
		if eligibility.OptionID == strings.TrimSpace(optionID) {
			return eligibility, true
		}
	}
	return Eligibility{}, false
}

func (u DecisionUnit) PendingRoles(round int) []string {
	pending := make([]string, 0, len(u.RequiredRoles))
	for _, role := range u.RequiredRoles {
		found := false
		for _, submission := range u.Submissions {
			if submission.Round == round && submission.Role == role {
				found = true
				break
			}
		}
		if !found {
			pending = append(pending, role)
		}
	}
	return pending
}

func (u DecisionUnit) CurrentRound() int {
	if !u.RoundSealed(1) {
		return 1
	}
	if !u.RoundSealed(2) {
		return 2
	}
	return 0
}

func (u DecisionUnit) CanSeal(round int) error {
	if round != 1 && round != 2 {
		return ErrInvalid
	}
	if u.RoundSealed(round) {
		return ErrConflict
	}
	for _, role := range u.RequiredRoles {
		found := false
		for _, s := range u.Submissions {
			if s.Round == round && s.Role == role {
				found = true
				break
			}
		}
		if !found {
			return ErrRoundsUnsealed
		}
	}
	return nil
}

func (u DecisionUnit) CanFinalize(actor string, now time.Time) error {
	if u.Decision != nil {
		return ErrConflict
	}
	if !u.RoundSealed(1) || !u.RoundSealed(2) {
		return ErrRoundsUnsealed
	}
	if now.After(u.EvidenceExpiresAt) {
		return ErrEvidenceExpired
	}
	accountableActor := ""
	roleActors := map[string]string{}
	for _, s := range u.Submissions {
		if now.After(s.EvidenceExpiresAt) {
			return ErrEvidenceExpired
		}
		if Contains(u.HardVetoRoles, s.Role) && !s.Passed {
			return ErrHardVeto
		}
		if s.Round == 2 {
			roleActors[s.Role] = s.ActorID
			if s.Role == u.AccountableRole {
				accountableActor = s.ActorID
			}
		}
	}
	if u.AccountableRole == "" || accountableActor == "" || accountableActor != actor {
		return ErrWrongRole
	}
	policy, ok := GeneratedSoDPolicyRules[u.SoDPolicy]
	if !ok {
		return ErrInvalid
	}
	if policy.DistinctAuthenticatedActorsRequired {
		seen := map[string]string{}
		for _, role := range u.RequiredRoles {
			roleActor := strings.TrimSpace(roleActors[role])
			if roleActor == "" {
				return ErrSoD
			}
			if previousRole, duplicated := seen[roleActor]; duplicated && previousRole != role {
				return ErrSoD
			}
			seen[roleActor] = role
		}
	}
	return nil
}

func CanonicalAuthorityClaimBytes(payload AuthorityReceiptClaims) ([]byte, error) {
	if !canonicalStringSet(payload.Actions) {
		return nil, ErrInvalid
	}
	if !validCanonicalScope(payload.Scope) {
		return nil, ErrInvalid
	}
	if payload.SchemaVersion != 1 || strings.TrimSpace(payload.ReceiptID) == "" || payload.ReceiptID != payload.DecisionID || strings.TrimSpace(payload.DecisionUnitID) == "" || strings.TrimSpace(payload.ActorID) == "" || !payload.ActorAuthenticated || !ValidRole(payload.Role) || !ValidDecisionKind(payload.DecisionKind) || len(payload.Scope) == 0 || strings.TrimSpace(payload.EvidenceFingerprint) == "" || len(payload.Actions) == 0 || strings.TrimSpace(payload.ProviderKind) == "" || strings.TrimSpace(payload.ProviderVersion) == "" || !canonicalDigest(payload.ProviderCommit) || strings.TrimSpace(payload.ContractVersion) == "" || strings.TrimSpace(payload.Issuer) == "" {
		return nil, ErrInvalid
	}
	raw, err := json.Marshal(payload)
	if err != nil || !VerifyAuthorityObjectFields(raw, GeneratedAuthorityReceiptClaimFields) {
		return nil, ErrInvalid
	}
	return raw, nil
}

func CanonicalStateAttestationBytes(payload AuthorityStateAttestation) ([]byte, error) {
	if payload.SchemaVersion != 1 || strings.TrimSpace(payload.ReceiptID) == "" || payload.ReceiptID != payload.DecisionID || strings.TrimSpace(payload.DecisionUnitID) == "" || !canonicalDigest(payload.PayloadDigest) || !ValidReceiptState(payload.State) || payload.Generation < 1 || payload.PreviousGeneration < 0 || payload.PreviousGeneration >= payload.Generation || payload.ETag != ReceiptETag(payload.ReceiptID, payload.Generation) || !canonicalDigest(payload.ChainCommit) || strings.TrimSpace(payload.ProviderKind) == "" || strings.TrimSpace(payload.ProviderVersion) == "" || !canonicalDigest(payload.ProviderCommit) || strings.TrimSpace(payload.ContractVersion) == "" || strings.TrimSpace(payload.Issuer) == "" {
		return nil, ErrInvalid
	}
	if payload.State == ReceiptAvailable && (payload.PreviousGeneration != 0 || payload.Generation != 1 || payload.WinnerIdempotencyKey != "" || payload.WinnerCommandDigest != "" || payload.StateActorID != "" || payload.StateAt != "") {
		return nil, ErrInvalid
	}
	if payload.State == ReceiptConsumed && (strings.TrimSpace(payload.WinnerIdempotencyKey) == "" || !canonicalDigest(payload.WinnerCommandDigest) || strings.TrimSpace(payload.StateActorID) == "" || strings.TrimSpace(payload.StateAt) == "") {
		return nil, ErrInvalid
	}
	if payload.State == ReceiptRevoked && (strings.TrimSpace(payload.WinnerIdempotencyKey) == "" || !canonicalDigest(payload.WinnerCommandDigest) || strings.TrimSpace(payload.StateActorID) == "" || strings.TrimSpace(payload.StateAt) == "") {
		return nil, ErrInvalid
	}
	raw, err := json.Marshal(payload)
	if err != nil || !VerifyAuthorityObjectFields(raw, GeneratedAuthorityStateAttestationFields) {
		return nil, ErrInvalid
	}
	return raw, nil
}

func ReceiptETag(receiptID string, generation int64) string {
	return fmt.Sprintf("\"receipt:%s:generation:%d\"", receiptID, generation)
}
func ValidReceiptState(value string) bool {
	return value == ReceiptAvailable || value == ReceiptConsumed || value == ReceiptRevoked
}
func VerifyAuthorityObjectFields(raw []byte, expected []string) bool {
	var object map[string]json.RawMessage
	if json.Unmarshal(raw, &object) != nil || len(object) != len(expected) {
		return false
	}
	for _, field := range expected {
		if _, ok := object[field]; !ok {
			return false
		}
	}
	return true
}

func Digest(raw []byte) string {
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:])
}
func EncodeExact(raw []byte) string          { return base64.RawStdEncoding.EncodeToString(raw) }
func DecodeExact(raw string) ([]byte, error) { return base64.RawStdEncoding.DecodeString(raw) }

func NewEvent(unitID, eventID, eventType, actor string, sequence int64, previousHash string, payload any, occurredAt time.Time) (Event, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return Event{}, err
	}
	if strings.TrimSpace(unitID) == "" || strings.TrimSpace(eventID) == "" || strings.TrimSpace(eventType) == "" || sequence < 1 {
		return Event{}, ErrInvalid
	}
	hashInput := []byte(fmt.Sprintf("%s\n%d\n%s\n%s\n%s\n", unitID, sequence, eventType, previousHash, occurredAt.UTC().Format(time.RFC3339Nano)))
	hashInput = append(hashInput, raw...)
	return Event{EventID: eventID, UnitID: unitID, Sequence: sequence, Type: eventType, ActorID: strings.TrimSpace(actor), Payload: raw, PreviousHash: previousHash, Hash: Digest(hashInput), OccurredAt: occurredAt.UTC()}, nil
}

func VerifyHashChain(events []Event) error {
	previous := ""
	for i, event := range events {
		expected, err := NewEvent(event.UnitID, event.EventID, event.Type, event.ActorID, int64(i+1), previous, json.RawMessage(event.Payload), event.OccurredAt)
		if err != nil || event.Sequence != int64(i+1) || expected.Hash != event.Hash || event.PreviousHash != previous {
			return ErrConflict
		}
		previous = event.Hash
	}
	return nil
}

func uniqueSorted(values []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}
func canonicalStringSet(values []string) bool {
	if len(values) == 0 {
		return false
	}
	previous := ""
	for _, value := range values {
		if value == "" || value != strings.TrimSpace(value) || (previous != "" && value <= previous) {
			return false
		}
		previous = value
	}
	return true
}

func validCanonicalScope(scope CanonicalScope) bool {
	if len(scope) != 1 {
		return false
	}
	for key, value := range scope {
		if (key != "objective" && key != "increment") || strings.TrimSpace(value) == "" || value != strings.TrimSpace(value) {
			return false
		}
	}
	return true
}

func canonicalDigest(value string) bool {
	if len(value) != 71 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	_, err := hex.DecodeString(value[7:])
	return err == nil
}
