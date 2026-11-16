package ru.vagguides.golf4manual;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class ManualSections {
    public static final int TOTAL_PAGES = 0;

    public static final List<Section> ALL = Collections.unmodifiableList(Arrays.asList(
            new Section("BFQ", "overview", "Двигатель BFQ", "Паспорт двигателя", 0, 0),
            new Section("ТО", "service", "Обслуживание", "Регламент и расходные материалы", 0, 0),
            new Section("ГРМ", "timing", "Механика двигателя", "Ремень ГРМ и установка фаз", 0, 0),
            new Section("РВ", "camshaft", "Механика двигателя", "Распредвал, коромысла и гидроопоры", 0, 0),
            new Section("ГБЦ", "cylinder_head", "Механика двигателя", "Головка блока цилиндров", 0, 0),
            new Section("МАСЛО", "lubrication", "Системы двигателя", "Смазка, поддон и масляный насос", 0, 0),
            new Section("ОХЛ", "cooling", "Системы двигателя", "Охлаждение и насос", 0, 0),
            new Section("MPI", "fuel", "Управление двигателем", "Впрыск, впуск и топливо", 0, 0),
            new Section("DIS", "ignition", "Управление двигателем", "Зажигание и свечи", 0, 0),
            new Section("EGR", "emissions", "Управление двигателем", "EGR, вторичный воздух и выпуск", 0, 0),
            new Section("ОП", "mounts", "Механика двигателя", "Опоры двигателя", 0, 0),
            new Section("DIAG", "diagnostics", "Диагностика", "Алгоритмы поиска неисправностей", 0, 0),
            new Section("Н·м", "torques", "Справочные данные", "Моменты затяжки BFQ", 0, 0),
            new Section("ЭЛ", "wiring", "Справочные данные", "Схема Simos 1.6", 0, 0)
    ));

    private ManualSections() {
    }

    public static Section forPage(int page) {
        return ALL.get(0);
    }

    public static Section forSlug(String slug) {
        if (slug != null) {
            for (Section section : ALL) {
                if (section.slug.equals(slug)) {
                    return section;
                }
            }
        }
        return ALL.get(0);
    }
}
