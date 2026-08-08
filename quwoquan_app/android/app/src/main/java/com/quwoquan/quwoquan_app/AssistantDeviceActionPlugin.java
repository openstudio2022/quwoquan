package com.quwoquan.quwoquan_app;

import android.Manifest;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.provider.CalendarContract;
import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import io.flutter.embedding.android.FlutterFragmentActivity;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.Map;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Native CalendarContract handler for the platform DeviceCalendarBridge.
 *
 * <p>The opaque permit is verified in the Dart platform boundary before this
 * handler is invoked. This class independently validates native arguments,
 * owns the explicit runtime-permission flow, and persists only opaque
 * idempotency/receipt material. Event title/location/notes are never returned
 * to Dart or copied into preferences.
 */
final class AssistantDeviceActionPlugin {
  static final int CALENDAR_PERMISSION_REQUEST = 47231;

  private static final String[] CALENDAR_PERMISSIONS = {
    Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR
  };
  private static final String PREFERENCES = "quwoquan.device_calendar";
  private static final String PERMISSION_REQUESTED = "permission_requested";
  private static final String RECORD_PREFIX = "mutation.";

  private final FlutterFragmentActivity activity;
  private MethodCall pendingCall;
  private MethodChannel.Result pendingResult;

  AssistantDeviceActionPlugin(FlutterFragmentActivity activity) {
    this.activity = activity;
  }

  void handle(MethodCall call, MethodChannel.Result result) {
    switch (call.method) {
      case "probe":
        handleProbe(result);
        return;
      case "createEvent":
        handleMutation("create", call, result);
        return;
      case "updateEvent":
        handleMutation("update", call, result);
        return;
      case "deleteEvent":
        handleMutation("delete", call, result);
        return;
      case "createCalendarReminder":
        // The pre-M3 shape has no permit binding and must never mutate state.
        result.success(failure("unavailable"));
        return;
      default:
        result.notImplemented();
    }
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
    String permission = permissionStatus();
    if (!"granted".equals(permission)) {
      result.success(
          failure(
              "restricted".equals(permission)
                  ? "permission_restricted"
                  : "permission_denied"));
      return true;
    }
    handle(call, result);
    return true;
  }

  private void handleProbe(MethodChannel.Result result) {
    String permission = permissionStatus();
    if (!"granted".equals(permission)) {
      result.success(probe("available", permission, false));
      return;
    }
    try {
      result.success(
          probe("available", "granted", firstWritableCalendarId() != null));
    } catch (RuntimeException error) {
      result.success(probe("unavailable", "granted", false));
    }
  }

  private void handleMutation(
      String operation, MethodCall call, MethodChannel.Result result) {
    if (!validArguments(operation, call)) {
      result.success(failure("invalid_request"));
      return;
    }

    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String inputDigest = stringArgument(call, "inputDigest");
    MutationRecord existing = readRecord(idempotencyKey);
    if (existing != null && !existing.matches(operation, inputDigest)) {
      result.success(failure("idempotency_conflict"));
      return;
    }
    if (existing != null && existing.succeeded()) {
      result.success(
          success(existing.eventId, existing.receiptDigest, true));
      return;
    }

    String permission = permissionStatus();
    if ("requestable".equals(permission)) {
      requestPermission(call, result);
      return;
    }
    if (!"granted".equals(permission)) {
      result.success(
          failure(
              "restricted".equals(permission)
                  ? "permission_restricted"
                  : "permission_denied"));
      return;
    }

    try {
      switch (operation) {
        case "create":
          createEvent(call, existing, result);
          return;
        case "update":
          updateEvent(call, existing, result);
          return;
        case "delete":
          deleteEvent(call, existing, result);
          return;
        default:
          result.success(failure("invalid_request"));
      }
    } catch (SecurityException error) {
      result.success(failure("permission_denied"));
    } catch (RuntimeException error) {
      result.success(failure("system_error"));
    }
  }

  private void requestPermission(
      MethodCall call, MethodChannel.Result result) {
    if (pendingResult != null) {
      result.success(failure("system_error"));
      return;
    }
    if (!preferences()
        .edit()
        .putBoolean(PERMISSION_REQUESTED, true)
        .commit()) {
      result.success(failure("system_error"));
      return;
    }
    pendingCall = call;
    pendingResult = result;
    ActivityCompat.requestPermissions(
        activity, CALENDAR_PERMISSIONS, CALENDAR_PERMISSION_REQUEST);
  }

  private void createEvent(
      MethodCall call,
      MutationRecord existing,
      MethodChannel.Result result) {
    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String inputDigest = stringArgument(call, "inputDigest");
    if (existing != null && existing.pending()) {
      String recovered = eventIdForMarker(eventMarker(idempotencyKey));
      if (!recovered.isEmpty()) {
        finishSuccess(
            "create",
            idempotencyKey,
            inputDigest,
            recovered,
            true,
            result);
        return;
      }
    }

    Long calendarId = writableCalendarId(stringArgument(call, "calendarId"));
    if (calendarId == null) {
      result.success(failure("no_calendar"));
      return;
    }
    if (!writePending("create", idempotencyKey, inputDigest, "")) {
      result.success(failure("system_error"));
      return;
    }

    ContentValues values = eventValues(call);
    values.put(CalendarContract.Events.CALENDAR_ID, calendarId);
    values.put(
        CalendarContract.Events.CUSTOM_APP_PACKAGE,
        activity.getPackageName());
    values.put(
        CalendarContract.Events.CUSTOM_APP_URI,
        eventMarker(idempotencyKey));

    Uri eventUri = null;
    try {
      eventUri =
          activity
              .getContentResolver()
              .insert(CalendarContract.Events.CONTENT_URI, values);
      if (eventUri == null) {
        result.success(failure("system_error"));
        return;
      }
      String eventId = Long.toString(ContentUris.parseId(eventUri));
      finishSuccess(
          "create",
          idempotencyKey,
          inputDigest,
          eventId,
          false,
          result);
    } catch (RuntimeException error) {
      rollbackCreatedEvent(eventUri);
      throw error;
    }
  }

  private void updateEvent(
      MethodCall call,
      MutationRecord existing,
      MethodChannel.Result result) {
    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String inputDigest = stringArgument(call, "inputDigest");
    String eventId = stringArgument(call, "deviceEventId");
    Long numericEventId = parseEventId(eventId);
    if (numericEventId == null || !eventExists(numericEventId)) {
      result.success(failure("event_not_found"));
      return;
    }
    String requestedCalendarId = stringArgument(call, "calendarId");
    Long calendarId = null;
    if (!requestedCalendarId.isEmpty()) {
      calendarId = writableCalendarId(requestedCalendarId);
      if (calendarId == null) {
        result.success(failure("no_calendar"));
        return;
      }
    }
    if (existing == null
        && !writePending("update", idempotencyKey, inputDigest, eventId)) {
      result.success(failure("system_error"));
      return;
    }

    ContentValues values = eventValues(call);
    if (calendarId != null) {
      values.put(CalendarContract.Events.CALENDAR_ID, calendarId);
    }
    int updated =
        activity
            .getContentResolver()
            .update(
                ContentUris.withAppendedId(
                    CalendarContract.Events.CONTENT_URI, numericEventId),
                values,
                null,
                null);
    if (updated == 0) {
      result.success(failure("event_not_found"));
      return;
    }
    finishSuccess(
        "update",
        idempotencyKey,
        inputDigest,
        eventId,
        existing != null,
        result);
  }

  private void deleteEvent(
      MethodCall call,
      MutationRecord existing,
      MethodChannel.Result result) {
    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String inputDigest = stringArgument(call, "inputDigest");
    String eventId = stringArgument(call, "deviceEventId");
    Long numericEventId = parseEventId(eventId);
    if (numericEventId == null) {
      result.success(failure("event_not_found"));
      return;
    }
    boolean exists = eventExists(numericEventId);
    if (existing != null && existing.pending() && !exists) {
      finishSuccess(
          "delete",
          idempotencyKey,
          inputDigest,
          eventId,
          true,
          result);
      return;
    }
    if (!exists) {
      result.success(failure("event_not_found"));
      return;
    }
    if (existing == null
        && !writePending("delete", idempotencyKey, inputDigest, eventId)) {
      result.success(failure("system_error"));
      return;
    }
    int deleted =
        activity
            .getContentResolver()
            .delete(
                ContentUris.withAppendedId(
                    CalendarContract.Events.CONTENT_URI, numericEventId),
                null,
                null);
    if (deleted == 0) {
      result.success(failure("event_not_found"));
      return;
    }
    finishSuccess(
        "delete",
        idempotencyKey,
        inputDigest,
        eventId,
        existing != null,
        result);
  }

  private ContentValues eventValues(MethodCall call) {
    ContentValues values = new ContentValues();
    values.put(
        CalendarContract.Events.TITLE, stringArgument(call, "title"));
    values.put(
        CalendarContract.Events.DESCRIPTION, stringArgument(call, "notes"));
    values.put(
        CalendarContract.Events.EVENT_LOCATION,
        stringArgument(call, "location"));
    values.put(
        CalendarContract.Events.DTSTART, longArgument(call, "startEpochMs"));
    values.put(
        CalendarContract.Events.DTEND, longArgument(call, "endEpochMs"));
    values.put(
        CalendarContract.Events.EVENT_TIMEZONE,
        stringArgument(call, "timezone"));
    return values;
  }

  private void finishSuccess(
      String operation,
      String idempotencyKey,
      String inputDigest,
      String eventId,
      boolean replayed,
      MethodChannel.Result result) {
    String receiptDigest =
        receiptDigest(operation, idempotencyKey, inputDigest, eventId);
    MutationRecord record =
        new MutationRecord(
            operation, inputDigest, eventId, receiptDigest, "succeeded");
    if (!writeRecord(idempotencyKey, record)) {
      result.success(failure("system_error"));
      return;
    }
    result.success(success(eventId, receiptDigest, replayed));
  }

  private boolean writePending(
      String operation,
      String idempotencyKey,
      String inputDigest,
      String eventId) {
    return writeRecord(
        idempotencyKey,
        new MutationRecord(
            operation, inputDigest, eventId, "", "pending"));
  }

  private MutationRecord readRecord(String idempotencyKey) {
    String encoded =
        preferences().getString(recordKey(idempotencyKey), "");
    if (encoded.isEmpty()) {
      return null;
    }
    try {
      JSONObject json = new JSONObject(encoded);
      return new MutationRecord(
          json.optString("operation", ""),
          json.optString("inputDigest", ""),
          json.optString("eventId", ""),
          json.optString("receiptDigest", ""),
          json.optString("status", ""));
    } catch (JSONException error) {
      // Corrupt replay state must fail closed as an idempotency conflict.
      return new MutationRecord("invalid", "invalid", "", "", "invalid");
    }
  }

  private boolean writeRecord(
      String idempotencyKey, MutationRecord record) {
    JSONObject json = new JSONObject();
    try {
      json.put("operation", record.operation);
      json.put("inputDigest", record.inputDigest);
      json.put("eventId", record.eventId);
      json.put("receiptDigest", record.receiptDigest);
      json.put("status", record.status);
    } catch (JSONException error) {
      return false;
    }
    return preferences()
        .edit()
        .putString(recordKey(idempotencyKey), json.toString())
        .commit();
  }

  private SharedPreferences preferences() {
    return activity.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
  }

  private String recordKey(String idempotencyKey) {
    return RECORD_PREFIX + sha256Hex(idempotencyKey);
  }

  private Long writableCalendarId(String requestedId) {
    if (!requestedId.isEmpty()) {
      try {
        long value = Long.parseLong(requestedId);
        return calendarIsWritable(value) ? value : null;
      } catch (NumberFormatException error) {
        return null;
      }
    }
    return firstWritableCalendarId();
  }

  private Long firstWritableCalendarId() {
    String selection =
        CalendarContract.Calendars.VISIBLE
            + "=1 AND "
            + CalendarContract.Calendars.SYNC_EVENTS
            + "=1 AND "
            + CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL
            + ">=?";
    String[] selectionArguments = {
      Integer.toString(CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR)
    };
    try (Cursor cursor =
        activity
            .getContentResolver()
            .query(
                CalendarContract.Calendars.CONTENT_URI,
                new String[] {CalendarContract.Calendars._ID},
                selection,
                selectionArguments,
                CalendarContract.Calendars._ID + " ASC")) {
      return cursor != null && cursor.moveToFirst()
          ? cursor.getLong(0)
          : null;
    }
  }

  private boolean calendarIsWritable(long calendarId) {
    String selection =
        CalendarContract.Calendars._ID
            + "=? AND "
            + CalendarContract.Calendars.VISIBLE
            + "=1 AND "
            + CalendarContract.Calendars.SYNC_EVENTS
            + "=1 AND "
            + CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL
            + ">=?";
    String[] selectionArguments = {
      Long.toString(calendarId),
      Integer.toString(CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR)
    };
    try (Cursor cursor =
        activity
            .getContentResolver()
            .query(
                CalendarContract.Calendars.CONTENT_URI,
                new String[] {CalendarContract.Calendars._ID},
                selection,
                selectionArguments,
                null)) {
      return cursor != null && cursor.moveToFirst();
    }
  }

  private boolean eventExists(long eventId) {
    try (Cursor cursor =
        activity
            .getContentResolver()
            .query(
                ContentUris.withAppendedId(
                    CalendarContract.Events.CONTENT_URI, eventId),
                new String[] {CalendarContract.Events._ID},
                null,
                null,
                null)) {
      return cursor != null && cursor.moveToFirst();
    }
  }

  private String eventIdForMarker(String marker) {
    String selection =
        CalendarContract.Events.CUSTOM_APP_PACKAGE
            + "=? AND "
            + CalendarContract.Events.CUSTOM_APP_URI
            + "=?";
    String[] selectionArguments = {activity.getPackageName(), marker};
    try (Cursor cursor =
        activity
            .getContentResolver()
            .query(
                CalendarContract.Events.CONTENT_URI,
                new String[] {CalendarContract.Events._ID},
                selection,
                selectionArguments,
                CalendarContract.Events._ID + " ASC")) {
      return cursor != null && cursor.moveToFirst()
          ? Long.toString(cursor.getLong(0))
          : "";
    }
  }

  private void rollbackCreatedEvent(Uri eventUri) {
    if (eventUri == null) {
      return;
    }
    try {
      activity.getContentResolver().delete(eventUri, null, null);
    } catch (RuntimeException ignored) {
      // The public result remains failed.
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

  private String permissionStatus() {
    boolean requested =
        preferences().getBoolean(PERMISSION_REQUESTED, false);
    boolean canExplain =
        ActivityCompat.shouldShowRequestPermissionRationale(
                activity, Manifest.permission.READ_CALENDAR)
            || ActivityCompat.shouldShowRequestPermissionRationale(
                activity, Manifest.permission.WRITE_CALENDAR);
    return permissionStatus(hasCalendarPermission(), requested, canExplain);
  }

  static String permissionStatus(
      boolean granted, boolean requested, boolean canExplain) {
    if (granted) {
      return "granted";
    }
    // Android's public SDK does not expose the system/policy-fixed permission
    // flags to an ordinary application.  A previously requested permission
    // without rationale therefore remains the honest observable "denied"
    // state; managed-device restrictions are not guessed from hidden APIs.
    return !requested || canExplain ? "requestable" : "denied";
  }

  static boolean validArguments(String operation, MethodCall call) {
    String idempotencyKey = stringArgument(call, "idempotencyKey");
    String inputDigest = stringArgument(call, "inputDigest");
    if (idempotencyKey.isEmpty()
        || idempotencyKey.length() > 128
        || !inputDigest.matches("^sha256:[0-9a-f]{64}$")) {
      return false;
    }
    if ("delete".equals(operation)) {
      return validDeviceEventId(call);
    }
    if ("update".equals(operation) && !validDeviceEventId(call)) {
      return false;
    }
    String title = stringArgument(call, "title");
    String timezone = stringArgument(call, "timezone");
    String calendarId = stringArgument(call, "calendarId");
    String location = stringArgument(call, "location");
    String notes = stringArgument(call, "notes");
    long start = longArgument(call, "startEpochMs");
    long end = longArgument(call, "endEpochMs");
    return !title.isEmpty()
        && title.length() <= 200
        && !timezone.isEmpty()
        && timezone.length() <= 100
        && calendarId.length() <= 512
        && location.length() <= 500
        && notes.length() <= 2000
        && start > 0
        && end > start;
  }

  private static boolean validDeviceEventId(MethodCall call) {
    String eventId = stringArgument(call, "deviceEventId");
    return !eventId.isEmpty() && eventId.length() <= 512;
  }

  static String eventMarker(String idempotencyKey) {
    return "quwoquan://device-calendar/" + sha256Hex(idempotencyKey);
  }

  static String receiptDigest(
      String operation,
      String idempotencyKey,
      String inputDigest,
      String eventId) {
    return "sha256:"
        + sha256Hex(
            "device-calendar-receipt\n"
                + operation
                + "\n"
                + idempotencyKey
                + "\n"
                + inputDigest
                + "\n"
                + eventId);
  }

  static Map<String, Object> success(
      String eventId, String receiptDigest, boolean replayed) {
    Map<String, Object> response = new HashMap<>();
    response.put("status", "succeeded");
    response.put("deviceEventId", eventId);
    response.put("receiptDigest", receiptDigest);
    response.put("replayed", replayed);
    return response;
  }

  static Map<String, Object> failure(String status) {
    Map<String, Object> response = new HashMap<>();
    response.put("status", status);
    response.put("deviceEventId", "");
    response.put("receiptDigest", "");
    response.put("replayed", false);
    return response;
  }

  static Map<String, Object> probe(
      String availability,
      String permission,
      boolean hasWritableCalendar) {
    Map<String, Object> response = new HashMap<>();
    response.put("availability", availability);
    response.put("permission", permission);
    response.put("hasWritableCalendar", hasWritableCalendar);
    return response;
  }

  private static String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value instanceof String ? ((String) value).trim() : "";
  }

  private static long longArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value instanceof Number ? ((Number) value).longValue() : 0L;
  }

  private static Long parseEventId(String value) {
    try {
      return Long.parseLong(value);
    } catch (NumberFormatException error) {
      return null;
    }
  }

  private static String sha256Hex(String value) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256")
              .digest(value.getBytes(StandardCharsets.UTF_8));
      StringBuilder hex = new StringBuilder(digest.length * 2);
      for (byte item : digest) {
        int unsigned = item & 0xff;
        hex.append(Character.forDigit(unsigned >>> 4, 16));
        hex.append(Character.forDigit(unsigned & 0x0f, 16));
      }
      return hex.toString();
    } catch (NoSuchAlgorithmException error) {
      throw new IllegalStateException("SHA-256 unavailable", error);
    }
  }

  private static final class MutationRecord {
    MutationRecord(
        String operation,
        String inputDigest,
        String eventId,
        String receiptDigest,
        String status) {
      this.operation = operation;
      this.inputDigest = inputDigest;
      this.eventId = eventId;
      this.receiptDigest = receiptDigest;
      this.status = status;
    }

    final String operation;
    final String inputDigest;
    final String eventId;
    final String receiptDigest;
    final String status;

    boolean matches(String expectedOperation, String expectedDigest) {
      return operation.equals(expectedOperation)
          && inputDigest.equals(expectedDigest);
    }

    boolean pending() {
      return "pending".equals(status);
    }

    boolean succeeded() {
      return "succeeded".equals(status)
          && !eventId.isEmpty()
          && receiptDigest.matches("^sha256:[0-9a-f]{64}$");
    }
  }
}
