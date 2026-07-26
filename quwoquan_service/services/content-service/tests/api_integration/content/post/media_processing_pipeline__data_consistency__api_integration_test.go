// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-004
package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	runtimemedia "quwoquan_service/runtime/media"
	contentgenerated "quwoquan_service/services/content-service/generated/media/media_asset"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	mediainfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media"
	mediaprocinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	mediareprocess "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	mediareprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
	uploadsessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	uploadsessionstorage "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/objectstorage"
	uploadsessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"
)

// TestMediaProcessingWorkerNormalizesAssetsAndProjectsDeliveryDescriptors 验证 UGC
// 视频和图片链路的「complete → media outbox → worker 处理 →
// RecordMediaProcessingResult(ready) → 发布可绑定」全链在真实 MinIO、Mongo 和
// ffmpeg 上成立。这条链此前只能靠 fixture 或测试直接伪造 processing-result。
//
// 基础设施依赖：Docker（testcontainers，与本包其它测试一致）与 ffmpeg/ffprobe
// 二进制；两者任一缺失都视为环境装配失败而不是跳过。
func TestMediaProcessingWorkerNormalizesAssetsAndProjectsDeliveryDescriptors(t *testing.T) {
	for _, binary := range []string{"ffmpeg", "ffprobe"} {
		if _, err := exec.LookPath(binary); err != nil {
			t.Fatalf("media processing api_integration requires %s on PATH: %v", binary, err)
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	harness := newMediaProcessingHarness(t, ctx)

	t.Run("video_with_audio_track", func(t *testing.T) {
		sourcePath := renderTestVideo(t, true)
		assetID := harness.uploadVideo(t, ctx, sourcePath, "with-audio")
		harness.drainWorker(t, ctx)
		asset := harness.requireReadyAsset(t, ctx, assetID)
		harness.assertDeliveryArtifacts(t, ctx, asset)
		harness.assertBindingSlice(t, ctx, assetID)
	})

	t.Run("image_is_normalized_before_public_slice_materialization", func(t *testing.T) {
		sourcePath := renderTestImage(t)
		assetID := harness.uploadImage(t, ctx, sourcePath, "normalization")
		harness.drainWorker(t, ctx)
		asset := harness.requireReadyImage(t, ctx, assetID)
		harness.assertImageBindingUsesNormalizedSource(t, ctx, asset)
	})

	t.Run("image_descriptor_reprocess_activates_and_rolls_back_verified_revision", func(t *testing.T) {
		sourcePath := renderTestImage(t)
		assetID := harness.uploadImage(t, ctx, sourcePath, "reprocess")
		harness.drainWorker(t, ctx)
		before := harness.requireReadyImage(t, ctx, assetID)
		beforeDescriptor := before.ImageProcessingDescriptor()

		control := mediareprocess.NewService(harness.mediaStore, harness.mediaStore)
		run, _, err := control.Start(
			commandmeta.WithIdempotencyKey(ctx, "reprocess-start-"+assetID),
			mediareprocess.StartCommand{
				RunID:    "reprocess-" + assetID,
				AssetIDs: []string{assetID},
			},
			contentgenerated.ContentImageDerivativePolicyVersion,
		)
		if err != nil {
			t.Fatalf("start image reprocess run: %v", err)
		}
		worker := mediareprocess.NewWorker(
			harness.mediaStore,
			harness.mediaStore,
			harness.processor,
			harness.service,
			"media-processing-e2e-reprocess",
		)
		if handled, err := worker.Drain(ctx, 1); err != nil || handled != 1 {
			t.Fatalf("drain image reprocess=(handled=%d, err=%v)", handled, err)
		}
		activeRun, err := control.Get(ctx, run.RunID())
		if err != nil {
			t.Fatalf("read completed image reprocess run: %v", err)
		}
		if activeRun.Status() != mediareprocessmodel.StatusCompleted {
			t.Fatalf("reprocess run status=%s, want completed", activeRun.Status())
		}
		after := harness.requireReadyImage(t, ctx, assetID)
		if after.ActiveImageDescriptorRevision() != 2 ||
			after.ImageProcessingDescriptor().ImagePublicSliceKey == beforeDescriptor.ImagePublicSliceKey {
			t.Fatalf("reprocess did not activate a distinct descriptor revision: %+v", after.Snapshot())
		}
		harness.assertImageBindingUsesNormalizedSource(t, ctx, after)

		if _, _, err := control.StartRollback(
			commandmeta.WithIdempotencyKey(ctx, "reprocess-rollback-"+assetID),
			run.RunID(),
		); err != nil {
			t.Fatalf("start image reprocess rollback: %v", err)
		}
		if handled, err := worker.Drain(ctx, 1); err != nil || handled != 1 {
			t.Fatalf("drain image reprocess rollback=(handled=%d, err=%v)", handled, err)
		}
		rolledBack, err := control.Get(ctx, run.RunID())
		if err != nil {
			t.Fatalf("read rolled-back image reprocess run: %v", err)
		}
		if rolledBack.Status() != mediareprocessmodel.StatusRolledBack {
			t.Fatalf("rollback status=%s, want rolled_back", rolledBack.Status())
		}
		restored := harness.requireReadyImage(t, ctx, assetID)
		if restored.ActiveImageDescriptorRevision() != 1 ||
			restored.ImageProcessingDescriptor().ImagePublicSliceKey != beforeDescriptor.ImagePublicSliceKey {
			t.Fatalf("rollback did not restore old descriptor: %+v", restored.Snapshot())
		}
	})

	t.Run("video_without_audio_gets_silent_track", func(t *testing.T) {
		sourcePath := renderTestVideo(t, false)
		assetID := harness.uploadVideo(t, ctx, sourcePath, "no-audio")
		harness.drainWorker(t, ctx)
		asset := harness.requireReadyAsset(t, ctx, assetID)
		if asset.VideoProcessingDescriptor().VideoAudioCodec != "aac" {
			t.Fatalf("silent source must gain an AAC track, got %+v", asset.VideoProcessingDescriptor())
		}
		harness.assertDeliveryArtifacts(t, ctx, asset)
	})

	t.Run("non_media_bytes_are_rejected_not_stuck", func(t *testing.T) {
		junkPath := filepath.Join(t.TempDir(), "junk.mp4")
		if err := os.WriteFile(junkPath, bytes.Repeat([]byte{0x42}, 4096), 0o644); err != nil {
			t.Fatalf("write junk source: %v", err)
		}
		assetID := harness.uploadVideo(t, ctx, junkPath, "junk")
		harness.drainWorker(t, ctx)
		asset, found, err := harness.mediaStore.LoadMediaAsset(ctx, assetID)
		if err != nil || !found {
			t.Fatalf("load junk asset: found=%v err=%v", found, err)
		}
		if asset.ProcessingStatus() != mediamodel.ProcessingStatusRejected {
			t.Fatalf(
				"undecodable bytes must reject, not stay processing: %s",
				asset.ProcessingStatus(),
			)
		}
		if asset.ProcessingFailureReason() == "" {
			t.Fatal("rejected asset must carry a failure reason")
		}
	})
}

type mediaProcessingHarness struct {
	bucket     string
	s3Client   *s3.Client
	presigner  *runtimemedia.S3PresignClient
	gateway    *mediainfra.ObjectGateway
	mediaStore *persistence.MongoMediaStore
	service    *mediaapp.MediaService
	uploads    *uploadsessionapp.UseCases
	worker     *mediaprocessing.Worker
	processor  mediaprocessing.Processor
	sequence   int
}

func newMediaProcessingHarness(t *testing.T, ctx context.Context) *mediaProcessingHarness {
	t.Helper()
	const (
		accessKey = "media-processing-e2e"
		secretKey = "media-processing-e2e-secret"
		bucket    = "media-processing"
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
		t.Fatalf("start MinIO for media processing: %v", err)
	}
	t.Cleanup(func() { _ = container.Terminate(context.Background()) })
	endpoint, err := container.Endpoint(ctx, "")
	if err != nil {
		t.Fatalf("resolve MinIO endpoint: %v", err)
	}
	baseEndpoint := "http://" + endpoint
	s3Client := s3.New(s3.Options{
		BaseEndpoint: aws.String(baseEndpoint), Region: region,
		Credentials:  credentials.NewStaticCredentialsProvider(accessKey, secretKey, ""),
		UsePathStyle: true,
	})
	if _, err := s3Client.CreateBucket(ctx, &s3.CreateBucketInput{Bucket: aws.String(bucket)}); err != nil {
		t.Fatalf("create MinIO bucket: %v", err)
	}
	presigner := runtimemedia.NewS3PresignClient(runtimemedia.OSSConfig{
		Endpoint: baseEndpoint, Bucket: bucket, Region: region,
		AccessKeyID: accessKey, AccessKeySecret: secretKey,
	})
	gateway, err := mediainfra.NewObjectGateway(mediainfra.ObjectGatewayConfig{
		Bucket: bucket, CDNDomain: "cdn.media-processing.test",
		CDNSignKey: "media-processing-sign-key", DeliveryTTL: time.Hour,
	}, presigner)
	if err != nil {
		t.Fatalf("build media object gateway: %v", err)
	}

	// 独立数据库隔离本链路的 outbox/checkpoint，避免消费其它测试的媒体事实。
	database := requireMongoDB(t).Client().Database("media_processing_e2e")
	t.Cleanup(func() { _ = database.Drop(context.Background()) })
	mediaStore := persistence.NewMongoMediaStore(database)
	if err := mediaStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure media indexes: %v", err)
	}
	uploadStore := uploadsessionpersistence.NewMongoStore(
		database.Collection("media_upload_sessions"),
		mediaStore,
	)
	if err := uploadStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure media upload session indexes: %v", err)
	}
	uploadGateway, err := uploadsessionstorage.NewGateway(
		uploadsessionstorage.Config{
			Bucket: bucket,
		},
		presigner,
	)
	if err != nil {
		t.Fatalf("build media upload session gateway: %v", err)
	}
	uploads := uploadsessionapp.NewUseCases(uploadStore, uploadGateway)
	service := mediaapp.NewMediaService(mediaapp.BindDataPorts(mediaStore), gateway)
	processor, err := mediaprocinfra.NewFFmpegMediaProcessor(presigner, mediaprocinfra.Config{
		Bucket:     bucket,
		JobTimeout: 3 * time.Minute,
	})
	if err != nil {
		t.Fatalf("build ffmpeg processor: %v", err)
	}
	worker := mediaprocessing.NewWorker(
		mediaStore, mediaStore, mediaStore, processor, service, mediaStore,
	)
	return &mediaProcessingHarness{
		bucket:     bucket,
		s3Client:   s3Client,
		presigner:  presigner,
		gateway:    gateway,
		mediaStore: mediaStore,
		service:    service,
		uploads:    uploads,
		worker:     worker,
		processor:  processor,
	}
}

// renderTestVideo synthesizes a deterministic 2s 540x960 H.264 source via
// ffmpeg lavfi, optionally with a sine audio track.
func renderTestVideo(t *testing.T, withAudio bool) string {
	t.Helper()
	outputPath := filepath.Join(t.TempDir(), "source.mp4")
	args := []string{
		"-hide_banner", "-loglevel", "error", "-y",
		"-f", "lavfi", "-i", "testsrc2=duration=2:size=540x960:rate=30",
	}
	if withAudio {
		args = append(args, "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
			"-c:a", "aac", "-shortest")
	}
	args = append(args, "-c:v", "libx264", "-pix_fmt", "yuv420p", outputPath)
	command := exec.Command("ffmpeg", args...)
	var stderr bytes.Buffer
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		t.Fatalf("render test video: %v: %s", err, stderr.String())
	}
	return outputPath
}

func renderTestImage(t *testing.T) string {
	t.Helper()
	outputPath := filepath.Join(t.TempDir(), "source.png")
	command := exec.Command(
		"ffmpeg",
		"-hide_banner",
		"-loglevel",
		"error",
		"-y",
		"-f",
		"lavfi",
		"-i",
		"color=c=orange:s=640x480",
		"-frames:v",
		"1",
		outputPath,
	)
	var stderr bytes.Buffer
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		t.Fatalf("render test image: %v: %s", err, stderr.String())
	}
	return outputPath
}

func (h *mediaProcessingHarness) uploadVideo(
	t *testing.T,
	ctx context.Context,
	sourcePath string,
	label string,
) string {
	t.Helper()
	return h.uploadVisualMedia(t, ctx, sourcePath, label, "video", "video/mp4")
}

func (h *mediaProcessingHarness) uploadImage(
	t *testing.T,
	ctx context.Context,
	sourcePath string,
	label string,
) string {
	t.Helper()
	return h.uploadVisualMedia(t, ctx, sourcePath, label, "image", "image/png")
}

// uploadVisualMedia drives the real client contract: init grant, presigned
// streaming PUT, and complete with SHA-256 verification.
func (h *mediaProcessingHarness) uploadVisualMedia(
	t *testing.T,
	ctx context.Context,
	sourcePath string,
	label string,
	mediaType string,
	contentType string,
) string {
	t.Helper()
	h.sequence++
	payload, err := os.ReadFile(sourcePath)
	if err != nil {
		t.Fatalf("read %s source: %v", mediaType, err)
	}
	digest := sha256.Sum256(payload)
	digestHex := "sha256:" + hex.EncodeToString(digest[:])
	owner := "persona-media-processing"

	initContext := commandmeta.WithIdempotencyKey(
		ctx,
		"media-processing-init-"+label,
	)
	init, err := h.uploads.Init(initContext, uploadsessionapp.InitCommand{
		OwnerID: owner, MediaType: mediaType, ContentType: contentType,
		FileSize: int64(len(payload)), ExpectedSHA256: digestHex,
	})
	if err != nil {
		t.Fatalf("init %s upload: %v", label, err)
	}
	request, err := http.NewRequestWithContext(
		ctx, http.MethodPut, init.UploadURL, bytes.NewReader(payload),
	)
	if err != nil {
		t.Fatalf("build presigned PUT: %v", err)
	}
	request.Header.Set("Content-Type", contentType)
	request.Header.Set("X-Amz-Checksum-Sha256", base64.StdEncoding.EncodeToString(digest[:]))
	request.Header.Set("X-Amz-Meta-Sha256", digestHex)
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("PUT %s %s bytes: %v", label, mediaType, err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		body, _ := io.ReadAll(response.Body)
		t.Fatalf("presigned PUT status=%d body=%s", response.StatusCode, string(body))
	}
	completeContext := commandmeta.WithIdempotencyKey(
		ctx,
		"media-processing-complete-"+label,
	)
	completed, err := h.uploads.Complete(completeContext, uploadsessionapp.CompleteCommand{
		SessionID: init.SessionID, OwnerID: owner,
		AccessPolicy: string(mediamodel.AccessPolicyOwnerOnly),
	})
	if err != nil {
		t.Fatalf("complete %s upload: %v", label, err)
	}
	asset, found, err := h.mediaStore.LoadMediaAsset(ctx, completed.AssetID)
	if err != nil || !found {
		t.Fatalf("load %s asset: found=%v err=%v", label, found, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusProcessing {
		t.Fatalf(
			"uploaded %s must start processing, got %s",
			mediaType,
			asset.ProcessingStatus(),
		)
	}
	return completed.AssetID
}

func (h *mediaProcessingHarness) drainWorker(t *testing.T, ctx context.Context) {
	t.Helper()
	// 一次 Drain 消费 completed/created 两类事实；转码为分钟级预算内的真活。
	if _, err := h.worker.Drain(ctx, 50); err != nil {
		t.Fatalf("drain media processing worker: %v", err)
	}
}

func (h *mediaProcessingHarness) requireReadyAsset(
	t *testing.T,
	ctx context.Context,
	assetID string,
) *mediamodel.MediaAsset {
	t.Helper()
	asset, found, err := h.mediaStore.LoadMediaAsset(ctx, assetID)
	if err != nil || !found {
		t.Fatalf("load processed asset: found=%v err=%v", found, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
		t.Fatalf(
			"asset must be ready after worker drain, got %s (reason=%q)",
			asset.ProcessingStatus(),
			asset.ProcessingFailureReason(),
		)
	}
	descriptor := asset.VideoProcessingDescriptor()
	if descriptor.VideoCodec != "h264" || descriptor.VideoContainer != "mp4" ||
		descriptor.VideoAudioCodec != "aac" || !descriptor.VideoFastStart ||
		descriptor.VerifiedDurationMs <= 0 ||
		descriptor.PreviewTrackVersion != 1 ||
		descriptor.VideoPublicSliceKey == "" || descriptor.CoverPublicSliceKey == "" ||
		descriptor.PreviewTrackManifestSliceKey == "" {
		t.Fatalf("ready descriptor violates the delivery contract: %+v", descriptor)
	}
	return asset
}

func (h *mediaProcessingHarness) requireReadyImage(
	t *testing.T,
	ctx context.Context,
	assetID string,
) *mediamodel.MediaAsset {
	t.Helper()
	asset, found, err := h.mediaStore.LoadMediaAsset(ctx, assetID)
	if err != nil || !found {
		t.Fatalf("load processed image: found=%v err=%v", found, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
		t.Fatalf(
			"image must be ready after worker drain, got %s (reason=%q)",
			asset.ProcessingStatus(),
			asset.ProcessingFailureReason(),
		)
	}
	descriptor := asset.ImageProcessingDescriptor()
	if descriptor.ProcessorProfile == "" ||
		descriptor.ImageWidth <= 0 ||
		descriptor.ImageHeight <= 0 ||
		descriptor.ImageNormalizedObjectKey == "" ||
		descriptor.ImagePublicSliceKey == "" ||
		descriptor.ImageDominantColor == "" ||
		descriptor.ImageLQIP == "" ||
		descriptor.ImageContentProfile == "" ||
		descriptor.DerivativePolicyVersion <= 0 ||
		(descriptor.ImageDeliveryContentType != "image/jpeg" &&
			descriptor.ImageDeliveryContentType != "image/png") {
		t.Fatalf("ready image descriptor violates the delivery contract: %+v", descriptor)
	}
	return asset
}

func (h *mediaProcessingHarness) assertDeliveryArtifacts(
	t *testing.T,
	ctx context.Context,
	asset *mediamodel.MediaAsset,
) {
	t.Helper()
	descriptor := asset.VideoProcessingDescriptor()
	for _, key := range []string{
		descriptor.VideoPublicSliceKey,
		descriptor.CoverPublicSliceKey,
		descriptor.PreviewTrackManifestSliceKey,
	} {
		if !strings.HasPrefix(key, "media/video/s/") {
			t.Fatalf("delivery key %q is not a public video slice", key)
		}
		if _, err := h.s3Client.HeadObject(ctx, &s3.HeadObjectInput{
			Bucket: aws.String(h.bucket), Key: aws.String(key),
		}); err != nil {
			t.Fatalf("delivery artifact %q is missing: %v", key, err)
		}
	}
	manifestBody, err := h.presigner.GetObject(ctx, h.bucket, descriptor.PreviewTrackManifestSliceKey)
	if err != nil {
		t.Fatalf("download preview manifest: %v", err)
	}
	defer manifestBody.Close()
	var manifest struct {
		Schema       string `json:"schema"`
		AssetID      string `json:"assetId"`
		AssetVersion int64  `json:"assetVersion"`
		TrackVersion int    `json:"trackVersion"`
		AccessPolicy string `json:"accessPolicy"`
		Sprites      []struct {
			SpriteID       string `json:"spriteId"`
			PublicSliceKey string `json:"publicSliceKey"`
			SHA256         string `json:"sha256"`
		} `json:"sprites"`
		Frames []struct {
			TimeMs   int64  `json:"timeMs"`
			SpriteID string `json:"spriteId"`
		} `json:"frames"`
	}
	if err := json.NewDecoder(manifestBody).Decode(&manifest); err != nil {
		t.Fatalf("decode preview manifest: %v", err)
	}
	if manifest.Schema != "quwoquan.content.preview_track_manifest" ||
		manifest.AssetID != asset.ID() ||
		manifest.TrackVersion != 1 ||
		manifest.AccessPolicy != "public" ||
		len(manifest.Sprites) == 0 || len(manifest.Frames) == 0 {
		t.Fatalf("preview manifest violates the delivery contract: %+v", manifest)
	}
	for _, sprite := range manifest.Sprites {
		if _, err := h.s3Client.HeadObject(ctx, &s3.HeadObjectInput{
			Bucket: aws.String(h.bucket), Key: aws.String(sprite.PublicSliceKey),
		}); err != nil {
			t.Fatalf("preview sprite %q is missing: %v", sprite.PublicSliceKey, err)
		}
	}

	// 交付 mp4 必须真实可解且已归一（faststart + h264/aac），复检产物本体
	// 而不是只信 descriptor。
	deliveryBody, err := h.presigner.GetObject(ctx, h.bucket, descriptor.VideoPublicSliceKey)
	if err != nil {
		t.Fatalf("download delivery mp4: %v", err)
	}
	deliveryPath := filepath.Join(t.TempDir(), "delivery.mp4")
	deliveryFile, err := os.Create(deliveryPath)
	if err != nil {
		t.Fatalf("create delivery temp file: %v", err)
	}
	if _, err := io.Copy(deliveryFile, deliveryBody); err != nil {
		t.Fatalf("write delivery temp file: %v", err)
	}
	deliveryBody.Close()
	deliveryFile.Close()
	probeOutput, err := exec.Command(
		"ffprobe", "-v", "error", "-print_format", "json",
		"-show_streams", "-show_format", deliveryPath,
	).Output()
	if err != nil {
		t.Fatalf("ffprobe delivery mp4: %v", err)
	}
	var probed struct {
		Streams []struct {
			CodecType string `json:"codec_type"`
			CodecName string `json:"codec_name"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(probeOutput, &probed); err != nil {
		t.Fatalf("parse delivery probe: %v", err)
	}
	codecs := map[string]string{}
	for _, stream := range probed.Streams {
		codecs[stream.CodecType] = stream.CodecName
	}
	if codecs["video"] != "h264" || codecs["audio"] != "aac" {
		t.Fatalf("delivery mp4 is not normalized h264/aac: %v", codecs)
	}
}

func (h *mediaProcessingHarness) assertImageBindingUsesNormalizedSource(
	t *testing.T,
	ctx context.Context,
	asset *mediamodel.MediaAsset,
) {
	t.Helper()
	descriptor := asset.ImageProcessingDescriptor()
	if descriptor.ImageNormalizedObjectKey == asset.ObjectKey() {
		t.Fatalf(
			"image normalized source must not reuse private upload object: %q",
			descriptor.ImageNormalizedObjectKey,
		)
	}
	if _, err := h.s3Client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(h.bucket), Key: aws.String(descriptor.ImageNormalizedObjectKey),
	}); err != nil {
		t.Fatalf("normalized image artifact %q is missing: %v", descriptor.ImageNormalizedObjectKey, err)
	}
	if _, err := h.s3Client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(h.bucket), Key: aws.String(descriptor.ImagePublicSliceKey),
	}); err != nil {
		t.Fatalf(
			"processing must read back public image slice before descriptor activation %q: %v",
			descriptor.ImagePublicSliceKey,
			err,
		)
	}

	reader := mediainfra.NewPostBindingReader(h.mediaStore, h.gateway)
	bindings, err := reader.FindMediaAssetsForBinding(ctx, []string{asset.ID()})
	if err != nil {
		t.Fatalf("find image binding: %v", err)
	}
	binding, found := bindings[asset.ID()]
	if !found || !binding.Ready || binding.PublicSliceKey != descriptor.ImagePublicSliceKey {
		t.Fatalf("image binding did not expose canonical normalized slice: %+v", binding)
	}
}

// assertBindingSlice 证明 ready 资产能进入发布绑定读取（发布链的直接入口），
// 即 worker 产物与 post_media_binding 的投影契约互通。
func (h *mediaProcessingHarness) assertBindingSlice(
	t *testing.T,
	ctx context.Context,
	assetID string,
) {
	t.Helper()
	reader := mediainfra.NewPostBindingReader(h.mediaStore, h.gateway)
	slices, err := reader.FindMediaAssetsForBinding(ctx, []string{assetID})
	if err != nil {
		t.Fatalf("find binding slice: %v", err)
	}
	slice, found := slices[assetID]
	if !found {
		t.Fatalf("binding slice for %q is missing", assetID)
	}
	if !slice.Ready || slice.VideoPublicSliceKey == "" ||
		slice.CoverPublicSliceKey == "" || slice.PreviewTrackVersion != 1 ||
		slice.PreviewTrackManifestSliceKey == "" {
		t.Fatalf("binding slice violates publication contract: %+v", slice)
	}
	if slice.PublicSliceKey != slice.VideoPublicSliceKey {
		t.Fatalf(
			"video binding must deliver the normalized slice, got %q vs %q",
			slice.PublicSliceKey,
			slice.VideoPublicSliceKey,
		)
	}
}
