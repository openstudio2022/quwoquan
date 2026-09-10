package com.quwoquan.testhost.patrol;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.graphics.Bitmap;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.util.Log;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;

import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONArray;
import org.junit.Test;
import org.junit.Assume;

import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.regex.Pattern;
import java.util.regex.Matcher;

/**
 * Black-box proof that the canonical launcher already started the production AUT and that its
 * accessibility tree reached the home surface.
 *
 * <p>This test never installs, force-stops, or cold-launches the AUT. It requires an existing main
 * process and requires that exact package to already own the foreground accessibility root, then
 * proves PID continuity. The Patrol host and this instrumentation driver remain physically
 * separate from the production AUT.
 */
public final class ProductionHomepageExternalAutTest {
    private static final String LOG_TAG = "QWQExternalAUT";
    private static final String MARKER = "QWQ_EXTERNAL_AUT ";
    private static final String SCHEMA = "environment-page-smoke.external-aut-homepage.v1";
    private static final String HOME_SURFACE_IDENTIFIER = "qwq.surface.home";
    private static final Pattern PACKAGE_NAME =
            Pattern.compile("^[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z0-9_]+)+$");

    @Test
    public void executesOfflinePageCaseInCanonicalProductionProcess() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Bundle arguments = InstrumentationRegistry.getArguments();
        // 既有首页 driver 按 class 选择；仅该旧调用跳过本方法，不产出离线 PASS。
        boolean explicitlySelected = arguments.getString("class", "").contains(
                "#executesOfflinePageCaseInCanonicalProductionProcess");
        Assume.assumeTrue(explicitlySelected || arguments.containsKey("qwqOfflinePagePlan"));
        assertTrue("离线专用方法必须收到当前计划", arguments.containsKey("qwqOfflinePagePlan"));
        String target = requiredPackage(arguments, "qwqTargetPackage");
        assertEquals(target, requiredPackage(arguments, "qwqExpectedPackage"));
        assertFalse(target.equals(instrumentation.getContext().getPackageName()));
        assertFalse(target.equals(instrumentation.getTargetContext().getPackageName()));
        JSONObject plan = new JSONObject(new String(Base64.decode(
                arguments.getString("qwqOfflinePagePlan", ""), Base64.NO_WRAP), StandardCharsets.UTF_8));
        assertEquals("quwoquan_ops.offline_page_case.v1", plan.getString("schema"));
        assertEquals(target, plan.getString("applicationId"));
        assertEquals("android", plan.getString("platform"));
        JSONArray steps = plan.getJSONArray("steps");
        assertTrue("页面用例必须包含有界实际步骤", steps.length() > 0 && steps.length() <= 40);
        // 在任何点击前校验整个计划，未知动作不能部分执行后才失败。
        for (int index = 0; index < steps.length(); index++) {
            JSONObject step = steps.getJSONObject(index);
            assertEquals(2, step.length());
            assertTrue(step.getString("operation").matches("visible|tap|scroll|seek|playback|back|reveal"));
            String selector = step.getString("selector");
            assertFalse(selector.trim().isEmpty());
            if (selector.startsWith("text-prefix:")) {
                assertTrue(step.getString("operation").matches("visible|seek|playback"));
                assertFalse(selector.substring("text-prefix:".length()).trim().isEmpty());
            }
        }
        UiAutomation automation = instrumentation.getUiAutomation();
        int before = requireSingleRunningPid(automation, target);
        assertEquals("必须使用 canonical 启动 PID", plan.getInt("canonicalProcessId"), before);
        JSONArray observations = new JSONArray();
        for (int index = 0; index < steps.length(); index++) {
            JSONObject step = steps.getJSONObject(index);
            String operation = step.getString("operation");
            assertEquals(before, requireSingleRunningPid(automation, target));
            String selector = step.getString("selector");
            if (operation.equals("back")) {
                assertTrue(automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK));
            }
            AccessibilityNodeInfo node = operation.equals("reveal")
                    ? revealSelectedNode(automation, target, selector)
                    : waitForSelectedNode(automation, target, selector, 15_000L);
            assertNotNull("实际页面缺少 " + selector, node);
            try {
                assertTrue(node.isVisibleToUser());
                String observed = observedNode(node);
                if (operation.equals("tap")) {
                    AccessibilityNodeInfo actionable = AccessibilityNodeInfo.obtain(node);
                    try {
                        while (!actionable.isClickable() && actionable.getParent() != null) {
                            AccessibilityNodeInfo parent = actionable.getParent();
                            actionable.recycle();
                            actionable = parent;
                        }
                        assertTrue("页面控件不可点击", actionable.performAction(AccessibilityNodeInfo.ACTION_CLICK));
                    } finally { actionable.recycle(); }
                } else if (operation.equals("scroll")) {
                    assertTrue("分页容器不可滚动", node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD));
                } else if (operation.equals("seek")) {
                    int oldPosition = playbackTimes(observed)[0];
                    assertTrue("进度节点必须支持调整", node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD));
                    SystemClock.sleep(500L);
                    AccessibilityNodeInfo after = waitForSelectedNode(automation, target, selector, 10_000L);
                    assertNotNull(after);
                    try {
                        String value = observedNode(after);
                        assertTrue("seek 必须改变实际播放位置", playbackTimes(value)[0] >= oldPosition + 2);
                        observed = value;
                    } finally { after.recycle(); }
                } else if (operation.equals("playback")) {
                    observed = observeCompletePlayback(automation, target, selector);
                } else {
                    assertTrue(operation.equals("visible") || operation.equals("reveal") || operation.equals("back"));
                }
                observations.put(new JSONObject().put("operation", operation).put("selector", selector).put("observed", observed));
            } finally { node.recycle(); }
            SystemClock.sleep(250L);
        }
        AccessibilityNodeInfo foreground = automation.getRootInActiveWindow();
        assertNotNull("截图前 AUT 必须仍在前台", foreground);
        try { assertEquals(target, String.valueOf(foreground.getPackageName())); }
        finally { foreground.recycle(); }
        Bitmap screenshot = automation.takeScreenshot();
        assertNotNull("原生终态截图不可缺失", screenshot);
        ByteArrayOutputStream screenshotBytes = new ByteArrayOutputStream();
        try { assertTrue(screenshot.compress(Bitmap.CompressFormat.PNG, 100, screenshotBytes)); }
        finally { screenshot.recycle(); }
        byte[] png = screenshotBytes.toByteArray();
        int after = requireSingleRunningPid(automation, target);
        assertEquals("页面验收不得替换 AUT 进程", before, after);
        AccessibilityNodeInfo afterScreenshot = automation.getRootInActiveWindow();
        assertNotNull("截图后 AUT 必须仍在前台", afterScreenshot);
        try { assertEquals(target, String.valueOf(afterScreenshot.getPackageName())); }
        finally { afterScreenshot.recycle(); }
        JSONObject evidence = new JSONObject().put("schema", "quwoquan_ops.offline_native_page_result.v1")
                .put("caseId", plan.getString("caseId")).put("planDigest", plan.getString("planDigest"))
                .put("platform", "android").put("applicationId", target).put("processIdBefore", before)
                .put("processIdAfter", after).put("status", "passed").put("observations", observations)
                .put("candidateDigest", plan.getString("candidateDigest"))
                .put("artifactDigest", plan.getString("artifactDigest"))
                .put("deviceId", plan.getString("deviceId"))
                .put("launchAttemptId", plan.getString("launchAttemptId"))
                .put("screenshotDigest", sha256(png)).put("screenshotByteLength", png.length);
        String encodedScreenshot = Base64.encodeToString(png, Base64.NO_WRAP);
        for (int offset = 0, index = 0; offset < encodedScreenshot.length(); offset += 3000, index++) {
            Bundle chunk = new Bundle();
            chunk.putString(Instrumentation.REPORT_KEY_STREAMRESULT, "QWQ_OFFLINE_SCREENSHOT "
                    + plan.getString("planDigest") + " " + index + " "
                    + encodedScreenshot.substring(offset, Math.min(offset + 3000, encodedScreenshot.length())) + "\n");
            instrumentation.sendStatus(0, chunk);
        }
        Bundle result = new Bundle();
        result.putString(Instrumentation.REPORT_KEY_STREAMRESULT, "QWQ_OFFLINE_PAGE " + evidence + "\n");
        instrumentation.sendStatus(0, result);
    }

    private static String sha256(byte[] bytes) throws Exception {
        StringBuilder hex = new StringBuilder("sha256:");
        for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes)) {
            hex.append(Character.forDigit((value & 0xff) >>> 4, 16));
            hex.append(Character.forDigit(value & 0xf, 16));
        }
        return hex.toString();
    }

    private static String observedNode(AccessibilityNodeInfo node) {
        return String.valueOf(node.getViewIdResourceName()) + " " + String.valueOf(node.getText())
                + " " + String.valueOf(node.getContentDescription());
    }

    private static AccessibilityNodeInfo revealSelectedNode(UiAutomation automation, String target, String selector) {
        for (int attempt = 0; attempt < 30; attempt++) {
            AccessibilityNodeInfo found = waitForSelectedNode(automation, target, selector, 300L);
            if (found != null) { return found; }
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            assertNotNull(root);
            try {
                assertEquals(target, String.valueOf(root.getPackageName()));
                assertTrue("实际列表不可继续滚动", scrollVisibleNode(root));
            } finally { root.recycle(); }
            SystemClock.sleep(250L);
        }
        throw new AssertionError("实际列表未发现 " + selector);
    }

    private static boolean scrollVisibleNode(AccessibilityNodeInfo node) {
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) { continue; }
            try { if (scrollVisibleNode(child)) { return true; } }
            finally { child.recycle(); }
        }
        return node.isVisibleToUser() && node.isScrollable()
                && node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
    }

    private static AccessibilityNodeInfo waitForSelectedNode(UiAutomation automation, String target,
            String selector, long timeout) {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) {
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            if (root != null) {
                try {
                    if (target.contentEquals(root.getPackageName())) {
                        AccessibilityNodeInfo found = findSelectedNode(root, selector);
                        if (found != null) { return found; }
                    }
                } finally { root.recycle(); }
            }
            SystemClock.sleep(150L);
        }
        return null;
    }

    private static boolean selectedText(CharSequence text, String selector) {
        if (text == null) { return false; }
        return selector.startsWith("text-prefix:")
                ? text.toString().startsWith(selector.substring("text-prefix:".length()))
                : selector.equals(text.toString());
    }

    private static AccessibilityNodeInfo findSelectedNode(AccessibilityNodeInfo node, String selector) {
        if (node.isVisibleToUser() && (selector.equals(node.getViewIdResourceName())
                || selectedText(node.getText(), selector)
                || selectedText(node.getContentDescription(), selector))) {
            return AccessibilityNodeInfo.obtain(node);
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) { continue; }
            try {
                AccessibilityNodeInfo found = findSelectedNode(child, selector);
                if (found != null) { return found; }
            } finally { child.recycle(); }
        }
        return null;
    }

    private static int[] playbackTimes(String value) {
        Matcher match = Pattern.compile("(\\d+):(\\d{2})\\s*/\\s*(\\d+):(\\d{2})").matcher(value);
        assertTrue("实际进度必须含当前时间和总时长", match.find());
        return new int[] {Integer.parseInt(match.group(1)) * 60 + Integer.parseInt(match.group(2)),
                Integer.parseInt(match.group(3)) * 60 + Integer.parseInt(match.group(4))};
    }

    private static String observeCompletePlayback(UiAutomation automation, String target, String selector) {
        int maximum = 0;
        int first = -1;
        long deadline = SystemClock.uptimeMillis() + 180_000L;
        while (SystemClock.uptimeMillis() < deadline) {
            AccessibilityNodeInfo node = waitForSelectedNode(automation, target, selector, 5_000L);
            assertNotNull(node);
            String value;
            try { value = observedNode(node); }
            finally { node.recycle(); }
            int[] times = playbackTimes(value);
            if (first < 0) { first = times[0]; assertTrue("完整播放必须从开头观察", first <= 2); }
            assertTrue(times[1] > 0);
            maximum = Math.max(maximum, times[0]);
            if (maximum >= times[1] - 1 && maximum > first) { return value; }
            SystemClock.sleep(150L);
        }
        throw new AssertionError("实际视频未完整播放");
    }

    @Test
    public void reusesCanonicalProductionProcessAndFindsHomeSurface() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Bundle arguments = InstrumentationRegistry.getArguments();
        String targetPackage = requiredPackage(arguments, "qwqTargetPackage");
        String expectedPackage = requiredPackage(arguments, "qwqExpectedPackage");
        assertEquals("production package selector must equal the artifact identity", expectedPackage, targetPackage);

        String driverPackage = instrumentation.getContext().getPackageName();
        String testHostPackage = instrumentation.getTargetContext().getPackageName();
        assertFalse("production AUT must not be the instrumentation driver", targetPackage.equals(driverPackage));
        assertFalse("production AUT must not be the Patrol test host", targetPackage.equals(testHostPackage));

        PackageManager packageManager = instrumentation.getTargetContext().getPackageManager();
        assertNotNull(
                "the exact production package must already be installed",
                packageManager.getPackageInfo(targetPackage, 0));

        UiAutomation automation = instrumentation.getUiAutomation();
        int pidBefore = requireSingleRunningPid(automation, targetPackage);
        AccessibilityNodeInfo homeSurface = waitForHomeSurface(automation, targetPackage, 15_000L);
        assertNotNull(
                "the canonical production AUT must already own the foreground root and expose home",
                homeSurface);
        try {
            assertEquals(targetPackage, String.valueOf(homeSurface.getPackageName()));
            assertEquals(HOME_SURFACE_IDENTIFIER, homeSurface.getViewIdResourceName());
            assertTrue(
                    "the canonical home accessibility node must be visible to the user",
                    homeSurface.isVisibleToUser());
        } finally {
            homeSurface.recycle();
        }

        int pidAfter = requireSingleRunningPid(automation, targetPackage);
        assertEquals(
                "bringing the canonical AUT to front must not replace its process",
                pidBefore,
                pidAfter);

        String marker =
                MARKER
                        + evidenceJson(
                                driverPackage,
                                testHostPackage,
                                targetPackage,
                                pidBefore,
                                pidAfter);
        Log.i(LOG_TAG, marker);
        // `adb shell am instrument -w -r` is the canonical collector for this
        // independent native journey. An instrumentation status bundle places
        // exactly one marker in that command's stdout without accepting stale
        // or unrelated logcat history.
        Bundle markerStatus = new Bundle();
        markerStatus.putString(Instrumentation.REPORT_KEY_STREAMRESULT, marker + "\n");
        instrumentation.sendStatus(0, markerStatus);
    }

    private static String requiredPackage(Bundle arguments, String key) {
        String value = arguments.getString(key, "").trim();
        assertTrue(key + " must be an exact application id", PACKAGE_NAME.matcher(value).matches());
        return value;
    }

    private static int requireSingleRunningPid(UiAutomation automation, String packageName)
            throws IOException {
        String raw = shell(automation, "pidof " + packageName).trim();
        assertTrue("canonical production AUT must already be running", !raw.isEmpty());
        String[] tokens = raw.split("\\s+");
        assertEquals("production AUT must have one canonical main process", 1, tokens.length);
        int pid = Integer.parseInt(tokens[0]);
        assertTrue("production AUT PID must be positive", pid > 0);
        return pid;
    }

    private static String shell(UiAutomation automation, String command) throws IOException {
        ParcelFileDescriptor descriptor = automation.executeShellCommand(command);
        try (FileInputStream input = new FileInputStream(descriptor.getFileDescriptor());
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                output.write(buffer, 0, read);
            }
            return output.toString(StandardCharsets.UTF_8.name());
        } finally {
            descriptor.close();
        }
    }

    private static AccessibilityNodeInfo waitForHomeSurface(
            UiAutomation automation, String packageName, long timeoutMillis) {
        long deadline = SystemClock.uptimeMillis() + timeoutMillis;
        while (SystemClock.uptimeMillis() < deadline) {
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            if (root != null) {
                try {
                    if (!packageName.contentEquals(root.getPackageName())) {
                        SystemClock.sleep(200L);
                        continue;
                    }
                    AccessibilityNodeInfo match = findHomeSurface(root, packageName);
                    if (match != null) {
                        return match;
                    }
                } finally {
                    root.recycle();
                }
            }
            SystemClock.sleep(200L);
        }
        return null;
    }

    private static AccessibilityNodeInfo findHomeSurface(
            AccessibilityNodeInfo node, String packageName) {
        if (packageName.contentEquals(node.getPackageName())
                && HOME_SURFACE_IDENTIFIER.equals(node.getViewIdResourceName())) {
            return AccessibilityNodeInfo.obtain(node);
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) {
                continue;
            }
            try {
                AccessibilityNodeInfo match = findHomeSurface(child, packageName);
                if (match != null) {
                    return match;
                }
            } finally {
                child.recycle();
            }
        }
        return null;
    }

    private static String evidenceJson(
            String driverPackage,
            String testHostPackage,
            String productionPackage,
            int pidBefore,
            int pidAfter)
            throws JSONException {
        return new JSONObject()
                .put("schema", SCHEMA)
                .put("platform", "android")
                .put("driverApplicationId", driverPackage)
                .put("testHostApplicationId", testHostPackage)
                .put("productionApplicationId", productionPackage)
                .put("processIdBefore", pidBefore)
                .put("processIdAfter", pidAfter)
                .put("stateBefore", "running_foreground")
                .put("stateAfter", "running_foreground")
                .put("activationMode", "observe_existing_foreground_process")
                .put("launchPerformed", false)
                .put("homepageAccessibilityIdentifier", HOME_SURFACE_IDENTIFIER)
                .put("homepageVisible", true)
                .put("homepageFrameIntersectsVisibleWindow", true)
                .toString();
    }
}
