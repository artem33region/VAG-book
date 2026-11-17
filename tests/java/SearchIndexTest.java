package ru.vagguides.golf4manual;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class SearchIndexTest {
    private static int checks;
    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }
    private static boolean has(SearchIndex.Result result, String slug, int position) {
        for (SearchIndex.Hit hit : result.hits) {
            if (hit.section.slug.equals(slug) && hit.position == position) return true;
        }
        return false;
    }
    private static String decode(String s) {
        return new String(Base64.getDecoder().decode(s), StandardCharsets.UTF_8);
    }
    public static void main(String[] args) throws Exception {
        Section engine = new Section("2B", "engine", "Двигатель BCA", "Механика двигателя", 1, 2);
        Section gearbox = new Section("7B", "automatic", "Трансмиссия", "Автоматическая коробка передач", 3, 4);
        SearchIndex index = new SearchIndex(Arrays.asList(engine, gearbox));
        index.add(engine, 6, "Снимите катушки зажигания и свечи.", "Зажигание");
        index.add(engine, 8, "Проверьте разъём датчика температуры.", "Диагностика");
        index.add(gearbox, 11, "Отсоедините трос блокировки селектора.", "Снятие троса");
        check(has(index.search("свечи"), "engine", 6), "Must search article body, not only section title");
        check(has(index.search("  СВЕЧИ   BCA  "), "engine", 6), "Words, casing and whitespace");
        check(has(index.search("датчика разъем"), "engine", 8), "Yo/e and reversed word order");
        check(has(index.search("РАЗЪЁМ"), "engine", 8), "Uppercase yo");
        check(has(index.search("блокиров"), "automatic", 11), "Word fragment");
        check(has(index.search("7B"), "automatic", 0), "Chapter code");
        check(index.search("7B").total == 1, "Metadata match must not return unrelated body rows");
        check(index.search("неттакогослова").total == 0, "No results");
        check(index.search("свечи селектора").total == 0, "Terms from unrelated articles cannot combine");
        check(index.search("  ").hits.size() == 2, "Clearing restores full catalogue");
        check(index.search("---").hits.size() == 2, "Punctuation only behaves as empty query");
        check(index.search("катушки-зажигания").total == 1, "Punctuation separators");
        SearchIndex.Result first = index.search("свечи");
        index.search("разъем");
        check(first.hits.get(0).position == 6, "Later searches cannot mutate earlier results");
        for (int i = 20; i < 150; i++) index.add(engine, i, "Проверка ремня и ролика " + i, "ГРМ");
        SearchIndex.Result many = index.search("ремня");
        check(many.total == 130 && many.hits.size() == 100, "Result limit and full count");
        check(index.search("свечи").hits.get(0).snippet.contains("свечи"), "Context snippet contains hit");
        check(index.search("свечи").hits.get(0).snippet.length() <= 192, "Bounded snippet length");

        // Real Russian articles exported without altering text or visible row positions.
        List<Section> sections = new ArrayList<>();
        Map<String, Section> bySlug = new HashMap<>();
        List<String[]> documents = new ArrayList<>();
        List<String[]> queries = new ArrayList<>();
        for (String line : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
            String[] fields = line.split("\t", -1);
            if (fields[0].equals("S")) {
                Section s = new Section(decode(fields[2]), fields[1], decode(fields[3]), decode(fields[4]), 0, 0);
                sections.add(s); bySlug.put(s.slug, s);
            } else if (fields[0].equals("D")) documents.add(fields);
            else if (fields[0].equals("Q")) queries.add(fields);
        }
        SearchIndex real = new SearchIndex(sections);
        Map<String, String> textByRow = new HashMap<>();
        for (String[] d : documents) {
            real.add(bySlug.get(d[1]), Integer.parseInt(d[2]), decode(d[3]), decode(d[4]));
            textByRow.put(d[1] + ":" + d[2], decode(d[3]));
        }
        long started = System.nanoTime();
        for (String[] q : queries) {
            String query = decode(q[1]);
            SearchIndex.Result result = real.search(query);
            check(result.total > 0, "Real corpus query returned no results: " + query);
            boolean correct = false;
            for (SearchIndex.Hit hit : result.hits) {
                check(hit.position == 0 || textByRow.containsKey(hit.section.slug + ":" + hit.position), "Invalid reader row");
                if (hit.section.slug.equals(q[2]) && hit.position > 0
                        && SearchIndex.normalize(textByRow.get(hit.section.slug + ":" + hit.position)).contains(SearchIndex.normalize(query))) {
                    correct = true;
                }
            }
            check(correct, "No body match in expected section: " + query);
        }
        check(real.search("zzzz_not_in_any_manual_zzzz").total == 0, "Real no-results query");
        check(real.search("").total == sections.size(), "Real empty query restores catalogue");
        System.out.println(checks + " search checks passed; " + documents.size() + " rows; "
                + (System.nanoTime() - started) / 1_000_000 + " ms for corpus queries");
    }
}
