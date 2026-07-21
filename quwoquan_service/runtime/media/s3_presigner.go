package runtimemedia

import (
	"context"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
)

// PresignClient abstracts presigned URL generation and object existence checks,
// enabling swap between S3/OSS/MinIO/R2 without changing business logic.
type PresignClient interface {
	PresignPutObject(ctx context.Context, bucket, key string, constraints PutObjectConstraints, ttl time.Duration) (string, error)
	StatObject(ctx context.Context, bucket, key string) (*ObjectInfo, error)
	PromoteObject(ctx context.Context, bucket, sourceKey, targetKey string, metadata map[string]string) error
	CopyObject(ctx context.Context, bucket, sourceKey, targetKey string) error
	DeleteObject(ctx context.Context, bucket, key string) error
}

type PutObjectConstraints struct {
	ContentType string
	SHA256      string
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
		endpoint := strings.TrimRight(strings.TrimSpace(cfg.Endpoint), "/")
		if !strings.Contains(endpoint, "://") {
			endpoint = "https://" + endpoint
		}
		opts.BaseEndpoint = aws.String(endpoint)
		opts.UsePathStyle = true
	}

	client := s3.New(opts)
	return &S3PresignClient{
		client:    client,
		presigner: s3.NewPresignClient(client),
	}
}

func (c *S3PresignClient) PresignPutObject(ctx context.Context, bucket, key string, constraints PutObjectConstraints, ttl time.Duration) (string, error) {
	input := &s3.PutObjectInput{
		Bucket:      aws.String(bucket),
		Key:         aws.String(key),
		ContentType: aws.String(constraints.ContentType),
	}
	if digest := strings.TrimPrefix(strings.ToLower(strings.TrimSpace(constraints.SHA256)), "sha256:"); digest != "" {
		raw, err := hex.DecodeString(digest)
		if err != nil || len(raw) != 32 {
			return "", fmt.Errorf("s3 presign put: invalid SHA-256 constraint")
		}
		encoded := base64.StdEncoding.EncodeToString(raw)
		input.ChecksumSHA256 = aws.String(encoded)
		input.Metadata = map[string]string{"sha256": "sha256:" + digest}
	}
	result, err := c.presigner.PresignPutObject(ctx, input, s3.WithPresignExpires(ttl))
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
		var apiErr smithy.APIError
		if errors.As(err, &apiErr) {
			switch apiErr.ErrorCode() {
			case "NotFound", "NoSuchKey", "NoSuchObject":
				return &ObjectInfo{Exists: false}, nil
			}
		}
		return nil, fmt.Errorf("s3 stat object: %w", err)
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
	if sourceKey != targetKey {
		if _, err := c.client.DeleteObject(ctx, &s3.DeleteObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(sourceKey),
		}); err != nil {
			return fmt.Errorf("s3 delete promoted source object: %w", err)
		}
	}
	return nil
}

// CopyObject materializes a public delivery slice without deleting the
// private CAS source. Metadata and content type are preserved by S3's default
// copy behavior, which is essential for a video Range/MIME response.
func (c *S3PresignClient) CopyObject(
	ctx context.Context,
	bucket string,
	sourceKey string,
	targetKey string,
) error {
	_, err := c.client.CopyObject(ctx, &s3.CopyObjectInput{
		Bucket:     aws.String(bucket),
		Key:        aws.String(targetKey),
		CopySource: aws.String(bucket + "/" + sourceKey),
	})
	if err != nil {
		return fmt.Errorf("s3 copy public slice: %w", err)
	}
	return nil
}

// DeleteObject 按 key 删除对象。S3 删除语义幂等：临时上传对象已不存在时仍视为清理成功。
func (c *S3PresignClient) DeleteObject(
	ctx context.Context,
	bucket string,
	key string,
) error {
	if _, err := c.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	}); err != nil {
		return fmt.Errorf("s3 delete object: %w", err)
	}
	return nil
}

// GetObject streams a stored object. The media-processing worker downloads
// the private CAS source through this server-side read path instead of a
// presigned URL, so worker traffic never depends on URL TTL semantics.
func (c *S3PresignClient) GetObject(
	ctx context.Context,
	bucket string,
	key string,
) (io.ReadCloser, error) {
	output, err := c.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("s3 get object: %w", err)
	}
	return output.Body, nil
}

// PutObject writes a derived delivery artifact (transcoded video, cover,
// preview sprite/manifest). Only server-side processing writes through this
// path; client uploads keep using presigned PUT grants.
func (c *S3PresignClient) PutObject(
	ctx context.Context,
	bucket string,
	key string,
	contentType string,
	body io.Reader,
) error {
	_, err := c.client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(bucket),
		Key:         aws.String(key),
		ContentType: aws.String(contentType),
		Body:        body,
	})
	if err != nil {
		return fmt.Errorf("s3 put object: %w", err)
	}
	return nil
}
