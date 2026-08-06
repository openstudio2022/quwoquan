package graph_test

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
)

// App handoff 的固定哈希握手记的是 ContractGraph 产物字节的 sha256，所以「同一磁盘输入
// 任意次编译产出逐字节相同」是握手能被满足的前提，不是可选优化。
//
// 每一轮都必须重新 load.Load：非确定性的入口是 loader 把 YAML mapping 展开成 governance
// slice 的装配处（Go map 的 `range` 顺序被运行时刻意随机化），复用同一个 catalog 只会重复
// graph.Build，看不见 map 顺序泄漏。断言同时覆盖 marshaled 产物与 governance 视图：
// DeclaredTypes 这类字段没有下游排序兜底，只有装配处收敛才稳定。
func TestContractGraphBytesAreStableAcrossIndependentLoads(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(
		t,
		metadataDir,
		"content/content/post",
		aggregateObject("Post"),
		commercialQuery("Post", "GetPost", "/content/posts/{postId}"),
	)
	writeObjectFixture(
		t,
		metadataDir,
		"content/content/comment",
		aggregateObject("Comment"),
		commercialQuery("Comment", "GetComment", "/content/comments/{commentId}"),
	)
	writeMappingHeavyFields(t, metadataDir, "content/content/post")
	writeMappingHeavyEvents(t, metadataDir, "content/content/post")

	var graphBytes, governanceBytes []byte
	for pass := 0; pass < 6; pass++ {
		catalog, err := load.Load(metadataDir)
		if err != nil {
			t.Fatalf("pass %d: load metadata: %v", pass, err)
		}
		contractGraph := graph.Build(catalog)
		encoded, err := contractcodegen.MarshalGraph(contractGraph)
		if err != nil {
			t.Fatalf("pass %d: marshal ContractGraph: %v", pass, err)
		}
		governance, err := json.Marshal(catalog.Governance)
		if err != nil {
			t.Fatalf("pass %d: marshal governance view: %v", pass, err)
		}
		if pass == 0 {
			graphBytes, governanceBytes = encoded, governance
			continue
		}
		if !bytes.Equal(graphBytes, encoded) {
			t.Fatalf(
				"pass %d produced different ContractGraph bytes from the same metadata",
				pass,
			)
		}
		if !bytes.Equal(governanceBytes, governance) {
			t.Fatalf(
				"pass %d produced a different governance view from the same metadata",
				pass,
			)
		}
	}
}

// writeMappingHeavyFields 用多条 mapping 形态的声明（enums / types / value_objects）压住
// 装配处：这些块在 YAML 里是 mapping，展开成 slice 时没有天然顺序。
func writeMappingHeavyFields(t *testing.T, metadataDir, relativeDir string) {
	t.Helper()
	writeFile(t, filepath.Join(metadataDir, relativeDir, "fields.yaml"), `
fields:
  - name: id
    type: string
    role: authoritative_state
  - name: status
    type: enum
    enum_ref: TestStatus
    role: authoritative_state
  - name: visibility
    type: enum
    enum_ref: PostVisibility
    role: authoritative_state
  - name: moderation
    type: enum
    enum_ref: PostModeration
    role: authoritative_state
types:
  PostAttribution:
    fields:
      - name: authorId
        type: string
        role: reference
      - name: authorName
        type: string
        role: owned_value
  PostMetrics:
    fields:
      - name: likeCount
        type: int
        role: projection
      - name: viewCount
        type: int
        role: projection
  PostAudit:
    fields:
      - name: reviewedBy
        type: string
        role: owned_value
value_objects:
  PostSlug:
    fields:
      - name: slug
        type: string
        role: owned_value
  PostLocale:
    fields:
      - name: locale
        type: string
        role: owned_value
enums:
  TestStatus: [active]
  PostVisibility: [public, followers, private]
  PostModeration: [pending_review, published, rejected]
`)
}

// writeMappingHeavyEvents 让同一对象声明多条领域事件，覆盖事件序列被逐条读进
// governance 后参与发布义务派生的路径。
func writeMappingHeavyEvents(t *testing.T, metadataDir, relativeDir string) {
	t.Helper()
	writeFile(t, filepath.Join(metadataDir, relativeDir, "events.yaml"), `
events:
  - name: PostPublished
    delivery_semantics: transactional_event_log
    topic: content.post.published
    no_consumer_reason: fixture event remains in the transactional event log
    payload_entity: Post
    payload_fields: [id, status]
  - name: PostModerated
    delivery_semantics: transactional_event_log
    topic: content.post.moderated
    no_consumer_reason: fixture event remains in the transactional event log
    payload_entity: Post
    payload_fields: [id, moderation]
  - name: PostDeleted
    delivery_semantics: transactional_event_log
    topic: content.post.deleted
    no_consumer_reason: fixture event remains in the transactional event log
    payload_entity: Post
    payload_fields: [id]
  - name: PostViewed
    delivery_semantics: best_effort_ephemeral
    no_consumer_reason: 瞬时信号没有下游订阅方
    payload_entity: Post
    payload_fields: [id]
  - name: PostDrafted
    delivery_semantics: not_published
    no_consumer_reason: 草稿事实自留在聚合内
    payload_entity: Post
    payload_fields: [id]
`)
}
