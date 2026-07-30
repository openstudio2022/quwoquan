package main

import (
	"fmt"
	"log"

	"quwoquan_service/runtime/boundedrecord"
	rtrec "quwoquan_service/runtime/recommendation"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

func (c feedRuntimeConfig) rankedWindowQuotaPolicy() boundedrecord.Policy {
	return boundedrecord.Policy{
		ShardCount:                 c.RankedWindowQuotaShardCount,
		MaximumLiveRecordsPerShard: c.RankedWindowMaximumLiveRecords,
		MaximumLiveBytesPerShard:   c.RankedWindowMaximumLiveBytes,
		MaximumLiveRecordsPerOwner: rtrec.RankedFeedWindowMaxActivePerSubject,
	}
}

func (c feedRuntimeConfig) deliveryPageQuotaPolicy() boundedrecord.Policy {
	return boundedrecord.Policy{
		ShardCount:                 c.DeliveryPageQuotaShardCount,
		MaximumLiveRecordsPerShard: c.DeliveryPageMaximumLiveRecords,
		MaximumLiveBytesPerShard:   c.DeliveryPageMaximumLiveBytes,
		MaximumLiveRecordsPerOwner: deliverymodel.MaximumActivePerScope,
	}
}

func validateFeedQuotaPolicies(feed feedRuntimeConfig) error {
	ranked := feed.rankedWindowQuotaPolicy()
	if err := ranked.Validate(); err != nil {
		return fmt.Errorf("ranked feed window quota policy: %w", err)
	}
	delivery := feed.deliveryPageQuotaPolicy()
	if err := delivery.Validate(); err != nil {
		return fmt.Errorf("feed delivery page quota policy: %w", err)
	}
	return nil
}

func logFeedQuotaPolicies(feed feedRuntimeConfig) {
	ranked := feed.rankedWindowQuotaPolicy()
	delivery := feed.deliveryPageQuotaPolicy()
	log.Printf(
		"content-service feed quota family=ranked_feed_window shards=%d owner_max=%d shard_records=%d shard_bytes=%d global_records=%d global_bytes=%d",
		ranked.ShardCount,
		ranked.MaximumLiveRecordsPerOwner,
		ranked.MaximumLiveRecordsPerShard,
		ranked.MaximumLiveBytesPerShard,
		ranked.MaximumLiveRecords(),
		ranked.MaximumLiveBytes(),
	)
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
