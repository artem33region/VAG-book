package ru.vagguides.golf4manual;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class ManualSections {
    public static final int TOTAL_PAGES = 0;

    public static final List<Section> ALL = Collections.unmodifiableList(Arrays.asList(
            new Section("BCA", "overview", "Двигатель BCA", "Паспорт двигателя", 0, 0),
            new Section("ТО", "service", "Обслуживание", "Регламент и расходные материалы", 0, 0),
            new Section("ГРМ", "timing", "Механика двигателя", "Два ремня ГРМ и установка фаз", 0, 0),
            new Section("РВ", "camshaft", "Механика двигателя", "Распредвалы и гидрокомпенсаторы", 0, 0),
            new Section("ГБЦ", "cylinder_head", "Механика двигателя", "Головка блока цилиндров", 0, 0),
            new Section("МАСЛО", "lubrication", "Системы двигателя", "Смазка, поддон и масляный насос", 0, 0),
            new Section("ОХЛ", "cooling", "Системы двигателя", "Охлаждение и водяной насос", 0, 0),
            new Section("ВПУСК", "intake", "Обслуживание", "Воздушный фильтр и впуск", 0, 0),
            new Section("MPI", "fuel", "Управление двигателем", "Впрыск и топливная система", 0, 0),
            new Section("ЗАЖ", "ignition", "Управление двигателем", "Катушки зажигания и свечи", 0, 0),
            new Section("EGR", "emissions", "Управление двигателем", "EGR, вентиляция картера и выпуск", 0, 0),
            new Section("ОП", "mounts", "Механика двигателя", "Опоры двигателя", 0, 0),
            new Section("DIAG", "diagnostics", "Диагностика", "Проверки двигателя и электрооборудования", 0, 0),
            new Section("Н·м", "torques", "Справочные данные", "Моменты затяжки BCA", 0, 0)
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
