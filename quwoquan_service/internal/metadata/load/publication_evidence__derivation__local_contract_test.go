package load_test

import (
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/load"
)

// 事务性事件发布 seam 的证据由归属（`storage.yaml` 的 `publication_role`）与真实性
// （服务内对该存储的事务性追加）合成。这组用例锁死「任一半单独都不成立」：
//
//   - 只有代码：证据的主语会变成文件位置而不是归属。清理型代码会写兄弟对象的发件箱，
//     消费侧代码会引用别人的发件箱，按文件位置扫都会误判成拥有。
//   - 只有声明：声明不证明表存在、更不证明有人往里发布。
func TestPublicationSeamEvidenceRequiresOwnershipAndTransactionalWrite(t *testing.T) {
	t.Parallel()

	transactionalAppend := "package persistence\n\nimport (\n\t\"context\"\n\n" +
		"\t\"github.com/jackc/pgx/v5\"\n)\n\n" +
		"func appendEvent(ctx context.Context, tx pgx.Tx, payload []byte) error {\n" +
		"\t_, err := tx.Exec(ctx, " +
		"`INSERT INTO demo_object_outbox(id, payload) VALUES ($1, $2)`, payload)\n" +
		"\treturn err\n}\n"

	for name, expectation := range map[string]struct {
		storage           string
		appendSource      string
		wantSeamStores    []string
		wantUnannotated   []string
		wantOutboxStorage string
	}{
		"标注归属且有事务性追加": {
			storage: "backend: postgres\nrole: authoritative\ntables:\n" +
				"  demo_objects:\n    publication_role: not_published\n" +
				"  demo_object_outbox:\n    publication_role: transactional_outbox\n",
			appendSource:      transactionalAppend,
			wantSeamStores:    []string{"demo_object_outbox"},
			wantOutboxStorage: "demo_object_outbox",
		},
		"事务性事件表与发件箱同权": {
			storage: "backend: postgres\nrole: authoritative\ntables:\n" +
				"  demo_object_outbox:\n    publication_role: transactional_event_log\n",
			appendSource:      transactionalAppend,
			wantSeamStores:    []string{"demo_object_outbox"},
			wantOutboxStorage: "demo_object_outbox",
		},
		// 名字含 outbox 的配件不是发布 seam：全仓 90 条 outbox 名声明里有 24 条是
		// sequences / dead_letters / checkpoints，判别位是字段而不是名字。
		"配件标注不构成发布 seam": {
			storage: "backend: postgres\nrole: authoritative\ntables:\n" +
				"  demo_object_outbox:\n    publication_role: publication_accessory\n",
			appendSource: transactionalAppend,
		},
		"未标注不得被读成不发布": {
			storage: "backend: postgres\nrole: authoritative\ntables:\n" +
				"  demo_object_outbox: {}\n",
			appendSource:    transactionalAppend,
			wantUnannotated: []string{"demo_object_outbox"},
		},
		// 「建了表、有了句柄、没人发布」是这条口径要拦的假实现形态。
		"标注了归属但没有事务性追加": {
			storage: "backend: postgres\nrole: authoritative\ntables:\n" +
				"  demo_object_outbox:\n    publication_role: transactional_outbox\n",
			appendSource: "package persistence\n\nimport \"context\"\n\n" +
				"func appendEvent(ctx context.Context, pool pool) error {\n" +
				"\t_, err := pool.Exec(ctx, \"INSERT INTO demo_object_outbox(id) VALUES ($1)\", 1)\n" +
				"\treturn err\n}\n",
			wantSeamStores: []string{"demo_object_outbox"},
		},
		"标注的存储与代码里的关系名不一致": {
			storage: "backend: postgres\nrole: authoritative\ntables:\n" +
				"  demo_object_declared_only_outbox:\n    publication_role: transactional_outbox\n",
			appendSource:   transactionalAppend,
			wantSeamStores: []string{"demo_object_declared_only_outbox"},
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
			serviceRoot := filepath.Join(
				repo.root, "quwoquan_service", "services", "demo-service",
			)
			repo.write(
				t,
				filepath.Join(
					serviceRoot, "contracts", "demo_context", "demo_object", "storage.yaml",
				),
				expectation.storage,
			)
			repo.write(
				t,
				filepath.Join(
					serviceRoot, "internal", "demo_context", "demo_object",
					"infrastructure", "persistence", "postgres_store.go",
				),
				expectation.appendSource,
			)
			evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))

			if got := strings.Join(evidence.PublicationStores, "|"); got !=
				strings.Join(expectation.wantSeamStores, "|") {
				t.Fatalf("publicationStores=%v, want %v",
					evidence.PublicationStores, expectation.wantSeamStores)
			}
			if got := strings.Join(evidence.UnannotatedStores, "|"); got !=
				strings.Join(expectation.wantUnannotated, "|") {
				t.Fatalf("unannotatedStores=%v, want %v",
					evidence.UnannotatedStores, expectation.wantUnannotated)
			}
			if expectation.wantOutboxStorage == "" {
				if len(evidence.Service.Outbox) != 0 {
					t.Fatalf("outbox 证据=%+v, want empty", evidence.Service.Outbox)
				}
				return
			}
			if len(evidence.Service.Outbox) == 0 {
				t.Fatal("outbox 证据为空, want 存储名 → 写入位置绑定")
			}
			for _, binding := range evidence.Service.Outbox {
				if binding.Storage != expectation.wantOutboxStorage {
					t.Fatalf("outbox 证据绑定了 %q, want %q",
						binding.Storage, expectation.wantOutboxStorage)
				}
				if binding.Artifact.Path == "" || len(binding.Artifact.SHA256) != 64 {
					t.Fatalf("outbox artifact 未绑定 path/sha256: %+v", binding.Artifact)
				}
			}
		})
	}
}

// 装配处传入集合名、共享参数化 store 执行事务性写入，是全仓的主流形态：
// `NewMongoAggregateCommandStore(db, receipts, outbox)` 在 cmd 里以三个不同集合名实例化
// 三份。字面量与写入相隔跨文件，所以判定必须能沿构造函数这条调用边把集合名路由回 store 包，
// 而不是靠语句临近性。
func TestPublicationSeamEvidenceFollowsConstructorInjectedCollectionNames(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	serviceRoot := filepath.Join(repo.root, "quwoquan_service", "services", "demo-service")
	repo.write(
		t,
		filepath.Join(serviceRoot, "contracts", "demo_context", "demo_object", "storage.yaml"),
		"backend: mongodb\nrole: authoritative\ncollections:\n"+
			"  demo_object_outbox:\n    publication_role: transactional_outbox\n",
	)
	// store 包只知道参数，不知道集合名。
	repo.write(
		t,
		filepath.Join(
			serviceRoot, "internal", "demo_context", "demo_sibling",
			"infrastructure", "persistence", "mongo_aggregate_command_store.go",
		),
		"package persistence\n\nimport (\n\t\"context\"\n\n"+
			"\t\"go.mongodb.org/mongo-driver/mongo\"\n)\n\n"+
			"type Store struct{ outbox *mongo.Collection }\n\n"+
			"func NewMongoAggregateCommandStore(db *mongo.Database, outbox string) *Store {\n"+
			"\treturn &Store{outbox: db.Collection(outbox)}\n}\n\n"+
			"func (s *Store) Append(sessionContext mongo.SessionContext, doc any) error {\n"+
			"\t_, err := s.outbox.InsertOne(sessionContext, doc)\n\treturn err\n}\n",
	)
	// 集合名字面量只出现在装配处。
	repo.write(
		t,
		filepath.Join(serviceRoot, "cmd", "api", "main.go"),
		"package main\n\nimport (\n\t\"go.mongodb.org/mongo-driver/mongo\"\n\n"+
			"\t\"demo/internal/demo_context/demo_sibling/infrastructure/persistence\"\n)\n\n"+
			"func wire(db *mongo.Database) {\n"+
			"\t_ = persistence.NewMongoAggregateCommandStore(db, \"demo_object_outbox\")\n}\n",
	)
	// 删掉对象树内的直接实现，确保证据只可能来自跨目录解析。
	repo.write(
		t,
		filepath.Join(
			serviceRoot, "internal", "demo_context", "demo_object",
			"infrastructure", "persistence", "postgres_store.go",
		),
		"package persistence\n",
	)

	evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))
	if len(evidence.Service.Outbox) == 0 {
		t.Fatal("outbox 证据为空：写入方在兄弟目录的共享 store 里也必须能被归属")
	}
	for _, binding := range evidence.Service.Outbox {
		if binding.Storage != "demo_object_outbox" {
			t.Fatalf("outbox 证据绑定了 %q, want demo_object_outbox", binding.Storage)
		}
		if binding.Artifact.Path == "" || len(binding.Artifact.SHA256) != 64 {
			t.Fatalf("outbox artifact 未绑定 path/sha256: %+v", binding.Artifact)
		}
	}
}
