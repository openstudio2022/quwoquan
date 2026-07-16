package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type AnonymousDeviceBindingStore interface {
	FindByDeviceFingerprintHash(ctx context.Context, deviceFingerprintHash string) (*model.AnonymousDeviceBinding, error)
	Create(ctx context.Context, binding *model.AnonymousDeviceBinding) error
	Touch(ctx context.Context, id, installIDHash, platform, appVersion string) error
}
