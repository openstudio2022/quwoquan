package com.quwoquan.testhost.patrol;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.util.Log;
import android.view.accessibility.AccessibilityNodeInfo;

import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

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
