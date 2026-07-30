// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002
package api_integration

import (
	"context"
	"encoding/json"
	"io"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	runtimemedia "quwoquan_service/runtime/media"
	mediaprocinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
)

func TestHLSCMAFArtifactsPreserveMIMEAndFallbackContractInObjectStorage(t *testing.T) {
	for _, binary := range []string{"ffmpeg", "ffprobe"} {
		if _, err := exec.LookPath(binary); err != nil {
			t.Fatalf("HLS/CMAF api_integration requires %s on PATH: %v", binary, err)
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	const (
		accessKey = "hls-cmaf-e2e"
		secretKey = "hls-cmaf-e2e-secret"
		bucket    = "hls-cmaf"
		region    = "us-east-1"
	)
	container, err := testcontainers.GenericContainer(
		ctx,
		testcontainers.GenericContainerRequest{
			ContainerRequest: testcontainers.ContainerRequest{
				Image:        "minio/minio:RELEASE.2025-04-22T22-12-26Z",
				ExposedPorts: []string{"9000/tcp"},
				Env: map[string]string{
					"MINIO_ROOT_USER":     accessKey,
					"MINIO_ROOT_PASSWORD": secretKey,
				},
				Cmd: []string{"server", "/data", "--address", ":9000"},
				WaitingFor: wait.ForHTTP("/minio/health/ready").
					WithPort("9000/tcp").
					WithStartupTimeout(2 * time.Minute),
			},
			Started: true,
		},
	)
	if err != nil {
		t.Fatalf("start HLS/CMAF MinIO: %v", err)
	}
	t.Cleanup(func() { _ = container.Terminate(context.Background()) })
	endpoint, err := container.Endpoint(ctx, "")
	if err != nil {
		t.Fatalf("resolve HLS/CMAF MinIO endpoint: %v", err)
	}
	baseEndpoint := "http://" + endpoint
	client := s3.New(s3.Options{
		BaseEndpoint: aws.String(baseEndpoint),
		Region:       region,
		Credentials: credentials.NewStaticCredentialsProvider(
			accessKey,
			secretKey,
			"",
		),
		UsePathStyle: true,
	})
	if _, err := client.CreateBucket(ctx, &s3.CreateBucketInput{
		Bucket: aws.String(bucket),
	}); err != nil {
		t.Fatalf("create HLS/CMAF bucket: %v", err)
	}
	objects := runtimemedia.NewS3PresignClient(runtimemedia.ObjectStorageConfig{
		Endpoint:        baseEndpoint,
		Bucket:          bucket,
		Region:          region,
		AccessKeyID:     accessKey,
		AccessKeySecret: secretKey,
	})
	processor, err := mediaprocinfra.NewFFmpegMediaProcessor(
		objects,
		mediaprocinfra.Config{Bucket: bucket},
	)
	if err != nil {
		t.Fatalf("build HLS/CMAF processor: %v", err)
	}
	source := renderTestVideo(t, true)
	probe, err := processor.Probe(ctx, source)
	if err != nil {
		t.Fatalf("probe HLS/CMAF source: %v", err)
	}
	slices := mediaprocinfra.DeliverySliceKeys("asset-hls-object-store", 4)
	artifacts, err := processor.PackageHLSCMAF(
		ctx,
		source,
		t.TempDir(),
		"asset-hls-object-store",
		4,
		probe,
		slices,
		mediaprocinfra.ProcessorProfile,
	)
	if err != nil {
		t.Fatalf("package HLS/CMAF to MinIO: %v", err)
	}
	requireContentType := func(key string, want string) {
		t.Helper()
		head, headErr := client.HeadObject(ctx, &s3.HeadObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(key),
		})
		if headErr != nil {
			t.Fatalf("head HLS/CMAF object %q: %v", key, headErr)
		}
		if got := aws.ToString(head.ContentType); got != want {
			t.Fatalf("HLS/CMAF object %q content-type=%q, want %q", key, got, want)
		}
	}
	requireContentType(artifacts.DescriptorSliceKey, "application/json")
	requireContentType(
		artifacts.MasterManifestSliceKey,
		"application/vnd.apple.mpegurl",
	)
	body, err := objects.GetObject(ctx, bucket, artifacts.DescriptorSliceKey)
	if err != nil {
		t.Fatalf("download HLS/CMAF descriptor: %v", err)
	}
	defer body.Close()
	var descriptor struct {
		AssetID               string `json:"assetId"`
		AssetVersion          int64  `json:"assetVersion"`
		FallbackVideoSliceKey string `json:"fallbackVideoSliceKey"`
		Renditions            []struct {
			PlaylistSliceKey string `json:"playlistSliceKey"`
		} `json:"renditions"`
	}
	if err := json.NewDecoder(body).Decode(&descriptor); err != nil {
		t.Fatalf("decode HLS/CMAF descriptor: %v", err)
	}
	if descriptor.AssetID != "asset-hls-object-store" ||
		descriptor.AssetVersion != 4 ||
		descriptor.FallbackVideoSliceKey != slices.Video ||
		len(descriptor.Renditions) != artifacts.RenditionCount {
		t.Fatalf("HLS/CMAF object descriptor lost fallback identity: %+v", descriptor)
	}
	for _, rendition := range descriptor.Renditions {
		requireContentType(rendition.PlaylistSliceKey, "application/vnd.apple.mpegurl")
		playlistBody, getErr := objects.GetObject(ctx, bucket, rendition.PlaylistSliceKey)
		if getErr != nil {
			t.Fatalf("download HLS/CMAF playlist: %v", getErr)
		}
		playlist, readErr := io.ReadAll(playlistBody)
		playlistBody.Close()
		if readErr != nil {
			t.Fatalf("read HLS/CMAF playlist: %v", readErr)
		}
		prefix := rendition.PlaylistSliceKey[:strings.LastIndex(rendition.PlaylistSliceKey, "/")]
		for _, line := range strings.Split(string(playlist), "\n") {
			line = strings.TrimSpace(line)
			if strings.HasSuffix(line, ".m4s") {
				requireContentType(prefix+"/"+line, "video/iso.segment")
				break
			}
		}
	}
}
