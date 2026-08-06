package ast

import "strings"

// StoragePublicationClass 是 `storage.yaml` 每张存储的 `publication_role` 取值分类。
// 它是「这张存储在事件发布中承担什么角色」的**唯一判别位**：readiness 不得再按存储名子串
// 猜测哪张表是发件箱。
//
// 为什么不能用名字：全仓 90 条名字含 `outbox` 的声明里有 24 条其实是配件
// （`*_outbox_sequences` 22、`*_outbox_dead_letters` 1、`*_outbox_checkpoints` 1），
// 还带着 `outbox_sequences` / `outbox_sequence` 的单复数漂移；反方向上 `skill_consent_events`
// 是真正的事务性事件表却完全不含 `outbox` 字样。把归属线建在名字子串上就是把它建在猜测上。
//
// 为什么不复用 per-collection `role`：`role`（`authoritative` / `append_only` /
// `projection` / …）表达的是访问语义，与「是否承载对外发布的事件」是两件事——同一张发件箱
// 在不同服务里被写成 `append_only`(42) / `authoritative`(24) / 未写(24)，把发布语义塞进去
// 会把两件事糅在一起，之后谁都拆不开。
type StoragePublicationClass int

const (
	// StoragePublicationUnannotated 表示这张存储没有标注 `publication_role`。
	// 未标注不等于不发布：它是**可见缺口**，由
	// `quwoquan_ops/gate/verify_object_evidence_closure.py` 报
	// `contract.storage_publication_unannotated`，绝不能被当成「不发布」静默豁免。
	StoragePublicationUnannotated StoragePublicationClass = iota
	// StoragePublicationTransactionalOutbox：事务性发件箱，与聚合状态同事务追加、由 relay 投递。
	StoragePublicationTransactionalOutbox
	// StoragePublicationTransactionalEventLog：事务性事件表（event_store 形态），事件即真相，
	// 允许零消费者，但同样要求与状态变更同事务可靠追加。
	StoragePublicationTransactionalEventLog
	// StoragePublicationAccessory：发布配件（sequences / checkpoints / dead_letters）。
	// 它服务于发布机制但自身不承载待投递事件，因此不构成发布 seam。
	StoragePublicationAccessory
	// StoragePublicationNotPublished：非发布型存储（聚合状态、投影、inbox 等）。
	StoragePublicationNotPublished
)

// IsPublicationSeam 表示这张存储本身是否构成事务性事件发布 seam。
// 只有发件箱与事务性事件表算；配件与非发布型都不算，未标注更不算（未标注要报缺口，
// 不能借「不算」变成豁免）。
func (class StoragePublicationClass) IsPublicationSeam() bool {
	return class == StoragePublicationTransactionalOutbox ||
		class == StoragePublicationTransactionalEventLog
}

var storagePublicationRoles = map[string]StoragePublicationClass{
	"transactional_outbox":    StoragePublicationTransactionalOutbox,
	"transactional_event_log": StoragePublicationTransactionalEventLog,
	"publication_accessory":   StoragePublicationAccessory,
	"not_published":           StoragePublicationNotPublished,
}

// ClassifyStoragePublicationRole 归一并分类 `publication_role`。
//
// 取值域由 `contracts/metadata/_schemas/storage.schema.json` 的 `publicationRole` enum
// 强制，所以 schema 校验通过后不存在未知取值；这里对未知取值仍按未标注处理，让缺口可见而
// 不是让它变成豁免。**不保留名字子串兜底**：留兜底就是留第二真相源。
func ClassifyStoragePublicationRole(role string) StoragePublicationClass {
	value := strings.ToLower(strings.TrimSpace(role))
	if class, ok := storagePublicationRoles[value]; ok {
		return class
	}
	return StoragePublicationUnannotated
}
