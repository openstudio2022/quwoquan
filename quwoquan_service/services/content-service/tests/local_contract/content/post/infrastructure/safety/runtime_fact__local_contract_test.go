package safety_test

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"os"
	"path/filepath"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/safety"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	safety "quwoquan_service/services/content-service/internal/content/post/infrastructure/safety"
	"strconv"
	"strings"
	"testing"
	"time"
)

const (
	runtimeAuthorizationPayloadTypeForTest = "application/vnd.quwoquan.post-safety-runtime-authorization.v1+json"
	runtimeAuthorizationIdentityForTest    = "quwoquan-environment-ops-local"
	runtimeAuthorizationPublicKeyForTest   = "DA+JAaxsgD8Aq1vDz458finqg+X2tuXDUFPKaSi5wwg="
)

func bytesDigest(raw []byte) string {
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func strictCanonicalJSON(raw []byte, target any) error {
	if err := safety.StrictRuntimeJSON(raw, target); err != nil {
		return err
	}
	canonical, err := json.Marshal(target)
	if err != nil || !bytes.Equal(raw, canonical) {
		return errors.New("non-canonical runtime JSON")
	}
	return nil
}

func verifyAuthorization(raw []byte, value wire.PostSafetyRuntimeAuthorization, expectedIdentity, encodedPublicKey string) error {
	if value.AuthorityIdentity != expectedIdentity || value.Signature == "" {
		return errors.New("invalid authority")
	}
	var object map[string]any
	if safety.StrictRuntimeJSON(raw, &value) != nil || json.Unmarshal(raw, &object) != nil {
		return errors.New("invalid authorization")
	}
	delete(object, "signature")
	payload, _ := json.Marshal(object)
	signature, err := base64.StdEncoding.DecodeString(strings.TrimPrefix(value.Signature, "ed25519:"))
	publicKey, keyErr := base64.StdEncoding.DecodeString(encodedPublicKey)
	pae := []byte("DSSEv1 " + strconv.Itoa(len(runtimeAuthorizationPayloadTypeForTest)) + " " + runtimeAuthorizationPayloadTypeForTest + " " + strconv.Itoa(len(payload)) + " ")
	pae = append(pae, payload...)
	if err != nil || keyErr != nil || !ed25519.Verify(publicKey, pae, signature) {
		return errors.New("invalid signature")
	}
	return nil
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestPythonAuthorizationExactBytesVerifyInGo(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	const unsigned = `{"environment":"gamma","target":"gamma-local","candidateDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","dataPlaneBindingDigest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","startupAttemptId":"attempt-1","runtimeGeneration":"generation-1","action":"initialize_post_safety_runtime","issuedAt":"2026-09-14T22:55:39.123450Z","authorityIdentity":"fixture-authority","evidencePredecessor":{"ref":"content-account-closure-runtime.json","digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}}`
	var payload map[string]any
	if err = json.Unmarshal([]byte(unsigned), &payload); err != nil {
		t.Fatal(err)
	}
	canonicalPayload, _ := json.Marshal(payload)
	pae := []byte("DSSEv1 " + strconv.Itoa(len(runtimeAuthorizationPayloadTypeForTest)) + " " + runtimeAuthorizationPayloadTypeForTest + " " + strconv.Itoa(len(canonicalPayload)) + " ")
	pae = append(pae, canonicalPayload...)
	signature := "ed25519:" + base64.StdEncoding.EncodeToString(ed25519.Sign(privateKey, pae))
	raw := []byte(unsigned[:len(unsigned)-1] + `,"signature":"` + signature + `"}`)
	var authorization wire.PostSafetyRuntimeAuthorization
	if err = strictCanonicalAuthorization(raw, &authorization); err != nil {
		t.Fatal(err)
	}
	if err = verifyAuthorization(raw, authorization, "fixture-authority", base64.StdEncoding.EncodeToString(publicKey)); err != nil {
		t.Fatal(err)
	}
	if err = strictCanonicalJSON(raw, &authorization); err == nil {
		t.Fatal("fixture no longer exercises timestamp remarshal mismatch")
	}
}

func strictCanonicalAuthorization(raw []byte, target *wire.PostSafetyRuntimeAuthorization) error {
	if err := safety.StrictRuntimeJSON(raw, target); err != nil {
		return err
	}
	exact := struct {
		Environment            string                         `json:"environment"`
		Target                 string                         `json:"target"`
		CandidateDigest        string                         `json:"candidateDigest"`
		DataPlaneBindingDigest string                         `json:"dataPlaneBindingDigest"`
		StartupAttemptId       string                         `json:"startupAttemptId"`
		RuntimeGeneration      string                         `json:"runtimeGeneration"`
		Action                 string                         `json:"action"`
		IssuedAt               string                         `json:"issuedAt"`
		AuthorityIdentity      string                         `json:"authorityIdentity"`
		EvidencePredecessor    wire.PostSafetyRuntimeEvidence `json:"evidencePredecessor"`
		Signature              string                         `json:"signature"`
	}{target.Environment, target.Target, target.CandidateDigest, target.DataPlaneBindingDigest, target.StartupAttemptId, target.RuntimeGeneration, target.Action, target.IssuedAt.UTC().Format("2006-01-02T15:04:05.000000Z"), target.AuthorityIdentity, target.EvidencePredecessor, target.Signature}
	canonical, err := json.Marshal(exact)
	if err != nil || !bytes.Equal(raw, canonical) {
		return errors.New("non-canonical authorization")
	}
	return nil
}

func TestRetainedGammaAuthorizationExactBytesVerifyInGo(t *testing.T) {
	root := os.Getenv("QWQ_POST_SAFETY_FIXTURE_ROOT")
	if root == "" {
		t.Skip("retained Gamma material fixture root not configured")
	}
	raw, err := os.ReadFile(filepath.Join(root, "authorization.json"))
	if err != nil {
		t.Fatal(err)
	}
	var authorization wire.PostSafetyRuntimeAuthorization
	if err = strictCanonicalAuthorization(raw, &authorization); err != nil {
		t.Fatal("retained Python authorization canonical bytes rejected", err)
	}
	if err = verifyAuthorization(raw, authorization, runtimeAuthorizationIdentityForTest, runtimeAuthorizationPublicKeyForTest); err != nil {
		t.Fatal("retained Python authorization signature rejected", err)
	}
}

func TestRuntimeDTORejectsMissingAndDuplicateFields(t *testing.T) {
	value := wire.PostSafetyRuntimeFact{Mode: "new_runtime", Binding: wire.PostSafetyRuntimeBinding{}, Closures: []wire.PostSafetyRuntimeClosure{}, RecordedAt: time.Now().UTC()}
	raw, _ := json.Marshal(value)
	var target wire.PostSafetyRuntimeFact
	if err := safety.StrictRuntimeJSON(raw, &target); err != nil {
		t.Fatal(err)
	}
	var object map[string]json.RawMessage
	_ = json.Unmarshal(raw, &object)
	delete(object, "previousBinding")
	missing, _ := json.Marshal(object)
	for _, bad := range [][]byte{missing, []byte(`{"mode":"new_runtime","mode":"restored"}`), append(raw, []byte(` {}`)...)} {
		if err := safety.StrictRuntimeJSON(bad, &target); err == nil {
			t.Fatal("invalid raw shape accepted")
		}
	}
	object["previousBinding"] = json.RawMessage(`null`)
	object["unknown"] = json.RawMessage(`true`)
	unknown, _ := json.Marshal(object)
	if err := safety.StrictRuntimeJSON(unknown, &target); err == nil {
		t.Fatal("unknown accepted")
	}
	object["binding"] = json.RawMessage(`null`)
	delete(object, "unknown")
	null, _ := json.Marshal(object)
	if err := safety.StrictRuntimeJSON(null, &target); err == nil {
		t.Fatal("nonnull binding accepted null")
	}
}

// 此测试只证明Mongo provider UUID身份不可由namespace名伪造，不生成创建资格。
func TestRuntimePhysicalUUIDChangesOnRecreation(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("runtime_identity"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		_ = runtime.Close(c)
	}()
	db := runtime.Database
	if _, err = safety.ReadPhysicalSafetyIdentity(ctx, db); err == nil {
		t.Fatal("missing collection treated as created")
	}
	if err = db.CreateCollection(ctx, safety.Collection); err != nil {
		t.Fatal(err)
	}
	first, err := safety.ReadPhysicalSafetyIdentity(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Collection(safety.Collection).InsertOne(ctx, bson.M{"objectDigest": "test"}); err != nil {
		t.Fatal(err)
	}
	afterWrite, err := safety.ReadPhysicalSafetyIdentity(ctx, db)
	if err != nil || afterWrite != first {
		t.Fatal("normal write changed instance", err)
	}
	if err = db.Collection(safety.Collection).Drop(ctx); err != nil {
		t.Fatal(err)
	}
	if err = db.CreateCollection(ctx, safety.Collection); err != nil {
		t.Fatal(err)
	}
	second, err := safety.ReadPhysicalSafetyIdentity(ctx, db)
	if err != nil || second == first {
		t.Fatal("recreated namespace reused identity", err)
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestRuntimeFilesRejectUnsafeMaterials(t *testing.T) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(filepath.Join(root, "secrets"), 0700); err != nil {
		t.Fatal(err)
	}
	raw := []byte(strings.Repeat("x", 32))
	key := filepath.Join(root, "secrets", "post-safety.key")
	if err = os.WriteFile(key, raw, 0600); err != nil {
		t.Fatal(err)
	}
	files, err := safety.OpenRuntimeFiles(root)
	if err != nil {
		t.Fatal(err)
	}
	got, err := files.Read("secrets/post-safety.key", 64)
	if err != nil || string(got) != string(raw) {
		t.Fatal("read controlled key", err)
	}
	if _, err = files.ReadDigest("secrets/post-safety.key", bytesDigest(raw)); err != nil {
		t.Fatal(err)
	}
	for _, ref := range []string{"", "../post-safety.key", key, "secrets/../secrets/post-safety.key", "secrets//post-safety.key", "secrets\\post-safety.key"} {
		if _, err = files.Read(ref, 64); err == nil {
			t.Fatalf("unsafe ref accepted %q", ref)
		}
	}
	if _, err = files.Read("secrets/missing", 64); err == nil {
		t.Fatal("missing key accepted")
	}
	if _, err = files.ReadDigest("secrets/post-safety.key", "sha256:"+strings.Repeat("0", 64)); err == nil {
		t.Fatal("wrong digest accepted")
	}
	if _, err = files.Read("secrets/post-safety.key", 16); err == nil {
		t.Fatal("oversized key accepted")
	}
	if err = os.Symlink(key, filepath.Join(root, "secrets", "alias")); err != nil {
		t.Fatal(err)
	}
	if _, err = files.Read("secrets/alias", 64); err == nil {
		t.Fatal("symlink accepted")
	}
	if err = os.Link(key, filepath.Join(root, "secrets", "hardlink")); err != nil {
		t.Fatal(err)
	}
	if _, err = files.Read("secrets/post-safety.key", 64); err == nil {
		t.Fatal("hardlink accepted")
	}
	if err = os.Remove(filepath.Join(root, "secrets", "hardlink")); err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(key, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err = files.Read("secrets/post-safety.key", 64); err == nil {
		t.Fatal("world readable key accepted")
	}
	if err = os.Chmod(key, 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(filepath.Join(root, "secrets"), 0755); err != nil {
		t.Fatal(err)
	}
	if _, err = files.Read("secrets/post-safety.key", 64); err == nil {
		t.Fatal("unprotected child directory accepted")
	}
	if err = os.Chmod(filepath.Join(root, "secrets"), 0700); err != nil {
		t.Fatal(err)
	}
	saved := root + "-previous"
	if err = os.Rename(root, saved); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(saved) })
	if err = os.Mkdir(root, 0700); err != nil {
		t.Fatal(err)
	}
	if _, err = files.Read("secrets/post-safety.key", 64); err == nil {
		t.Fatal("replaced root accepted")
	}
}

func TestProductionRuntimeAuthorityBlocksListenerOnMaterialDrift(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required")
	}
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("runtime_listener_gate"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, stop := context.WithTimeout(context.Background(), 20*time.Second)
		defer stop()
		_ = runtime.Close(c)
	}()
	if err = runtime.Database.CreateCollection(ctx, safety.Collection); err != nil {
		t.Fatal(err)
	}
	root, startup := writeSignedRuntimeFixture(t, ctx, runtime.Database, "gamma")
	active := activeAccountAuthority{}
	for _, tc := range []struct {
		name   string
		mutate func(string)
	}{
		{"valid", func(string) {}},
		{"missing-startup", func(root string) { mustRemove(t, filepath.Join(root, "startup.json")) }},
		{"tampered-startup", func(root string) { tamperRuntimeFile(t, filepath.Join(root, "startup.json")) }},
		{"missing-current", func(root string) { mustRemove(t, filepath.Join(root, "current.json")) }},
		{"tampered-current", func(root string) { tamperRuntimeFile(t, filepath.Join(root, "current.json")) }},
		{"missing-fact", func(root string) { mustRemove(t, filepath.Join(root, "fact.json")) }},
		{"tampered-fact", func(root string) { tamperRuntimeFile(t, filepath.Join(root, "fact.json")) }},
		{"missing-key", func(root string) { mustRemove(t, filepath.Join(root, "secrets", "post-safety.key")) }},
		{"tampered-key", func(root string) { tamperRuntimeFile(t, filepath.Join(root, "secrets", "post-safety.key")) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			caseRoot := cloneRuntimeFixture(t, root)
			tc.mutate(caseRoot)
			_, key, loadErr := safety.LoadRuntimeAuthority(ctx, runtime.Database, "gamma", caseRoot, "current.json", "fact.json", "secrets/post-safety.key", active)
			if tc.name == "valid" {
				if loadErr != nil {
					t.Fatalf("listener remained closed: %v", loadErr)
				}
				clear(key)
				return
			}
			if loadErr == nil {
				clear(key)
				t.Fatal("listener would open with invalid material")
			}
		})
	}
	authority, key, err := safety.LoadRuntimeAuthority(ctx, runtime.Database, "gamma", root, "current.json", "fact.json", "secrets/post-safety.key", active)
	if err != nil {
		t.Fatal(err)
	}
	manager, err := safety.New(runtime.Database, "gamma", key, authority)
	clear(key)
	if err != nil {
		t.Fatal(err)
	}
	runTx := func(fn func(context.Context) error) error {
		session, e := runtime.Client.StartSession()
		if e != nil {
			return e
		}
		defer session.EndSession(ctx)
		_, e = session.WithTransaction(ctx, func(tx context.Context) (any, error) { return nil, fn(tx) })
		return e
	}
	if err = runTx(func(tx context.Context) error {
		_, e := manager.Initialize(tx, "content", "ordinary-post", 1, "allowed", "verified_source", "sha256:"+strings.Repeat("e", 64))
		return e
	}); err != nil {
		t.Fatalf("verified ordinary create failed: %v", err)
	}
	if err = os.Remove(filepath.Join(root, "current.json")); err != nil {
		t.Fatal(err)
	}
	if err = runTx(func(tx context.Context) error {
		_, e := manager.Decide(tx, "content", "ordinary-post", 1, 2, "terminated", "author_deleted", "sha256:"+strings.Repeat("f", 64))
		return e
	}); err == nil {
		t.Fatal("ordinary delete proceeded after current removal")
	}
	if err = runtime.Database.Collection(safety.Collection).Drop(ctx); err != nil {
		t.Fatal(err)
	}
	if err = runtime.Database.CreateCollection(ctx, safety.Collection); err != nil {
		t.Fatal(err)
	}
	if _, key, err := safety.LoadRuntimeAuthority(ctx, runtime.Database, "gamma", root, "current.json", "fact.json", "secrets/post-safety.key", active); err == nil {
		clear(key)
		t.Fatal("recreated collection retained listener authority")
	}
	t.Setenv("QWQ_RUNTIME_TARGET", "")
	if _, key, err := safety.LoadRuntimeAuthority(ctx, runtime.Database, "prod", root, "current.json", "fact.json", "secrets/post-safety.key", active); err == nil {
		clear(key)
		t.Fatal("nonproduction authorization opened prod listener")
	}
	t.Setenv("QWQ_RUNTIME_TARGET", "prod-hosted")
	if _, key, err := safety.LoadRuntimeAuthority(ctx, runtime.Database, "prod", root, "current.json", "fact.json", "secrets/post-safety.key", active); err == nil {
		clear(key)
		t.Fatal("hosted runtime target opened prod listener")
	}
	_ = startup
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestDataRuntimeAuthorityAcceptsNoAccountReaderButContentRemainsClosed(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required")
	}
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("data_runtime_no_account"))
	if err != nil {
		t.Fatal(err)
	}
	defer runtime.Close(context.Background())
	if err = runtime.Database.CreateCollection(ctx, safety.Collection); err != nil {
		t.Fatal(err)
	}
	root, _ := writeSignedRuntimeFixture(t, ctx, runtime.Database, "gamma")
	authority, key, err := safety.LoadRuntimeAuthority(ctx, runtime.Database, "gamma", root, "current.json", "fact.json", "secrets/post-safety.key", nil)
	if err != nil {
		t.Fatalf("Data importer could not reuse canonical authority: %v", err)
	}
	clear(key)
	if err = authority.VerifySource(ctx, "gamma", "qwq_data", "post-1"); err != nil {
		t.Fatalf("Data source rejected after canonical recovery verification: %v", err)
	}
	if err = authority.VerifySource(ctx, "gamma", "content", "post-1"); err == nil {
		t.Fatal("content source opened without account authority")
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestDataRuntimeAuthorityInitializesOnlyWithCurrentRecoveryMaterials(t *testing.T) {
	if os.Getenv("QWQ_POST_SAFETY_MONGO") != "1" {
		t.Skip("explicit isolated Mongo required")
	}
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	ctx, cancel := context.WithTimeout(t.Context(), 90*time.Second)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("data_runtime_authority"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, stop := context.WithTimeout(context.Background(), 20*time.Second)
		defer stop()
		_ = runtime.Close(c)
	}()
	if err = runtime.Database.CreateCollection(ctx, safety.Collection); err != nil {
		t.Fatal(err)
	}
	root, _ := writeSignedRuntimeFixture(t, ctx, runtime.Database, "gamma")
	newManager := func(t *testing.T, fixtureRoot, environment string) (*safety.Manager, *safety.RuntimeAuthority) {
		t.Helper()
		authority, key, loadErr := safety.LoadRuntimeAuthority(ctx, runtime.Database, "gamma", fixtureRoot, "current.json", "fact.json", "secrets/post-safety.key", activeAccountAuthority{})
		if loadErr != nil {
			t.Fatal(loadErr)
		}
		manager, newErr := safety.New(runtime.Database, environment, key, authority)
		clear(key)
		if newErr != nil {
			t.Fatal(newErr)
		}
		return manager, authority
	}
	runInitialize := func(manager *safety.Manager, owner, sourceID string) error {
		session, startErr := runtime.Client.StartSession()
		if startErr != nil {
			return startErr
		}
		defer session.EndSession(ctx)
		_, txErr := session.WithTransaction(ctx, func(tx context.Context) (any, error) {
			_, initializeErr := manager.Initialize(tx, owner, sourceID, 1, "allowed", "verified_source", "sha256:"+strings.Repeat("9", 64))
			return nil, initializeErr
		})
		return txErr
	}

	manager, _ := newManager(t, cloneRuntimeFixture(t, root), "gamma")
	if err = runInitialize(manager, "qwq_data", "data-post-valid"); err != nil {
		t.Fatalf("valid signed Data runtime was rejected: %v", err)
	}

	for _, tc := range []struct {
		name   string
		mutate func(string)
	}{
		{"missing-current", func(caseRoot string) { mustRemove(t, filepath.Join(caseRoot, "current.json")) }},
		{"tampered-current", func(caseRoot string) { tamperRuntimeFile(t, filepath.Join(caseRoot, "current.json")) }},
		{"missing-account-closure-predecessor", func(caseRoot string) { mustRemove(t, filepath.Join(caseRoot, "account-closure.json")) }},
		{"tampered-account-closure-predecessor", func(caseRoot string) { tamperRuntimeFile(t, filepath.Join(caseRoot, "account-closure.json")) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			caseRoot := cloneRuntimeFixture(t, root)
			caseManager, _ := newManager(t, caseRoot, "gamma")
			tc.mutate(caseRoot)
			if initializeErr := runInitialize(caseManager, "qwq_data", "data-post-"+tc.name); initializeErr == nil {
				t.Fatal("Data initialize accepted drifted runtime materials")
			}
		})
	}

	wrongEnvironment, _ := newManager(t, cloneRuntimeFixture(t, root), "alpha")
	if err = runInitialize(wrongEnvironment, "qwq_data", "data-post-wrong-environment"); !errors.Is(err, app.ErrPostSafetyConflict) {
		t.Fatalf("wrong environment error = %v, want conflict", err)
	}
	validManager, _ := newManager(t, cloneRuntimeFixture(t, root), "gamma")
	for _, tc := range []struct {
		owner    string
		sourceID string
	}{
		{owner: "qwq_data", sourceID: ""},
		{owner: "unknown", sourceID: "data-post-unknown-owner"},
	} {
		if err = runInitialize(validManager, tc.owner, tc.sourceID); !errors.Is(err, app.ErrPostSafetyConflict) {
			t.Fatalf("owner=%q sourceID=%q error = %v, want conflict", tc.owner, tc.sourceID, err)
		}
	}
}

type activeAccountAuthority struct{}

func (activeAccountAuthority) ReadAccountSecurity(context.Context, string) (rtauth.AccountSecuritySnapshot, error) {
	return rtauth.AccountSecuritySnapshot{AccountState: "active", AuthEpoch: 1}, nil
}

func writeSignedRuntimeFixture(t *testing.T, ctx context.Context, db *mongo.Database, environment string) (string, wire.PostSafetyDeploymentStartupMaterial) {
	t.Helper()
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(filepath.Join(root, "secrets"), 0700); err != nil {
		t.Fatal(err)
	}
	write := func(name string, raw []byte) wire.PostSafetyRuntimeEvidence {
		path := filepath.Join(root, name)
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
		return wire.PostSafetyRuntimeEvidence{Ref: name, Digest: bytesDigest(raw)}
	}
	key := []byte(strings.Repeat("k", 32))
	write("secrets/post-safety.key", key)
	physical, err := safety.ReadPhysicalSafetyIdentity(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	keyID, err := safety.RuntimeKeyIdentity(key)
	if err != nil {
		t.Fatal(err)
	}
	binding := wire.PostSafetyRuntimeBinding{Environment: environment, Target: environment + "-local", CandidateDigest: "sha256:" + strings.Repeat("a", 64), DataPlaneBindingDigest: "sha256:" + strings.Repeat("b", 64), ResourceRef: "mongo-content", Namespace: db.Name(), PhysicalInstanceId: physical, RuntimeGeneration: "generation-1", HmacKeyIdentity: keyID}
	accountRaw := []byte(`{"accountClosure":"verified"}`)
	account := write("account-closure.json", accountRaw)
	authorization := wire.PostSafetyRuntimeAuthorization{Environment: environment, Target: environment + "-local", CandidateDigest: binding.CandidateDigest, DataPlaneBindingDigest: binding.DataPlaneBindingDigest, StartupAttemptId: "attempt-1", RuntimeGeneration: binding.RuntimeGeneration, Action: "initialize_post_safety_runtime", IssuedAt: time.Now().UTC(), AuthorityIdentity: runtimeAuthorizationIdentityForTest, EvidencePredecessor: account}
	authorization.Signature = signRuntimeAuthorization(t, authorization)
	authRaw, _ := json.Marshal(authorization)
	authEvidence := write("authorization.json", authRaw)
	safetyDigest := "sha256:" + strings.Repeat("c", 64)
	creation := wire.PostSafetyRuntimeCreationReceipt{Binding: binding, AllocationAttemptId: "attempt-1", PhysicalAllocationId: physical, NamespaceReadback: db.Name(), InitialSafetyRecordCount: 0, InitialSafetyCanonicalDigest: safetyDigest, AllocatedAt: time.Now().UTC()}
	creationRaw, _ := json.Marshal(creation)
	creationEvidence := write("creation.json", creationRaw)
	fact := wire.PostSafetyRuntimeFact{Mode: "new_runtime", Binding: binding, Authorization: authEvidence, Creation: creationEvidence, PreviousBinding: nil, Recovery: nil, Closures: []wire.PostSafetyRuntimeClosure{{Kind: "account_closure", RecordCount: 0, CanonicalDigest: "sha256:" + strings.Repeat("d", 64), Watermark: "account-watermark", OwnerEvidence: account}, {Kind: "post_safety", RecordCount: 0, CanonicalDigest: safetyDigest, Watermark: "safety-watermark", OwnerEvidence: creationEvidence}}, RecordedAt: time.Now().UTC()}
	factRaw, _ := json.Marshal(fact)
	factEvidence := write("fact.json", factRaw)
	current := wire.PostSafetyRuntimeCurrentBinding{Binding: binding, Fact: factEvidence}
	currentRaw, _ := json.Marshal(current)
	currentEvidence := write("current.json", currentRaw)
	startup := wire.PostSafetyDeploymentStartupMaterial{Environment: environment, Target: environment + "-local", CandidateDigest: binding.CandidateDigest, DataPlaneBindingDigest: binding.DataPlaneBindingDigest, StartupAttemptId: "attempt-1", RuntimeGeneration: binding.RuntimeGeneration, Authorization: authEvidence, AccountClosureAuthority: wire.PostSafetyAccountClosureAuthorityDescriptor{AccountClosureEvidence: account}, PostSafetyCurrent: &currentEvidence}
	startupRaw, _ := json.Marshal(startup)
	write("startup.json", startupRaw)
	return root, startup
}

func signRuntimeAuthorization(t *testing.T, value wire.PostSafetyRuntimeAuthorization) string {
	t.Helper()
	path := filepath.Join(os.Getenv("HOME"), ".cache/quwoquan/keys/evidence-signing/quwoquan-environment-ops-local.ed25519.pem")
	pemRaw, err := os.ReadFile(path)
	if err != nil {
		t.Skip("paired test authority key unavailable")
	}
	block, _ := pem.Decode(pemRaw)
	if block == nil {
		t.Fatal("invalid authority PEM")
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		t.Fatal(err)
	}
	private, ok := parsed.(ed25519.PrivateKey)
	if !ok {
		t.Fatal("authority key is not Ed25519")
	}
	raw, _ := json.Marshal(value)
	var object map[string]any
	_ = json.Unmarshal(raw, &object)
	delete(object, "signature")
	payload, _ := json.Marshal(object)
	pae := []byte("DSSEv1 " + strconv.Itoa(len(runtimeAuthorizationPayloadTypeForTest)) + " " + runtimeAuthorizationPayloadTypeForTest + " " + strconv.Itoa(len(payload)) + " ")
	pae = append(pae, payload...)
	return "ed25519:" + base64.StdEncoding.EncodeToString(ed25519.Sign(private, pae))
}
func mustRemove(t *testing.T, path string) {
	t.Helper()
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
}
func tamperRuntimeFile(t *testing.T, path string) {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	mustRemove(t, path)
	raw = append(raw, ' ')
	if err = os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
}
func cloneRuntimeFixture(t *testing.T, source string) string {
	t.Helper()
	target, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(target, 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(filepath.Join(target, "secrets"), 0700); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"startup.json", "current.json", "fact.json", "authorization.json", "account-closure.json", "creation.json", "secrets/post-safety.key"} {
		raw, e := os.ReadFile(filepath.Join(source, name))
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(filepath.Join(target, name), raw, 0600); e != nil {
			t.Fatal(e)
		}
	}
	return target
}
