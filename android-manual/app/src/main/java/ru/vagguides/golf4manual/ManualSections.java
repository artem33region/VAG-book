package ru.vagguides.golf4manual;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class ManualSections {
    public static final int TOTAL_PAGES = 388;

    public static final List<Section> ALL = Collections.unmodifiableList(Arrays.asList(
            new Section("00", "about", "О книге", "Обзор моделей и введение", 3, 8),
            new Section("0.1", "roadside", "В дороге", "Ремонт в пути", 9, 12),
            new Section("0.2", "weekly", "В дороге", "Еженедельные проверки", 13, 19),

            new Section("1A", "maintenance_petrol", "Обслуживание", "Бензиновые модели", 21, 40),
            new Section("1B", "maintenance_diesel", "Обслуживание", "Дизельные модели", 41, 58),

            new Section("2A", "engine_sohc", "Двигатель", "Бензиновый двигатель SOHC", 59, 78),
            new Section("2B", "engine_dohc", "Двигатель", "Бензиновый двигатель DOHC", 79, 110),
            new Section("2C", "engine_diesel", "Двигатель", "Дизельный двигатель", 111, 132),
            new Section("2D", "engine_overhaul", "Двигатель", "Снятие и капитальный ремонт двигателя", 133, 160),
            new Section("3", "cooling", "Системы двигателя", "Охлаждение, отопление и кондиционер", 161, 172),

            new Section("4A", "fuel_petrol", "Питание и выпуск", "Топливная система бензиновых двигателей", 173, 190),
            new Section("4B", "fuel_diesel", "Питание и выпуск", "Топливная система дизельных двигателей", 191, 204),
            new Section("4C", "emissions_petrol", "Питание и выпуск", "Снижение токсичности и выпуск — бензин", 205, 218),
            new Section("4D", "emissions_diesel", "Питание и выпуск", "Снижение токсичности и выпуск — дизель", 219, 226),

            new Section("5A", "starting", "Электрооборудование", "Системы запуска и зарядки", 227, 232),
            new Section("5B", "ignition", "Электрооборудование", "Зажигание бензиновых двигателей", 233, 236),
            new Section("5C", "preheating", "Электрооборудование", "Предпусковой подогрев дизеля", 237, 238),

            new Section("6", "clutch", "Трансмиссия", "Сцепление", 239, 246),
            new Section("7A", "manual_transmission", "Трансмиссия", "Механическая коробка передач", 247, 252),
            new Section("7B", "automatic_transmission", "Трансмиссия", "Автоматическая коробка передач", 253, 256),
            new Section("8", "driveshafts", "Трансмиссия", "Приводные валы и ШРУСы", 257, 264),

            new Section("9", "brakes", "Ходовая часть", "Тормозная система", 265, 278),
            new Section("10", "suspension", "Ходовая часть", "Подвеска и рулевое управление", 279, 302),
            new Section("11", "bodywork", "Кузов", "Кузов и наружное оборудование", 303, 328),
            new Section("12", "body_electrical", "Кузов", "Электрооборудование кузова", 329, 347),
            new Section("12W", "wiring", "Схемы", "Электрические схемы", 348, 356),

            new Section("REF", "reference", "Справочник", "Данные, инструмент и общие приёмы", 357, 363),
            new Section("MOT", "inspection", "Справочник", "Проверка технического состояния", 364, 367),
            new Section("DIAG", "diagnostics", "Справочник", "Поиск неисправностей", 368, 374),
            new Section("GLO", "glossary", "Справочник", "Словарь технических терминов", 375, 379),
            new Section("IDX", "index", "Справочник", "Предметный указатель", 380, 383)
    ));

    private ManualSections() {
    }

    public static Section forPage(int page) {
        for (Section section : ALL) {
            if (section.containsPage(page)) {
                return section;
            }
        }
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
