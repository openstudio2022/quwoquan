package runtimemedia

import (
	"context"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// PresignClient abstracts presigned URL generation and object existence checks,
// enabling swap between S3/OSS/MinIO/R2 without changing business logic.
type PresignClient interface {
	PresignPutObject(ctx context.Context, bucket, key, contentType string, ttl time.Duration) (string, error)
	HeadObject(ctx context.Context, bucket, key string) (bool, error)
}

// S3PresignClient implements PresignClient using AWS SDK v2 (S3-compatible).
type S3PresignClient struct {
	client    *s3.Client
	presigner *s3.PresignClient
}

// NewS3PresignClient creates a real S3/MinIO/R2 presign client.
func NewS3PresignClient(cfg OSSConfig) *S3PresignClient {
	opts := s3.Options{
		Region:      cfg.Region,
		Credentials: credentials.NewStaticCredentialsProvider(cfg.AccessKeyID, cfg.AccessKeySecret, ""),
	}
	if cfg.Endpoint != "" {
		opts.BaseEndpoint = aws.String(fmt.Sprintf("https://%s", cfg.Endpoint))
		opts.UsePathStyle = true
	}

	client := s3.New(opts)
	return &S3PresignClient{
		client:    client,
		presigner: s3.NewPresignClient(client),
	}
}

func (c *S3PresignClient) PresignPutObject(ctx context.Context, bucket, key, contentType string, ttl time.Duration) (string, error) {
	result, err := c.presigner.PresignPutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(bucket),
		Key:         aws.String(key),
		ContentType: aws.String(contentType),
	}, s3.WithPresignExpires(ttl))
	if err != nil {
		return "", fmt.Errorf("s3 presign put: %w", err)
	}
	return result.URL, nil
}

func (c *S3PresignClient) HeadObject(ctx context.Context, bucket, key string) (bool, error) {
	_, err := c.client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return false, nil
	}
	return true, nil
}

// StubPresignClient is the legacy URL-concatenation fallback for dev without S3.
type StubPresignClient struct{}

func (StubPresignClient) PresignPutObject(_ context.Context, bucket, key, contentType string, ttl time.Duration) (string, error) {
	expires := time.Now().Add(ttl).Unix()
	url := fmt.Sprintf("https://%s.s3.stub/%s?X-Amz-Expires=%d&X-Amz-ContentType=%s",
		bucket, key, expires, contentType)
	return url, nil
}

func (StubPresignClient) HeadObject(_ context.Context, _, _ string) (bool, error) {
	return true, nil
}
