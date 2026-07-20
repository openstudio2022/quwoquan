package application

// SearchObservation 是一次检索结果的应用层观测 DTO。
type SearchObservation struct {
	Mode            string
	Bucket          string
	Seconds         float64
	ResultCount     int
	Degraded        bool
	Err             bool
	TermHeatApplied bool
}

// SearchRequestObserver 记录检索结果与反馈闭环指标。
type SearchRequestObserver interface {
	ObserveSearch(observation SearchObservation)
	ObserveFeedback(eventType string)
}

// SearchLoadObserver 记录入口背压与并发水位。
type SearchLoadObserver interface {
	ObserveLoadShed(reason string)
	SetInflight(inflight int)
}

// RecentSearchObservation 是 RecentSearchState 公开 operation 的有界观测 DTO。
// Operation/Status 都由 handler 的闭集常量产生，禁止把 query、persona 或 entry id
// 放进 metric label。
type RecentSearchObservation struct {
	Operation string
	Status    string
	Seconds   float64
}

// RecentSearchObserver 记录最近搜索读写路径的吞吐、错误率和延迟。
type RecentSearchObserver interface {
	ObserveRecentSearch(observation RecentSearchObservation)
}

// RelatedTermsCacheObserver 记录热词缓存命中情况。
type RelatedTermsCacheObserver interface {
	ObserveRelatedTermsCache(hit bool)
}
