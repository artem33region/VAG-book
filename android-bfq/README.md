# VW BFQ 1.6 — Android-справочник

Отдельное автономное приложение по бензиновому двигателю BFQ. Устанавливается
рядом с общим справочником Golf IV/Bora благодаря отдельному application ID
`ru.vagguides.bfqmanual`.

Контент хранится как нативные JSON-статьи и отдельные WebP-иллюстрации. PDF в
APK не включается.

Сборка:

```powershell
gradle.bat --offline --no-daemon :app:assembleDebug
```
