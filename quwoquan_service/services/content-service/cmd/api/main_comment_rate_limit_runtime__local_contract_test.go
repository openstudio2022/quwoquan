package main

import "testing"

func TestValidateCommentRateLimitConfigRequiresCommercialWindows(t *testing.T) {
	t.Parallel()

	cfg := config{}
	cfg.CommentRateLimit.BurstWindowSeconds = 30
	cfg.CommentRateLimit.BurstMax = 5
	cfg.CommentRateLimit.DailyWindowSeconds = 24 * 60 * 60
	cfg.CommentRateLimit.DailyMax = 200
	if err := validateCommentRateLimitConfig(cfg, "prod"); err != nil {
		t.Fatalf("有效评论频控配置被拒绝：%v", err)
	}

	cfg.CommentRateLimit.BurstMax = 0
	if err := validateCommentRateLimitConfig(cfg, "prod"); err == nil {
		t.Fatal("prod 接受了关闭 burst 频控的配置")
	}
}
