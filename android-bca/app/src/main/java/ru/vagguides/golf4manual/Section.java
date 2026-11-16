package ru.vagguides.golf4manual;

import java.util.Locale;

public final class Section {
    public final String code;
    public final String slug;
    public final String category;
    public final String title;
    public final int startPage;
    public final int endPage;

    public Section(String code, String slug, String category, String title, int startPage, int endPage) {
        this.code = code;
        this.slug = slug;
        this.category = category;
        this.title = title;
        this.startPage = startPage;
        this.endPage = endPage;
    }

    public int pageCount() {
        return endPage - startPage + 1;
    }

    public boolean containsPage(int page) {
        return page >= startPage && page <= endPage;
    }

    public boolean matches(String query) {
        String needle = query.trim().toLowerCase(Locale.ROOT);
        return needle.isEmpty()
                || code.toLowerCase(Locale.ROOT).contains(needle)
                || slug.toLowerCase(Locale.ROOT).contains(needle)
                || category.toLowerCase(Locale.ROOT).contains(needle)
                || title.toLowerCase(Locale.ROOT).contains(needle);
    }
}
