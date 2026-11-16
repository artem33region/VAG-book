package ru.vagguides.golf4manual;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class MainActivity extends Activity {
    private SectionAdapter adapter;
    private TextView sectionCount;
    private LinearLayout continueCard;
    private TextView continueTitle;
    private TextView continueMeta;
    private TextView updates;
    private AutoUpdateChecker updateChecker;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.setStatusBarColor(Ui.NAVY_DARK);
        window.setNavigationBarColor(Ui.NAVY_DARK);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.PAPER);

        LinearLayout hero = buildHero();
        root.addView(hero, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout catalogueHeader = new LinearLayout(this);
        catalogueHeader.setGravity(Gravity.CENTER_VERTICAL);
        catalogueHeader.setPadding(Ui.dp(this, 18), Ui.dp(this, 14), Ui.dp(this, 18), Ui.dp(this, 8));
        TextView catalogueTitle = Ui.text(this, "Разделы двигателя", 18, Ui.INK, true);
        sectionCount = Ui.text(this, "", 12, Ui.MUTED, false);
        sectionCount.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        catalogueHeader.addView(catalogueTitle, new LinearLayout.LayoutParams(0, Ui.dp(this, 30), 1f));
        catalogueHeader.addView(sectionCount, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Ui.dp(this, 30)));
        root.addView(catalogueHeader);

        ListView list = new ListView(this);
        list.setDivider(null);
        list.setDividerHeight(0);
        list.setClipToPadding(false);
        list.setPadding(Ui.dp(this, 12), 0, Ui.dp(this, 12), Ui.dp(this, 16));
        list.setBackgroundColor(Color.TRANSPARENT);
        list.setScrollBarStyle(View.SCROLLBARS_INSIDE_OVERLAY);
        adapter = new SectionAdapter();
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> openSection(adapter.getItem(position), 0));
        root.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f));

        setContentView(root);
        updateSectionCount();
        updateChecker = new AutoUpdateChecker(this, release -> updates.setText(release == null
                ? getString(R.string.updates_button)
                : getString(R.string.update_available_automatic, release.versionName)));
    }

    @Override
    protected void onResume() {
        super.onResume();
        updateContinueCard();
        updateChecker.checkIfDue();
    }

    @Override
    protected void onDestroy() {
        if (updateChecker != null) updateChecker.close();
        super.onDestroy();
    }

    private LinearLayout buildHero() {
        LinearLayout hero = new LinearLayout(this);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setPadding(Ui.dp(this, 20), Ui.dp(this, 18), Ui.dp(this, 20), Ui.dp(this, 18));
        GradientDrawable background = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{Ui.NAVY_DARK, Ui.NAVY, Ui.BLUE});
        hero.setBackground(background);

        TextView eyebrow = Ui.text(this, "СПРАВОЧНИК ПО ДВИГАТЕЛЮ", 11, Ui.ACCENT, true);
        eyebrow.setLetterSpacing(0.08f);
        hero.addView(eyebrow, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView title = Ui.text(this, "VW BFQ 1.6", 28, Color.WHITE, true);
        title.setPadding(0, Ui.dp(this, 3), 0, Ui.dp(this, 3));
        hero.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView subtitle = Ui.text(
                this,
                "102 л. с. · Simos 3.3 · русский текст · фото и схемы",
                13,
                0xFFD8E4EF,
                false);
        subtitle.setLineSpacing(0f, 1.08f);
        hero.addView(subtitle, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        updates = Ui.text(this, getString(R.string.updates_button), 15, Ui.ACCENT, true);
        updates.setGravity(Gravity.CENTER_VERTICAL);
        updates.setMinHeight(Ui.dp(this, 48));
        updates.setOnClickListener(view -> startActivity(new Intent(this, UpdateActivity.class)));
        hero.addView(updates, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 48)));

        continueCard = new LinearLayout(this);
        continueCard.setOrientation(LinearLayout.VERTICAL);
        continueCard.setPadding(Ui.dp(this, 14), Ui.dp(this, 10), Ui.dp(this, 14), Ui.dp(this, 10));
        continueCard.setBackground(Ui.outlined(0x22FFFFFF, 0x55FFFFFF, 12, this));
        continueCard.setVisibility(View.GONE);
        continueTitle = Ui.text(this, "", 14, Color.WHITE, true);
        continueMeta = Ui.text(this, "", 12, 0xFFD8E4EF, false);
        continueCard.addView(continueTitle);
        continueCard.addView(continueMeta);
        LinearLayout.LayoutParams continueParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        continueParams.topMargin = Ui.dp(this, 14);
        hero.addView(continueCard, continueParams);

        EditText search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Поиск: ГРМ, масло, зажигание…");
        search.setHintTextColor(0xFF72808C);
        search.setTextColor(Ui.INK);
        search.setTextSize(14);
        search.setPadding(Ui.dp(this, 15), 0, Ui.dp(this, 15), 0);
        search.setBackground(Ui.rounded(Color.WHITE, 12, this));
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (adapter != null) {
                    adapter.filter(s.toString());
                    updateSectionCount();
                }
            }
            @Override public void afterTextChanged(Editable s) { }
        });
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                Ui.dp(this, 48));
        searchParams.topMargin = Ui.dp(this, 14);
        hero.addView(search, searchParams);
        return hero;
    }

    private void updateContinueCard() {
        SharedPreferences preferences = getSharedPreferences(ViewerActivity.PREFS, MODE_PRIVATE);
        String slug = preferences.getString(ViewerActivity.KEY_LAST_SLUG, null);
        if (slug == null) {
            continueCard.setVisibility(View.GONE);
            return;
        }
        int position = Math.max(0, preferences.getInt(ViewerActivity.KEY_LAST_POSITION, 0));
        Section section = ManualSections.forSlug(slug);
        if (!slug.equals(section.slug)) {
            continueCard.setVisibility(View.GONE);
            return;
        }
        continueTitle.setText(String.format(
                Locale.getDefault(),
                "Продолжить: %s",
                section.title));
        continueMeta.setText(String.format(
                Locale.getDefault(),
                "Продолжить чтение статьи  ›"));
        int offset = preferences.getInt(ViewerActivity.KEY_LAST_OFFSET, 0);
        continueCard.setOnClickListener(view -> openSection(section, position, offset));
        continueCard.setVisibility(View.VISIBLE);
    }

    private void updateSectionCount() {
        if (adapter != null && sectionCount != null) {
            sectionCount.setText(sectionCountLabel(adapter.getCount()));
        }
    }

    private static String sectionCountLabel(int count) {
        int lastTwo = Math.abs(count) % 100;
        int last = lastTwo % 10;
        String form;
        if (lastTwo >= 11 && lastTwo <= 14) {
            form = "разделов";
        } else if (last == 1) {
            form = "раздел";
        } else if (last >= 2 && last <= 4) {
            form = "раздела";
        } else {
            form = "разделов";
        }
        return String.format(Locale.getDefault(), "%d %s", count, form);
    }

    private void openSection(Section section, int position) {
        openSection(section, position, 0);
    }

    private void openSection(Section section, int position, int offset) {
        Intent intent = new Intent(this, ViewerActivity.class);
        intent.putExtra(ViewerActivity.EXTRA_TITLE, section.title);
        intent.putExtra(ViewerActivity.EXTRA_CODE, section.code);
        intent.putExtra(ViewerActivity.EXTRA_SLUG, section.slug);
        intent.putExtra(ViewerActivity.EXTRA_POSITION, Math.max(0, position));
        intent.putExtra(ViewerActivity.EXTRA_OFFSET, offset);
        startActivity(intent);
    }

    private final class SectionAdapter extends BaseAdapter {
        private final List<Section> visible = new ArrayList<>(ManualSections.ALL);

        void filter(String query) {
            visible.clear();
            for (Section section : ManualSections.ALL) {
                if (section.matches(query)) {
                    visible.add(section);
                }
            }
            notifyDataSetChanged();
        }

        @Override public int getCount() { return visible.size(); }
        @Override public Section getItem(int position) { return visible.get(position); }
        @Override public long getItemId(int position) { return position; }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            RowHolder holder;
            if (convertView == null) {
                FrameLayout shell = new FrameLayout(MainActivity.this);
                shell.setPadding(0, 0, 0, Ui.dp(MainActivity.this, 9));
                shell.setLayoutParams(new AbsListView.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT));

                LinearLayout row = new LinearLayout(MainActivity.this);
                row.setGravity(Gravity.CENTER_VERTICAL);
                row.setPadding(Ui.dp(MainActivity.this, 12), Ui.dp(MainActivity.this, 12),
                        Ui.dp(MainActivity.this, 12), Ui.dp(MainActivity.this, 12));
                row.setBackground(Ui.outlined(Color.WHITE, 0xFFE0DDD5, 14, MainActivity.this));
                shell.addView(row, new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT));

                TextView code = Ui.text(MainActivity.this, "", 14, Color.WHITE, true);
                code.setGravity(Gravity.CENTER);
                code.setBackground(Ui.rounded(Ui.BLUE, 12, MainActivity.this));
                row.addView(code, new LinearLayout.LayoutParams(
                        Ui.dp(MainActivity.this, 52),
                        Ui.dp(MainActivity.this, 52)));

                LinearLayout copy = new LinearLayout(MainActivity.this);
                copy.setOrientation(LinearLayout.VERTICAL);
                copy.setPadding(Ui.dp(MainActivity.this, 13), 0, Ui.dp(MainActivity.this, 8), 0);
                TextView category = Ui.text(MainActivity.this, "", 10, Ui.BLUE, true);
                category.setLetterSpacing(0.08f);
                TextView name = Ui.text(MainActivity.this, "", 15, Ui.INK, true);
                name.setMaxLines(2);
                TextView meta = Ui.text(MainActivity.this, "", 12, Ui.MUTED, false);
                copy.addView(category, new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
                copy.addView(name, new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
                copy.addView(meta, new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
                row.addView(copy, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

                TextView arrow = Ui.text(MainActivity.this, "›", 30, Ui.MUTED, false);
                arrow.setGravity(Gravity.CENTER);
                row.addView(arrow, new LinearLayout.LayoutParams(
                        Ui.dp(MainActivity.this, 24),
                        Ui.dp(MainActivity.this, 52)));

                holder = new RowHolder(code, category, name, meta);
                shell.setTag(holder);
                convertView = shell;
            } else {
                holder = (RowHolder) convertView.getTag();
            }

            Section section = getItem(position);
            holder.code.setText(section.code);
            holder.code.setTextSize(section.code.length() > 4 ? 11 : section.code.length() > 3 ? 12 : 14);
            holder.category.setText(section.category.toUpperCase(Locale.getDefault()));
            holder.name.setText(section.title);
            holder.meta.setText(String.format(
                    Locale.getDefault(),
                    "Инструкции · фото · схемы"));
            return convertView;
        }
    }

    private static final class RowHolder {
        final TextView code;
        final TextView category;
        final TextView name;
        final TextView meta;

        RowHolder(TextView code, TextView category, TextView name, TextView meta) {
            this.code = code;
            this.category = category;
            this.name = name;
            this.meta = meta;
        }
    }
}
