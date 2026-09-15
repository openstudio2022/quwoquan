package safety

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"reflect"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/safety"
)

// ReadPhysicalSafetyIdentity读取现役安全collection的provider UUID。
// namespace复制/重建会分配不同UUID；endpoint、replica-set名称、caller字符串不能代替。
// 不创建collection，缺失不是新实例证明。
func ReadPhysicalSafetyIdentity(ctx context.Context, db *mongo.Database) (string, error) {
	if db == nil {
		return "", errRuntimeMaterial
	}
	// listCollections 是 deployment identity 读端，不属于业务事务；Mongo 禁止在
	// transaction 内执行该命令，因此 operation 复验使用独立、短时管理读上下文。
	identityCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	specs, err := db.ListCollectionSpecifications(identityCtx, bson.M{"name": Collection})
	if err != nil {
		return "", fmt.Errorf("%w: physical identity unavailable", errRuntimeMaterial)
	}
	if len(specs) != 1 || specs[0].UUID == nil || len(specs[0].UUID.Data) != 16 {
		return "", errRuntimeMaterial
	}
	return "mongodb-collection-uuid:" + hex.EncodeToString(specs[0].UUID.Data), nil
}

// StrictRuntimeJSON按generated DTO反射校验raw presence，包括显式null；不手抄schema。
// 不允许重复key、未知key或多个JSON值，timestamp严格解析交由typed decoder。
func StrictRuntimeJSON(raw []byte, target any) error {
	typ := reflect.TypeOf(target)
	if typ == nil || typ.Kind() != reflect.Pointer || reflect.ValueOf(target).IsNil() {
		return errRuntimeMaterial
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	value, err := readUniqueJSON(dec)
	if err != nil {
		return errRuntimeMaterial
	}
	if _, err = dec.Token(); err != io.EOF {
		return errRuntimeMaterial
	}
	if err = validateRuntimeShape(value, typ.Elem()); err != nil {
		return err
	}
	typed := json.NewDecoder(bytes.NewReader(raw))
	typed.DisallowUnknownFields()
	if err = typed.Decode(target); err != nil {
		return errRuntimeMaterial
	}
	return nil
}
func strictCanonicalRuntimeJSON(raw []byte, target any) error {
	if err := StrictRuntimeJSON(raw, target); err != nil {
		return err
	}
	canonical, err := json.Marshal(target)
	if err != nil || !bytes.Equal(raw, canonical) {
		return errRuntimeMaterial
	}
	return nil
}

// strictCanonicalRuntimeAuthorizationJSON按Python producer固定六位UTC微秒编码复原。
// Go time.Time序列化会裁掉小数秒尾零，因此不能仅靠generated DTO重编码来核验
// producer的exact canonical bytes。
func strictCanonicalRuntimeAuthorizationJSON(raw []byte, target *wire.PostSafetyRuntimeAuthorization) error {
	if err := StrictRuntimeJSON(raw, target); err != nil {
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
	}{
		Environment: target.Environment, Target: target.Target,
		CandidateDigest: target.CandidateDigest, DataPlaneBindingDigest: target.DataPlaneBindingDigest,
		StartupAttemptId: target.StartupAttemptId, RuntimeGeneration: target.RuntimeGeneration,
		Action: target.Action, IssuedAt: target.IssuedAt.UTC().Format("2006-01-02T15:04:05.000000Z"),
		AuthorityIdentity: target.AuthorityIdentity, EvidencePredecessor: target.EvidencePredecessor,
		Signature: target.Signature,
	}
	canonical, err := json.Marshal(exact)
	if err != nil || !bytes.Equal(raw, canonical) {
		return errRuntimeMaterial
	}
	return nil
}

func readUniqueJSON(dec *json.Decoder) (any, error) {
	token, err := dec.Token()
	if err != nil {
		return nil, err
	}
	delim, ok := token.(json.Delim)
	if !ok {
		return token, nil
	}
	switch delim {
	case '{':
		result := map[string]any{}
		for dec.More() {
			key, err := dec.Token()
			if err != nil {
				return nil, err
			}
			name, ok := key.(string)
			if !ok {
				return nil, errRuntimeMaterial
			}
			if _, ok = result[name]; ok {
				return nil, errRuntimeMaterial
			}
			value, err := readUniqueJSON(dec)
			if err != nil {
				return nil, err
			}
			result[name] = value
		}
		_, err = dec.Token()
		return result, err
	case '[':
		result := []any{}
		for dec.More() {
			value, err := readUniqueJSON(dec)
			if err != nil {
				return nil, err
			}
			result = append(result, value)
		}
		_, err = dec.Token()
		return result, err
	default:
		return nil, errRuntimeMaterial
	}
}
func validateRuntimeShape(value any, typ reflect.Type) error {
	if typ.Kind() == reflect.Pointer {
		if value == nil {
			return nil
		}
		return validateRuntimeShape(value, typ.Elem())
	}
	if value == nil {
		return errRuntimeMaterial
	}
	if typ == reflect.TypeOf(time.Time{}) {
		if _, ok := value.(string); !ok {
			return errRuntimeMaterial
		}
		return nil
	}
	switch typ.Kind() {
	case reflect.Struct:
		object, ok := value.(map[string]any)
		if !ok {
			return errRuntimeMaterial
		}
		count := 0
		for i := 0; i < typ.NumField(); i++ {
			field := typ.Field(i)
			name := strings.Split(field.Tag.Get("json"), ",")[0]
			if name == "-" {
				continue
			}
			if name == "" {
				name = field.Name
			}
			count++
			member, present := object[name]
			if !present {
				return errRuntimeMaterial
			}
			if err := validateRuntimeShape(member, field.Type); err != nil {
				return err
			}
		}
		if len(object) != count {
			return errRuntimeMaterial
		}
	case reflect.Slice:
		rows, ok := value.([]any)
		if !ok {
			return errRuntimeMaterial
		}
		for _, row := range rows {
			if err := validateRuntimeShape(row, typ.Elem()); err != nil {
				return err
			}
		}
	}
	return nil
}
func RuntimeKeyIdentity(key []byte) (string, error) {
	if len(key) < 32 {
		return "", errRuntimeMaterial
	}
	hash := hmac.New(sha256.New, key)
	_, _ = hash.Write([]byte("quwoquan/content.post/post-safety-runtime/key-identity"))
	sum := sha256.Sum256(hash.Sum(nil))
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

// inspectRuntimeFact只做typed材料与真实存储身份核验，不代替creation动作授权或owner闭包验证。
// expected必须来自受管部署供给，禁止调用者从待验fact反填；未完成上游核验不能用本函数开放HTTP。
func inspectRuntimeFact(ctx context.Context, db *mongo.Database, files *RuntimeFiles, currentRef, factRef, keyRef string, expected wire.PostSafetyRuntimeBinding) (wire.PostSafetyRuntimeFact, error) {
	var fact wire.PostSafetyRuntimeFact
	currentBytes, err := files.Read(currentRef, 1<<20)
	if err != nil {
		return fact, err
	}
	var current wire.PostSafetyRuntimeCurrentBinding
	if err = StrictRuntimeJSON(currentBytes, &current); err != nil {
		return fact, err
	}
	if current.Binding != expected || current.Fact.Ref != factRef || db == nil || db.Name() != expected.Namespace {
		return fact, errRuntimeMaterial
	}
	physical, err := ReadPhysicalSafetyIdentity(ctx, db)
	if err != nil {
		return fact, err
	}
	if physical != expected.PhysicalInstanceId {
		return fact, errRuntimeMaterial
	}
	key, err := files.Read(keyRef, 4096)
	if err != nil {
		return fact, err
	}
	defer clear(key)
	identity, err := RuntimeKeyIdentity(key)
	if err != nil || identity != expected.HmacKeyIdentity {
		return fact, errRuntimeMaterial
	}
	raw, err := files.ReadDigest(factRef, current.Fact.Digest)
	if err != nil {
		return fact, err
	}
	if err = StrictRuntimeJSON(raw, &fact); err != nil {
		return fact, err
	}
	if fact.Binding != expected || fact.RecordedAt.IsZero() {
		return fact, errRuntimeMaterial
	}
	if expected.Target != expected.Environment+"-local" || (expected.Environment != "alpha" && expected.Environment != "beta" && expected.Environment != "gamma") {
		return fact, errRuntimeMaterial
	}
	if !validDigest(expected.CandidateDigest) || !validDigest(expected.DataPlaneBindingDigest) || expected.ResourceRef == "" || expected.RuntimeGeneration == "" {
		return fact, errRuntimeMaterial
	}
	switch fact.Mode {
	case "new_runtime":
		if fact.PreviousBinding != nil || fact.Recovery != nil {
			return fact, errRuntimeMaterial
		}
	case "restored":
		return fact, fmt.Errorf("%w: complete recovery owner readback is required", errRuntimeMaterial)
	default:
		return fact, errRuntimeMaterial
	}
	if len(fact.Closures) != 2 || fact.Closures[0].Kind != "account_closure" || fact.Closures[1].Kind != "post_safety" {
		return fact, errRuntimeMaterial
	}
	for _, closure := range fact.Closures {
		if closure.RecordCount != 0 || !validDigest(closure.CanonicalDigest) || closure.Watermark == "" {
			return fact, errRuntimeMaterial
		}
		if _, err = files.ReadDigest(closure.OwnerEvidence.Ref, closure.OwnerEvidence.Digest); err != nil {
			return fact, err
		}
	}
	if _, err = files.ReadDigest(fact.Authorization.Ref, fact.Authorization.Digest); err != nil {
		return fact, err
	}
	creationBytes, err := files.ReadDigest(fact.Creation.Ref, fact.Creation.Digest)
	if err != nil {
		return fact, err
	}
	var creation wire.PostSafetyRuntimeCreationReceipt
	if err = StrictRuntimeJSON(creationBytes, &creation); err != nil {
		return fact, err
	}
	if creation.Binding != expected || creation.PhysicalAllocationId != physical || creation.NamespaceReadback != db.Name() || creation.AllocationAttemptId == "" || creation.AllocatedAt.IsZero() || creation.InitialSafetyRecordCount != 0 || creation.InitialSafetyCanonicalDigest != fact.Closures[1].CanonicalDigest {
		return fact, errRuntimeMaterial
	}
	// 防读取期间current发生切换；不声称这一采样是跨进程generation租约。
	again, err := files.Read(currentRef, 1<<20)
	if err != nil || !bytes.Equal(currentBytes, again) {
		return fact, errRuntimeMaterial
	}
	return fact, nil
}

const (
	runtimeAuthorizationPayloadType = "application/vnd.quwoquan.post-safety-runtime-authorization.v1+json"
	runtimeAuthorizationIdentity    = "quwoquan-environment-ops-local"
	runtimeAuthorizationPublicKey   = "DA+JAaxsgD8Aq1vDz458finqg+X2tuXDUFPKaSi5wwg="
)

func verifyRuntimeAuthorization(raw []byte, value wire.PostSafetyRuntimeAuthorization) error {
	return verifyRuntimeAuthorizationWithKey(raw, value, runtimeAuthorizationIdentity, runtimeAuthorizationPublicKey)
}

func verifyRuntimeAuthorizationWithKey(raw []byte, value wire.PostSafetyRuntimeAuthorization, expectedIdentity, encodedPublicKey string) error {
	if value.AuthorityIdentity != expectedIdentity || value.Signature == "" {
		return errRuntimeMaterial
	}
	var object map[string]any
	if StrictRuntimeJSON(raw, &value) != nil || json.Unmarshal(raw, &object) != nil {
		return errRuntimeMaterial
	}
	delete(object, "signature")
	payload, err := json.Marshal(object)
	if err != nil {
		return errRuntimeMaterial
	}
	encoded := strings.TrimPrefix(value.Signature, "ed25519:")
	if encoded == value.Signature {
		return errRuntimeMaterial
	}
	signature, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return errRuntimeMaterial
	}
	publicKey, err := base64.StdEncoding.DecodeString(encodedPublicKey)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return errRuntimeMaterial
	}
	pae := []byte("DSSEv1 " + strconv.Itoa(len(runtimeAuthorizationPayloadType)) + " " + runtimeAuthorizationPayloadType + " " + strconv.Itoa(len(payload)) + " ")
	pae = append(pae, payload...)
	if !ed25519.Verify(ed25519.PublicKey(publicKey), pae, signature) {
		return errRuntimeMaterial
	}
	return nil
}

// RuntimeAuthority是Content生产装配消费的不可变安全材料authority。每次调用都
// 从受保护根重新读取startup/current/fact，并复核真实Mongo collection UUID和密钥身份。
type RuntimeAuthority struct {
	db          *mongo.Database
	files       *RuntimeFiles
	environment string
	startupRef  string
	currentRef  string
	factRef     string
	keyRef      string
	account     rtauth.AccountSecurityAuthority
}

// LoadRuntimeAuthority在任何Post索引或listener暴露前执行完整首次验证，并返回
// Manager所需的独立HMAC key。Prod只能消费正式writer材料；当前非生产
// authorization合同明确不包含prod，因此此reader对prod保持fail-closed。
// OpenRuntimeManager 是 API 与 release importer 唯一的 Post Safety 装配入口。
// 两者必须传入各自进程已经解析出的 canonical Mongo database 与账号安全
// authority；本函数只消费环境 owner 发布的完整 startup/current/recovery/HMAC
// 材料，绝不从候选 payload 推导或补写 authority。
func OpenRuntimeManager(ctx context.Context, db *mongo.Database, environment, root, currentRef, factRef, keyRef string, account rtauth.AccountSecurityAuthority) (*Manager, error) {
	authority, key, err := LoadRuntimeAuthority(ctx, db, environment, root, currentRef, factRef, keyRef, account)
	if err != nil {
		return nil, err
	}
	defer clear(key)
	manager, err := New(db, environment, key, authority)
	if err != nil {
		return nil, err
	}
	if err = manager.EnsureIndexes(ctx); err != nil {
		return nil, err
	}
	return manager, nil
}

func LoadRuntimeAuthority(ctx context.Context, db *mongo.Database, environment, root, currentRef, factRef, keyRef string, account rtauth.AccountSecurityAuthority) (*RuntimeAuthority, []byte, error) {
	if db == nil || environment == "prod" {
		return nil, nil, app.ErrPostSafetyNotReady
	}
	files, err := OpenRuntimeFiles(root)
	if err != nil {
		return nil, nil, app.ErrPostSafetyNotReady
	}
	a := &RuntimeAuthority{db: db, files: files, environment: environment, startupRef: "startup.json", currentRef: currentRef, factRef: factRef, keyRef: keyRef, account: account}
	if err = a.VerifyRecovery(ctx); err != nil {
		return nil, nil, err
	}
	key, err := files.Read(keyRef, 4096)
	if err != nil {
		return nil, nil, app.ErrPostSafetyNotReady
	}
	return a, key, nil
}

func (a *RuntimeAuthority) VerifyRecovery(ctx context.Context) error {
	if a == nil || a.files == nil || a.db == nil {
		return app.ErrPostSafetyNotReady
	}
	startupRaw, err := a.files.Read(a.startupRef, 1<<20)
	if err != nil {
		return app.ErrPostSafetyNotReady
	}
	var startup wire.PostSafetyDeploymentStartupMaterial
	if strictCanonicalRuntimeJSON(startupRaw, &startup) != nil || startup.PostSafetyCurrent == nil || startup.PostSafetyCurrent.Ref != a.currentRef {
		return fmt.Errorf("%w: startup", app.ErrPostSafetyNotReady)
	}
	currentRaw, err := a.files.ReadDigest(startup.PostSafetyCurrent.Ref, startup.PostSafetyCurrent.Digest)
	if err != nil {
		return fmt.Errorf("%w: current digest", app.ErrPostSafetyNotReady)
	}
	var current wire.PostSafetyRuntimeCurrentBinding
	if strictCanonicalRuntimeJSON(currentRaw, &current) != nil || current.Fact.Ref != a.factRef {
		return fmt.Errorf("%w: current shape", app.ErrPostSafetyNotReady)
	}
	binding := current.Binding
	if startup.Environment != binding.Environment || startup.Target != binding.Target || startup.CandidateDigest != binding.CandidateDigest || startup.DataPlaneBindingDigest != binding.DataPlaneBindingDigest || startup.RuntimeGeneration != binding.RuntimeGeneration {
		return fmt.Errorf("%w: deployment binding", app.ErrPostSafetyNotReady)
	}
	fact, err := inspectRuntimeFact(ctx, a.db, a.files, a.currentRef, a.factRef, a.keyRef, binding)
	if err != nil || fact.Authorization != startup.Authorization || fact.Closures[0].OwnerEvidence != startup.AccountClosureAuthority.AccountClosureEvidence {
		return fmt.Errorf("%w: runtime fact: %v", app.ErrPostSafetyNotReady, err)
	}
	var authorization wire.PostSafetyRuntimeAuthorization
	authorizationRaw, err := a.files.ReadDigest(startup.Authorization.Ref, startup.Authorization.Digest)
	if err != nil || strictCanonicalRuntimeAuthorizationJSON(authorizationRaw, &authorization) != nil || verifyRuntimeAuthorization(authorizationRaw, authorization) != nil || authorization.Environment != startup.Environment || authorization.Target != startup.Target || authorization.CandidateDigest != startup.CandidateDigest || authorization.DataPlaneBindingDigest != startup.DataPlaneBindingDigest || authorization.StartupAttemptId != startup.StartupAttemptId || authorization.RuntimeGeneration != startup.RuntimeGeneration || authorization.Action != "initialize_post_safety_runtime" || authorization.IssuedAt.IsZero() || authorization.AuthorityIdentity == "" || authorization.Signature == "" {
		return app.ErrPostSafetyNotReady
	}
	if authorization.EvidencePredecessor != startup.AccountClosureAuthority.AccountClosureEvidence {
		return app.ErrPostSafetyNotReady
	}
	if _, err = a.files.ReadDigest(authorization.EvidencePredecessor.Ref, authorization.EvidencePredecessor.Digest); err != nil {
		return app.ErrPostSafetyNotReady
	}
	again, err := a.files.Read(a.startupRef, 1<<20)
	if err != nil || !bytes.Equal(startupRaw, again) {
		return app.ErrPostSafetyNotReady
	}
	return nil
}

func (a *RuntimeAuthority) VerifySource(ctx context.Context, environment, owner, sourceID string) error {
	if err := a.VerifyRecovery(ctx); err != nil {
		return err
	}
	if environment == "" || environment != a.environment || sourceID == "" {
		return app.ErrPostSafetyConflict
	}
	switch owner {
	case "content":
		if a.account == nil {
			return app.ErrPostSafetyNotReady
		}
		snapshot, err := a.account.ReadAccountSecurity(ctx, sourceID)
		if err != nil || strings.TrimSpace(snapshot.AccountState) != "active" || snapshot.AuthEpoch < 1 {
			return app.ErrPostSafetyNotReady
		}
		return nil
	case "qwq_data":
		// sourceID是Post ID，而Data来源资格属于runtime级。这里不等待不存在的逐Post
		// servicekit reader；上面的VerifyRecovery已按当前startup/binding复验完整runtime材料。
		return nil
	default:
		return app.ErrPostSafetyConflict
	}
}

var _ app.PostSafetyAuthority = (*RuntimeAuthority)(nil)
