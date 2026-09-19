package user_account

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	auth "quwoquan_service/runtime/auth"
	generated "quwoquan_service/services/user-service/generated/account/user_account"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	"regexp"
	"strings"
	"time"
)

// 类型与编码由 UserAccount fields.yaml authoring，其他服务不得重建签发规则。
type CollectionQueryBinding struct {
	OperationID   string `json:"operationId"`
	CollectionID  string `json:"collectionId"`
	PersistedHash string `json:"persistedHash"`
	BodyDigest    string `json:"bodyDigest"`
	Method        string `json:"method"`
	Path          string `json:"path"`
	Surface       string `json:"surface"`
	RequestID     string `json:"requestId"`
}
type CollectionQueryGrantResult struct {
	Grant     string `json:"grant"`
	ExpiresAt int64  `json:"expiresUnixSeconds"`
}
type VerifiedCollectionQueryIdentity struct {
	AccountID string `json:"accountId"`
	PersonaID string `json:"personaId"`
	AuthEpoch int64  `json:"authEpoch"`
	ExpiresAt int64  `json:"expiresUnixSeconds"`
}
type collectionQueryClaims struct {
	Kind            string                 `json:"kind"`
	Issuer          string                 `json:"issuer"`
	Recipient       string                 `json:"recipient"`
	Delegate        string                 `json:"delegate"`
	AccountID       string                 `json:"accountId"`
	PersonaID       string                 `json:"personaId"`
	AuthEpoch       int64                  `json:"authEpoch"`
	IssuedAt        int64                  `json:"issuedUnixSeconds"`
	ExpiresAt       int64                  `json:"expiresUnixSeconds"`
	SourceExpiresAt int64                  `json:"sourceExpiresUnixSeconds"`
	Binding         CollectionQueryBinding `json:"binding"`
}

// SourceCredentialVerifier 必须是正式 access credential verifier，不能接受网关自报身份。
type SourceCredentialVerifier interface {
	Verify(string) (*auth.Claims, error)
}

// PersonaOwnershipReader 是 Persona 对象的公开读端口，不扩展 AccountSecuritySnapshot。
type PersonaOwnershipReader interface {
	ResolveOwnerAccountID(context.Context, string) (string, bool, error)
}
type CollectionAuthorityKeys struct {
	ActiveID         string
	VerificationKeys map[string][]byte
}
type CollectionQueryAuthority struct {
	source   SourceCredentialVerifier
	accounts accountports.AccountSecurityReader
	personas PersonaOwnershipReader
	keys     CollectionAuthorityKeys
	now      func() time.Time
}

var collectionDigest = regexp.MustCompile(`^[0-9a-f]{64}$`)

func NewCollectionQueryAuthority(source SourceCredentialVerifier, accounts accountports.AccountSecurityReader, personas PersonaOwnershipReader, keys CollectionAuthorityKeys, now func() time.Time) (*CollectionQueryAuthority, error) {
	if source == nil || accounts == nil || personas == nil || now == nil || keys.ActiveID == "" || strings.Contains(keys.ActiveID, ".") {
		return nil, errors.New("collection authority dependencies incomplete")
	}
	copied := map[string][]byte{}
	for id, key := range keys.VerificationKeys {
		if id == "" || strings.Contains(id, ".") || len(key) < 32 {
			return nil, errors.New("collection authority key invalid")
		}
		copied[id] = bytes.Clone(key)
	}
	if len(copied[keys.ActiveID]) < 32 {
		return nil, errors.New("collection authority active key missing")
	}
	return &CollectionQueryAuthority{source, accounts, personas, CollectionAuthorityKeys{keys.ActiveID, copied}, now}, nil
}
func collectionDenied() error { return generated.AppErrorFromCollectionQueryDenied("") }
func collectionUnavailable() error {
	return generated.AppErrorFromCollectionQueryAuthorityUnavailable("")
}
func validCollectionBinding(b CollectionQueryBinding) bool {
	if b.OperationID != "content.post_collection.GetPostCollection" && b.OperationID != "content.post_collection.GetPostCollectionManagement" {
		return false
	}
	return b.CollectionID != "" && len(b.CollectionID) <= 128 && strings.TrimSpace(b.CollectionID) == b.CollectionID && collectionDigest.MatchString(b.PersistedHash) && strings.HasPrefix(b.BodyDigest, "sha256:") && collectionDigest.MatchString(strings.TrimPrefix(b.BodyDigest, "sha256:")) && b.Method == "POST" && b.Path == "/internal/graphql" && b.Surface == "postCollection" && b.RequestID != "" && len(b.RequestID) <= 128
}
func exactService(p auth.Principal, name, scope string) bool {
	if p.Subject != "service:"+name || p.Actor.PersonaID != "" {
		return false
	}
	role := false
	for _, r := range p.Roles {
		role = role || r == "service"
	}
	if !role {
		return false
	}
	for _, s := range strings.Fields(p.Scope) {
		if s == scope {
			return true
		}
	}
	return false
}
func (a *CollectionQueryAuthority) current(ctx context.Context, account, persona string, epoch int64) error {
	if ctx.Err() != nil {
		return collectionUnavailable()
	}
	state, err := a.accounts.ReadAccountSecurity(ctx, account)
	if errors.Is(err, accountports.ErrAccountNotFound) {
		return collectionDenied()
	}
	if err != nil {
		return collectionUnavailable()
	}
	if state.AccountState != "active" || state.AuthEpoch != epoch || epoch <= 0 {
		return collectionDenied()
	}
	owner, exists, err := a.personas.ResolveOwnerAccountID(ctx, persona)
	if err != nil {
		return collectionUnavailable()
	}
	if !exists || owner != account {
		return collectionDenied()
	}
	if ctx.Err() != nil {
		return collectionUnavailable()
	}
	return nil
}
func (a *CollectionQueryAuthority) Issue(ctx context.Context, caller auth.Principal, sourceToken string, binding CollectionQueryBinding) (CollectionQueryGrantResult, error) {
	if !exactService(caller, "api-edge", "user.collection_query.issue") || !validCollectionBinding(binding) {
		return CollectionQueryGrantResult{}, collectionDenied()
	}
	claims, err := a.source.Verify(sourceToken)
	if err != nil || claims == nil {
		return CollectionQueryGrantResult{}, collectionDenied()
	}
	if claims.TokenType != auth.TokenTypeAccess || claims.Subject == "" || strings.HasPrefix(claims.Subject, "service:") || claims.Persona == "" || claims.ServiceActorID != "" {
		return CollectionQueryGrantResult{}, collectionDenied()
	}
	if err = a.current(ctx, claims.Subject, claims.Persona, claims.AuthEpoch); err != nil {
		return CollectionQueryGrantResult{}, err
	}
	now := a.now().UTC().Unix()
	expires := now + 60
	if claims.ExpiresAt < expires {
		expires = claims.ExpiresAt
	}
	if expires <= now {
		return CollectionQueryGrantResult{}, collectionDenied()
	}
	payload := collectionQueryClaims{Kind: "collection_query", Issuer: "user-service", Recipient: "content-service", Delegate: "api-edge", AccountID: claims.Subject, PersonaID: claims.Persona, AuthEpoch: claims.AuthEpoch, IssuedAt: now, ExpiresAt: expires, SourceExpiresAt: claims.ExpiresAt, Binding: binding}
	raw, err := json.Marshal(payload)
	if err != nil {
		return CollectionQueryGrantResult{}, collectionUnavailable()
	}
	encoded := a.keys.ActiveID + "." + base64.RawURLEncoding.EncodeToString(raw)
	mac := hmac.New(sha256.New, a.keys.VerificationKeys[a.keys.ActiveID])
	_, _ = mac.Write([]byte(encoded))
	return CollectionQueryGrantResult{Grant: encoded + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil)), ExpiresAt: expires}, nil
}
func (a *CollectionQueryAuthority) Verify(ctx context.Context, caller auth.Principal, grant string, binding CollectionQueryBinding) (VerifiedCollectionQueryIdentity, error) {
	if !exactService(caller, "content-service", "user.collection_query.verify") || !validCollectionBinding(binding) || len(grant) > 16384 {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	parts := strings.Split(grant, ".")
	if len(parts) != 3 {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	key, ok := a.keys.VerificationKeys[parts[0]]
	if !ok {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(parts[0] + "." + parts[1]))
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var c collectionQueryClaims
	var extra any
	if decoder.Decode(&c) != nil || decoder.Decode(&extra) != io.EOF {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	now := a.now().UTC().Unix()
	if c.Kind != "collection_query" || c.Issuer != "user-service" || c.Recipient != "content-service" || c.Delegate != "api-edge" || c.Binding != binding || c.AccountID == "" || c.PersonaID == "" || c.IssuedAt > now || c.ExpiresAt <= now || c.ExpiresAt <= c.IssuedAt || c.ExpiresAt-c.IssuedAt > 60 || c.ExpiresAt > c.SourceExpiresAt {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	if err = a.current(ctx, c.AccountID, c.PersonaID, c.AuthEpoch); err != nil {
		return VerifiedCollectionQueryIdentity{}, err
	}
	if a.now().UTC().Unix() >= c.ExpiresAt {
		return VerifiedCollectionQueryIdentity{}, collectionDenied()
	}
	return VerifiedCollectionQueryIdentity{c.AccountID, c.PersonaID, c.AuthEpoch, c.ExpiresAt}, nil
}
