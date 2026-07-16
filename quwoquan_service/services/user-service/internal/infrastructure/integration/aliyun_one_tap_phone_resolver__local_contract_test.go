package integration

import (
	"context"
	"errors"
	"strings"
	"testing"

	dypns "github.com/alibabacloud-go/dypnsapi-20170525/v3/client"
	util "github.com/alibabacloud-go/tea-utils/v2/service"
)

type aliyunGetMobileFunc func(
	request *dypns.GetMobileRequest,
	runtime *util.RuntimeOptions,
) (*dypns.GetMobileResponse, error)

func (f aliyunGetMobileFunc) GetMobileWithOptions(
	request *dypns.GetMobileRequest,
	runtime *util.RuntimeOptions,
) (*dypns.GetMobileResponse, error) {
	return f(request, runtime)
}

func TestAliyunOneTapPhoneResolverExchangesTokenWithoutExposingIt(t *testing.T) {
	const secretToken = "aliyun-client-login-token-secret"
	resolver := newAliyunOneTapPhoneResolverWithClient(
		aliyunGetMobileFunc(func(
			request *dypns.GetMobileRequest,
			runtime *util.RuntimeOptions,
		) (*dypns.GetMobileResponse, error) {
			if request == nil || stringValue(request.AccessToken) != secretToken {
				t.Fatal("resolver must forward the exact client token to GetMobile")
			}
			if runtime == nil || runtime.Autoretry == nil || *runtime.Autoretry {
				t.Fatal("login token exchange must not retry a single-use token")
			}
			return &dypns.GetMobileResponse{
				Body: &dypns.GetMobileResponseBody{
					Code: stringPointer("OK"),
					GetMobileResultDTO: &dypns.GetMobileResponseBodyGetMobileResultDTO{
						Mobile: stringPointer("18013813909"),
					},
				},
			}, nil
		}),
	)

	phone, display, err := resolver.ResolvePhone(
		context.Background(),
		"CMCC",
		secretToken,
	)
	if err != nil {
		t.Fatalf("ResolvePhone failed: %v", err)
	}
	if phone != "18013813909" || display != "180****3909" {
		t.Fatalf("unexpected phone result phone=%q display=%q", phone, display)
	}
}

func TestAliyunOneTapPhoneResolverSanitizesProviderErrors(t *testing.T) {
	const secretToken = "aliyun-client-login-token-secret"
	resolver := newAliyunOneTapPhoneResolverWithClient(
		aliyunGetMobileFunc(func(
			_ *dypns.GetMobileRequest,
			_ *util.RuntimeOptions,
		) (*dypns.GetMobileResponse, error) {
			return nil, errors.New("request failed with AccessToken=" + secretToken)
		}),
	)

	_, _, err := resolver.ResolvePhone(context.Background(), "CUCC", secretToken)
	if err == nil {
		t.Fatal("expected provider failure")
	}
	if strings.Contains(err.Error(), secretToken) || strings.Contains(err.Error(), "AccessToken") {
		t.Fatalf("provider error leaked token: %v", err)
	}
}

func TestAliyunOneTapPhoneResolverRejectsNonMainlandPhone(t *testing.T) {
	resolver := newAliyunOneTapPhoneResolverWithClient(
		aliyunGetMobileFunc(func(
			_ *dypns.GetMobileRequest,
			_ *util.RuntimeOptions,
		) (*dypns.GetMobileResponse, error) {
			return &dypns.GetMobileResponse{
				Body: &dypns.GetMobileResponseBody{
					Code: stringPointer("OK"),
					GetMobileResultDTO: &dypns.GetMobileResponseBodyGetMobileResultDTO{
						Mobile: stringPointer("not-a-phone"),
					},
				},
			}, nil
		}),
	)

	if _, _, err := resolver.ResolvePhone(context.Background(), "CTCC", "token"); err == nil {
		t.Fatal("invalid provider phone must fail closed")
	}
}

func stringPointer(value string) *string {
	return &value
}
