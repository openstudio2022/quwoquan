package intersection

// IntersectionMetricsRecorder 是交集统一体验的业务 SLI 观测口（漏斗/冷却/保鲜/清零）。
// 应用层只依赖该接口（DDD：domain<-application，禁止 import infrastructure），
// Prometheus 实现落在 infrastructure/intersectionmetrics，由 main.go 注入。
// HTTP 延迟 / 错误率 / 可用性 SLI 由 runtime/observability 的 http_server_* 中间件
// 按 route 自动产出，本接口只补「重复曝光率 / 冷却写入 / 保鲜过滤 / 展示完备性 / 清零」
// 等业务负向/正向信号，单一真相源对齐 configs/observability/intersection_slo.yaml。
type IntersectionMetricsRecorder interface {
	// ObserveFeedCandidate 记录一个进入 spotlight 候选窗的交集（已通过冷却+保鲜+完备性）。
	// class: fact|affinity；rankState 由读模型下发（fresh 等），命中曝光冷却的交集
	// 不进入候选窗（见 ObserveFeedFiltered reason=seen）。
	ObserveFeedCandidate(channel, class, rankState string)
	// ObserveFeedFiltered 记录一个在进入候选窗前被过滤的交集。
	// reason: negative（负反馈冷却）| seen（曝光未转化，处于 rec:icool 冷却窗口）|
	// stale（过 expiresAt；Content 只过滤并计数，重物化由 Recommendation 读面在下一次读取时
	// 按过期 refresh 收据执行）| display_incomplete（缺 primaryText/头像，空窗治理）|
	// cold_start_supply | supply_probe_unavailable。
	ObserveFeedFiltered(channel, reason string)
	// ObserveExposureReported 记录写入跨会话冷却记忆窗的交集数（冷却写入量）。
	ObserveExposureReported(count int)
	// ObserveNegativeFeedbackReported 记录写入交集负反馈冷却集（rec:ineg）的 subject 数
	// （F 推荐差异化）。是「负反馈 → 降权/冷却生效」漏斗的写入量真相源，支撑
	// 「过冷却/保鲜不再重复推荐」验收（ObserveFeedFiltered reason=negative 为消费侧对偶）。
	ObserveNegativeFeedbackReported(count int)
	// ObserveInboxVisit 记录一次「我的交集」清零（推进已读水位）按维度计数。
	ObserveInboxVisit(dimension string)
	// ObserveInboxFiltered 记录我的交集 summary/list 中被保鲜过滤的交集（stale；重物化由
	// Recommendation 读面按过期 refresh 收据执行，Content 不在此触发）。
	ObserveInboxFiltered(reason string)
	// ObserveRedisDegraded 记录一次 Redis 不可用降级（写降级 / 读回落持久兜底）。
	// op: exposure_write | exposure_clear | negative_feedback_write | watermark_write |
	// watermark_read。是「Redis 可用性 / 降级率」
	// SLI 的真实度量源，支撑「Redis 故障不拖垮主请求、watermark 持久不丢」的可观测验收。
	ObserveRedisDegraded(op string)
}

// noopIntersectionMetrics 默认实现：未注入 recorder 时零开销，便于单测与无观测环境。
type noopIntersectionMetrics struct{}

func (noopIntersectionMetrics) ObserveFeedCandidate(string, string, string) {}
func (noopIntersectionMetrics) ObserveFeedFiltered(string, string)          {}
func (noopIntersectionMetrics) ObserveExposureReported(int)                 {}
func (noopIntersectionMetrics) ObserveNegativeFeedbackReported(int)         {}
func (noopIntersectionMetrics) ObserveInboxVisit(string)                    {}
func (noopIntersectionMetrics) ObserveInboxFiltered(string)                 {}
func (noopIntersectionMetrics) ObserveRedisDegraded(string)                 {}
