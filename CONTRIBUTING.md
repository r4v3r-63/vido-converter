# Разработка

Используйте существующий каталог репозитория. Нужны Python 3.10+, Tkinter,
FFmpeg и ffprobe в PATH. Для запуска готового EXE всё это уже включено в архив.

## Подготовка и запуск из исходников

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python desktop.py
```

На Debian/Ubuntu системные зависимости устанавливаются командой
`sudo apt-get install python3 python3-venv python3-tk ffmpeg`.
На Windows Python должен включать Tcl/Tk; FFmpeg и ffprobe должны быть доступны
в PATH. Дополнительных Python-пакетов для самого приложения нет.

## Проверки перед отправкой

```sh
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
```

Исправить оформление: `python -m ruff format .`.
Тесты создают короткие видео и проверяют кодеки, размер, FPS, аудио,
сохранность исходников, конфликты имён, ошибки и остановку пакета.
Тесты движка не требуют окна или сетевых сокетов.

## Сборка Windows

На Windows установите инструменты сборки:

```sh
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Kadr --add-binary "C:\path\to\ffmpeg.exe;." desktop.py
python tests/smoke_packaged.py dist/Kadr.exe
```

Замените путь на фактический путь к FFmpeg. GitHub Actions выполняет эти шаги
автоматически на Windows после push в main. На этом этапе EXE и ZIP доступны
как артефакты сборки, новый релиз не создаётся.
Smoke-тест запускает настоящее окно при увеличенном масштабе, проверяет видимость
кнопок при уменьшении окна и конвертацию встроенным FFmpeg в выбранную папку.

Для выпуска отправьте тег `vX.Y.Z` на проверенный коммит. После успешных тестов
workflow создаёт GitHub Release с ZIP, контрольной суммой SHA256 и уведомлениями
о сторонних компонентах. Не меняйте существующие теги выпущенных версий.

GPU нужно дополнительно проверять на компьютерах с соответствующим оборудованием
и драйверами. Облачный runner проверяет CPU; аппаратное кодирование на нём
не гарантировано. Программа показывает кодировщики после успешной пробной
конвертации; причины отказов доступны через «Диагностика GPU».
