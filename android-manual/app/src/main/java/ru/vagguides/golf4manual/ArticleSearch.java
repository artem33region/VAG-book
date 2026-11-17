package ru.vagguides.golf4manual;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Owns one activity's async search work. Stale callbacks cannot replace a newer query. */
public final class ArticleSearch {
    public interface Listener {
        void onResult(SearchIndex.Result result);
        void onError();
    }

    private final Context context;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private SearchIndex index;
    private Future<?> pending;
    private Runnable delayed;
    private long generation;
    private boolean closed;

    public ArticleSearch(Context context) {
        this.context = context.getApplicationContext();
    }

    public void search(String query, Listener listener) {
        final long request = ++generation;
        if (delayed != null) handler.removeCallbacks(delayed);
        if (pending != null) pending.cancel(true);
        if (closed) return;
        if (SearchIndex.isEmptyQuery(query)) {
            listener.onResult(new SearchIndex(ManualSections.ALL).search(""));
            return;
        }
        delayed = () -> pending = executor.submit(() -> {
            try {
                if (index == null) index = load();
                SearchIndex.Result result = index.search(query);
                handler.post(() -> { if (!closed && request == generation) listener.onResult(result); });
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            } catch (Exception error) {
                handler.post(() -> { if (!closed && request == generation) listener.onError(); });
            }
        });
        handler.postDelayed(delayed, 180);
    }

    private SearchIndex load() throws Exception {
        SearchIndex loaded = new SearchIndex(ManualSections.ALL);
        for (Section section : ManualSections.ALL) {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
            String json;
            try (InputStream input = context.getAssets().open("articles/" + section.slug + ".json");
                 ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[16384];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
                    output.write(buffer, 0, count);
                }
                json = new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
            JSONArray rows = new JSONObject(json).getJSONArray("blocks");
            int position = 0;
            String heading = "";
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.getJSONObject(i);
                String type = row.optString("type", "text");
                String text = row.optString("text", "").trim();
                boolean image = "image".equals(type);
                // Exactly the same visibility rule as ViewerActivity.loadArticle().
                if (image ? row.optString("asset", "").trim().isEmpty() : text.isEmpty()) continue;
                if ("heading".equals(type)) heading = text;
                loaded.add(section, position, image ? row.optString("description", "") : text, heading);
                position++;
            }
        }
        return loaded;
    }

    public void close() {
        closed = true;
        generation++;
        if (delayed != null) handler.removeCallbacks(delayed);
        if (pending != null) pending.cancel(true);
        executor.shutdownNow();
    }
}
