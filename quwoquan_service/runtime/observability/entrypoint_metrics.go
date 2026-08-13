package runtimeobservability

import (
	"github.com/prometheus/client_golang/prometheus"
)

// entrypoint_metrics 承载对象契约 runtime_entrypoints[].telemetry.metric 的
// 统一注册：投影器（projector）、事实追加（internal_port）、订阅消费
// （subscription）、中间件（middleware）在其入口出口以契约声明的指标名
// 计数，标签集与契约 telemetry.attributes 同源。
// 指标名是契约真相源（verify_object_alert_coverage 消费面校验对齐），
// 禁止实现侧另起名字。

// NewEntrypointOutcomeCounter 注册单 outcome 标签的入口计数器；
// 重复注册（多个组合根共享同一进程）时复用既有 collector。
func NewEntrypointOutcomeCounter(contractMetric string) *prometheus.CounterVec {
	return newEntrypointCounter(contractMetric, []string{"outcome"})
}

// NewEntrypointCounter 注册契约声明的多属性入口计数器；
// labels 必须与契约 telemetry.attributes 一致（低基数）。
func NewEntrypointCounter(contractMetric string, labels []string) *prometheus.CounterVec {
	return newEntrypointCounter(contractMetric, labels)
}

func newEntrypointCounter(name string, labels []string) *prometheus.CounterVec {
	counter := prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: name,
		Help: "Contract runtime entrypoint outcome counter (source: operations.yaml runtime_entrypoints telemetry).",
	}, labels)
	if err := prometheus.Register(counter); err != nil {
		already := &prometheus.AlreadyRegisteredError{}
		if asErr, ok := err.(prometheus.AlreadyRegisteredError); ok {
			*already = asErr
			return already.ExistingCollector.(*prometheus.CounterVec)
		}
		panic(err)
	}
	return counter
}
