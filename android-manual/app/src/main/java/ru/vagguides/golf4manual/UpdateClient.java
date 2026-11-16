package ru.vagguides.golf4manual;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** The manual and automatic checks use the same endpoint and validation. */
public final class UpdateClient {
    private UpdateClient() { }

    public static UpdateInfo parseRelease(String packageName, JSONObject value) throws Exception {
        return new UpdateInfo(packageName, value.getString("packageName"), value.getLong("versionCode"),
                value.getString("versionName"), value.getString("url"), value.getString("sha256"), value.getLong("size"));
    }

    public static JSONObject fetchRelease(String packageName) throws Exception {
        JSONObject manifest = new JSONObject(fetchManifest());
        if (manifest.getInt("schemaVersion") != 1) throw new IllegalArgumentException("Unsupported schema");
        JSONObject entry = manifest.getJSONObject("apps").getJSONObject(packageName);
        parseRelease(packageName, entry);
        return entry;
    }

    private static String fetchManifest() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(UpdateInfo.MANIFEST_URL).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setInstanceFollowRedirects(false);
        connection.setUseCaches(false);
        connection.setRequestProperty("Cache-Control", "no-cache");
        try {
            if (connection.getResponseCode() != 200) throw new IllegalStateException("Manifest unavailable");
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (output.size() + count > 64 * 1024) throw new IllegalStateException("Manifest too large");
                    output.write(buffer, 0, count);
                }
                return new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
        } finally {
            connection.disconnect();
        }
    }
}
