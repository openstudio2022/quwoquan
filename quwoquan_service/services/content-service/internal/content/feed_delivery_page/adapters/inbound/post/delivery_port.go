package post

import (
	"context"

	rtobs "quwoquan_service/runtime/observability"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

// 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
var deliveryPageAppendOutcomes = rtobs.NewEntrypointOutcomeCounter("content_feed_delivery_page_append")

// DeliveryPort is the only Post-facing entrypoint. It exposes immutable append
// and non-sliding load without leaking the Redis adapter into Post.
type DeliveryPort struct {
	store deliveryapp.Store
}

func NewDeliveryPort(store deliveryapp.Store) *DeliveryPort {
	if store == nil {
		panic("FeedDeliveryPage Post port requires object store")
	}
	return &DeliveryPort{store: store}
}

func (port *DeliveryPort) Append(
	ctx context.Context,
	page deliverymodel.Page,
) (deliverymodel.Page, error) {
	appended, err := port.store.Append(ctx, page)
	outcome := "ok"
	if err != nil {
		outcome = "error"
	}
	deliveryPageAppendOutcomes.WithLabelValues(outcome).Inc()
	return appended, err
}

func (port *DeliveryPort) Load(
	ctx context.Context,
	scopeHash string,
	deliveryPageID string,
) (deliverymodel.Page, error) {
	return port.store.Load(ctx, scopeHash, deliveryPageID)
}

var _ deliveryapp.Store = (*DeliveryPort)(nil)
