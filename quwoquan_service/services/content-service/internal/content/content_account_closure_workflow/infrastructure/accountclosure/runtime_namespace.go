package accountclosure

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	wire "quwoquan_service/services/content-service/generated/content/content_account_closure_workflow/contract/runtime"
)

var errRuntimeNamespace = errors.New("CONTENT.RELEASE.query_barrier_not_ready: account closure namespace creation/readback rejected")

// RuntimeNamespace持有本次独占创建动作的实际UUID，不提供运行授权。
// 只由受管producer调用；源User/outbox/Redis的创建与权限必须另行验证。
// 不接收caller填入的collection快照，零值无法伪造成成功allocation。
type RuntimeNamespace struct {
	db         *mongo.Database
	identities map[string]string
}

func runtimeCollections() []string {
	names := []string{InboxCollection, FailureCollection, SearchWorkCollection, MediaArtifactWorkCollection,
		ClosedSubjectCollection, ClosedSubjectTombstoneCollection, contentAccountRestrictionStateCollection,
		contentAccountRestrictionInboxCollection, contentAccountRestrictionWatermarkCollection}
	sort.Strings(names)
	return names
}

// CreateRuntimeNamespace仅创建，不推断旧namespace为new；失败不删除或覆盖任何资源。
// 执行前调用者必须持有受管target排他锁、批准资源及尚未开放的写入窗口。
func CreateRuntimeNamespace(ctx context.Context, db *mongo.Database, environment, target string) (*RuntimeNamespace, error) {
	if db == nil || target != environment+"-local" || (environment != "alpha" && environment != "beta" && environment != "gamma") {
		return nil, errRuntimeNamespace
	}
	existing, err := db.ListCollectionNames(ctx, bson.M{})
	if err != nil {
		return nil, err
	}
	if len(existing) != 0 {
		return nil, errRuntimeNamespace
	}
	allocation := &RuntimeNamespace{db: db, identities: make(map[string]string)}
	for _, name := range runtimeCollections() {
		// create命令而非隐式insert/index；并发或部分既存资源直接失败，保留partial诊断。
		if err := db.CreateCollection(ctx, name); err != nil {
			return nil, err
		}
		identity, err := runtimeCollectionUUID(ctx, db, name)
		if err != nil {
			return nil, err
		}
		allocation.identities[name] = identity
	}
	if _, _, err := allocation.InitialClosure(ctx); err != nil {
		return nil, err
	}
	return allocation, nil
}

func runtimeCollectionUUID(ctx context.Context, db *mongo.Database, name string) (string, error) {
	specs, err := db.ListCollectionSpecifications(ctx, bson.M{"name": name})
	if err != nil {
		return "", err
	}
	if len(specs) != 1 || specs[0].UUID == nil || len(specs[0].UUID.Data) != 16 {
		return "", errRuntimeNamespace
	}
	return "mongodb-collection-uuid:" + hex.EncodeToString(specs[0].UUID.Data), nil
}

// VerifyIdentity只核验持续物理身份；正常写入增长不再与初始空摘要比较。
func (a *RuntimeNamespace) VerifyIdentity(ctx context.Context) error {
	if a == nil || a.db == nil || len(a.identities) != len(runtimeCollections()) {
		return errRuntimeNamespace
	}
	for _, name := range runtimeCollections() {
		actual, err := runtimeCollectionUUID(ctx, a.db, name)
		if err != nil {
			return err
		}
		if actual != a.identities[name] {
			return errRuntimeNamespace
		}
	}
	return nil
}

// InitialClosure只用于首次初始化停写窗口，真实遍历九集合且仅接受本次创建空态。
// 返回generated owner DTO和绑定逐集合UUID的canonical摘要，不是完整runtime evidence。
func (a *RuntimeNamespace) InitialClosure(ctx context.Context) ([]wire.ContentAccountClosureRuntimeCollection, string, error) {
	if err := a.VerifyIdentity(ctx); err != nil {
		return nil, "", err
	}
	rows := make([]wire.ContentAccountClosureRuntimeCollection, 0, len(a.identities))
	canonical := make([]map[string]any, 0, len(a.identities))
	for _, name := range runtimeCollections() {
		cursor, err := a.db.Collection(name).Find(ctx, bson.M{})
		if err != nil {
			return nil, "", err
		}
		nonempty := cursor.Next(ctx)
		readErr := cursor.Err()
		closeErr := cursor.Close(ctx)
		if readErr != nil {
			return nil, "", readErr
		}
		if closeErr != nil {
			return nil, "", closeErr
		}
		if nonempty {
			return nil, "", errRuntimeNamespace
		}
		row := wire.ContentAccountClosureRuntimeCollection{Collection: name, PhysicalInstanceId: a.identities[name], RecordCount: 0, CanonicalDigest: closureDigest([]byte("[]"))}
		rows = append(rows, row)
		// map序列化递归按键排序，满足owner canonical JSON规则，不依赖DTO字段声明顺序。
		canonical = append(canonical, map[string]any{"collection": row.Collection, "physicalInstanceId": row.PhysicalInstanceId, "recordCount": row.RecordCount, "canonicalDigest": row.CanonicalDigest})
	}
	if err := a.VerifyIdentity(ctx); err != nil {
		return nil, "", err
	}
	raw, err := json.Marshal(canonical)
	if err != nil {
		return nil, "", err
	}
	return rows, closureDigest(raw), nil
}

func closureDigest(raw []byte) string {
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:])
}
