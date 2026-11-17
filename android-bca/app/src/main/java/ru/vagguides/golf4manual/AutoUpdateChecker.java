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

    /** Called on every main-screen resume, including a new launch or return from background. */
    public void checkOnOpen() {
        if (destroyed || working) return;
        try {
            PackageInfo installed = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0);
            long version = Build.VERSION.SDK_INT >= 28 ? installed.getLongVersionCode() : installed.versionCode;
            installedVersion = version;
            String packageName = activity.getPackageName();
            // Keep an earlier result visible while the fresh request runs or the device is offline.
            showCached(packageName, version);
            working = true;
            executor.execute(() -> {
                try {
                    JSONObject entry = UpdateClient.fetchRelease(packageName);
                    UpdateInfo found = UpdateClient.parseRelease(packageName, entry);
                    activity.runOnUiThread(() -> {
                        if (destroyed) return;
                        working = false;
                        preferences.edit().putString("release", entry.toString()).apply();
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
