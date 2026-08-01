package com.quwoquan.quwoquan_app;

import android.Manifest;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.provider.CalendarContract;
import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.util.HashMap;
import java.util.Map;
import java.util.TimeZone;

final class AssistantDeviceActionPlugin {
  static final int CALENDAR_PERMISSION_REQUEST = 47231;

  private static final String[] CALENDAR_PERMISSIONS = {
    Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR
  };
  private static final String PREFERENCES = "quwoquan.assistant.device_actions";

  private final FlutterFragmentActivity activity;
  private MethodCall pendingCall;
  private MethodChannel.Result pendingResult;

  AssistantDeviceActionPlugin(FlutterFragmentActivity activity) {
    this.activity = activity;
  }

  void handle(MethodCall call, MethodChannel.Result result) {
    if (!"createCalendarReminder".equals(call.method)) {
      result.notImplemented();
      return;
    }
    if (!validArguments(call)) {
      result.success(status("failed", ""));
      return;
    }
    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String existing =
        activity.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .getString(idempotencyKey, "");
    if (!existing.isEmpty()) {
      result.success(status("created", existing));
      return;
    }
    if (hasCalendarPermission()) {
      createCalendarReminder(call, result);
      return;
    }
    if (pendingResult != null) {
      result.success(status("failed", ""));
      return;
    }
    pendingCall = call;
    pendingResult = result;
    ActivityCompat.requestPermissions(
        activity, CALENDAR_PERMISSIONS, CALENDAR_PERMISSION_REQUEST);
  }

  boolean onRequestPermissionsResult(
      int requestCode, @NonNull int[] grantResults) {
    if (requestCode != CALENDAR_PERMISSION_REQUEST) {
      return false;
    }
    MethodCall call = pendingCall;
    MethodChannel.Result result = pendingResult;
    pendingCall = null;
    pendingResult = null;
    if (result == null || call == null) {
      return true;
    }
    boolean granted =
        grantResults.length == CALENDAR_PERMISSIONS.length;
    for (int grantResult : grantResults) {
      granted = granted && grantResult == PackageManager.PERMISSION_GRANTED;
    }
    if (!granted) {
      result.success(status("denied", ""));
      return true;
    }
    createCalendarReminder(call, result);
    return true;
  }

  private void createCalendarReminder(
      MethodCall call, MethodChannel.Result result) {
    try {
      Long calendarId = firstWritableCalendarId();
      if (calendarId == null) {
        result.success(status("unavailable", ""));
        return;
      }
      long startsAtEpochMs = longArgument(call, "startsAtEpochMs");
      int durationMinutes =
          boundedIntArgument(call, "durationMinutes", 60, 1, 1440);
      int reminderMinutes =
          boundedIntArgument(call, "reminderMinutes", 10, 0, 10080);
      ContentValues event = new ContentValues();
      event.put(CalendarContract.Events.CALENDAR_ID, calendarId);
      event.put(CalendarContract.Events.TITLE, stringArgument(call, "title"));
      event.put(CalendarContract.Events.DESCRIPTION, stringArgument(call, "notes"));
      event.put(CalendarContract.Events.DTSTART, startsAtEpochMs);
      event.put(
          CalendarContract.Events.DTEND,
          startsAtEpochMs + durationMinutes * 60_000L);
      event.put(
          CalendarContract.Events.EVENT_TIMEZONE,
          TimeZone.getDefault().getID());
      Uri eventUri =
          activity
              .getContentResolver()
              .insert(CalendarContract.Events.CONTENT_URI, event);
      if (eventUri == null) {
        result.success(status("failed", ""));
        return;
      }
      long eventId = ContentUris.parseId(eventUri);
      ContentValues reminder = new ContentValues();
      reminder.put(CalendarContract.Reminders.EVENT_ID, eventId);
      reminder.put(CalendarContract.Reminders.MINUTES, reminderMinutes);
      reminder.put(
          CalendarContract.Reminders.METHOD,
          CalendarContract.Reminders.METHOD_ALERT);
      activity
          .getContentResolver()
          .insert(CalendarContract.Reminders.CONTENT_URI, reminder);
      String objectId = Long.toString(eventId);
      activity
          .getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
          .edit()
          .putString(stringArgument(call, "idempotencyKey"), objectId)
          .apply();
      result.success(status("created", objectId));
    } catch (RuntimeException error) {
      result.success(status("failed", ""));
    }
  }

  private Long firstWritableCalendarId() {
    ContentResolver resolver = activity.getContentResolver();
    String[] projection = {CalendarContract.Calendars._ID};
    String selection =
        CalendarContract.Calendars.VISIBLE
            + "=1 AND "
            + CalendarContract.Calendars.SYNC_EVENTS
            + "=1";
    try (Cursor cursor =
        resolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            selection,
            null,
            CalendarContract.Calendars._ID + " ASC")) {
      return cursor != null && cursor.moveToFirst() ? cursor.getLong(0) : null;
    }
  }

  private boolean hasCalendarPermission() {
    return ActivityCompat.checkSelfPermission(
                activity, Manifest.permission.READ_CALENDAR)
            == PackageManager.PERMISSION_GRANTED
        && ActivityCompat.checkSelfPermission(
                activity, Manifest.permission.WRITE_CALENDAR)
            == PackageManager.PERMISSION_GRANTED;
  }

  static boolean validArguments(MethodCall call) {
    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String title = stringArgument(call, "title");
    long startsAt = longArgument(call, "startsAtEpochMs");
    return !idempotencyKey.isEmpty()
        && idempotencyKey.length() <= 128
        && !title.isEmpty()
        && title.length() <= 200
        && startsAt > 0;
  }

  static Map<String, Object> status(String value, String objectId) {
    Map<String, Object> response = new HashMap<>();
    response.put("status", value);
    response.put("deviceObjectId", objectId);
    return response;
  }

  private static String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value == null ? "" : value.toString().trim();
  }

  private static long longArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value instanceof Number ? ((Number) value).longValue() : 0L;
  }

  static int boundedIntArgument(
      MethodCall call,
      String key,
      int fallback,
      int minimum,
      int maximum) {
    Object value = call.argument(key);
    int resolved = value instanceof Number ? ((Number) value).intValue() : fallback;
    return Math.min(Math.max(resolved, minimum), maximum);
  }
}
