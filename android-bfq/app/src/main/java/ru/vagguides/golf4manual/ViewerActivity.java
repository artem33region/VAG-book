package ru.vagguides.golf4manual;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.Bundle;
import android.util.LruCache;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ViewerActivity extends Activity {
    public static final String PREFS = "reader_state";
    public static final String KEY_LAST_SLUG = "last_slug";
    public static final String KEY_LAST_POSITION = "last_position";
    public static final String KEY_LAST_OFFSET = "last_offset";

    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_CODE = "code";
    public static final String EXTRA_SLUG = "slug";
    public static final String EXTRA_POSITION = "position";
    public static final String EXTRA_OFFSET = "offset";

    private final ExecutorService ioExecutor = Executors.newFixedThreadPool(2);
    // Accessed only on the UI thread; every visible copy must receive the result.
    private final Map<String, List<ImageView>> loadingAssets = new HashMap<>();
    private final LruCache<String, Bitmap> bitmapCache = new LruCache<String, Bitmap>(16 * 1024) {
        @Override
        protected int sizeOf(String key, Bitmap value) {
            return Math.max(1, value.getByteCount() / 1024);
        }
    };

    private ListView articleList;
    private View loadingPanel;
    private TextView loadingText;
    private ArticleAdapter adapter;
    private String slug;
    private int requestedPosition;
    private int requestedOffset;
    private boolean destroyed;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.setStatusBarColor(Ui.NAVY_DARK);
        window.setNavigationBarColor(Ui.NAVY_DARK);

        String title = getIntent().getStringExtra(EXTRA_TITLE);
        String code = getIntent().getStringExtra(EXTRA_CODE);
        slug = getIntent().getStringExtra(EXTRA_SLUG);
        requestedPosition = savedInstanceState != null
                ? savedInstanceState.getInt(EXTRA_POSITION, 0)
                : getIntent().getIntExtra(EXTRA_POSITION, 0);
        requestedOffset = savedInstanceState != null
                ? savedInstanceState.getInt(EXTRA_OFFSET, 0)
                : getIntent().getIntExtra(EXTRA_OFFSET, 0);

        buildInterface(code, title);
        loadArticle();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        outState.putInt(EXTRA_POSITION, currentPosition());
        outState.putInt(EXTRA_OFFSET, currentOffset());
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onPause() {
        saveReadingPosition();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        ioExecutor.shutdownNow();
        loadingAssets.clear();
        bitmapCache.evictAll();
        super.onDestroy();
    }

    private void buildInterface(String codeValue, String titleValue) {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.PAPER);

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(Ui.dp(this, 8), Ui.dp(this, 7), Ui.dp(this, 14), Ui.dp(this, 7));
        toolbar.setBackgroundColor(Ui.NAVY);

        TextView back = Ui.text(this, "‹", 34, Color.WHITE, false);
        back.setGravity(Gravity.CENTER);
        back.setContentDescription("Назад к разделам");
        back.setOnClickListener(view -> finish());
        toolbar.addView(back, new LinearLayout.LayoutParams(Ui.dp(this, 48), Ui.dp(this, 52)));

        TextView code = Ui.text(this, codeValue == null ? "" : codeValue, 12, Ui.NAVY_DARK, true);
        code.setGravity(Gravity.CENTER);
        code.setBackground(Ui.rounded(Ui.ACCENT, 9, this));
        toolbar.addView(code, new LinearLayout.LayoutParams(Ui.dp(this, 50), Ui.dp(this, 34)));

        TextView title = Ui.text(this, titleValue == null ? "BFQ 1.6" : titleValue, 16, Color.WHITE, true);
        title.setMaxLines(2);
        title.setMinHeight(Ui.dp(this, 52));
        title.setGravity(Gravity.CENTER_VERTICAL);
        title.setPadding(Ui.dp(this, 12), 0, 0, 0);
        toolbar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        root.addView(toolbar);

        TextView mode = Ui.text(
                this,
                "BFQ  ·  РУССКИЙ ТЕКСТ  ·  ФОТО И СХЕМЫ",
                10,
                Ui.BLUE,
                true);
        mode.setLetterSpacing(0.06f);
        mode.setGravity(Gravity.CENTER_VERTICAL);
        mode.setPadding(Ui.dp(this, 18), Ui.dp(this, 9), Ui.dp(this, 18), Ui.dp(this, 9));
        mode.setBackgroundColor(0xFFEAF0F5);
        root.addView(mode, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout stage = new FrameLayout(this);
        articleList = new ListView(this);
        articleList.setDivider(null);
        articleList.setDividerHeight(0);
        articleList.setClipToPadding(false);
        articleList.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 36));
        articleList.setBackgroundColor(Ui.PAPER);
        stage.addView(articleList, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        LinearLayout loading = new LinearLayout(this);
        loading.setOrientation(LinearLayout.VERTICAL);
        loading.setGravity(Gravity.CENTER);
        loading.setPadding(Ui.dp(this, 24), Ui.dp(this, 22), Ui.dp(this, 24), Ui.dp(this, 22));
        loading.setBackground(Ui.rounded(Color.WHITE, 14, this));
        ProgressBar progress = new ProgressBar(this);
        loading.addView(progress, new LinearLayout.LayoutParams(Ui.dp(this, 42), Ui.dp(this, 42)));
        loadingText = Ui.text(this, "Открываю статью…", 14, Ui.INK, true);
        loadingText.setGravity(Gravity.CENTER);
        loadingText.setPadding(0, Ui.dp(this, 12), 0, 0);
        loading.addView(loadingText);
        loadingPanel = loading;
        stage.addView(loading, new FrameLayout.LayoutParams(
                Ui.dp(this, 260),
                Ui.dp(this, 132),
                Gravity.CENTER));
        root.addView(stage, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f));

        setContentView(root);
    }

    private void loadArticle() {
        if (slug == null || slug.trim().isEmpty()) {
            showError("Не указан раздел руководства");
            return;
        }
        ioExecutor.execute(() -> {
            try {
                String json = readAssetText("articles/" + slug + ".json");
                JSONObject root = new JSONObject(json);
                JSONArray rows = root.getJSONArray("blocks");
                List<ArticleBlock> blocks = new ArrayList<>(rows.length());
                for (int index = 0; index < rows.length(); index++) {
                    JSONObject row = rows.getJSONObject(index);
                    String type = row.optString("type", "text");
                    String text = row.optString("text", "").trim();
                    String asset = row.optString("asset", "").trim();
                    String description = row.optString("description", "Иллюстрация из справочника");
                    if ("image".equals(type) ? !asset.isEmpty() : !text.isEmpty()) {
                        blocks.add(new ArticleBlock(type, text, asset, description));
                    }
                }
                runOnUiThread(() -> showArticle(blocks));
            } catch (Exception exception) {
                runOnUiThread(() -> showError("Не удалось открыть статью. Переустановите обновление приложения."));
            }
        });
    }

    private void showArticle(List<ArticleBlock> blocks) {
        if (destroyed) {
            return;
        }
        adapter = new ArticleAdapter(blocks);
        articleList.setAdapter(adapter);
        loadingPanel.setVisibility(View.GONE);
        int safePosition = Math.max(0, Math.min(requestedPosition, Math.max(0, blocks.size() - 1)));
        requestedPosition = safePosition;
        articleList.setSelectionFromTop(safePosition, requestedOffset);
    }

    private void showError(String message) {
        if (destroyed) return;
        loadingPanel.setVisibility(View.VISIBLE);
        View first = ((ViewGroup) loadingPanel).getChildAt(0);
        first.setVisibility(View.GONE);
        loadingText.setText(message);
        loadingText.setTextColor(0xFFC3262D);
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private int currentPosition() {
        return articleList == null || articleList.getChildCount() == 0
                ? requestedPosition : Math.max(0, articleList.getFirstVisiblePosition());
    }

    private int currentOffset() {
        return articleList == null || articleList.getChildCount() == 0
                ? requestedOffset : articleList.getChildAt(0).getTop() - articleList.getPaddingTop();
    }

    private void saveReadingPosition() {
        if (slug == null || adapter == null) {
            return;
        }
        getSharedPreferences(PREFS, MODE_PRIVATE)
                .edit()
                .putString(KEY_LAST_SLUG, slug)
                .putInt(KEY_LAST_POSITION, currentPosition())
                .putInt(KEY_LAST_OFFSET, currentOffset())
                .apply();
    }

    private String readAssetText(String asset) throws Exception {
        try (InputStream input = getAssets().open(asset);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[16 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                output.write(buffer, 0, read);
            }
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        }
    }

    private void loadImage(String asset, ImageView target) {
        if (destroyed) return;
        Bitmap cached = bitmapCache.get(asset);
        target.setTag(asset);
        if (cached != null && !cached.isRecycled()) {
            target.setImageBitmap(cached);
            target.setBackgroundColor(Color.WHITE);
            target.setAlpha(1f);
            return;
        }
        target.setImageDrawable(null);
        target.setBackgroundColor(0xFFE5E3DE);
        target.setAlpha(0.55f);
        List<ImageView> waiting = loadingAssets.get(asset);
        if (waiting != null) {
            if (!waiting.contains(target)) waiting.add(target);
            return;
        }
        waiting = new ArrayList<>();
        waiting.add(target);
        loadingAssets.put(asset, waiting);
        ioExecutor.execute(() -> {
            Bitmap bitmap = null;
            try (InputStream input = getAssets().open(asset)) {
                BitmapFactory.Options options = new BitmapFactory.Options();
                options.inPreferredConfig = Bitmap.Config.RGB_565;
                bitmap = BitmapFactory.decodeStream(input, null, options);
            } catch (Exception ignored) {
                // The placeholder remains visible if an individual image is damaged.
            }
            Bitmap ready = bitmap;
            runOnUiThread(() -> {
                if (destroyed) {
                    if (ready != null) ready.recycle();
                    return;
                }
                List<ImageView> targets = loadingAssets.remove(asset);
                if (ready != null) {
                    bitmapCache.put(asset, ready);
                    if (targets == null) return;
                    for (ImageView view : targets) {
                        if (asset.equals(view.getTag())) {
                            view.setImageBitmap(ready);
                            view.setBackgroundColor(Color.WHITE);
                            view.setAlpha(1f);
                        }
                    }
                }
            });
        });
    }

    private final class ArticleAdapter extends BaseAdapter {
        private static final int TYPE_TEXT = 0;
        private static final int TYPE_HEADING = 1;
        private static final int TYPE_CAPTION = 2;
        private static final int TYPE_NOTE = 3;
        private static final int TYPE_IMAGE = 4;

        private final List<ArticleBlock> blocks;

        ArticleAdapter(List<ArticleBlock> blocks) {
            this.blocks = blocks;
        }

        @Override public int getCount() { return blocks.size(); }
        @Override public ArticleBlock getItem(int position) { return blocks.get(position); }
        @Override public long getItemId(int position) { return position; }
        @Override public int getViewTypeCount() { return 5; }

        @Override
        public int getItemViewType(int position) {
            String type = getItem(position).type;
            if ("heading".equals(type)) return TYPE_HEADING;
            if ("caption".equals(type)) return TYPE_CAPTION;
            if ("note".equals(type)) return TYPE_NOTE;
            if ("image".equals(type)) return TYPE_IMAGE;
            return TYPE_TEXT;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            ArticleBlock block = getItem(position);
            int type = getItemViewType(position);
            if (type == TYPE_IMAGE) {
                ImageHolder holder;
                if (convertView == null) {
                    LinearLayout card = new LinearLayout(ViewerActivity.this);
                    card.setOrientation(LinearLayout.VERTICAL);
                    card.setPadding(Ui.dp(ViewerActivity.this, 14), Ui.dp(ViewerActivity.this, 10),
                            Ui.dp(ViewerActivity.this, 14), Ui.dp(ViewerActivity.this, 13));
                    card.setBackgroundColor(Color.WHITE);
                    card.setLayoutParams(new AbsListView.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.WRAP_CONTENT));

                    ImageView image = new ImageView(ViewerActivity.this);
                    image.setAdjustViewBounds(true);
                    image.setScaleType(ImageView.ScaleType.FIT_CENTER);
                    image.setMinimumHeight(Ui.dp(ViewerActivity.this, 150));
                    card.addView(image, new LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.WRAP_CONTENT));

                    TextView hint = Ui.text(ViewerActivity.this, "Нажмите, чтобы увеличить", 11, Ui.MUTED, false);
                    hint.setGravity(Gravity.CENTER);
                    hint.setPadding(0, Ui.dp(ViewerActivity.this, 7), 0, 0);
                    card.addView(hint);
                    holder = new ImageHolder(image);
                    card.setTag(holder);
                    convertView = card;
                } else {
                    holder = (ImageHolder) convertView.getTag();
                }
                holder.image.setContentDescription(block.description);
                holder.image.setOnClickListener(view -> {
                    Intent intent = new Intent(ViewerActivity.this, ImageActivity.class);
                    intent.putExtra(ImageActivity.EXTRA_ASSET, block.asset);
                    intent.putExtra(ImageActivity.EXTRA_DESCRIPTION, block.description);
                    startActivity(intent);
                });
                loadImage(block.asset, holder.image);
                return convertView;
            }

            TextView text;
            if (convertView == null) {
                FrameLayout shell = new FrameLayout(ViewerActivity.this);
                shell.setPadding(Ui.dp(ViewerActivity.this, 16), Ui.dp(ViewerActivity.this, 4),
                        Ui.dp(ViewerActivity.this, 16), Ui.dp(ViewerActivity.this, 4));
                shell.setLayoutParams(new AbsListView.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT));
                text = Ui.text(ViewerActivity.this, "", 16, Ui.INK, false);
                text.setTextIsSelectable(true);
                text.setLineSpacing(Ui.dp(ViewerActivity.this, 2), 1.08f);
                shell.addView(text, new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT));
                shell.setTag(text);
                convertView = shell;
            } else {
                text = (TextView) convertView.getTag();
            }

            if (type == TYPE_HEADING) {
                text.setTextSize(20);
                text.setTextColor(Ui.NAVY_DARK);
                text.setTypeface(text.getTypeface(), android.graphics.Typeface.BOLD);
                text.setPadding(Ui.dp(ViewerActivity.this, 2), Ui.dp(ViewerActivity.this, 12),
                        Ui.dp(ViewerActivity.this, 2), Ui.dp(ViewerActivity.this, 7));
                text.setBackgroundColor(Color.TRANSPARENT);
            } else if (type == TYPE_NOTE) {
                text.setTextSize(15);
                text.setTextColor(Ui.NAVY_DARK);
                text.setTypeface(text.getTypeface(), android.graphics.Typeface.BOLD);
                text.setPadding(Ui.dp(ViewerActivity.this, 14), Ui.dp(ViewerActivity.this, 12),
                        Ui.dp(ViewerActivity.this, 14), Ui.dp(ViewerActivity.this, 12));
                text.setBackground(Ui.outlined(0xFFFFF6D9, 0xFFE2C15C, 11, ViewerActivity.this));
            } else if (type == TYPE_CAPTION) {
                text.setTextSize(14);
                text.setTextColor(Ui.MUTED);
                text.setTypeface(text.getTypeface(), android.graphics.Typeface.ITALIC);
                text.setPadding(Ui.dp(ViewerActivity.this, 12), Ui.dp(ViewerActivity.this, 5),
                        Ui.dp(ViewerActivity.this, 12), Ui.dp(ViewerActivity.this, 9));
                text.setBackgroundColor(0xFFF0EFEB);
            } else {
                text.setTextSize(16);
                text.setTextColor(Ui.INK);
                text.setTypeface(text.getTypeface(), android.graphics.Typeface.NORMAL);
                text.setPadding(Ui.dp(ViewerActivity.this, 2), Ui.dp(ViewerActivity.this, 7),
                        Ui.dp(ViewerActivity.this, 2), Ui.dp(ViewerActivity.this, 9));
                text.setBackgroundColor(Color.TRANSPARENT);
            }
            text.setText(block.text);
            return convertView;
        }
    }

    private static final class ImageHolder {
        final ImageView image;

        ImageHolder(ImageView image) {
            this.image = image;
        }
    }

    private static final class ArticleBlock {
        final String type;
        final String text;
        final String asset;
        final String description;

        ArticleBlock(String type, String text, String asset, String description) {
            this.type = type;
            this.text = text;
            this.asset = asset;
            this.description = description;
        }
    }
}
