package com.quwoquan.quwoquan_app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.util.DisplayMetrics;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.Locale;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Verifies that the compiled sw393dp launch drawable matches the Flutter-authored final frame. */
@RunWith(AndroidJUnit4.class)
public final class StartupLaunchResourceInstrumentedTest {
  private static final int LOGICAL_WIDTH = 393;
  private static final int LOGICAL_HEIGHT = 852;
  private static final int TEST_DENSITY = 3;

  @Test
  public void sw393LaunchBackgroundMatchesFlutterFinalFrame() {
    Context targetContext = InstrumentationRegistry.getInstrumentation().getTargetContext();
    Configuration configuration =
        new Configuration(targetContext.getResources().getConfiguration());
    configuration.densityDpi = DisplayMetrics.DENSITY_XXHIGH;
    configuration.smallestScreenWidthDp = LOGICAL_WIDTH;
    configuration.screenWidthDp = LOGICAL_WIDTH;
    configuration.screenHeightDp = LOGICAL_HEIGHT;
    configuration.orientation = Configuration.ORIENTATION_PORTRAIT;
    configuration.uiMode =
        (configuration.uiMode & ~Configuration.UI_MODE_NIGHT_MASK)
            | Configuration.UI_MODE_NIGHT_NO;
    Context configuredContext = targetContext.createConfigurationContext(configuration);

    Drawable launchBackground = configuredContext.getDrawable(R.drawable.launch_background);
    assertNotNull(launchBackground);

    int width = LOGICAL_WIDTH * TEST_DENSITY;
    int height = LOGICAL_HEIGHT * TEST_DENSITY;
    Bitmap actual = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
    launchBackground.setBounds(0, 0, width, height);
    launchBackground.draw(new Canvas(actual));

    Bitmap expected =
        BitmapFactory.decodeResource(
            configuredContext.getResources(), R.drawable.launch_welcome_final);
    assertNotNull(expected);
    assertEquals(width, expected.getWidth());
    assertEquals(height, expected.getHeight());

    PixelDifference difference = compare(expected, actual);
    assertTrue(
        String.format(
            Locale.US,
            "compiled launch drawable drifted from Flutter frame: mean=%.3f outlier=%.4f",
            difference.meanChannelDifference,
            difference.outlierRatio),
        difference.meanChannelDifference <= 8.0 && difference.outlierRatio <= 0.08);
  }

  private static PixelDifference compare(Bitmap expected, Bitmap actual) {
    long channelDifference = 0L;
    long sampledChannels = 0L;
    long outliers = 0L;
    long sampledPixels = 0L;
    for (int y = 0; y < expected.getHeight(); y += 2) {
      for (int x = 0; x < expected.getWidth(); x += 2) {
        int expectedPixel = expected.getPixel(x, y);
        int actualPixel = actual.getPixel(x, y);
        int red = Math.abs(Color.red(expectedPixel) - Color.red(actualPixel));
        int green = Math.abs(Color.green(expectedPixel) - Color.green(actualPixel));
        int blue = Math.abs(Color.blue(expectedPixel) - Color.blue(actualPixel));
        channelDifference += red + green + blue;
        sampledChannels += 3L;
        sampledPixels += 1L;
        if (Math.max(red, Math.max(green, blue)) > 24) {
          outliers += 1L;
        }
      }
    }
    return new PixelDifference(
        channelDifference / (double) sampledChannels, outliers / (double) sampledPixels);
  }

  private static final class PixelDifference {
    final double meanChannelDifference;
    final double outlierRatio;

    PixelDifference(double meanChannelDifference, double outlierRatio) {
      this.meanChannelDifference = meanChannelDifference;
      this.outlierRatio = outlierRatio;
    }
  }
}
