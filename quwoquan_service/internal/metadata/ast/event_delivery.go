package ast

import "strings"

// EventDeliveryClass 是 `events.yaml` 的 `delivery_semantics` 取值按**投递保证**的分类。
// 它是 readiness 判定「该聚合是否必须具备事务性事件发布 seam」的唯一依据：发件箱存在的
// 理由是「状态已提交、事件却可能丢失」这一跨边界后果，所以分类问的是投递保证，而不是
// kind、也不是当前有没有 consumer。
//
// 不看 consumer 是刻意的：consumer 归属在别的服务手里，把本对象的可靠性义务挂在别人是否
// 订阅上会产生远距离作用——别的服务加一条订阅就能让这个对象悄悄变红，撤掉又变绿，而本对象
// 什么都没改。可靠性义务必须由声明方自己的契约事实决定。
//
// 前身是 `channel`：一个没有值域的字段，同时混装投递机制、topic 名和笔误（`outbox` 6 处）。
// 拆分后取值域由 `contracts/metadata/_schemas/events.schema.json` 的 `deliverySemantics`
// enum 强制，topic 名归 `topic` 字段。所以 Unrecognized/Absent 在 schema 校验通过后不可能
// 出现；这里仍保留它们并 fail-safe 到要求侧，是为了让绕过 schema 的调用路径不会白拿一个达标。
type EventDeliveryClass int

const (
	EventDeliveryUnrecognized EventDeliveryClass = iota
	EventDeliverySelfRetained
	EventDeliveryCrossBoundary
)

// RequiresReliablePublication 表示该分类是否要求对象具备事务性事件发布 seam。
// 只有 SelfRetained 不要求；未知取值落在要求侧。
func (class EventDeliveryClass) RequiresReliablePublication() bool {
	return class != EventDeliverySelfRetained
}

// selfRetainedDeliverySemantics：事件不产生「状态已提交、事件却丢了」的跨边界后果。
//
//   - not_published：事件留在聚合自己的存储里（聚合自留的事实 / journal），读取方直接读
//     aggregate。与 storage.yaml 的 `publication_role: not_published` 同义。
//   - best_effort_ephemeral：语义上明确允许丢失的瞬时信号；持久真相由另一条事件承载，
//     丢了由端侧重新拉取。
var selfRetainedDeliverySemantics = map[string]struct{}{
	"not_published":         {},
	"best_effort_ephemeral": {},
}

// crossBoundaryDeliverySemantics：事件必须跨出聚合存储边界，或本身要求被可靠留存。
//
//   - transactional_outbox：与聚合状态同事务写入发件箱，由 relay 搬运出去。与 storage.yaml
//     的 `publication_role: transactional_outbox` 同义。
//   - transactional_event_log：与聚合状态同事务追加到事务性事件表，可靠落地即完成义务，
//     不需要搬运（零消费者也要追加）。与 `publication_role: transactional_event_log` 同义。
//   - durable_stream：直接追加进有留存的 durable stream，产出侧没有事务性发件箱。提交后
//     丢失即下游永久不一致。
//   - synchronous_call：跨边界同步调用 / 内部 HTTP 投递。这类取值声明了投递却没声明可靠
//     机制，按跨边界处理，缺口如实暴露；要豁免必须先在契约里把它改成自留语义，而不是靠
//     readiness 放水。
var crossBoundaryDeliverySemantics = map[string]struct{}{
	"transactional_outbox":    {},
	"transactional_event_log": {},
	"durable_stream":          {},
	"synchronous_call":        {},
}

// ClassifyEventDelivery 按投递保证分类 `delivery_semantics` 取值。
// 只做大小写与首尾空白归一，不做别名归一：留兜底就是留第二真相源。
func ClassifyEventDelivery(deliverySemantics string) EventDeliveryClass {
	value := strings.ToLower(strings.TrimSpace(deliverySemantics))
	if _, ok := selfRetainedDeliverySemantics[value]; ok {
		return EventDeliverySelfRetained
	}
	if _, ok := crossBoundaryDeliverySemantics[value]; ok {
		return EventDeliveryCrossBoundary
	}
	return EventDeliveryUnrecognized
}

// RequiresNamedConsumer 表示该取值是否要求事件必须声明至少一个具名消费者。
//
// 只有 `transactional_outbox` 要求。发件箱与 relay 的**全部**存在理由就是把事件交给别人：
// 没有收件人的 relay 是没接完的线，不是设计。反方向由
// `transactional_event_log` 承担：DESIGN.md 第 9.2 节把「事务性事件表」与「有具名消费者」
// 钉成互斥且无例外，所以 `ForbidsNamedConsumer` 与本函数合起来正是那条互斥在事件侧的执行。
func RequiresNamedConsumer(deliverySemantics string) bool {
	return strings.ToLower(strings.TrimSpace(deliverySemantics)) == "transactional_outbox"
}

// ForbidsNamedConsumer 表示该取值是否与「有具名消费者」互斥。
// 有消费者却标成 `transactional_event_log`，等于把「投递断了」洗成「本来就不用投递」。
func ForbidsNamedConsumer(deliverySemantics string) bool {
	return strings.ToLower(strings.TrimSpace(deliverySemantics)) == "transactional_event_log"
}
