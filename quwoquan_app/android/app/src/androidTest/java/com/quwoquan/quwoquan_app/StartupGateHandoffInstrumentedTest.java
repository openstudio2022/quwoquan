package com.quwoquan.quwoquan_app;

import static androidx.test.espresso.Espresso.onView;
import static androidx.test.espresso.assertion.ViewAssertions.matches;
import static androidx.test.espresso.matcher.ViewMatchers.isDisplayed;
import static androidx.test.espresso.matcher.ViewMatchers.withText;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.view.KeyEvent;
import androidx.test.core.app.ActivityScenario;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry;
import androidx.test.runner.lifecycle.Stage;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.android.FlutterFragmentActivity;
import java.lang.reflect.Method;
import java.util.Collection;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

/**
 * Native Gate/Main handoff instrumentation.
 *
 * <p>These tests intentionally avoid Patrol's Flutter Dart runner so recovery
 * can be asserted without creating a second product welcome path.
 */
@RunWith(AndroidJUnit4.class)
public class StartupGateHandoffInstrumentedTest {
  private Context appContext;

  @Before
  public void setUp() {
    appContext = ApplicationProvider.getApplicationContext();
    finishProductActivities();
    StartupHealthStore.clearAllMarkersForInstrumentedTest(appContext);
    StartupProcessClock.initialize();
  }

  @After
  public void tearDown() {
    StartupHealthStore.clearAllMarkersForInstrumentedTest(appContext);
    finishProductActivities();
  }

  @Test
  public void launcherIntentHandsOffToMainWithoutGateFlutterEngine() throws Exception {
    appContext.startActivity(launcherIntent());
    waitUntil(
        () -> currentActivityOfType(MainActivity.class) != null,
        20_000L,
        "MainActivity was not started from the package launcher");
    Activity main = currentActivityOfType(MainActivity.class);
    assertNotNull(main);
    assertTrue(main instanceof MainActivity);
    assertNull(currentActivityOfType(StartupGateActivity.class));
  }

  @Test
  public void repeatedLauncherTapReusesMainAndBackDoesNotRevealDuplicate() throws Exception {
    appContext.startActivity(launcherIntent());
    waitUntil(
        () -> currentActivityOfType(MainActivity.class) != null,
        20_000L,
        "MainActivity was not started from the package launcher");
    MainActivity firstMain = (MainActivity) currentActivityOfType(MainActivity.class);
    assertNotNull(firstMain);
    FlutterEngine firstEngine = flutterEngineOf(firstMain);
    assertNotNull(firstEngine);

    appContext.startActivity(launcherIntent());
    waitUntil(
        () -> currentActivityOfType(MainActivity.class) == firstMain,
        5_000L,
        "Repeated launcher tap created or resumed the wrong MainActivity");
    MainActivity repeatedMain = (MainActivity) currentActivityOfType(MainActivity.class);
    assertSame(firstMain, repeatedMain);
    assertSame(firstEngine, flutterEngineOf(repeatedMain));
    assertNull(currentActivityOfType(StartupGateActivity.class));

    InstrumentationRegistry.getInstrumentation()
        .sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);
    InstrumentationRegistry.getInstrumentation().waitForIdleSync();
    assertConditionRemains(
        () -> {
          Activity afterBack = currentActivityOfType(MainActivity.class);
          return afterBack == null || afterBack == firstMain;
        },
        1_000L,
        "Back revealed a different MainActivity");
    assertConditionRemains(
        () -> activityCountOfType(MainActivity.class) <= 1,
        1_000L,
        "Back revealed a duplicate MainActivity");
    assertNull(currentActivityOfType(StartupGateActivity.class));
  }

  @Test
  public void confirmedFatalStaysOnNativeRecoveryWithoutFlutterEngine() throws Exception {
    StartupHealthStore.seedConfirmedStartupFatalForInstrumentedTest(appContext);
    assertTrue(StartupHealthStore.shouldRecoverConfirmedStartupFatal(appContext));

    try (ActivityScenario<StartupGateActivity> scenario =
        ActivityScenario.launch(StartupGateActivity.class)) {
      onView(withText("应用暂时无法启动")).check(matches(isDisplayed()));
      assertConditionRemains(
          () -> currentActivityOfType(MainActivity.class) == null,
          2_000L,
          "MainActivity must not start during native recovery");
      scenario.onActivity(
          gate -> assertFalse(gate.isFinishing()));
    }
  }

  @Test
  public void mainEarlyFailureIsVisibleToNextGate() {
    StartupHealthStore.clearAllMarkersForInstrumentedTest(appContext);
    StartupHealthStore.markCurrentArtifactStarting(appContext);
    StartupHealthStore.markCurrentArtifactFatal(appContext);
    assertTrue(StartupHealthStore.shouldRecoverConfirmedStartupFatal(appContext));

    Intent launch = new Intent(appContext, StartupGateActivity.class);
    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    try (ActivityScenario<StartupGateActivity> scenario =
        ActivityScenario.launch(launch)) {
      onView(withText("应用暂时无法启动")).check(matches(isDisplayed()));
      scenario.onActivity(gate -> assertFalse(gate.isFinishing()));
    }
  }

  private static Activity currentActivityOfType(Class<? extends Activity> type) {
    AtomicReference<Activity> current = new AtomicReference<>();
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              Collection<Activity> resumed =
                  ActivityLifecycleMonitorRegistry.getInstance()
                      .getActivitiesInStage(Stage.RESUMED);
              for (Activity activity : resumed) {
                if (type.isInstance(activity)) {
                  current.set(activity);
                  return;
                }
              }
              Collection<Activity> started =
                  ActivityLifecycleMonitorRegistry.getInstance()
                      .getActivitiesInStage(Stage.STARTED);
              for (Activity activity : started) {
                if (type.isInstance(activity)) {
                  current.set(activity);
                  return;
                }
              }
            });
    return current.get();
  }

  private static int activityCountOfType(Class<? extends Activity> type) {
    AtomicReference<Integer> count = new AtomicReference<>(0);
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              int found = 0;
              for (Stage stage : new Stage[] {Stage.RESUMED, Stage.STARTED, Stage.PAUSED}) {
                for (Activity activity :
                    ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(stage)) {
                  if (type.isInstance(activity)) {
                    found++;
                  }
                }
              }
              count.set(found);
            });
    return count.get();
  }

  private static FlutterEngine flutterEngineOf(MainActivity activity) {
    try {
      Method getter = FlutterFragmentActivity.class.getDeclaredMethod("getFlutterEngine");
      getter.setAccessible(true);
      return (FlutterEngine) getter.invoke(activity);
    } catch (ReflectiveOperationException error) {
      throw new AssertionError("Unable to inspect MainActivity FlutterEngine", error);
    }
  }

  private Intent launcherIntent() {
    Intent launch =
        appContext.getPackageManager().getLaunchIntentForPackage(appContext.getPackageName());
    assertNotNull("Package launcher intent must resolve", launch);
    ComponentName component = launch.getComponent();
    assertNotNull("Package launcher component must be explicit", component);
    assertEquals(StartupGateActivity.class.getName(), component.getClassName());
    assertEquals(Intent.ACTION_MAIN, launch.getAction());
    assertTrue(launch.hasCategory(Intent.CATEGORY_LAUNCHER));
    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    return launch;
  }

  private static void finishProductActivities() {
    InstrumentationRegistry.getInstrumentation()
        .runOnMainSync(
            () -> {
              for (Stage stage : new Stage[] {Stage.RESUMED, Stage.STARTED, Stage.PAUSED}) {
                Collection<Activity> activities =
                    ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(stage);
                for (Activity activity : activities) {
                  if (activity instanceof MainActivity
                      || activity instanceof StartupGateActivity) {
                    activity.finish();
                  }
                }
              }
            });
    InstrumentationRegistry.getInstrumentation().waitForIdleSync();
  }

  private static void waitUntil(Condition condition, long timeoutMs, String message)
      throws InterruptedException {
    long deadline = System.currentTimeMillis() + timeoutMs;
    while (System.currentTimeMillis() < deadline) {
      if (condition.met()) {
        return;
      }
      Thread.sleep(50L);
    }
    assertTrue(message, condition.met());
  }

  private static void assertConditionRemains(Condition condition, long durationMs, String message)
      throws InterruptedException {
    long deadline = System.currentTimeMillis() + durationMs;
    while (System.currentTimeMillis() < deadline) {
      assertTrue(message, condition.met());
      Thread.sleep(50L);
    }
    assertTrue(message, condition.met());
  }

  private interface Condition {
    boolean met();
  }
}
