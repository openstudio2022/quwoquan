package integration

import (
	"context"
	"errors"
	"strings"

	openapi "github.com/alibabacloud-go/darabonba-openapi/v2/client"
	dypns "github.com/alibabacloud-go/dypnsapi-20170525/v3/client"
	util "github.com/alibabacloud-go/tea-utils/v2/service"

	"quwoquan_service/services/user-service/internal/application"
)

const aliyunDypnsEndpoint = "dypnsapi.aliyuncs.com"

type aliyunGetMobileClient interface {
	GetMobileWithOptions(
		request *dypns.GetMobileRequest,
		runtime *util.RuntimeOptions,
	) (*dypns.GetMobileResponse, error)
}

// AliyunOneTapPhoneResolver 使用阿里云号码认证 GetMobile 将客户端一次性 token
// 换成手机号。AccessKey 只存在于 user-service 运行时，客户端永远不可见。
type AliyunOneTapPhoneResolver struct {
	client aliyunGetMobileClient
}

func NewAliyunOneTapPhoneResolver(
	accessKeyID string,
	accessKeySecret string,
	endpoint string,
) (*AliyunOneTapPhoneResolver, error) {
	accessKeyID = strings.TrimSpace(accessKeyID)
	accessKeySecret = strings.TrimSpace(accessKeySecret)
	if accessKeyID == "" || accessKeySecret == "" {
		return nil, errors.New("aliyun one tap resolver unavailable: credentials not configured")
	}
	endpoint = strings.TrimSpace(endpoint)
	if endpoint == "" {
		endpoint = aliyunDypnsEndpoint
	}
	client, err := dypns.NewClient(
		&openapi.Config{
			AccessKeyId:     &accessKeyID,
			AccessKeySecret: &accessKeySecret,
			Endpoint:        &endpoint,
		},
	)
	if err != nil {
		return nil, errors.New("aliyun one tap resolver unavailable: client initialization failed")
	}
	return &AliyunOneTapPhoneResolver{client: client}, nil
}

func newAliyunOneTapPhoneResolverWithClient(
	client aliyunGetMobileClient,
) *AliyunOneTapPhoneResolver {
	return &AliyunOneTapPhoneResolver{client: client}
}

func (r *AliyunOneTapPhoneResolver) ResolvePhone(
	ctx context.Context,
	_ string,
	carrierToken string,
) (string, string, error) {
	if err := ctx.Err(); err != nil {
		return "", "", err
	}
	carrierToken = strings.TrimSpace(carrierToken)
	if carrierToken == "" {
		return "", "", errors.New("carrier token invalid")
	}
	if r == nil || r.client == nil {
		return "", "", errors.New("aliyun one tap resolver unavailable")
	}
	runtime := (&util.RuntimeOptions{}).
		SetAutoretry(false).
		SetMaxAttempts(1).
		SetConnectTimeout(1500).
		SetReadTimeout(2500)
	response, err := r.client.GetMobileWithOptions(
		(&dypns.GetMobileRequest{}).SetAccessToken(carrierToken),
		runtime,
	)
	if err != nil {
		return "", "", sanitizedAliyunResolverError(err)
	}
	if response == nil || response.Body == nil {
		return "", "", errors.New("aliyun one tap response invalid")
	}
	code := strings.TrimSpace(stringValue(response.Body.Code))
	if code != "OK" {
		if code == "" {
			return "", "", errors.New("aliyun one tap response invalid")
		}
		return "", "", errors.New("carrier token invalid")
	}
	dto := response.Body.GetMobileResultDTO
	if dto == nil {
		return "", "", errors.New("aliyun one tap response invalid")
	}
	phone := normalizeAliyunPhone(stringValue(dto.Mobile))
	if phone == "" {
		return "", "", errors.New("aliyun one tap response invalid")
	}
	return phone, maskAliyunPhone(phone), nil
}

func sanitizedAliyunResolverError(err error) error {
	switch {
	case errors.Is(err, context.Canceled):
		return context.Canceled
	case errors.Is(err, context.DeadlineExceeded):
		return context.DeadlineExceeded
	}
	text := strings.ToLower(err.Error())
	if strings.Contains(text, "timeout") || strings.Contains(text, "deadline") {
		return context.DeadlineExceeded
	}
	return errors.New("aliyun one tap provider unavailable")
}

func normalizeAliyunPhone(value string) string {
	value = strings.TrimSpace(value)
	value = strings.TrimPrefix(value, "+86")
	value = strings.TrimPrefix(value, "86")
	if len(value) != 11 || !strings.HasPrefix(value, "1") {
		return ""
	}
	for _, char := range value {
		if char < '0' || char > '9' {
			return ""
		}
	}
	return value
}

func maskAliyunPhone(phone string) string {
	if len(phone) != 11 {
		return ""
	}
	return phone[:3] + "****" + phone[7:]
}

func stringValue(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

var _ application.OneTapPhoneResolver = (*AliyunOneTapPhoneResolver)(nil)
