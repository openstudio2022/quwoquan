package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"

	rerrors "quwoquan_service/runtime/errors"
	accountorchestration "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

func TestLoginAnonymouslyRejectsOverlongDeviceMetadataBeforeStoreAccess(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name       string
		platform   string
		appVersion string
	}{
		{
			name:       "platform exceeds storage contract",
			platform:   strings.Repeat("p", 17),
			appVersion: "local-e2e",
		},
		{
			name:       "app version exceeds storage contract",
			platform:   "ios",
			appVersion: strings.Repeat("v", 33),
		},
	}

	service := accountorchestration.NewAuthService(nil, nil, nil, nil, nil)
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			_, err := service.LoginAnonymously(
				context.Background(),
				"install-id",
				"device-fingerprint",
				testCase.platform,
				testCase.appVersion,
			)
			if err == nil {
				t.Fatal("expected invalid argument error")
			}
			var appError *rerrors.AppError
			if !errors.As(err, &appError) {
				t.Fatalf("expected structured runtime error, got %T: %v", err, err)
			}
			if got, want := appError.Code.String(), "USER.USER.invalid_argument"; got != want {
				t.Fatalf("unexpected error code: got %s, want %s", got, want)
			}
			if got, want := appError.HTTPStatus, 400; got != want {
				t.Fatalf("unexpected HTTP status: got %d, want %d", got, want)
			}
		})
	}
}
