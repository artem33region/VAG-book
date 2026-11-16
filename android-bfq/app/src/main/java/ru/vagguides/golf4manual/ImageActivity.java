package ru.vagguides.golf4manual;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.io.InputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ImageActivity extends Activity {
    public static final String EXTRA_ASSET = "asset";
    public static final String EXTRA_DESCRIPTION = "description";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private ZoomImageView image;
    private ProgressBar progress;
    private Bitmap bitmap;
    private boolean destroyed;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.setStatusBarColor(Ui.NAVY_DARK);
        window.setNavigationBarColor(Ui.NAVY_DARK);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFF20262D);
        image = new ZoomImageView(this);
        image.setContentDescription(getIntent().getStringExtra(EXTRA_DESCRIPTION));
        root.addView(image, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        TextView back = Ui.text(this, "‹", 38, Color.WHITE, false);
        back.setGravity(Gravity.CENTER);
        back.setContentDescription("Вернуться к статье");
        back.setBackground(Ui.rounded(0xCC19324A, 24, this));
        back.setOnClickListener(view -> finish());
        FrameLayout.LayoutParams backParams = new FrameLayout.LayoutParams(
                Ui.dp(this, 48), Ui.dp(this, 48), Gravity.START | Gravity.TOP);
        backParams.setMargins(Ui.dp(this, 12), Ui.dp(this, 12), 0, 0);
        root.addView(back, backParams);

        progress = new ProgressBar(this);
        root.addView(progress, new FrameLayout.LayoutParams(
                Ui.dp(this, 48), Ui.dp(this, 48), Gravity.CENTER));
        setContentView(root);
        loadImage();
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        executor.shutdownNow();
        image.setImageDrawable(null);
        if (bitmap != null && !bitmap.isRecycled()) {
            bitmap.recycle();
        }
        super.onDestroy();
    }

    private void loadImage() {
        String asset = getIntent().getStringExtra(EXTRA_ASSET);
        if (asset == null) {
            finish();
            return;
        }
        executor.execute(() -> {
            Bitmap loaded = null;
            try (InputStream input = getAssets().open(asset)) {
                loaded = BitmapFactory.decodeStream(input);
            } catch (Exception ignored) {
                // The activity simply closes if the selected asset is unavailable.
            }
            Bitmap ready = loaded;
            runOnUiThread(() -> {
                // Destruction may happen after decoding but before this callback.
                if (destroyed) {
                    if (ready != null) ready.recycle();
                    return;
                }
                progress.setVisibility(android.view.View.GONE);
                if (ready == null) {
                    finish();
                    return;
                }
                bitmap = ready;
                image.setImageBitmap(ready);
            });
        });
    }
}
