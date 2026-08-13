package bootstrap

import (
	"fmt"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	circleinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/circle"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// buildGatheringParticipationReader 装配共同经历回流引用（post.gatheringRef）的
// Circle Participation 校验端口。production composition 缺失该上游即启动失败：
// 校验链路 fail-closed，不允许携带 gatheringRef 的发布在无校验状态下通过。
func buildGatheringParticipationReader(
	cfg config,
) (postports.GatheringParticipationReader, error) {
	if strings.TrimSpace(cfg.CircleService.URL) == "" {
		return nil, fmt.Errorf(
			"content-service requires circle-service gathering participation reader",
		)
	}
	tokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("circle gathering participation auth config invalid: %w", err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"content-service",
		[]string{"circle.gathering.participation_status.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("circle gathering participation credentials invalid: %w", err)
	}
	client, err := circleinfra.NewGatheringParticipationClient(
		cfg.CircleService.URL,
		credentials,
	)
	if err != nil {
		return nil, fmt.Errorf("circle gathering participation client invalid: %w", err)
	}
	return client, nil
}
