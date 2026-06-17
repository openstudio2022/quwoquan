package application

// IntersectionMetricsRecorder 是交集统一体验的业务 SLI 观测口（漏斗/冷却/保鲜/清零）。
// 应用层只依赖该接口（DDD：domain<-application，禁止 import infrastructure），
// Prometheus 实现落在 infrastructure/intersectionmetrics，由 main.go 注入。
// HTTP 延迟 / 错误率 / 可用性 SLI 由 runtime/observability 的 http_server_* 中间件
// 按 route 自动产出，本接口只补「重复曝光率 / 冷却写入 / 保鲜过滤 / 展示完备性 / 清零」
// 等业务负向/正向信号，单一真相源对齐 configs/observability/intersection_slo.yaml。
type IntersectionMetricsRecorder interface {
	// ObserveFeedCandidate 记录一个进入 spotlight 候选窗的交集（已通过保鲜+完备性）。
	// class: fact|affinity；rankState: fresh|seen（seen 表示命中跨会话冷却记忆窗，
	// 仍展示但降权——重复曝光率 = seen/total）。
	ObserveFeedCandidate(channel, class, rankState string)
	// ObserveFeedFiltered 记录一个在进入候选窗前被过滤的交集。
	// reason: stale（过保鲜，触发重算）| display_incomplete（缺 primaryText/头像，空窗治理）。
	ObserveFeedFiltered(channel, reason string)
	// ObserveExposureReported 记录写入跨会话冷却记忆窗的对象数（冷却写入量）。
	ObserveExposureReported(count int)
	// ObserveInboxVisit 记录一次「我的交集」清零（推进已读水位）按维度计数。
	ObserveInboxVisit(dimension string)
	// ObserveInboxFiltered 记录我的交集 summary/list 中被保鲜过滤的交集（触发重算）。
	ObserveInboxFiltered(reason string)
}

// noopIntersectionMetrics 默认实现：未注入 recorder 时零开销，便于单测与无观测环境。
type noopIntersectionMetrics struct{}

func (noopIntersectionMetrics) ObserveFeedCandidate(string, string, string) {}
func (noopIntersectionMetrics) ObserveFeedFiltered(string, string)          {}
func (noopIntersectionMetrics) ObserveExposureReported(int)                 {}
func (noopIntersectionMetrics) ObserveInboxVisit(string)                    {}
func (noopIntersectionMetrics) ObserveInboxFiltered(string)                 {}
