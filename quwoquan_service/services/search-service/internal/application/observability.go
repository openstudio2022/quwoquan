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

// RelatedTermsCacheObserver 记录热词缓存命中情况。
type RelatedTermsCacheObserver interface {
	ObserveRelatedTermsCache(hit bool)
}
