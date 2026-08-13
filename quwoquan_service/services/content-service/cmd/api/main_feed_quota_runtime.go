package bootstrap

import (
	"fmt"
	"log"

	"quwoquan_service/runtime/boundedrecord"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

func (c feedRuntimeConfig) deliveryPageQuotaPolicy() boundedrecord.Policy {
	return boundedrecord.Policy{
		ShardCount:                 c.DeliveryPageQuotaShardCount,
		MaximumLiveRecordsPerShard: c.DeliveryPageMaximumLiveRecords,
		MaximumLiveBytesPerShard:   c.DeliveryPageMaximumLiveBytes,
		MaximumLiveRecordsPerOwner: deliverymodel.MaximumActivePerScope,
	}
}

func validateFeedQuotaPolicies(feed feedRuntimeConfig) error {
	delivery := feed.deliveryPageQuotaPolicy()
	if err := delivery.Validate(); err != nil {
		return fmt.Errorf("feed delivery page quota policy: %w", err)
	}
	return nil
}

func logFeedQuotaPolicies(feed feedRuntimeConfig) {
	delivery := feed.deliveryPageQuotaPolicy()
	log.Printf(
		"content-service feed quota family=feed_delivery_page shards=%d owner_max=%d shard_records=%d shard_bytes=%d global_records=%d global_bytes=%d",
		delivery.ShardCount,
		delivery.MaximumLiveRecordsPerOwner,
		delivery.MaximumLiveRecordsPerShard,
		delivery.MaximumLiveBytesPerShard,
		delivery.MaximumLiveRecords(),
		delivery.MaximumLiveBytes(),
	)
}
