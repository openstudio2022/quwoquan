package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.os.SystemClock;
import android.util.Log;
import android.view.View;

public final class NativeWelcomeView extends View {
  private static final String STARTUP_TAG = "QWQStartup";
  private static final long SEQUENCE_DURATION_MS = 1500L;
  private static final long PETAL_DURATION_MS = 700L;
  private static final long PETAL_STAGGER_MS = 70L;
  private static final float INITIAL_PETAL_PROGRESS = 0.24f;
  private static final int PETAL_COUNT = 8;
  private static final int[] PETAL_COLORS = {
    Color.rgb(251, 146, 60),
    Color.rgb(253, 224, 71),
    Color.rgb(163, 230, 53),
    Color.rgb(52, 211, 153),
    Color.rgb(34, 211, 238),
    Color.rgb(56, 189, 248),
    Color.rgb(167, 139, 250),
    Color.rgb(251, 113, 133)
  };

  private final long sequenceStartedMs;
  private final String firstDrawEventName;
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
  private final RectF petalRect = new RectF();
  private boolean firstDrawLogged = false;

  public NativeWelcomeView(Context context, long sequenceStartedMs) {
    this(context, sequenceStartedMs, "android_native_welcome_first_draw");
  }

  public NativeWelcomeView(
      Context context, long sequenceStartedMs, String firstDrawEventName) {
    super(context);
    this.sequenceStartedMs =
        sequenceStartedMs > 0L ? sequenceStartedMs : SystemClock.uptimeMillis();
    this.firstDrawEventName = firstDrawEventName;
    setWillNotDraw(false);
  }

  @Override
  protected void onDraw(Canvas canvas) {
    super.onDraw(canvas);
    final int width = getWidth();
    final int height = getHeight();
    if (width <= 0 || height <= 0) {
      return;
    }

    final long elapsedMs = Math.max(0L, SystemClock.uptimeMillis() - sequenceStartedMs);
    if (!firstDrawLogged) {
      firstDrawLogged = true;
      Log.i(STARTUP_TAG, firstDrawEventName + " elapsedMs=" + elapsedMs);
    }
    final long cycleElapsedMs = elapsedMs % SEQUENCE_DURATION_MS;
    final boolean replayHintVisible = elapsedMs >= SEQUENCE_DURATION_MS;
    drawBackground(canvas, width, height);
    drawBrand(canvas, width, height, cycleElapsedMs);
    if (replayHintVisible) {
      drawStartupHint(canvas, width, height);
    } else {
      drawAssistantWhisper(canvas, width, height);
    }
    postInvalidateOnAnimation();
  }

  private void drawBackground(Canvas canvas, int width, int height) {
    paint.reset();
    paint.setAntiAlias(true);
    paint.setShader(
        new LinearGradient(
            0,
            0,
            0,
            height,
            new int[] {Color.rgb(20, 145, 255), Color.rgb(10, 132, 255), Color.rgb(21, 84, 209)},
            new float[] {0f, 0.48f, 1f},
            Shader.TileMode.CLAMP));
    canvas.drawRect(0, 0, width, height, paint);

    paint.setShader(
        new RadialGradient(
            -width * 0.08f,
            -height * 0.12f,
            width * 0.72f,
            new int[] {Color.argb(36, 255, 255, 255), Color.TRANSPARENT},
            new float[] {0f, 1f},
            Shader.TileMode.CLAMP));
    canvas.drawCircle(-width * 0.08f, -height * 0.12f, width * 0.72f, paint);
    paint.setShader(null);
  }

  private void drawBrand(Canvas canvas, int width, int height, long cycleElapsedMs) {
    final float scale = Math.min(width / 393f, height / 852f);
    final float graphicDiameter = 256f * scale;
    final float centerX = width / 2f;
    final float centerY = height * 0.37f;

    drawFlower(canvas, centerX, centerY, scale, cycleElapsedMs);
    final float titleBaseline = centerY + graphicDiameter / 2f + 86f * scale;
    drawGradientText(
        canvas,
        "趣我圈",
        centerX,
        titleBaseline,
        48f * scale,
        true,
        new int[] {Color.rgb(192, 132, 252), Color.rgb(103, 232, 249), Color.WHITE});
    drawText(
        canvas,
        "遇见同趣，绽放热爱",
        centerX,
        titleBaseline + 72f * scale,
        18f * scale,
        Color.argb(230, 239, 248, 255),
        false,
        1.0f);
  }

  private void drawFlower(Canvas canvas, float centerX, float centerY, float scale, long cycleElapsedMs) {
    paint.reset();
    paint.setAntiAlias(true);
    paint.setShader(
        new RadialGradient(
            centerX,
            centerY,
            62f * scale,
            new int[] {Color.argb(48, 255, 255, 255), Color.argb(28, 103, 232, 249), Color.TRANSPARENT},
            new float[] {0f, 0.44f, 1f},
            Shader.TileMode.CLAMP));
    canvas.drawCircle(centerX, centerY, 62f * scale, paint);
    paint.setShader(null);

    final float petalBaseWidth = 52f * scale;
    final float petalBaseHeight = 94f * scale;
    final float radialOffset = 54f * scale;
    for (int i = 0; i < PETAL_COUNT; i++) {
      final float progress = petalProgress(cycleElapsedMs, i);
      final int color = PETAL_COLORS[i];
      final int alpha = Math.round(255f * 0.86f * progress);
      final float petalWidth = petalBaseWidth * progress;
      final float petalHeight = petalBaseHeight * progress;
      final float petalCenterY = centerY - radialOffset * progress;
      petalRect.set(
          centerX - petalWidth / 2f,
          petalCenterY - petalHeight / 2f,
          centerX + petalWidth / 2f,
          petalCenterY + petalHeight / 2f);

      canvas.save();
      canvas.rotate(i * 45f, centerX, centerY);
      paint.reset();
      paint.setAntiAlias(true);
      paint.setColor(withAlpha(color, alpha));
      canvas.drawRoundRect(petalRect, petalWidth / 2f, petalWidth / 2f, paint);
      paint.setColor(Color.argb(Math.round(alpha * 0.20f), 255, 255, 255));
      canvas.drawOval(
          centerX - petalWidth * 0.30f,
          petalCenterY - petalHeight * 0.42f,
          centerX + petalWidth * 0.30f,
          petalCenterY - petalHeight * 0.10f,
          paint);
      canvas.restore();
    }
  }

  private float petalProgress(long cycleElapsedMs, int index) {
    final float raw = clamp01((cycleElapsedMs - index * PETAL_STAGGER_MS) / (float) PETAL_DURATION_MS);
    final float eased = 1f - (float) Math.pow(1f - raw, 3f);
    return INITIAL_PETAL_PROGRESS + (1f - INITIAL_PETAL_PROGRESS) * eased;
  }

  private void drawStartupHint(Canvas canvas, int width, int height) {
    drawText(
        canvas,
        "启动中，马上进入",
        width / 2f,
        height - 40f * getResources().getDisplayMetrics().density,
        12f * getResources().getDisplayMetrics().scaledDensity,
        Color.argb(210, 239, 248, 255),
        false,
        1.0f);
  }

  private void drawAssistantWhisper(Canvas canvas, int width, int height) {
    drawText(
        canvas,
        "✦ 小趣  专注你的热爱，剩下的交给我",
        width / 2f,
        height - 40f * getResources().getDisplayMetrics().density,
        10f * getResources().getDisplayMetrics().scaledDensity,
        Color.argb(190, 239, 248, 255),
        false,
        1.0f);
  }

  private void drawGradientText(
      Canvas canvas,
      String text,
      float centerX,
      float baseline,
      float textSize,
      boolean bold,
      int[] colors) {
    paint.reset();
    paint.setAntiAlias(true);
    paint.setTextAlign(Paint.Align.CENTER);
    paint.setTextSize(textSize);
    paint.setFakeBoldText(bold);
    final float halfWidth = paint.measureText(text) / 2f;
    paint.setShader(
        new LinearGradient(
            centerX - halfWidth,
            baseline,
            centerX + halfWidth,
            baseline,
            colors,
            new float[] {0f, 0.48f, 1f},
            Shader.TileMode.CLAMP));
    canvas.drawText(text, centerX, baseline, paint);
    paint.setShader(null);
  }

  private void drawText(
      Canvas canvas,
      String text,
      float centerX,
      float baseline,
      float textSize,
      int color,
      boolean bold,
      float letterSpacing) {
    paint.reset();
    paint.setAntiAlias(true);
    paint.setTextAlign(Paint.Align.CENTER);
    paint.setTextSize(textSize);
    paint.setColor(color);
    paint.setFakeBoldText(bold);
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
      paint.setLetterSpacing(letterSpacing / Math.max(textSize, 1f));
    }
    canvas.drawText(text, centerX, baseline, paint);
  }

  private static int withAlpha(int color, int alpha) {
    return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
  }

  private static float clamp01(float value) {
    if (value < 0f) {
      return 0f;
    }
    if (value > 1f) {
      return 1f;
    }
    return value;
  }
}
