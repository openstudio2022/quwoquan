package load

import (
	"path/filepath"
	"testing"
)

// 归属侧（`publication_role` 标注）由契约线一次性补齐，实现侧的取真必须现在就锁死，否则
// 标注落地那天才发现解析漏了整类形态。这组用例直接对**现仓真实代码**建索引，覆盖五条曾经
// 判错或差点判错的形态。
func TestServiceWriteIndexResolvesRepositoryPublicationStores(t *testing.T) {
	t.Parallel()

	repoRoot := repositoryRootForTest(t)
	for name, expectation := range map[string]struct {
		service  string
		storage  string
		resolves bool
	}{
		// Postgres 是裸标识符：`INSERT INTO subject_follow_outbox(` 没有引号、紧跟左括号。
		// 只匹配带引号字面量会让 17 张 Postgres 表全漏。
		"裸标识符 SQL 关系位": {
			service:  "user-service",
			storage:  "subject_follow_outbox",
			resolves: true,
		},
		// 集合名只出现在 cmd 装配处，写入发生在兄弟目录的共享参数化 store：
		// `MongoAggregateCommandStore` 被三个集合名实例化三份。写入方所在目录是实现细节。
		"装配处注入的共享 store": {
			service:  "chat-service",
			storage:  "conversation_user_states_outbox",
			resolves: true,
		},
		// `event_store` 形态：事件表与聚合状态同事务提交，通篇没有 outbox 字样。
		"事务性事件表": {
			service:  "assistant-service",
			storage:  "skill_consent_events",
			resolves: true,
		},
		// 「声明了、代码里根本没有」必须解析不到，否则这条口径拦不住假实现。
		"仓内不存在的存储名": {
			service:  "chat-service",
			storage:  "conversation_user_states_ghost_outbox",
			resolves: false,
		},
		// 序列自增比发件箱追加还深一跳（`AppendAggregateOutboxEvents` → `nextOutboxSequence`），
		// 一跳事务传播跟不到，所以这里如实解析不到。它同时说明配件表为什么不能靠「解析
		// 得到/解析不到」来分类：分类只由 `publication_role` 判别位决定，索引解析结果
		// 只回答「有没有观测到写入」。
		"配件表深一跳、索引跟不到": {
			service:  "chat-service",
			storage:  "chat_aggregate_outbox_sequences",
			resolves: false,
		},
		// 只有集合句柄、没有任何写调用。判据从包级 join 收紧到函数内之后，这条必须解析
		// 不到：包级 join 会因为同包别处有事务写入而把它判成有发布实现。
		"只有句柄没有写调用": {
			service:  "content-service",
			storage:  "rm_search_intent",
			resolves: false,
		},
		// 集合句柄在构造处绑定到结构体字段、写入在方法里发生，字面量与写调用相隔数十行且
		// 跨文件。不解析字段绑定会让这一整类真实发件箱变成盲点。
		"构造处绑定字段、方法内写入": {
			service:  "content-service",
			storage:  "content_outbox",
			resolves: true,
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			index, err := buildServiceWriteIndex(
				filepath.Join(repoRoot, "quwoquan_service", "services", expectation.service),
			)
			if err != nil {
				t.Fatalf("build write index: %v", err)
			}
			site, ok := index.resolveTransactionalWrite(expectation.storage)
			if ok != expectation.resolves {
				t.Fatalf("resolve(%q)=%v, want %v", expectation.storage, ok, expectation.resolves)
			}
			if !ok {
				return
			}
			if site.file == "" || site.function == "" {
				t.Fatalf("resolve(%q) 没有绑定到具体的事务性写入位置", expectation.storage)
			}
		})
	}
}

// 投递判定必须读**真实存在**的实现行为，不读契约声明的索引。`content.report` 是反例：
// 契约声明了 `published_at` 列与 `idx_report_outbox_unpublished` 索引，真实 DDL 七列里
// 两者都不存在，实现走 `outbox_sequence` + `report_outbox_sequence` 检查点。按声明判会把
// 一个能投递的实现判成缺口；按「读取存储 + 推进进度」判则如实成立。
func TestDeliveryJudgementFollowsProvisionedBehaviourNotDeclaredIndexes(t *testing.T) {
	t.Parallel()

	repoRoot := repositoryRootForTest(t)
	for name, expectation := range map[string]struct {
		service  string
		storage  string
		delivers bool
	}{
		"检查点式投递（声明的索引建不出来）": {
			service:  "content-service",
			storage:  "report_outbox",
			delivers: true,
		},
		// CredentialBinding 两条领域事件仍是零业务 consumer 的
		// transactional_event_log；这里单独验证的是基础设施安全审计镜像确实完成
		// read -> durable append -> checkpoint，不能把它反推为 lifecycle edge。
		"CredentialBinding 已装配 durable audit mirror": {
			service:  "user-service",
			storage:  "credential_bindings_outbox",
			delivers: true,
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			index, err := buildServiceWriteIndex(
				filepath.Join(repoRoot, "quwoquan_service", "services", expectation.service),
			)
			if err != nil {
				t.Fatalf("build write index: %v", err)
			}
			if _, ok := index.resolveDeliveryImplementation(expectation.storage); ok != expectation.delivers {
				t.Fatalf("delivery(%q)=%v, want %v", expectation.storage, ok, expectation.delivers)
			}
		})
	}
}

// 消费侧接触不是拥有：`content.profile_interaction_activity_view` 的 projector 只读durable
// outbox（它自己的 port 注释写着 "used only by durable outbox consumers"），清理型工作流
// `content.content_account_closure_workflow` 会写 8 张兄弟对象的发件箱。两者按文件位置扫都
// 会拿到证据，按归属扫都不该拿到——所以这里断言的是「它们自己没有声明任何发布 seam」，
// 与索引能不能在服务内解析到这些表无关。
func TestConsumptionAndCleanupTouchDoNotDeclarePublicationOwnership(t *testing.T) {
	t.Parallel()

	repoRoot := repositoryRootForTest(t)
	for _, subject := range []struct {
		service string
		context string
		object  string
	}{
		{"content-service", "content", "profile_interaction_activity_view"},
		{"content-service", "content", "content_account_closure_workflow"},
		{"user-service", "identity", "authentication_challenge"},
	} {
		t.Run(subject.object, func(t *testing.T) {
			t.Parallel()
			publication, err := resolveStoragePublication(
				filepath.Join(repoRoot, "quwoquan_service", "services", subject.service),
				subject.context,
				subject.object,
			)
			if err != nil {
				t.Fatalf("resolve storage publication: %v", err)
			}
			if len(publication.seams) != 0 {
				t.Fatalf("%s 声明了发布 seam %v，与它只在消费侧/清理侧接触发件箱的事实矛盾",
					subject.object, publication.seams)
			}
		})
	}
}

// repositoryRootForTest 从包目录上溯到仓库根。这里不引入 testsupport：那条链会经 compiler
// 回到本包，在测试二进制里构成导入环。
func repositoryRootForTest(t *testing.T) string {
	t.Helper()
	working, err := filepath.Abs(".")
	if err != nil {
		t.Fatalf("resolve working directory: %v", err)
	}
	// internal/metadata/load -> internal/metadata -> internal -> quwoquan_service -> repo root
	root := filepath.Join(working, "..", "..", "..", "..")
	absolute, err := filepath.Abs(root)
	if err != nil {
		t.Fatalf("resolve repository root: %v", err)
	}
	if !isDir(filepath.Join(absolute, "quwoquan_service", "services")) {
		t.Fatalf("repository root %q 不含 quwoquan_service/services", absolute)
	}
	return absolute
}
