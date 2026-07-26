package recentsearch

// Observation 是 RecentSearchState 公开 operation 的有界观测 DTO。
// Operation/Status 都由 adapter 的闭集常量产生，禁止把 query、persona 或 entry id
// 放进 metric label。
type Observation struct {
	Operation string
	Status    string
	Seconds   float64
}

// Observer 记录最近搜索读写路径的吞吐、错误率和延迟。
type Observer interface {
	ObserveRecentSearch(observation Observation)
}
