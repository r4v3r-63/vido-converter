"""Native desktop interface. No browser, HTTP server or file uploads."""
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app import command, FFMPEG


def probe_encoder(target, encoder, device, runner=subprocess.run):
    """Use a normal frame size: hardware encoders can reject tiny images."""
    args = command(Path("unused"), target, "original", "original", True, encoder, device)
    index = args.index("-i")
    args[index:index + 2] = ["-f", "lavfi", "-i", "color=size=640x360:rate=30", "-frames:v", "3"]
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    result = runner(args, capture_output=True, timeout=30, **flags)
    return None if result.returncode == 0 else result.stderr.decode("utf-8", "replace").strip() or "FFmpeg вернул ошибку без описания"



class Converter:
    def __init__(self, root):
        self.root = root
        self.paths = []
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.closing = False
        self.failed = 0
        self.gpu_diagnostics = 'Проверка ещё выполняется.'
        root.title('Кадр — конвертер видео')
        root.geometry('1000x780')
        root.minsize(800, 700)
        root.configure(bg='#f5f6f8')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#f5f6f8')
        style.configure('TLabel', background='#f5f6f8', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=8)
        style.configure('Treeview', rowheight=29, font=('Segoe UI', 10))
        outer = ttk.Frame(root, padding=24)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Кадр', font=('Segoe UI', 25, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Пакетная конвертация видео • исходники остаются без изменений').pack(anchor='w', pady=(2, 18))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill='x')
        self.add = ttk.Button(toolbar, text='＋ Добавить видео', command=self.choose_files)
        self.add.pack(side='left')
        self.remove = ttk.Button(toolbar, text='Удалить выбранные', command=self.remove_files)
        self.remove.pack(side='left', padx=8)
        self.clear = ttk.Button(toolbar, text='Очистить', command=self.clear_files)
        self.clear.pack(side='left')
        table = ttk.Frame(outer)
        table.pack(fill='both', expand=True, pady=14)
        self.tree = ttk.Treeview(table, columns=('file', 'status'), show='headings')
        self.tree.heading('file', text='Файл')
        self.tree.heading('status', text='Состояние')
        self.tree.column('file', width=580)
        self.tree.column('status', width=170)
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.bind('<Double-1>', self.show_detail)
        settings = ttk.Frame(outer)
        settings.pack(fill='x')
        self.size = tk.StringVar(value='1920 × 1080 · Full HD')
        self.fps = tk.StringVar(value='Как в оригинале')
        self.fmt = tk.StringVar(value='MP4')
        self.sizes = {'Как в оригинале': 'original', '3840 × 2160 · 4K': '2160', '1920 × 1080 · Full HD': '1080', '1280 × 720 · HD': '720', '854 × 480 · SD': '480'}
        self.combos = []
        for i, (label, variable, values) in enumerate([
            ('Разрешение', self.size, list(self.sizes)),
            ('Частота кадров', self.fps, ['Как в оригинале', '24', '25', '30', '50', '60']),
            ('Формат', self.fmt, ['MP4', 'MKV', 'WebM'])]):
            settings.columnconfigure(i, weight=1)
            ttk.Label(settings, text=label).grid(row=0, column=i, sticky='w', padx=(0, 12))
            combo = ttk.Combobox(settings, textvariable=variable, values=values, state='readonly')
            combo.grid(row=1, column=i, sticky='ew', padx=(0, 12), pady=(6, 0))
            self.combos.append(combo)
        hardware = ttk.Frame(outer)
        hardware.pack(fill='x', pady=(14, 0))
        ttk.Label(hardware, text='Кодирование:').pack(side='left')
        self.devices = {'Процессор (CPU)': ('cpu', 0)}
        self.encoder = tk.StringVar(value='Процессор (CPU)')
        self.gpu_combo = ttk.Combobox(hardware, textvariable=self.encoder, values=list(self.devices), state='readonly', width=55)
        self.gpu_combo.pack(side='left', fill='x', expand=True, padx=12)
        self.combos.append(self.gpu_combo)
        self.gpu_diagnostics_button = ttk.Button(hardware, text='Диагностика GPU', command=self.show_gpu_diagnostics)
        self.gpu_diagnostics_button.pack(side='right')
        self.gpu_status = tk.StringVar(value='Проверка доступных видеокарт…')
        ttk.Label(outer, textvariable=self.gpu_status).pack(anchor='w', pady=(4, 0))
        threading.Thread(target=self.detect_devices, daemon=True).start()
        self.mute = tk.BooleanVar()
        self.sound = ttk.Checkbutton(outer, text='Удалить звук из готовых видео', variable=self.mute)
        self.sound.pack(anchor='w', pady=14)
        folder = ttk.Frame(outer)
        folder.pack(fill='x')
        self.destination = tk.StringVar(value=str(Path.home() / 'Videos' / 'Kadr'))
        ttk.Label(folder, text='Сохранить в:').pack(side='left')
        self.folder_entry = ttk.Entry(folder, textvariable=self.destination)
        self.folder_entry.pack(side='left', fill='x', expand=True, padx=10)
        self.browse = ttk.Button(folder, text='Выбрать папку', command=self.choose_folder)
        self.browse.pack(side='left')
        ttk.Label(outer, text='Пропорции сохраняются. Ограничений на размер и количество файлов нет.').pack(anchor='w', pady=(12, 8))
        self.progress = ttk.Progressbar(outer, mode='determinate')
        self.progress.pack(fill='x')
        self.status = tk.StringVar(value='Добавьте видео и выберите папку для результатов.')
        ttk.Label(outer, textvariable=self.status).pack(anchor='w', pady=8)
        bottom = ttk.Frame(outer)
        bottom.pack(fill='x')
        self.start_button = ttk.Button(bottom, text='Конвертировать видео', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(bottom, text='Остановить', command=self.cancel.set, state='disabled')
        self.stop_button.pack(side='left', padx=10)
        ttk.Button(bottom, text='Открыть папку результатов', command=self.open_folder).pack(side='right')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def detect_devices(self):
        available = {'Процессор (CPU)': ('cpu', 0)}
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
        candidates = []
        diagnostics = []
        try:
            data = subprocess.run(['nvidia-smi', '--query-gpu=index,name', '--format=csv,noheader'], capture_output=True, text=True, timeout=10, **flags)
            for line in data.stdout.splitlines():
                index, name = line.split(',', 1)
                candidates.append((name.strip() + ' · NVENC', 'nvidia', int(index)))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if not candidates:
            candidates.append(('NVIDIA · NVENC', 'nvidia', 0))
        candidates.extend([('AMD · AMF (адаптер по умолчанию)', 'amd', 0), ('Intel · Quick Sync (адаптер по умолчанию)', 'intel', 0)])
        with tempfile.TemporaryDirectory() as tmp:
            for label, encoder, device in candidates:
                try:
                    target = Path(tmp) / 'probe.mp4'
                    error = probe_encoder(target, encoder, device)
                    if error is None:
                        available[label] = (encoder, device)
                        diagnostics.append(label + ': доступно')
                    else:
                        diagnostics.append(label + ':\n' + error)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    diagnostics.append(label + ':\n' + str(exc))
        self.events.put(('devices', available, '\n\n'.join(diagnostics)))

    def show_gpu_diagnostics(self):
        window = tk.Toplevel(self.root)
        window.title('Диагностика видеокарт')
        window.geometry('850x500')
        text = tk.Text(window, wrap='word', font=('Consolas', 10))
        text.pack(fill='both', expand=True, padx=12, pady=12)
        text.insert('1.0', self.gpu_diagnostics)
        text.configure(state='disabled')
        def copy():
            window.clipboard_clear()
            window.clipboard_append(self.gpu_diagnostics)
        ttk.Button(window, text='Скопировать диагностику', command=copy).pack(pady=8)

    def choose_files(self):
        names = filedialog.askopenfilenames(title='Выберите видео', filetypes=[('Видеофайлы', '*.mp4 *.mkv *.avi *.mov *.webm *.mts *.m2ts *.flv *.wmv *.ts *.mpeg *.mpg *.m4v'), ('Все файлы', '*.*')])
        self.add_files(names)

    def add_files(self, names):
        if self.running:
            return
        known = set(self.paths)
        for name in names:
            path = Path(name).resolve()
            if path not in known:
                self.paths.append(path)
                known.add(path)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, path in enumerate(self.paths):
            self.tree.insert('', 'end', iid=str(i), values=(str(path), 'В очереди'))
        self.status.set(f'В очереди: {len(self.paths)}')

    def remove_files(self):
        chosen = {int(i) for i in self.tree.selection()}
        self.paths = [p for i, p in enumerate(self.paths) if i not in chosen]
        self.refresh()

    def clear_files(self):
        self.paths.clear()
        self.refresh()

    def choose_folder(self):
        path = filedialog.askdirectory(title='Папка результатов')
        if path:
            self.destination.set(path)

    def show_detail(self, event=None):
        selected = self.tree.selection()
        if selected:
            messagebox.showinfo('Подробности', '\n\n'.join(str(v) for v in self.tree.item(selected[0], 'values')))

    def open_folder(self):
        path = Path(self.destination.get()).expanduser()
        if not path.is_dir():
            messagebox.showinfo('Папка результатов', 'Папка появится после начала конвертации.')
        elif sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])

    def start(self):
        if self.running:
            return
        if not self.paths:
            messagebox.showinfo('Добавьте видео', 'Сначала выберите видеофайлы.')
            return
        if not self.destination.get().strip():
            messagebox.showerror('Папка результатов', 'Выберите папку для сохранения.')
            return
        destination = Path(self.destination.get()).expanduser()
        try:
            destination.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=destination):
                pass
        except OSError as exc:
            messagebox.showerror('Не удалось открыть папку', str(exc))
            return
        if self.fmt.get() == 'WebM' and self.devices[self.encoder.get()][0] != 'cpu':
            messagebox.showinfo('Аппаратное кодирование', 'Выберите MP4 или MKV для видеокарты, либо процессор для WebM.')
            return
        self.refresh()
        self.failed = 0
        self.cancel.clear()
        self.running = True
        self.progress.configure(value=0, maximum=len(self.paths))
        for widget in [self.add, self.remove, self.clear, self.browse, self.folder_entry, self.sound, self.start_button, *self.combos]:
            widget.configure(state='disabled')
        self.stop_button.configure(state='normal')
        settings = (self.sizes[self.size.get()], 'original' if self.fps.get() == 'Как в оригинале' else self.fps.get(), self.mute.get(), self.fmt.get().lower(), *self.devices[self.encoder.get()])
        threading.Thread(target=self.work, args=(list(self.paths), destination, settings), daemon=True).start()

    def work(self, paths, destination, settings):
        size, fps, mute, fmt, encoder, device = settings
        for index, source in enumerate(paths):
            if self.cancel.is_set():
                break
            self.events.put(('row', index, 'Обработка…'))
            target = temporary = None
            try:
                # Exclusive reservation protects originals and existing results,
                # including identical filenames from different source folders.
                number = 0
                while True:
                    suffix = '' if number == 0 else f' ({number})'
                    target = destination / f'{source.stem}_converted{suffix}.{fmt}'
                    try:
                        target.open('xb').close()
                        break
                    except FileExistsError:
                        number += 1
                fd, name = tempfile.mkstemp(suffix='.' + fmt, prefix='.kadr-', dir=destination)
                os.close(fd)
                temporary = Path(name)
                with tempfile.TemporaryFile() as errors:
                    process = subprocess.Popen(command(source, temporary, size, fps, mute, encoder, device), stdout=subprocess.DEVNULL, stderr=errors, **({'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}))
                    while process.poll() is None:
                        if self.cancel.wait(0.1):
                            process.terminate()
                            process.wait()
                            break
                    if self.cancel.is_set():
                        raise InterruptedError('Остановлено')
                    if process.returncode:
                        errors.seek(0)
                        raise ValueError(errors.read().decode('utf-8', 'replace')[-2000:] or 'Ошибка FFmpeg')
                os.replace(temporary, target)
                temporary = None
                target = None
                self.events.put(('row', index, 'Готово'))
            except Exception as exc:
                self.events.put(('row', index, 'Остановлено' if self.cancel.is_set() else 'Ошибка: ' + str(exc)))
            finally:
                for path in (temporary, target):
                    if path is not None:
                        path.unlink(missing_ok=True)
            self.events.put(('progress', index + 1))
        self.events.put(('finished',))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'devices':
                    self.devices = event[1]
                    self.gpu_diagnostics = event[2]
                    self.gpu_combo.configure(values=list(self.devices))
                    self.gpu_status.set('Выберите видеокарту для MP4/MKV. Масштабирование и чтение остаются на CPU.' if len(self.devices) > 1 else 'GPU не прошли проверку. Причины — в кнопке «Диагностика GPU».')
                elif event[0] == 'row':
                    _, index, status = event
                    self.tree.set(str(index), 'status', status)
                    if status.startswith('Ошибка'):
                        self.failed += 1
                    self.status.set(f'Файл {index + 1} из {len(self.paths)}: {status[:120]}')
                elif event[0] == 'progress':
                    self.progress.configure(value=event[1])
                elif event[0] == 'finished':
                    self.running = False
                    for widget in [self.add, self.remove, self.clear, self.browse, self.folder_entry, self.sound, self.start_button]:
                        widget.configure(state='normal')
                    for combo in self.combos:
                        combo.configure(state='readonly')
                    self.stop_button.configure(state='disabled')
                    self.status.set('Остановлено. Готовые файлы сохранены.' if self.cancel.is_set() else f'Готово. Ошибок: {self.failed}. Результаты в выбранной папке.')
        except queue.Empty:
            pass
        if self.closing and not self.running:
            self.root.destroy()
        else:
            self.root.after(100, self.poll)

    def close(self):
        if self.running and not messagebox.askyesno('Завершить работу?', 'Остановить конвертацию и закрыть программу?'):
            return
        self.closing = True
        self.cancel.set()
        if not self.running:
            self.root.destroy()


def smoke(root, ui, report):
    """Run the real GUI and worker against a generated video in the built exe."""
    import json
    scratch = tempfile.TemporaryDirectory()
    folder = Path(scratch.name)
    source = folder / 'sample.mp4'
    try:
        subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=10', '-t', '0.2', '-c:v', 'libx264', str(source)], check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        ui.add_files([source])
        ui.destination.set(str(folder))
        ui.size.set('Как в оригинале')
        ui.start()
        deadline = __import__('time').monotonic() + 60
        def check():
            if ui.running and __import__('time').monotonic() < deadline:
                root.after(100, check)
                return
            output = folder / 'sample_converted.mp4'
            success = not ui.running and ui.failed == 0 and output.exists() and output.stat().st_size > 100
            Path(report).write_text(json.dumps({'success': success, 'status': ui.status.get()}), encoding='utf-8')
            root.destroy()
        root.after(100, check)
    except Exception as exc:
        Path(report).write_text(json.dumps({'success': False, 'error': str(exc)}), encoding='utf-8')
        root.destroy()
    return scratch


if __name__ == '__main__':
    root = tk.Tk()
    ui = Converter(root)
    scratch = None
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        scratch = smoke(root, ui, sys.argv[2])
    root.mainloop()
    if scratch:
        scratch.cleanup()
