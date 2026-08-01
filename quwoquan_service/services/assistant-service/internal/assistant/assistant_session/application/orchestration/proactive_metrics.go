package orchestration

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var subscriptionDeliverySuppressedTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Namespace: "assistant",
		Subsystem: "subscription",
		Name:      "delivery_suppressed_total",
		Help:      "Proactive subscription deliveries suppressed before side effects.",
	},
	[]string{"reason"},
)

var subscriptionDeliveryAttemptTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Namespace: "assistant",
		Subsystem: "subscription",
		Name:      "delivery_attempt_total",
		Help:      "Proactive subscription external delivery attempts by outcome and attempt kind.",
	},
	[]string{"outcome", "attempt_kind"},
)

var subscriptionCronTickTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Namespace: "assistant",
		Subsystem: "subscription",
		Name:      "cron_tick_total",
		Help:      "Skill subscription scheduler ticks by outcome.",
	},
	[]string{"outcome"},
)

func recordSubscriptionDeliverySuppressed(reason string) {
	reason = strings.TrimSpace(reason)
	switch reason {
	case "inactive",
		"not_due",
		"cooldown",
		"lease_held",
		"consent_missing",
		"assistant_disabled",
		"quiet_hours",
		"daily_limit",
		"destination_membership":
	default:
		reason = "other"
	}
	subscriptionDeliverySuppressedTotal.WithLabelValues(reason).Inc()
}

func recordSubscriptionDeliveryAttempt(outcome string, retry bool) {
	if outcome != "delivered" && outcome != "failed" {
		outcome = "failed"
	}
	attemptKind := "initial"
	if retry {
		attemptKind = "retry"
	}
	subscriptionDeliveryAttemptTotal.WithLabelValues(
		outcome,
		attemptKind,
	).Inc()
}

func recordSubscriptionCronTick(err error) {
	outcome := "succeeded"
	if err != nil {
		outcome = "failed"
	}
	subscriptionCronTickTotal.WithLabelValues(outcome).Inc()
}
