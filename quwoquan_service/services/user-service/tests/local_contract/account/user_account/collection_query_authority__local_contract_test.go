package local_contract

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-002
import (
	"context"
	"crypto/rand"
	"errors"
	auth "quwoquan_service/runtime/auth"
	authority "quwoquan_service/services/user-service/internal/account/user_account/application"
	ports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	"strings"
	"testing"
	"time"
)

type securityReader struct {
	state string
	epoch int64
	fail  bool
}

func (s *securityReader) ReadAccountSecurity(context.Context, string) (ports.AccountSecuritySnapshot, error) {
	if s.fail {
		return ports.AccountSecuritySnapshot{}, errors.New("unavailable")
	}
	return ports.AccountSecuritySnapshot{AccountState: s.state, AuthEpoch: s.epoch}, nil
}

type personaReader struct {
	owner  string
	exists bool
	fail   bool
}

func (p *personaReader) ResolveOwnerAccountID(context.Context, string) (string, bool, error) {
	if p.fail {
		return "", false, errors.New("unavailable")
	}
	return p.owner, p.exists, nil
}
func service(name, scope string) auth.Principal {
	return auth.Principal{Claims: auth.Claims{Subject: "service:" + name, Roles: []string{"service"}, Scope: scope}}
}
func binding() authority.CollectionQueryBinding {
	return authority.CollectionQueryBinding{OperationID: "content.post_collection.GetPostCollectionManagement", CollectionID: "c", PersistedHash: strings.Repeat("a", 64), BodyDigest: "sha256:" + strings.Repeat("b", 64), Method: "POST", Path: "/internal/graphql", Surface: "postCollection", RequestID: "request"}
}
func setupAuthority(t *testing.T) (*authority.CollectionQueryAuthority, string, *securityReader, *personaReader, *time.Time) {
	t.Helper()
	key := make([]byte, 32)
	if _, e := rand.Read(key); e != nil {
		t.Fatal(e)
	}
	config := auth.TokenConfig{Secret: key, Issuer: "test", Audience: "test", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: 45 * time.Second}
	signer, e := auth.NewHS256Signer(config)
	if e != nil {
		t.Fatal(e)
	}
	verifier, e := auth.NewHS256Verifier(config)
	if e != nil {
		t.Fatal(e)
	}
	token, e := signer.Sign(auth.TokenSubject{AccountID: "a", PersonaID: "p", AuthEpoch: 2})
	if e != nil {
		t.Fatal(e)
	}
	grantKey := make([]byte, 32)
	_, _ = rand.Read(grantKey)
	now := time.Now()
	s := &securityReader{"active", 2, false}
	p := &personaReader{"a", true, false}
	a, e := authority.NewCollectionQueryAuthority(verifier, s, p, authority.CollectionAuthorityKeys{ActiveID: "key", VerificationKeys: map[string][]byte{"key": grantKey}}, func() time.Time { return now })
	if e != nil {
		t.Fatal(e)
	}
	return a, token, s, p, &now
}
func TestCollectionAuthorityIssueVerifyBoundedRetry(t *testing.T) {
	a, token, _, _, now := setupAuthority(t)
	ctx := context.Background()
	b := binding()
	grant, e := a.Issue(ctx, service("api-edge", "user.collection_query.issue"), token, b)
	if e != nil {
		t.Fatal(e)
	}
	if grant.ExpiresAt > now.Unix()+45 || grant.ExpiresAt <= now.Unix() {
		t.Fatal("grant outlives source")
	}
	for i := 0; i < 2; i++ {
		identity, e := a.Verify(ctx, service("content-service", "user.collection_query.verify"), grant.Grant, b)
		if e != nil || identity.AccountID != "a" || identity.PersonaID != "p" || identity.ExpiresAt != grant.ExpiresAt {
			t.Fatal(identity, e)
		}
	}
	*now = now.Add(time.Minute)
	if _, e = a.Verify(ctx, service("content-service", "user.collection_query.verify"), grant.Grant, b); e == nil {
		t.Fatal("expired admitted")
	}
}
func TestCollectionAuthorityRejectsForgedBindingsAndIdentity(t *testing.T) {
	a, token, _, p, _ := setupAuthority(t)
	ctx := context.Background()
	b := binding()
	issuer := service("api-edge", "user.collection_query.issue")
	verify := service("content-service", "user.collection_query.verify")
	g, e := a.Issue(ctx, issuer, token, b)
	if e != nil {
		t.Fatal(e)
	}
	for _, mutate := range []func(*authority.CollectionQueryBinding){func(b *authority.CollectionQueryBinding) { b.OperationID = "content.post.DeletePost" }, func(b *authority.CollectionQueryBinding) { b.CollectionID = "other" }, func(b *authority.CollectionQueryBinding) { b.PersistedHash = strings.Repeat("c", 64) }, func(b *authority.CollectionQueryBinding) { b.BodyDigest = "sha256:" + strings.Repeat("c", 64) }, func(b *authority.CollectionQueryBinding) { b.Method = "GET" }, func(b *authority.CollectionQueryBinding) { b.Path = "/other" }, func(b *authority.CollectionQueryBinding) { b.Surface = "homeFeed" }, func(b *authority.CollectionQueryBinding) { b.RequestID = "other" }} {
		wrong := b
		mutate(&wrong)
		if _, e = a.Verify(ctx, verify, g.Grant, wrong); e == nil {
			t.Fatal("changed binding admitted")
		}
	}
	for _, caller := range []auth.Principal{service("evil", "user.collection_query.issue"), service("api-edge", "wrong"), {}} {
		if _, e = a.Issue(ctx, caller, token, b); e == nil {
			t.Fatal("caller admitted")
		}
	}
	if _, e = a.Verify(ctx, service("api-edge", "user.collection_query.verify"), g.Grant, b); e == nil {
		t.Fatal("recipient caller mismatch")
	}
	if _, e = a.Issue(ctx, issuer, "forged", b); e == nil {
		t.Fatal("forged token")
	}
	p.owner = "other"
	if _, e = a.Issue(ctx, issuer, token, b); e == nil {
		t.Fatal("cross account persona")
	}
}
func TestCollectionAuthorityRejectsTamperingUnknownKeyAndCancelledRequest(t *testing.T) {
	a, token, _, _, _ := setupAuthority(t)
	ctx := context.Background()
	b := binding()
	caller := service("content-service", "user.collection_query.verify")
	g, err := a.Issue(ctx, service("api-edge", "user.collection_query.issue"), token, b)
	if err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{"unknown" + g.Grant[strings.Index(g.Grant, "."):], g.Grant + "x", "", strings.Repeat("a", 17000)} {
		if _, err = a.Verify(ctx, caller, bad, b); err == nil {
			t.Fatal("invalid signature/key admitted")
		}
	}
	cancelled, cancel := context.WithCancel(ctx)
	cancel()
	if _, err = a.Verify(cancelled, caller, g.Grant, b); err == nil {
		t.Fatal("cancelled request admitted")
	}
}

func TestCollectionAuthorityRechecksRevocationAndDependency(t *testing.T) {
	a, token, s, p, _ := setupAuthority(t)
	ctx := context.Background()
	b := binding()
	g, e := a.Issue(ctx, service("api-edge", "user.collection_query.issue"), token, b)
	if e != nil {
		t.Fatal(e)
	}
	check := func() {
		t.Helper()
		if _, e := a.Verify(ctx, service("content-service", "user.collection_query.verify"), g.Grant, b); e == nil {
			t.Fatal("revocation/failure admitted")
		}
	}
	for _, state := range []string{"closed", "suspended", ""} {
		s.state = state
		check()
	}
	s.state = "active"
	s.epoch++
	check()
	s.epoch = 2
	p.exists = false
	check()
	p.exists = true
	p.owner = "other"
	check()
	p.owner = "a"
	s.fail = true
	check()
	s.fail = false
	p.fail = true
	check()
}
