// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-002

package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	runtimemedia "quwoquan_service/runtime/media"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	sessionstorage "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/objectstorage"
)

func TestMediaObjectGatewayUsesRealS3CompatibleObjectLifecycle(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	const (
		accessKey = "content-media-integration"
		secretKey = "content-media-integration-secret"
		bucket    = "content-media"
		region    = "us-east-1"
	)
	container, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:        "minio/minio:RELEASE.2025-04-22T22-12-26Z",
			ExposedPorts: []string{"9000/tcp"},
			Env: map[string]string{
				"MINIO_ROOT_USER": accessKey, "MINIO_ROOT_PASSWORD": secretKey,
			},
			Cmd:        []string{"server", "/data", "--address", ":9000"},
			WaitingFor: wait.ForHTTP("/minio/health/ready").WithPort("9000/tcp").WithStartupTimeout(2 * time.Minute),
		},
		Started: true,
	})
	if err != nil {
		t.Fatalf("start real MinIO dependency: %v", err)
	}
	t.Cleanup(func() { _ = container.Terminate(context.Background()) })
	endpoint, err := container.Endpoint(ctx, "")
	if err != nil {
		t.Fatalf("resolve MinIO endpoint: %v", err)
	}
	baseEndpoint := "http://" + endpoint
	client := s3.New(s3.Options{
		BaseEndpoint: aws.String(baseEndpoint), Region: region,
		Credentials:  credentials.NewStaticCredentialsProvider(accessKey, secretKey, ""),
		UsePathStyle: true,
	})
	if _, err := client.CreateBucket(ctx, &s3.CreateBucketInput{Bucket: aws.String(bucket)}); err != nil {
		t.Fatalf("create real MinIO bucket: %v", err)
	}

	payload := bytes.Repeat([]byte{0x5a}, 128)
	digest := sha256.Sum256(payload)
	digestHex := "sha256:" + hex.EncodeToString(digest[:])
	gateway, err := sessionstorage.NewGateway(sessionstorage.Config{
		Bucket: bucket,
	}, runtimemedia.NewS3PresignClient(runtimemedia.OSSConfig{
		Endpoint: baseEndpoint, Bucket: bucket, Region: region,
		AccessKeyID: accessKey, AccessKeySecret: secretKey,
	}))
	if err != nil {
		t.Fatalf("build media object gateway: %v", err)
	}
	grant, err := gateway.PrepareUpload(ctx, sessionapp.PrepareUploadParams{
		SessionID: "media-real-s3-1", OwnerID: "persona-real-s3", MediaType: "image",
		ContentType: "image/jpeg", FileSize: int64(len(payload)), ExpectedSHA256: digestHex,
		ExpiresAt: time.Now().UTC().Add(5 * time.Minute),
	})
	if err != nil {
		t.Fatalf("prepare real object upload: %v", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPut, grant.UploadURL, bytes.NewReader(payload))
	if err != nil {
		t.Fatalf("build presigned upload request: %v", err)
	}
	request.Header.Set("Content-Type", "image/jpeg")
	request.Header.Set("X-Amz-Checksum-Sha256", base64.StdEncoding.EncodeToString(digest[:]))
	request.Header.Set("X-Amz-Meta-Sha256", digestHex)
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("PUT bytes through real presigned URL: %v", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		body, _ := io.ReadAll(response.Body)
		t.Fatalf("real presigned PUT status=%d body=%s", response.StatusCode, string(body))
	}

	completed, err := gateway.CompleteUpload(ctx, sessionapp.CompleteUploadParams{
		ObjectKey: grant.ObjectKey, ExpectedSHA256: digestHex, MediaType: "image",
		ContentType: "image/jpeg", FileSize: int64(len(payload)),
	})
	if err != nil {
		t.Fatalf("verify and promote real uploaded object: %v", err)
	}
	if !strings.HasPrefix(completed.ObjectKey, "media/objects/sha256/") || completed.SHA256 != digestHex {
		t.Fatalf("unexpected content-addressed result: %+v", completed)
	}
	promoted, err := client.HeadObject(
		ctx,
		&s3.HeadObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(completed.ObjectKey),
		},
	)
	if err != nil {
		t.Fatalf("promoted content-addressed object is missing: %v", err)
	}
	if aws.ToString(promoted.ContentType) != "image/jpeg" {
		t.Fatalf(
			"promoted object content type=%q want image/jpeg",
			aws.ToString(promoted.ContentType),
		)
	}
	if _, err := client.HeadObject(ctx, &s3.HeadObjectInput{Bucket: aws.String(bucket), Key: aws.String(grant.ObjectKey)}); err == nil {
		t.Fatal("temporary upload object remains after promotion")
	} else {
		var responseError interface{ HTTPStatusCode() int }
		if errors.As(err, &responseError) && responseError.HTTPStatusCode() != http.StatusNotFound {
			t.Fatalf("unexpected source lookup failure after promotion: %v", err)
		}
	}
}
