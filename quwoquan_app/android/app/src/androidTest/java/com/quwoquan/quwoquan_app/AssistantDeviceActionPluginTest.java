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
  public void validatesCanonicalCalendarReminderArguments() {
    Map<String, Object> arguments = validArguments();

    assertTrue(
        AssistantDeviceActionPlugin.validArguments(
            new MethodCall("createCalendarReminder", arguments)));

    arguments.put("idempotencyKey", "");
    assertFalse(
        AssistantDeviceActionPlugin.validArguments(
            new MethodCall("createCalendarReminder", arguments)));
  }

  @Test
  public void clampsNativeCalendarBounds() {
    Map<String, Object> arguments = validArguments();
    arguments.put("durationMinutes", -20);
    arguments.put("reminderMinutes", 99_999);
    MethodCall call = new MethodCall("createCalendarReminder", arguments);

    assertEquals(
        1,
        AssistantDeviceActionPlugin.boundedIntArgument(
            call, "durationMinutes", 60, 1, 1440));
    assertEquals(
        10_080,
        AssistantDeviceActionPlugin.boundedIntArgument(
            call, "reminderMinutes", 10, 0, 10_080));
  }

  @Test
  public void returnsTypedNativeReceiptShape() {
    Map<String, Object> expected = new HashMap<>();
    expected.put("status", "created");
    expected.put("deviceObjectId", "event-1");
    assertEquals(
        expected,
        AssistantDeviceActionPlugin.status("created", "event-1"));
  }

  @Test
  public void createsOneReadableCalendarEventForIdempotentReplay() {
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
    String idempotencyKey = "native-test-" + System.nanoTime();
    Map<String, Object> arguments = validArguments();
    arguments.put("idempotencyKey", idempotencyKey);
    arguments.put("title", "小趣 Android 原生合同测试");
    long[] eventId = {0L};

    try (ActivityScenario<MainActivity> scenario =
        ActivityScenario.launch(MainActivity.class)) {
      scenario.onActivity(
          activity -> {
            AssistantDeviceActionPlugin plugin =
                new AssistantDeviceActionPlugin(activity);
            Map<String, Object> first = invoke(plugin, arguments);
            assertEquals("created", first.get("status"));
            eventId[0] =
                Long.parseLong(first.get("deviceObjectId").toString());
            assertReadableEvent(
                context.getContentResolver(),
                eventId[0],
                "小趣 Android 原生合同测试");

            Map<String, Object> replay = invoke(plugin, arguments);
            assertEquals("created", replay.get("status"));
            assertEquals(
                Long.toString(eventId[0]),
                replay.get("deviceObjectId"));
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
          .getSharedPreferences(
              "quwoquan.assistant.device_actions",
              Context.MODE_PRIVATE)
          .edit()
          .remove(idempotencyKey)
          .commit();
      context.getContentResolver().delete(
          syncAdapterUri(
              ContentUris.withAppendedId(
                  CalendarContract.Calendars.CONTENT_URI, calendarId)),
          null,
          null);
    }
  }

  private static Uri insertLocalCalendar(ContentResolver resolver) {
    String account = "quwoquan-native-test";
    ContentValues values = new ContentValues();
    values.put(CalendarContract.Calendars.ACCOUNT_NAME, account);
    values.put(
        CalendarContract.Calendars.ACCOUNT_TYPE,
        CalendarContract.ACCOUNT_TYPE_LOCAL);
    values.put(CalendarContract.Calendars.NAME, account);
    values.put(
        CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
        "小趣原生合同测试");
    values.put(CalendarContract.Calendars.CALENDAR_COLOR, 0xFF0A84FF);
    values.put(
        CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL,
        CalendarContract.Calendars.CAL_ACCESS_OWNER);
    values.put(CalendarContract.Calendars.OWNER_ACCOUNT, account);
    values.put(CalendarContract.Calendars.VISIBLE, 1);
    values.put(CalendarContract.Calendars.SYNC_EVENTS, 1);
    Uri inserted =
        resolver.insert(
            syncAdapterUri(CalendarContract.Calendars.CONTENT_URI),
            values);
    if (inserted == null) {
      throw new AssertionError("failed to insert local test calendar");
    }
    return inserted;
  }

  private static Uri syncAdapterUri(Uri uri) {
    return uri.buildUpon()
        .appendQueryParameter(
            CalendarContract.CALLER_IS_SYNCADAPTER, "true")
        .appendQueryParameter(
            CalendarContract.Calendars.ACCOUNT_NAME,
            "quwoquan-native-test")
        .appendQueryParameter(
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.ACCOUNT_TYPE_LOCAL)
        .build();
  }

  private static void assertReadableEvent(
      ContentResolver resolver,
      long eventId,
      String title) {
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

  @SuppressWarnings("unchecked")
  private static Map<String, Object> invoke(
      AssistantDeviceActionPlugin plugin,
      Map<String, Object> arguments) {
    AtomicReference<Object> value = new AtomicReference<>();
    plugin.handle(
        new MethodCall("createCalendarReminder", arguments),
        new MethodChannel.Result() {
          @Override
          public void success(Object result) {
            value.set(result);
          }

          @Override
          public void error(
              String code, String message, Object details) {
            throw new AssertionError(code + ": " + message);
          }

          @Override
          public void notImplemented() {
            throw new AssertionError("method not implemented");
          }
        });
    Object result = value.get();
    if (!(result instanceof Map)) {
      throw new AssertionError("missing device action result");
    }
    return (Map<String, Object>) result;
  }

  private static Map<String, Object> validArguments() {
    Map<String, Object> arguments = new HashMap<>();
    arguments.put("idempotencyKey", "arn_1:tool_1");
    arguments.put("title", "提交周报");
    arguments.put("startsAtEpochMs", 1_800_000_000_000L);
    arguments.put("durationMinutes", 30);
    arguments.put("reminderMinutes", 10);
    arguments.put("notes", "来自小趣确认动作");
    return arguments;
  }
}
