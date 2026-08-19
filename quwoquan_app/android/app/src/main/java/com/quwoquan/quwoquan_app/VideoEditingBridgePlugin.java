package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.graphics.Bitmap;
import android.media.MediaMetadataRetriever;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import androidx.annotation.NonNull;
import androidx.media3.common.MediaItem;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.transformer.Composition;
import androidx.media3.transformer.EditedMediaItem;
import androidx.media3.transformer.ExportException;
import androidx.media3.transformer.ExportResult;
import androidx.media3.transformer.Transformer;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * `quwoquan/video_editing` 的 Android 实现（post-create-update OPEN-007 第一段）。
 *
 * <p>channel 契约与 iOS AVFoundation 桥完全一致：`extractVideoFrames` 返回
 * `[{path, timeMs}]`；`exportVideoEdit`（trim 走 media3 Transformer 的
 * ClippingConfiguration，mute 走 removeAudio）返回
 * `{videoPath, coverPath, durationMs}`；失败回结构化 PlatformException，
 * Dart 侧防腐层据此决定降级或结构化不可用，禁止伪成功。
 */
@UnstableApi
public final class VideoEditingBridgePlugin {

  private static final String INVALID_ARGUMENTS = "video_editing_invalid_arguments";
  private static final String EXPORT_FAILED = "video_editing_export_failed";
  private static final String FRAME_EXTRACTION_FAILED = "video_editing_frame_extraction_failed";

  private final Context applicationContext;
  private final ExecutorService executor = Executors.newSingleThreadExecutor();
  private final Handler mainHandler = new Handler(Looper.getMainLooper());

  public VideoEditingBridgePlugin(Context applicationContext) {
    this.applicationContext = applicationContext;
  }

  public void handle(@NonNull MethodCall call, @NonNull MethodChannel.Result result) {
    switch (call.method) {
      case "extractVideoFrames":
        extractVideoFrames(call, result);
        break;
      case "exportVideoEdit":
        exportVideoEdit(call, result);
        break;
      default:
        result.notImplemented();
        break;
    }
  }

  private void extractVideoFrames(MethodCall call, MethodChannel.Result result) {
    final String sourcePath = stringArgument(call, "sourcePath");
    final long startMs = longArgument(call, "startMs", 0L);
    final long endMs = longArgument(call, "endMs", 0L);
    final int frameCount = (int) longArgument(call, "frameCount", 12L);
    final int maxDimension = (int) longArgument(call, "maxDimension", 360L);
    if (sourcePath.isEmpty() || frameCount <= 0) {
      result.error(INVALID_ARGUMENTS, "sourcePath/frameCount 参数无效", null);
      return;
    }
    executor.execute(
        () -> {
          MediaMetadataRetriever retriever = new MediaMetadataRetriever();
          try {
            retriever.setDataSource(sourcePath);
            long durationMs = parseDurationMs(retriever);
            long safeStartMs = Math.max(0L, startMs);
            long safeEndMs = endMs > safeStartMs ? endMs : Math.max(safeStartMs + 1000L, durationMs);
            if (durationMs > 0) {
              safeEndMs = Math.min(safeEndMs, durationMs);
            }
            long span = Math.max(1L, safeEndMs - safeStartMs);
            List<Map<String, Object>> frames = new ArrayList<>(frameCount);
            for (int index = 0; index < frameCount; index++) {
              long timeMs =
                  frameCount == 1
                      ? safeStartMs
                      : safeStartMs + span * index / (frameCount - 1);
              Bitmap frame =
                  retriever.getFrameAtTime(
                      timeMs * 1000L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
              if (frame == null) {
                continue;
              }
              File file = writeJpeg(scaleToMaxDimension(frame, maxDimension), "video_frame");
              Map<String, Object> entry = new HashMap<>();
              entry.put("path", file.getAbsolutePath());
              entry.put("timeMs", timeMs);
              frames.add(entry);
            }
            postSuccess(result, frames);
          } catch (Exception error) {
            postError(result, FRAME_EXTRACTION_FAILED, error.getMessage());
          } finally {
            releaseQuietly(retriever);
          }
        });
  }

  private void exportVideoEdit(MethodCall call, MethodChannel.Result result) {
    final String sourcePath = stringArgument(call, "sourcePath");
    final long trimStartMs = longArgument(call, "trimStartMs", 0L);
    final long trimEndMs = longArgument(call, "trimEndMs", 0L);
    final boolean muted = Boolean.TRUE.equals(call.argument("muted"));
    final long coverTimeMs = longArgument(call, "coverTimeMs", 0L);
    if (sourcePath.isEmpty() || !new File(sourcePath).exists()) {
      result.error(INVALID_ARGUMENTS, "sourcePath 不存在", null);
      return;
    }
    final File outputFile;
    try {
      outputFile = File.createTempFile("edited_video_", ".mp4", cacheDirectory());
    } catch (Exception error) {
      result.error(EXPORT_FAILED, "无法创建导出文件: " + error.getMessage(), null);
      return;
    }

    MediaItem.Builder mediaItemBuilder =
        new MediaItem.Builder().setUri(Uri.fromFile(new File(sourcePath)));
    boolean hasTrim = trimStartMs > 0 || trimEndMs > 0;
    if (hasTrim) {
      MediaItem.ClippingConfiguration.Builder clipping =
          new MediaItem.ClippingConfiguration.Builder()
              .setStartPositionMs(Math.max(0L, trimStartMs));
      if (trimEndMs > trimStartMs) {
        clipping.setEndPositionMs(trimEndMs);
      }
      mediaItemBuilder.setClippingConfiguration(clipping.build());
    }
    EditedMediaItem editedItem =
        new EditedMediaItem.Builder(mediaItemBuilder.build()).setRemoveAudio(muted).build();

    // Transformer 必须在主 looper 上启动；完成回调再切回 Flutter 主线程回包。
    mainHandler.post(
        () -> {
          Transformer transformer =
              new Transformer.Builder(applicationContext)
                  .addListener(
                      new Transformer.Listener() {
                        @Override
                        public void onCompleted(
                            @NonNull Composition composition, @NonNull ExportResult exportResult) {
                          executor.execute(
                              () -> {
                                try {
                                  String coverPath = generateCover(sourcePath, coverTimeMs);
                                  Map<String, Object> payload = new HashMap<>();
                                  payload.put("videoPath", outputFile.getAbsolutePath());
                                  payload.put("coverPath", coverPath);
                                  payload.put("durationMs", exportResult.approximateDurationMs);
                                  postSuccess(result, payload);
                                } catch (Exception error) {
                                  postError(result, EXPORT_FAILED, error.getMessage());
                                }
                              });
                        }

                        @Override
                        public void onError(
                            @NonNull Composition composition,
                            @NonNull ExportResult exportResult,
                            @NonNull ExportException exportException) {
                          postError(result, EXPORT_FAILED, exportException.getMessage());
                        }
                      })
                  .build();
          transformer.start(editedItem, outputFile.getAbsolutePath());
        });
  }

  private String generateCover(String sourcePath, long coverTimeMs) throws Exception {
    MediaMetadataRetriever retriever = new MediaMetadataRetriever();
    try {
      retriever.setDataSource(sourcePath);
      Bitmap frame =
          retriever.getFrameAtTime(
              Math.max(0L, coverTimeMs) * 1000L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
      if (frame == null) {
        return "";
      }
      return writeJpeg(scaleToMaxDimension(frame, 1080), "video_cover").getAbsolutePath();
    } finally {
      releaseQuietly(retriever);
    }
  }

  private File writeJpeg(Bitmap bitmap, String prefix) throws Exception {
    File file = File.createTempFile(prefix + "_", ".jpg", cacheDirectory());
    try (FileOutputStream stream = new FileOutputStream(file)) {
      bitmap.compress(Bitmap.CompressFormat.JPEG, 90, stream);
    }
    return file;
  }

  private static Bitmap scaleToMaxDimension(Bitmap bitmap, int maxDimension) {
    int largest = Math.max(bitmap.getWidth(), bitmap.getHeight());
    if (maxDimension <= 0 || largest <= maxDimension) {
      return bitmap;
    }
    float scale = (float) maxDimension / largest;
    return Bitmap.createScaledBitmap(
        bitmap,
        Math.max(1, Math.round(bitmap.getWidth() * scale)),
        Math.max(1, Math.round(bitmap.getHeight() * scale)),
        true);
  }

  private File cacheDirectory() {
    File directory = new File(applicationContext.getCacheDir(), "video_editing");
    if (!directory.exists() && !directory.mkdirs()) {
      return applicationContext.getCacheDir();
    }
    return directory;
  }

  private static long parseDurationMs(MediaMetadataRetriever retriever) {
    String raw = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
    if (raw == null) {
      return 0L;
    }
    try {
      return Long.parseLong(raw.trim());
    } catch (NumberFormatException ignored) {
      return 0L;
    }
  }

  private static void releaseQuietly(MediaMetadataRetriever retriever) {
    try {
      retriever.release();
    } catch (Exception ignored) {
      // release 失败不影响结果。
    }
  }

  private void postSuccess(MethodChannel.Result result, Object payload) {
    mainHandler.post(() -> result.success(payload));
  }

  private void postError(MethodChannel.Result result, String code, String message) {
    mainHandler.post(() -> result.error(code, message == null ? code : message, null));
  }

  private static String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value == null ? "" : value.toString().trim();
  }

  private static long longArgument(MethodCall call, String key, long fallback) {
    Object value = call.argument(key);
    if (value instanceof Number) {
      return ((Number) value).longValue();
    }
    return fallback;
  }
}
