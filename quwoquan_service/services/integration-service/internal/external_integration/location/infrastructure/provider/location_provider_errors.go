package provider

import (
	"context"
	"errors"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/integration-service/generated/external_integration/location"
)

var (
	ErrProviderRateLimited     = errors.New("location provider rate limited")
	ErrProviderInvalidResponse = errors.New("location provider invalid response")
	ErrProviderPartialResponse = errors.New("location provider partial response")
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
	if errors.Is(err, ErrProviderRateLimited) {
		return generated.AppErrorFromLocationProviderRateLimited(
			"location provider request was rate limited",
		)
	}
	if errors.Is(err, ErrProviderInvalidResponse) ||
		errors.Is(err, ErrProviderPartialResponse) {
		return generated.AppErrorFromLocationProviderInvalidResponse(
			"location provider response was invalid",
		)
	}
	return generated.AppErrorFromLocationProviderUnavailable(
		"location provider request failed",
	)
}
