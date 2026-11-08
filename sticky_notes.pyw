import tkinter as tk
from tkinter import font as tkfont
from tkinter import simpledialog, messagebox
import json, os, sys, uuid, shutil, socket, time
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_DIR, "sticky_notes.json")
ICO_FILE = os.path.join(APP_DIR, "sticky_notes_icon.ico")
ERROR_LOG_FILE = os.path.join(APP_DIR, "sticky_notes_error.log")

THEMES = {
    "solarized": {"bg": "#002b36", "text_bg": "#073642", "fg": "#839496"},
    "darknight": {"bg": "#111111", "text_bg": "#1e1e1e", "fg": "#ffffff"},
    "classic": {"bg": "#e6c229", "text_bg": "#fff275", "fg": "#2c2c2c"},
}
_lock_socket = None


def check_single_instance(port=50123):
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(("127.0.0.1", port))
        _lock_socket.listen(1)
        return True
    except socket.error:
        return False


class NoteWindow:

    def __init__(
        self,
        manager,
        note_id,
        text="",
        geometry="300x200+100+100",
        font_family="BIZTER",
        font_size=10,
        alpha=1.0,
        topmost=True,
        theme="solarized",
        is_hidden=False,
    ):
        self.manager = manager
        self.id = note_id
        self.font_family = font_family
        self.font_size = font_size
        self.alpha_val = alpha
        self.topmost_val = topmost
        self.theme_name = theme if theme in THEMES else "solarized"
        self.is_hidden = is_hidden

        self.root = tk.Toplevel(manager.root)
        self.root.title("Solarized Note")
        self.root.overrideredirect(True)
        self.root.geometry(geometry)
        self.root.attributes("-topmost", self.topmost_val)
        self.root.attributes("-alpha", self.alpha_val)

        self.header = tk.Frame(self.root, height=15)
        self.header.pack(fill=tk.X, side=tk.TOP)

        self.text_area = tk.Text(
            self.root, font=(self.font_family, self.font_size), bd=0, padx=10, pady=5, undo=True
        )
        self.text_area.insert("1.0", text)
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=(2, 4), pady=(0, 4))
        self.apply_theme_colors()

        self.root.bind("<Motion>", self.update_cursor)
        self.root.bind("<Button-1>", self.on_left_click)
        self.root.bind("<B1-Motion>", self.on_left_drag)
        self.text_area.bind("<Control-s>", lambda e: self.manual_save())
        self.text_area.bind("<Control-S>", lambda e: self.manual_save())

        self.create_context_menu()
        self.root.bind("<Button-3>", self.show_menu)
        self.text_area.bind("<Double-Button-1>", lambda e: self.manager.create_new_note())

        self.drag_mode, self.border_width, self.snap_distance = "move", 8, 15
        if self.is_hidden:
            self.root.withdraw()

    def apply_theme_colors(self):
        t = THEMES[self.theme_name]
        self.root.configure(bg=t["bg"])
        self.header.configure(bg=t["bg"])
        self.text_area.configure(bg=t["text_bg"], fg=t["fg"], insertbackground=t["fg"])

    def change_theme(self, new_theme):
        if new_theme in THEMES:
            self.theme_name = new_theme
            self.apply_theme_colors()
    def create_context_menu(self):
        bg_col, fg_col = THEMES["solarized"]["bg"], THEMES["solarized"]["fg"]
        act_bg = THEMES["solarized"]["text_bg"]
        self.menu = tk.Menu(
            self.root, tearoff=0, bg=bg_col, fg=fg_col, activebackground=act_bg, activeforeground=fg_col
        )
        self.menu.add_command(label="➕ 新しい付箋を追加", command=self.manager.create_new_note)
        self.menu.add_command(label="💾 現状を保存", command=self.manual_save)
        self.menu.add_separator()

        self.color_menu = tk.Menu(
            self.menu, tearoff=0, bg=bg_col, fg=fg_col, activebackground=act_bg, activeforeground=fg_col
        )
        self.color_menu.add_command(
            label="🟢 標準 (Solarized)", command=lambda: self.change_theme("solarized")
        )
        self.color_menu.add_command(
            label="🔵 ダークナイト", command=lambda: self.change_theme("darknight")
        )
        self.color_menu.add_command(label="🟡 クラシック", command=lambda: self.change_theme("classic"))
        self.menu.add_cascade(label="🎨 付箋の色を変更", menu=self.color_menu)
        self.menu.add_separator()

        self.menu.add_command(label="🔤 フォント名を指定...", command=self.open_font_dialog)
        self.menu.add_command(label="📏 サイズを数値指定...", command=self.open_size_dialog)

        self.alpha_menu = tk.Menu(
            self.menu, tearoff=0, bg=bg_col, fg=fg_col, activebackground=act_bg, activeforeground=fg_col
        )
        for i in range(10, 0, -1):
            self.alpha_menu.add_command(
                label=f"{i*10}%", command=lambda v=i / 10.0: self.change_alpha(v)
            )
        self.menu.add_cascade(label="👻 不透明度", menu=self.alpha_menu)

        self.topmost_var = tk.BooleanVar(value=self.topmost_val)
        self.menu.add_checkbutton(
            label="📌 常に最前面に表示", variable=self.topmost_var, command=self.toggle_topmost
        )
        self.menu.add_separator()
        self.menu.add_command(label="👁️ この付箋を一時的に閉じる", command=self.hide_note)
        self.menu.add_command(label="❌ この付箋を完全に削除", command=self.close_note)
        self.menu.add_command(label="🚪 すべて終了", command=self.manager.quit_app)

    def manual_save(self):
        self.manager.save_all()
        return "break"

    def open_font_dialog(self):
        new_font = simpledialog.askstring(
            "フォントの変更",
            "フォント名を入力してください:\n(例: BIZTER, MS Gothic, Meiryo)",
            initialvalue=self.font_family,
            parent=self.root,
        )
        if new_font:
            self.change_font(new_font.strip(), self.font_size)

    def open_size_dialog(self):
        new_size = simpledialog.askinteger(
            "サイズ指定",
            "サイズを入力 (5 〜 72):",
            initialvalue=self.font_size,
            minvalue=5,
            maxvalue=72,
            parent=self.root,
        )
        if new_size:
            self.change_font(self.font_family, new_size)

    def change_font(self, family, size):
        self.font_family, self.font_size = family, size
        self.text_area.configure(font=(self.font_family, self.font_size))

    def change_alpha(self, value):
        self.alpha_val = value
        self.root.attributes("-alpha", self.alpha_val)

    def toggle_topmost(self):
        self.topmost_val = self.topmost_var.get()
        self.root.attributes("-topmost", self.topmost_val)

    def update_cursor(self, event):
        if event.widget == self.text_area:
            self.root.config(cursor="")
            return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        r, b = (event.x >= w - self.border_width), (event.y >= h - self.border_width)
        if r and b:
            self.root.config(cursor="size_nw_se")
        elif r:
            self.root.config(cursor="size_we")
        elif b:
            self.root.config(cursor="size_ns")
        else:
            self.root.config(cursor="")

    def on_left_click(self, event):
        self.start_x, self.start_y = event.x_root, event.y_root
        self.start_width, self.start_height = self.root.winfo_width(), self.root.winfo_height()
        self.start_geo_x, self.start_geo_y = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        r, b = (event.x >= w - self.border_width), (event.y >= h - self.border_width)
        self.drag_mode = (
            "resize_br" if (r and b) else "resize_r" if r else "resize_b" if b else "move"
        )

    def on_left_drag(self, event):
        if event.widget == self.text_area and self.drag_mode == "move":
            return
        dx, dy = event.x_root - self.start_x, event.y_root - self.start_y
        if self.drag_mode == "move":
            new_x, new_y = self.start_geo_x + dx, self.start_geo_y + dy
            w, h = self.start_width, self.start_height
            if not (event.state & 0x0001):
                for note_id, note in self.manager.notes.items():
                    if note_id == self.id or note.is_hidden:
                        continue
                    try:
                        nx, ny = note.root.winfo_x(), note.root.winfo_y()
                        nw, nh = note.root.winfo_width(), note.root.winfo_height()
                        if abs(new_x - (nx + nw)) < self.snap_distance:
                            new_x = nx + nw
                        elif abs((new_x + w) - nx) < self.snap_distance:
                            new_x = nx - w
                        if abs(new_y - (ny + nh)) < self.snap_distance:
                            new_y = ny + nh
                        elif abs((new_y + h) - ny) < self.snap_distance:
                            new_y = ny - h
                        if abs(new_x - nx) < self.snap_distance:
                            new_x = nx
                        if abs(new_y - ny) < self.snap_distance:
                            new_y = ny
                    except:
                        pass
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                if abs(new_x) < self.snap_distance:
                    new_x = 0
                elif abs((new_x + w) - sw) < self.snap_distance:
                    new_x = sw - w
                if abs(new_y) < self.snap_distance:
                    new_y = 0
                elif abs((new_y + h) - sh) < self.snap_distance:
                    new_y = sh - h
            self.root.geometry(f"+{new_x}+{new_y}")
        else:
            nw, nh = self.start_width, self.start_height
            if "r" in self.drag_mode:
                nw = max(150, self.start_width + dx)
            if "b" in self.drag_mode:
                nh = max(100, self.start_height + dy)
            self.root.geometry(f"{nw}x{nh}+{self.start_geo_x}+{self.start_geo_y}")

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def hide_note(self):
        self.root.withdraw()
        self.is_hidden = True
        self.manager.save_all()

    def close_note(self):
        if messagebox.askyesno("削除確認", "この付箋を削除しますか？", parent=self.root):
            self.root.destroy()
            self.manager.remove_note(self.id)
class NoteManager:

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.notes, self.tray_icon, self.all_hidden = {}, None, False
        self.tray_image = None
        self.load_all()
        # Windowsの描画が落ち着くまで1秒待ってからトレイアイコンを設定
        self.root.after(1000, self.setup_tray_icon)

    def create_new_note(self):
        note_id = str(uuid.uuid4())
        bx, by, offset = 100, 100, 25
        while True:
            overlap = False
            for note in self.notes.values():
                try:
                    if abs(note.root.winfo_x() - bx) < 10 and abs(note.root.winfo_y() - by) < 10:
                        overlap = True
                        break
                except:
                    pass
            if overlap:
                bx, by = bx + offset, by + offset
                if bx > self.root.winfo_screenwidth() - 300:
                    bx, by = 100, 100
                    break
            else:
                break
        note = NoteWindow(self, note_id, text="", geometry=f"300x200+{bx}+{by}", theme="solarized")
        self.notes[note_id] = note

    def remove_note(self, note_id):
        if note_id in self.notes:
            del self.notes[note_id]
        self.save_all()

    def toggle_all_notes_visibility(self):
        self.all_hidden = not self.all_hidden
        for note in self.notes.values():
            try:
                if self.all_hidden:
                    note.root.withdraw()
                    note.is_hidden = True
                else:
                    note.root.deiconify()
                    note.root.attributes("-topmost", note.topmost_val)
                    note.is_hidden = False
            except:
                pass
        self.save_all()

    def on_tray_clicked(self, icon, button):
        if str(button) == "Button.left" or getattr(button, "name", "") == "LEFT":
            self.root.after(0, self.toggle_all_notes_visibility)

    def load_all(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for nid, inf in data.items():
                        note = NoteWindow(
                            self,
                            nid,
                            text=inf["text"],
                            geometry=inf["geometry"],
                            font_family=inf.get("font_family", "BIZTER"),
                            font_size=inf.get("font_size", 10),
                            alpha=inf.get("alpha", 1.0),
                            topmost=inf.get("topmost", True),
                            theme=inf.get("theme", "solarized"),
                            is_hidden=inf.get("is_hidden", False),
                        )
                        self.notes[nid] = note
            except Exception as e:
                self.log_error(f"読み込み失敗: {e}")
        if not self.notes:
            self.notes[str(uuid.uuid4())] = NoteWindow(self, str(uuid.uuid4()))

    def rotate_backups(self):
        if not self.notes or not os.path.exists(CONFIG_FILE):
            return
        # 👇 ここを 14 から 4 に変更します
        for i in range(4, 0, -1):
            o, n = f"{CONFIG_FILE}.bak{i}", f"{CONFIG_FILE}.bak{i+1}"
            if os.path.exists(o):
                try:
                    shutil.copy2(o, n)
                except:
                    pass
        try:
            shutil.copy2(CONFIG_FILE, f"{CONFIG_FILE}.bak1")
        except:
            pass


    def save_all(self):
        data = {}
        for nid, note in self.notes.items():
            try:
                data[nid] = {
                    "text": note.text_area.get("1.0", "end-1c"),
                    "geometry": note.root.geometry(),
                    "font_family": note.font_family,
                    "font_size": note.font_size,
                    "alpha": note.alpha_val,
                    "topmost": note.topmost_val,
                    "theme": note.theme_name,
                    "is_hidden": note.is_hidden,
                }
            except:
                pass
        tmp = CONFIG_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            os.rename(tmp, CONFIG_FILE)
        except Exception as e:
            self.log_error(f"保存失敗: {e}")

    def log_error(self, msg):
        try:
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except:
            pass

    def get_tray_image(self):
        if not os.path.exists(ICO_FILE):
            img = Image.new("RGB", (32, 32), THEMES["solarized"]["bg"])
            draw = ImageDraw.Draw(img)
            draw.rectangle((2, 2, 29, 29), outline=THEMES["classic"]["bg"], width=2)
            img.save(ICO_FILE, format="ICO")
        self.tray_image = Image.open(ICO_FILE)
        return self.tray_image

    def setup_tray_icon(self):
        m = pystray.Menu(
            item("➕ 新しい付箋を追加", lambda icon, item: self.root.after(0, self.create_new_note)),
            item("👁️ 表示/非表示切替", lambda icon, item: self.root.after(0, self.toggle_all_notes_visibility)),
            item("🚪 アプリ終了", lambda icon, item: self.root.after(0, self.quit_app)),
        )
        try:
            self.tray_icon = pystray.Icon("solarized_notes", self.get_tray_image(), "Notes", m)
            self.tray_icon.activated = self.on_tray_clicked
            # pystray標準の非同期メソッドでWindowsと安全に連携
            self.tray_icon.run_detached()
        except Exception as e:
            print(f"設定エラー: {e}")

    def quit_app(self):
        self.rotate_backups()
        self.save_all()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if not check_single_instance():
        re = tk.Tk()
        re.withdraw()
        messagebox.showwarning("多重起動", "アプリは既に起動しています。")
        re.destroy()
        sys.exit(0)
    NoteManager().run()
