package observability

import "github.com/prometheus/client_golang/prometheus"

var closeOutboxDeliveries = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "user_account_close_outbox_delivery_total",
		Help: "UserAccount lifecycle outbox delivery outcomes.",
	},
	[]string{"result"},
)

var userAccountOutboxRelayReady = prometheus.NewGauge(
	prometheus.GaugeOpts{
		Name: "user_account_outbox_relay_ready",
		Help: "Whether the UserAccount lifecycle outbox relay is ready (1=ready, 0=unready).",
	},
)

var userAccountOutboxTerminalFailures = prometheus.NewGauge(
	prometheus.GaugeOpts{
		Name: "user_account_outbox_terminal_failures",
		Help: "Number of UserAccount lifecycle outbox events awaiting terminal failure replay.",
	},
)

var userProfileSearchOutboxDeliveries = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "user_profile_search_outbox_delivery_total",
		Help: "UserProfile search projection outbox delivery outcomes.",
	},
	[]string{"result"},
)

var userProfileSearchOutboxReady = prometheus.NewGauge(
	prometheus.GaugeOpts{
		Name: "user_profile_search_outbox_ready",
		Help: "Whether the UserProfile search projection outbox relay is ready (1=ready, 0=unready).",
	},
)

var userProfileSearchOutboxPending = prometheus.NewGauge(
	prometheus.GaugeOpts{
		Name: "user_profile_search_outbox_pending",
		Help: "Number of UserProfile search projection events awaiting Elasticsearch/OpenSearch acknowledgement.",
	},
)

func init() {
	prometheus.MustRegister(
		closeOutboxDeliveries,
		userAccountOutboxRelayReady,
		userAccountOutboxTerminalFailures,
		userProfileSearchOutboxDeliveries,
		userProfileSearchOutboxReady,
		userProfileSearchOutboxPending,
	)
}

type CloseOutboxObserver struct{}

func (CloseOutboxObserver) RecordDelivery(result string) {
	closeOutboxDeliveries.WithLabelValues(result).Inc()
}

func (CloseOutboxObserver) RecordReadiness(
	ready bool,
	terminalFailures int,
) {
	if ready {
		userAccountOutboxRelayReady.Set(1)
	} else {
		userAccountOutboxRelayReady.Set(0)
	}
	userAccountOutboxTerminalFailures.Set(float64(terminalFailures))
}

type ProfileSearchOutboxObserver struct{}

func (ProfileSearchOutboxObserver) RecordDelivery(result string) {
	userProfileSearchOutboxDeliveries.WithLabelValues(result).Inc()
}

func (ProfileSearchOutboxObserver) RecordReadiness(ready bool, pending int) {
	if ready {
		userProfileSearchOutboxReady.Set(1)
	} else {
		userProfileSearchOutboxReady.Set(0)
	}
	userProfileSearchOutboxPending.Set(float64(pending))
}
