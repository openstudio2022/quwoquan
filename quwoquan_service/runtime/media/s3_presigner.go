package runtimemedia

import (
	"context"
	"encoding/base64"
	"encoding/hex"
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
	StatObject(ctx context.Context, bucket, key string) (*ObjectInfo, error)
	PromoteObject(ctx context.Context, bucket, sourceKey, targetKey string, metadata map[string]string) error
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

func (c *S3PresignClient) StatObject(ctx context.Context, bucket, key string) (*ObjectInfo, error) {
	resp, err := c.client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return &ObjectInfo{Exists: false}, nil
	}
	sha256Hex := ""
	if resp.ChecksumSHA256 != nil && *resp.ChecksumSHA256 != "" {
		if decoded, decodeErr := base64.StdEncoding.DecodeString(*resp.ChecksumSHA256); decodeErr == nil {
			sha256Hex = "sha256:" + hex.EncodeToString(decoded)
		}
	}
	if sha256Hex == "" && resp.Metadata != nil {
		if v, ok := resp.Metadata["sha256"]; ok && v != "" {
			sha256Hex = v
		}
	}
	return &ObjectInfo{
		Exists:      true,
		Sha256:      sha256Hex,
		ContentType: aws.ToString(resp.ContentType),
		Size:        aws.ToInt64(resp.ContentLength),
		Metadata:    resp.Metadata,
	}, nil
}

func (c *S3PresignClient) PromoteObject(ctx context.Context, bucket, sourceKey, targetKey string, metadata map[string]string) error {
	input := &s3.CopyObjectInput{
		Bucket:            aws.String(bucket),
		Key:               aws.String(targetKey),
		CopySource:        aws.String(bucket + "/" + sourceKey),
		MetadataDirective: "REPLACE",
	}
	if len(metadata) > 0 {
		input.Metadata = metadata
	}
	_, err := c.client.CopyObject(ctx, input)
	if err != nil {
		return fmt.Errorf("s3 copy object: %w", err)
	}
	return nil
}

// StubPresignClient is the URL-concatenation fallback for dev without S3.
type StubPresignClient struct{}

func (StubPresignClient) PresignPutObject(_ context.Context, bucket, key, contentType string, ttl time.Duration) (string, error) {
	expires := time.Now().Add(ttl).Unix()
	url := fmt.Sprintf("https://%s.s3.stub/%s?X-Amz-Expires=%d&X-Amz-ContentType=%s",
		bucket, key, expires, contentType)
	return url, nil
}

func (StubPresignClient) StatObject(_ context.Context, _, key string) (*ObjectInfo, error) {
	return &ObjectInfo{
		Exists: true,
		Sha256: "sha256:" + fmt.Sprintf("%064x", len(key)),
	}, nil
}

func (StubPresignClient) PromoteObject(_ context.Context, _, _, _ string, _ map[string]string) error {
	return nil
}
