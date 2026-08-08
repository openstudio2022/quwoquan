package com.quwoquan.quwoquan_app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.Manifest;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.CalendarContract;
import androidx.test.core.app.ActivityScenario;
import androidx.test.platform.app.InstrumentationRegistry;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;

public final class AssistantDeviceActionPluginTest {
  @Test
  public void permissionStatusUsesOnlyPubliclyObservableState() {
    assertEquals("granted", AssistantDeviceActionPlugin.permissionStatus(true, true, false));
    assertEquals("requestable", AssistantDeviceActionPlugin.permissionStatus(false, false, false));
    assertEquals("requestable", AssistantDeviceActionPlugin.permissionStatus(false, true, true));
    assertEquals("denied", AssistantDeviceActionPlugin.permissionStatus(false, true, false));
  }

  @Test
  public void validatesCanonicalCrudArguments() {
    Map<String, Object> create = eventArguments("create-1");
    assertTrue(
        AssistantDeviceActionPlugin.validArguments(
            "create", new MethodCall("createEvent", create)));

    create.put("inputDigest", "not-a-digest");
    assertFalse(
        AssistantDeviceActionPlugin.validArguments(
            "create", new MethodCall("createEvent", create)));

    Map<String, Object> delete = deleteArguments("delete-1", "42");
    assertTrue(
        AssistantDeviceActionPlugin.validArguments(
            "delete", new MethodCall("deleteEvent", delete)));
    delete.put("deviceEventId", "");
    assertFalse(
        AssistantDeviceActionPlugin.validArguments(
            "delete", new MethodCall("deleteEvent", delete)));
  }

  @Test
  public void returnsPrivacySafeReceiptShape() {
    String digest =
        AssistantDeviceActionPlugin.receiptDigest(
            "create", "idempotency-1", canonicalDigest('a'), "event-1");
    Map<String, Object> response =
        AssistantDeviceActionPlugin.success("event-1", digest, false);

    assertEquals("succeeded", response.get("status"));
    assertEquals("event-1", response.get("deviceEventId"));
    assertTrue(response.get("receiptDigest").toString().matches("^sha256:[0-9a-f]{64}$"));
    assertFalse(response.containsKey("title"));
    assertFalse(response.containsKey("notes"));
    assertFalse(response.containsKey("location"));
  }

  @Test
  public void createUpdateDeleteAndReplayAreIdempotent() {
    Context context =
        InstrumentationRegistry.getInstrumentation().getTargetContext();
    InstrumentationRegistry.getInstrumentation()
        .getUiAutomation()
        .grantRuntimePermission(
            context.getPackageName(), Manifest.permission.READ_CALENDAR);
    InstrumentationRegistry.getInstrumentation()
        .getUiAutomation()
        .grantRuntimePermission(
            context.getPackageName(), Manifest.permission.WRITE_CALENDAR);
    Uri calendarUri = insertLocalCalendar(context.getContentResolver());
    long calendarId = ContentUris.parseId(calendarUri);
    String suffix = Long.toString(System.nanoTime());
    long[] eventId = {0L};

    try (ActivityScenario<MainActivity> scenario =
        ActivityScenario.launch(MainActivity.class)) {
      scenario.onActivity(
          activity -> {
            AssistantDeviceActionPlugin plugin =
                new AssistantDeviceActionPlugin(activity);
            Map<String, Object> create = eventArguments("create-" + suffix);
            create.put("calendarId", Long.toString(calendarId));
            Map<String, Object> created =
                invoke(plugin, "createEvent", create);
            assertEquals("succeeded", created.get("status"));
            eventId[0] =
                Long.parseLong(created.get("deviceEventId").toString());
            assertEventTitle(
                context.getContentResolver(), eventId[0], "Android 合同测试");

            AssistantDeviceActionPlugin restartedPlugin =
                new AssistantDeviceActionPlugin(activity);
            Map<String, Object> createReplay =
                invoke(restartedPlugin, "createEvent", create);
            assertEquals("succeeded", createReplay.get("status"));
            assertEquals(Boolean.TRUE, createReplay.get("replayed"));
            assertEquals(
                Long.toString(eventId[0]),
                createReplay.get("deviceEventId"));

            Map<String, Object> update = eventArguments("update-" + suffix);
            update.put("deviceEventId", Long.toString(eventId[0]));
            update.put("calendarId", Long.toString(calendarId));
            update.put("title", "Android 合同测试（更新）");
            update.put("inputDigest", canonicalDigest('b'));
            Map<String, Object> updated =
                invoke(restartedPlugin, "updateEvent", update);
            assertEquals("succeeded", updated.get("status"));
            assertEventTitle(
                context.getContentResolver(),
                eventId[0],
                "Android 合同测试（更新）");

            Map<String, Object> updateReplay =
                invoke(restartedPlugin, "updateEvent", update);
            assertEquals(Boolean.TRUE, updateReplay.get("replayed"));

            Map<String, Object> delete =
                deleteArguments("delete-" + suffix, Long.toString(eventId[0]));
            Map<String, Object> deleted =
                invoke(restartedPlugin, "deleteEvent", delete);
            assertEquals("succeeded", deleted.get("status"));
            assertFalse(eventExists(context.getContentResolver(), eventId[0]));

            Map<String, Object> deleteReplay =
                invoke(restartedPlugin, "deleteEvent", delete);
            assertEquals("succeeded", deleteReplay.get("status"));
            assertEquals(Boolean.TRUE, deleteReplay.get("replayed"));
          });
    } finally {
      if (eventId[0] > 0) {
        context
            .getContentResolver()
            .delete(
                ContentUris.withAppendedId(
                    CalendarContract.Events.CONTENT_URI, eventId[0]),
                null,
                null);
      }
      context
          .getSharedPreferences("quwoquan.device_calendar", Context.MODE_PRIVATE)
          .edit()
          .clear()
          .commit();
      context
          .getContentResolver()
          .delete(
              syncAdapterUri(
                  ContentUris.withAppendedId(
                      CalendarContract.Calendars.CONTENT_URI, calendarId)),
              null,
              null);
    }
  }

  private static Uri insertLocalCalendar(ContentResolver resolver) {
    String account = "quwoquan-device-calendar-test";
    ContentValues values = new ContentValues();
    values.put(CalendarContract.Calendars.ACCOUNT_NAME, account);
    values.put(
        CalendarContract.Calendars.ACCOUNT_TYPE,
        CalendarContract.ACCOUNT_TYPE_LOCAL);
    values.put(CalendarContract.Calendars.NAME, account);
    values.put(
        CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
        "DeviceCalendar 合同测试");
    values.put(CalendarContract.Calendars.CALENDAR_COLOR, 0xFF0A84FF);
    values.put(
        CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL,
        CalendarContract.Calendars.CAL_ACCESS_OWNER);
    values.put(CalendarContract.Calendars.OWNER_ACCOUNT, account);
    values.put(CalendarContract.Calendars.VISIBLE, 1);
    values.put(CalendarContract.Calendars.SYNC_EVENTS, 1);
    Uri inserted =
        resolver.insert(
            syncAdapterUri(CalendarContract.Calendars.CONTENT_URI), values);
    if (inserted == null) {
      throw new AssertionError("failed to insert local test calendar");
    }
    return inserted;
  }

  private static Uri syncAdapterUri(Uri uri) {
    return uri.buildUpon()
        .appendQueryParameter(CalendarContract.CALLER_IS_SYNCADAPTER, "true")
        .appendQueryParameter(
            CalendarContract.Calendars.ACCOUNT_NAME,
            "quwoquan-device-calendar-test")
        .appendQueryParameter(
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.ACCOUNT_TYPE_LOCAL)
        .build();
  }

  private static void assertEventTitle(
      ContentResolver resolver, long eventId, String title) {
    try (Cursor cursor =
        resolver.query(
            ContentUris.withAppendedId(
                CalendarContract.Events.CONTENT_URI, eventId),
            new String[] {CalendarContract.Events.TITLE},
            null,
            null,
            null)) {
      assertTrue(cursor != null && cursor.moveToFirst());
      assertEquals(title, cursor.getString(0));
    }
  }

  private static boolean eventExists(
      ContentResolver resolver, long eventId) {
    try (Cursor cursor =
        resolver.query(
            ContentUris.withAppendedId(
                CalendarContract.Events.CONTENT_URI, eventId),
            new String[] {CalendarContract.Events._ID},
            null,
            null,
            null)) {
      return cursor != null && cursor.moveToFirst();
    }
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> invoke(
      AssistantDeviceActionPlugin plugin,
      String method,
      Map<String, Object> arguments) {
    AtomicReference<Object> value = new AtomicReference<>();
    plugin.handle(
        new MethodCall(method, arguments),
        new MethodChannel.Result() {
          @Override
          public void success(Object result) {
            value.set(result);
          }

          @Override
          public void error(String code, String message, Object details) {
            throw new AssertionError(code + ": " + message);
          }

          @Override
          public void notImplemented() {
            throw new AssertionError("method not implemented");
          }
        });
    Object result = value.get();
    if (!(result instanceof Map)) {
      throw new AssertionError("missing device calendar result");
    }
    return (Map<String, Object>) result;
  }

  private static Map<String, Object> eventArguments(String idempotencyKey) {
    Map<String, Object> arguments = new HashMap<>();
    arguments.put("idempotencyKey", idempotencyKey);
    arguments.put("inputDigest", canonicalDigest('a'));
    arguments.put("calendarId", "");
    arguments.put("title", "Android 合同测试");
    arguments.put("startEpochMs", 1_800_000_000_000L);
    arguments.put("endEpochMs", 1_800_003_600_000L);
    arguments.put("timezone", "Asia/Shanghai");
    arguments.put("location", "西湖");
    arguments.put("notes", "DeviceCalendar 原生合同");
    return arguments;
  }

  private static Map<String, Object> deleteArguments(
      String idempotencyKey, String eventId) {
    Map<String, Object> arguments = new HashMap<>();
    arguments.put("idempotencyKey", idempotencyKey);
    arguments.put("inputDigest", canonicalDigest('c'));
    arguments.put("deviceEventId", eventId);
    return arguments;
  }

  private static String canonicalDigest(char value) {
    return "sha256:" + new String(new char[64]).replace('\0', value);
  }
}
