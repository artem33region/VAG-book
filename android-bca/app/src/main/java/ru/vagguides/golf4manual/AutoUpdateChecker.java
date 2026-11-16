package ru.vagguides.golf4manual;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Build;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Silent foreground-triggered checks; never downloads or installs automatically. */
public final class AutoUpdateChecker {
    public interface Listener { void onUpdate(UpdateInfo release); }

    private final Activity activity;
    private final Listener listener;
    private final SharedPreferences preferences;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final SharedPreferences.OnSharedPreferenceChangeListener cacheListener;
    private long installedVersion = Long.MAX_VALUE;
    private boolean working;
    private boolean destroyed;

    public AutoUpdateChecker(Activity activity, Listener listener) {
        this.activity = activity;
        this.listener = listener;
        preferences = activity.getSharedPreferences("automatic_updates", Context.MODE_PRIVATE);
        cacheListener = (prefs, key) -> {
            if (!destroyed && "release".equals(key)) showCached(activity.getPackageName(), installedVersion);
        };
        preferences.registerOnSharedPreferenceChangeListener(cacheListener);
    }

    public void checkIfDue() {
        if (destroyed || working) return;
        try {
            PackageInfo installed = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0);
            long version = Build.VERSION.SDK_INT >= 28 ? installed.getLongVersionCode() : installed.versionCode;
            installedVersion = version;
            String packageName = activity.getPackageName();
            // An earlier successful result remains useful while offline or throttled.
            showCached(packageName, version);
            long now = System.currentTimeMillis();
            if (!AutoUpdatePolicy.shouldCheck(now, preferences.getLong("lastAttempt", 0),
                    preferences.getLong("lastSuccess", 0), preferences.getLong("checkedVersion", -1), version)) return;
            working = true;
            // Persist before starting so rotation/relaunch does not flood the server.
            preferences.edit().putLong("lastAttempt", now).putLong("checkedVersion", version)
                    .putLong("lastSuccess", 0).apply();
            executor.execute(() -> {
                try {
                    JSONObject entry = UpdateClient.fetchRelease(packageName);
                    UpdateInfo found = UpdateClient.parseRelease(packageName, entry);
                    preferences.edit().putString("release", entry.toString()).putLong("lastSuccess", now).apply();
                    activity.runOnUiThread(() -> {
                        if (destroyed) return;
                        working = false;
                        listener.onUpdate(found.isNewerThan(version) ? found : null);
                    });
                } catch (Exception ignored) {
                    // Network errors must not interrupt offline reading.
                    activity.runOnUiThread(() -> { if (!destroyed) working = false; });
                }
            });
        } catch (Exception ignored) {
            working = false;
        }
    }

    private void showCached(String packageName, long installedVersion) {
        try {
            String json = preferences.getString("release", "");
            UpdateInfo cached = UpdateClient.parseRelease(packageName, new JSONObject(json));
            listener.onUpdate(cached.isNewerThan(installedVersion) ? cached : null);
        } catch (Exception ignored) {
            listener.onUpdate(null);
        }
    }

    public void close() {
        destroyed = true;
        preferences.unregisterOnSharedPreferenceChangeListener(cacheListener);
        executor.shutdownNow();
    }
}
