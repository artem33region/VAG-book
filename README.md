# VAG-book

Два автономных Android-справочника: VW Golf IV / Bora и двигатель BFQ 1.6.
Статьи и иллюстрации доступны без интернета. На главном экране есть кнопка
**«Обновления»** для проверки, загрузки и установки новой версии.

## Скачать

- [Golf IV / Bora 6.0](https://raw.githubusercontent.com/artem33region/VAG-book/main/releases/golf4-6.apk)
- [BFQ 1.6 5.0](https://raw.githubusercontent.com/artem33region/VAG-book/main/releases/bfq-5.apk)

Эту версию нужно один раз установить поверх прежнего APK. Следующие версии
можно получать через кнопку «Обновления». Приложения имеют разные package ID
и устанавливаются рядом. Android 6.0 (API 23) или новее.

## Как работают обновления

Приложение читает [updates.json](updates.json), выбирает запись своего package ID
и сравнивает числовой `versionCode`. Более старая или равная версия не предлагается.
Автопроверка выполняется при запуске и возвращении на главный экран: после
успешного запроса — не чаще раза в сутки, после ошибки — не чаще раза в час.
После установки новой версии проверка выполняется сразу при следующем запуске.
Если найдено обновление, на главном экране появляется строка «Доступна версия …».
Результат сохраняется между запусками, ошибки сети не показываются и не мешают чтению.
Когда приложение закрыто, фоновые проверки по расписанию не запускаются.
Ручная проверка на экране «Обновления» доступна в любое время без ожидания интервала.
Загрузка запускается отдельно по кнопке и продолжается через системный DownloadManager.

После загрузки проверяются размер, SHA-256, package ID, версия APK и сертификат
подписи. Установка запускается только после нажатия «Установить обновление».
Если требуется, открывается системное разрешение установки из этого приложения.
Установку подтверждает пользователь в интерфейсе Android. Отключение интернета
не мешает читать справочник.

Используются [DownloadManager](https://developer.android.com/reference/android/app/DownloadManager)
и [разрешение установки пакетов](https://developer.android.com/reference/android/content/pm/PackageManager#canRequestPackageInstalls()).

## Сборка

Нужны JDK 17 или 21, Android SDK Platform 34 и Build Tools 34.0.0.
Укажите путь SDK через `ANDROID_HOME` или локальный `local.properties`.
Gradle Wrapper включён в каждый проект.

```powershell
cd android-manual
.\gradlew.bat :app:lintDebug :app:assembleDebug
cd ../android-bfq
.\gradlew.bat :app:lintDebug :app:assembleDebug
cd ..
```

При офлайн-сборке с уже заполненным кешем используйте `--offline`.
Если в кеше нет Maven-версии AAPT2, можно добавить параметр
`-Pandroid.aapt2FromMavenOverride=<путь SDK>/build-tools/34.0.0/aapt2.exe`.

APK создаются в `<проект>/app/build/outputs/apk/debug/`.
Текущие сборки подписаны существующим локальным Android Debug-ключом.
Для обновления уже установленных приложений нужно сохранять именно этот ключ;
новый автоматически созданный debug-ключ другого компьютера не подходит.
Ключи, локальные настройки SDK, кеши и модели исключены через `.gitignore`.

## Выпуск следующего обновления

1. Увеличьте `versionCode` и `versionName` изменённого приложения в `app/build.gradle`.
2. Соберите оба проекта и выполните проверки. Используйте прежний ключ подписи.
3. Из корня запустите:

   ```powershell
   python prepare_updates.py --sdk "$env:LOCALAPPDATA/Android/Sdk"
   python -m unittest discover -s tests -v
   ```

4. Проверьте изменения, закоммитьте исходники, `releases/` и `updates.json`,
   затем выполните `git push origin main`.

Скрипт сверяет фактические package ID и версии внутри APK, проверяет подписи,
создаёт файлы `releases/golf4-<versionCode>.apk` и `releases/bfq-<versionCode>.apk`
и вычисляет размеры и SHA-256. Существующий номер выпуска нельзя перезаписать
другим APK. Манифест обновляется после подготовки файлов обоих приложений.
Старые APK сохраняются, чтобы уже начатые загрузки могли завершиться.

## Проверки и материалы

Для Python-проверок: Python 3.10+, `pip install -r requirements.txt` и JDK для
теста Java-логики обновления.

```powershell
python -m unittest discover -s tests -v
python audit_app_quality.py --strict
python audit_bfq_content.py
python audit_native_content.py --assets android-manual/app/src/main/assets --strict
```

Большие исходные PDF, модели перевода и рабочие кеши хранятся локально;
для сборки Android-приложений они не нужны. Тест сверки с оригинальным PDF
пропускается, если этот файл отсутствует. Проверки PDF-вёрстки используют
Arial из `C:/Windows/Fonts`; для запуска вне Windows укажите доступные шрифты
в `translate_haynes.py`.

Предыдущие исправления описаны в [ERROR_REVIEW.txt](ERROR_REVIEW.txt).
Материалы содержат машинный перевод с отдельными ручными исправлениями;
автоматические проверки не заменяют техническую вычитку всей книги.
