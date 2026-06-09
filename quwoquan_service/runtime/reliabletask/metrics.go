package reliabletask

import (
	"context"
	"strings"

	"github.com/prometheus/client_golang/prometheus"
)

type MetricsCollector struct {
	store MetricsStore
	desc  *prometheus.Desc
}

func NewMetricsCollector(store MetricsStore) *MetricsCollector {
	return &MetricsCollector{
		store: store,
		desc: prometheus.NewDesc(
			"qwq_reliabletask_records",
			"Reliable task records by kind and status.",
			[]string{"kind", "status"},
			nil,
		),
	}
}

func (c *MetricsCollector) Describe(ch chan<- *prometheus.Desc) {
	ch <- c.desc
}

func (c *MetricsCollector) Collect(ch chan<- prometheus.Metric) {
	if c == nil || c.store == nil {
		return
	}
	snapshot, err := c.store.ReliableTaskMetrics(context.Background())
	if err != nil {
		return
	}
	for status, count := range snapshot.TasksByStatus {
		ch <- prometheus.MustNewConstMetric(c.desc, prometheus.GaugeValue, float64(count), "task", status)
	}
	for status, count := range snapshot.NotificationsByStatus {
		ch <- prometheus.MustNewConstMetric(c.desc, prometheus.GaugeValue, float64(count), "notification", status)
	}
	for key, count := range snapshot.ProviderAttempts {
		status := key
		if idx := strings.LastIndex(key, ":"); idx >= 0 {
			status = key[idx+1:]
		}
		ch <- prometheus.MustNewConstMetric(c.desc, prometheus.GaugeValue, float64(count), "provider_attempt", status)
	}
}
