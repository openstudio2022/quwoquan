package application

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// proactivePersonalizationTotal attributes proactive (cron) skill messages by
// whether the user's interest profile was applied, the lifecycle stage, and the
// skill. It is the production-evaluation signal for T4-4: it lets us track
// personalization coverage (personalized vs degraded) and the lifecycle mix
// (new / active / dormant) per skill without log scraping. Label cardinality is
// bounded (personalized: true|false; lifecycle: new|active|dormant|none; skill:
// the small P0 skill set).
var proactivePersonalizationTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Namespace: "assistant",
	Subsystem: "proactive",
	Name:      "personalization_total",
	Help:      "Proactive skill messages by interest-profile personalization outcome.",
}, []string{"personalized", "lifecycle", "skill"})

func recordProactivePersonalization(result P0ProactiveSkillResult) {
	personalized := "false"
	lifecycle := "none"
	if result.Personalized {
		personalized = "true"
		if result.LifecycleStage != "" {
			lifecycle = result.LifecycleStage
		}
	}
	skill := result.SkillID
	if skill == "" {
		skill = "unknown"
	}
	proactivePersonalizationTotal.WithLabelValues(personalized, lifecycle, skill).Inc()
}
