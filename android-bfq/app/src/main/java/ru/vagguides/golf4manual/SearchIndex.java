package ru.vagguides.golf4manual;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Offline article search. No Android dependencies; positions refer to visible reader rows. */
public final class SearchIndex {
    public static final int LIMIT = 100;

    public static final class Hit {
        public final Section section;
        public final int position;
        public final String snippet;

        public Hit(Section section, int position, String snippet) {
            this.section = section;
            this.position = position;
            this.snippet = snippet;
        }
    }

    public static final class Result {
        public final List<Hit> hits;
        public final int total;

        Result(List<Hit> hits, int total) {
            this.hits = Collections.unmodifiableList(hits);
            this.total = total;
        }
    }

    private static final class Entry {
        final Section section;
        final int position;
        final String text;
        final String normalized;
        final String context;

        Entry(Section section, int position, String text, String heading) {
            this.section = section;
            this.position = position;
            this.text = text;
            normalized = normalize(text);
            context = normalize(metadata(section) + " " + heading);
        }
    }

    private final List<Section> sections;
    private final List<Entry> entries = new ArrayList<>();

    public SearchIndex(List<Section> sections) {
        this.sections = new ArrayList<>(sections);
    }

    public void add(Section section, int position, String text, String heading) {
        if (position < 0) throw new IllegalArgumentException("Negative reader position");
        if (!text.trim().isEmpty()) entries.add(new Entry(section, position, text, heading));
    }

    public static String normalize(String value) {
        String lower = value.toLowerCase(Locale.ROOT).replace('ё', 'е');
        StringBuilder result = new StringBuilder(lower.length());
        for (int i = 0; i < lower.length(); i++) {
            char c = lower.charAt(i);
            result.append(Character.isLetterOrDigit(c) ? c : ' ');
        }
        return result.toString();
    }

    private static String metadata(Section section) {
        return section.code + " " + section.slug + " " + section.category + " " + section.title;
    }

    public static boolean isEmptyQuery(String query) {
        return normalize(query).trim().isEmpty();
    }

    public Result search(String query) {
        String normalized = normalize(query).trim();
        List<Hit> hits = new ArrayList<>();
        if (normalized.isEmpty()) {
            for (Section section : sections) hits.add(new Hit(section, 0, ""));
            return new Result(hits, hits.size());
        }
        String[] words = normalized.split("\\s+");
        Set<String> found = new HashSet<>();
        int total = 0;
        for (Section section : sections) {
            if (matches(normalize(metadata(section)), "", words)) {
                found.add(section.slug + ":0");
                total++;
                if (hits.size() < LIMIT) hits.add(new Hit(section, 0, "Открыть раздел с начала"));
            }
        }
        for (Entry entry : entries) {
            if (Thread.currentThread().isInterrupted()) break;
            if (!matches(entry.normalized, entry.context, words)) continue;
            // A section title match must not make every unrelated paragraph a hit.
            boolean inText = false;
            for (String word : words) if (entry.normalized.contains(word)) { inText = true; break; }
            if (!inText || !found.add(entry.section.slug + ":" + entry.position)) continue;
            total++;
            if (hits.size() < LIMIT) hits.add(new Hit(entry.section, entry.position, snippet(entry, words)));
        }
        return new Result(hits, total);
    }

    private static boolean matches(String text, String context, String[] words) {
        for (String word : words) if (!text.contains(word) && !context.contains(word)) return false;
        return true;
    }

    private static String snippet(Entry entry, String[] words) {
        int first = entry.text.length();
        for (String word : words) {
            int at = entry.normalized.indexOf(word);
            if (at >= 0) first = Math.min(first, at);
        }
        int start = Math.max(0, Math.min(first - 45, entry.text.length()));
        int end = Math.min(entry.text.length(), start + 190);
        return (start > 0 ? "…" : "") + entry.text.substring(start, end).replaceAll("\\s+", " ").trim()
                + (end < entry.text.length() ? "…" : "");
    }
}
