package provider

import (
	"context"
	"errors"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/integration-service/internal/generated"
)

// normalizeLocationProviderError 阻止供应商错误、HTTP 细节或 SDK 类型越过 adapter 边界。
func normalizeLocationProviderError(ctx context.Context, err error) error {
	if err == nil {
		return nil
	}
	var appError *rerrors.AppError
	if errors.As(err, &appError) {
		return err
	}
	if errors.Is(err, context.DeadlineExceeded) ||
		errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return generated.AppErrorFromUpstreamTimeout("location provider request timed out")
	}
	return generated.AppErrorFromLocationProviderUnavailable(
		"location provider request failed",
	)
}
