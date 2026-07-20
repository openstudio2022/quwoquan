package observability

import "github.com/prometheus/client_golang/prometheus"

var closeOutboxDeliveries = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "user_account_close_outbox_delivery_total",
		Help: "UserAccountClosed outbox delivery outcomes.",
	},
	[]string{"result"},
)

func init() {
	prometheus.MustRegister(closeOutboxDeliveries)
}

type CloseOutboxObserver struct{}

func (CloseOutboxObserver) RecordDelivery(result string) {
	closeOutboxDeliveries.WithLabelValues(result).Inc()
}
