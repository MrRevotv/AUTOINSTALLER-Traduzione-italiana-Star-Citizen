import sys
import os
import json
import requests
import concurrent.futures
import tempfile
import subprocess
import winreg  # Per avvio automatico su Windows
import shutil   # Per copiare il file in una cartella stabile
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QCheckBox, QDialog,
    QDialogButtonBox, QMessageBox, QProgressBar, QFileDialog, QLineEdit, QHBoxLayout,
    QPushButton, QStyleOptionButton, QStyle, QSizePolicy, QSplashScreen
)
from PyQt5.QtGui import QIcon, QFont, QPainter, QPixmap, QDesktopServices
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint

# ------------------------------------------------------------
#                 CONFIGURAZIONE & COSTANTI
# ------------------------------------------------------------
SETTINGS_FOLDER = os.path.join(os.getenv('LOCALAPPDATA'), "InstallerTraduzioneMRREVO")
if not os.path.exists(SETTINGS_FOLDER):
    os.makedirs(SETTINGS_FOLDER)

SETTINGS_FILE = os.path.join(SETTINGS_FOLDER, "settings.json")

LAUNCHER_VERSION = "1.4"
CURRENT_TRANSLATION_VERSION = "1"
SPLASH_IMAGE_URL = "https://drive.google.com/uc?export=download&id=1v4gxwj8XoRyK_29Ign-2FJjy0DZUrJTB"
VERSION_FILE_URL = "https://drive.google.com/uc?export=download&id=1cXpbauWp5JnZYQaUS0Sh--tzqtVXpHpW"

STATIC_SPLASH_FILENAME = "static_splash.png"

# ------------------------------------------------------------
#   FUNZIONI PER LA POSIZIONE STABILE DELL'UPDATER
# ------------------------------------------------------------
def get_stable_updater_path():
    """
    Restituisce il percorso stabile in cui deve essere installato l’updater.
    Ad esempio: %LOCALAPPDATA%\InstallerTraduzioneMRREVO\AUTO Installer traduzione SC.exe
    """
    local_appdata = os.getenv("LOCALAPPDATA")
    stable_dir = os.path.join(local_appdata, "InstallerTraduzioneMRREVO")
    if not os.path.exists(stable_dir):
        os.makedirs(stable_dir)
    stable_path = os.path.join(stable_dir, "AUTO Installer traduzione SC.exe")
    return stable_path

def ensure_stable_location():
    """
    Se il file eseguibile corrente (l'updater che l'utente ha scaricato)
    non si trova nella posizione stabile, viene copiato lì.
    Restituisce il percorso stabile.
    """
    stable_path = get_stable_updater_path()
    current_path = os.path.abspath(sys.argv[0])
    # Confronto case-insensitive su Windows
    if current_path.lower() != stable_path.lower():
        try:
            shutil.copy2(current_path, stable_path)
            print(f"[DEBUG] Copia eseguita: aggiornato l'updater in posizione stabile: {stable_path}")
        except Exception as e:
            print("[DEBUG] Errore copiando l'updater nella posizione stabile:", e)
    else:
        print("[DEBUG] L'updater è già nella posizione stabile.")
    return stable_path

# ------------------------------------------------------------
#            CLASSE NoFocusButton (se serve)
# ------------------------------------------------------------
class NoFocusButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.NoFocus)
    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.state &= ~QStyle.State_HasFocus
        painter = QPainter(self)
        self.style().drawControl(QStyle.CE_PushButton, option, painter, self)

# ------------------------------------------------------------
#         LETTURA E SCRITTURA DELLE IMPOSTAZIONI (JSON)
# ------------------------------------------------------------
def load_settings():
    print("[DEBUG] load_settings() chiamato.")
    default_settings = {
        "start_with_windows": False,
        "use_dynamic_splash": True,
        "installed_translation_version": "",
        "last_selected_folder": ""
    }
    if not os.path.exists(SETTINGS_FILE):
        print("[DEBUG] Nessun file settings.json, uso impostazioni di default.")
        return default_settings
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in default_settings:
            if key not in data:
                data[key] = default_settings[key]
        print("[DEBUG] Impostazioni caricate correttamente:", data)
        return data
    except Exception as e:
        print(f"[DEBUG] Errore leggendo {SETTINGS_FILE}: {e}. Uso default.")
        return default_settings

def save_settings(settings):
    print(f"[DEBUG] save_settings() - Salvo impostazioni: {settings}")
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("[DEBUG] Errore salvando settings.json:", e)

# ------------------------------------------------------------
#      GESTIONE AVVIO AUTOMATICO SU WINDOWS (winreg)
# ------------------------------------------------------------
def set_autostart_in_registry(enabled, target_executable):
    """
    Registra (o elimina) nel registro il percorso target_executable per l’avvio automatico.
    In questo modo, se enabled è True, verrà avviato lo stable updater.
    """
    run_key_name = "MyLauncherExample"
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    print(f"[DEBUG] set_autostart_in_registry({enabled}) con target: {target_executable}")
    try:
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE)
    except Exception as e:
        print("[DEBUG] Impossibile aprire la chiave di registro:", e)
        return
    if enabled:
        try:
            winreg.SetValueEx(registry_key, run_key_name, 0, winreg.REG_SZ, target_executable)
            print("[DEBUG] Chiave di avvio automatico impostata con target:", target_executable)
        except Exception as e:
            print("[DEBUG] Errore scrivendo la chiave:", e)
    else:
        try:
            winreg.DeleteValue(registry_key, run_key_name)
            print("[DEBUG] Chiave di avvio automatico rimossa.")
        except FileNotFoundError:
            pass
        except Exception as e:
            print("[DEBUG] Errore eliminando la chiave:", e)
    registry_key.Close()

# ------------------------------------------------------------
#            FUNZIONI DI RETE E RISORSE
# ------------------------------------------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def check_translation_version():
    print("[DEBUG] check_translation_version() chiamato.")
    try:
        response = requests.get(VERSION_FILE_URL, stream=True, timeout=10)
        if response.status_code == 200:
            version_str = response.text.strip()
            print("[DEBUG] Versione online:", version_str)
            return version_str
    except Exception as e:
        print("[DEBUG] Errore nel controllo versione:", e)
    return CURRENT_TRANSLATION_VERSION

def download_splash_image(url):
    print("[DEBUG] download_splash_image() chiamato.")
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            data = response.content
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                print("[DEBUG] Splash scaricato correttamente.")
                return pixmap
    except Exception as e:
        print("[DEBUG] Errore scaricando lo splash:", e)
    return None

def find_star_citizen_installations(progress_callback=None):
    print("[DEBUG] find_star_citizen_installations() avviato.")
    valid_folders = []
    def search_drive(drive):
        folders = []
        try:
            for root, dirs, files in os.walk(drive):
                if 'StarCitizen' in root and 'Data.p4k' in files:
                    folder_name = os.path.basename(root)
                    folders.append((folder_name, root))
        except Exception as e:
            print(f"[DEBUG] Errore nella ricerca sul drive {drive}:", e)
        return folders
    drives = ['A:\\','B:\\','C:\\','D:\\','E:\\','F:\\','G:\\','H:\\']
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_drive = {executor.submit(search_drive, drive): drive for drive in drives}
        for future in concurrent.futures.as_completed(future_to_drive):
            result = future.result()
            valid_folders.extend(result)
    print("[DEBUG] Cartelle StarCitizen trovate:", valid_folders)
    return valid_folders

# ------------------------------------------------------------
#                   THREAD
# ------------------------------------------------------------
class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder
    def run(self):
        folder_name, folder_path = self.folder
        print(f"[DEBUG] DownloadThread avviato su {folder_name} -> {folder_path}")
        file_url = "https://drive.google.com/uc?export=download&id=1nS6AvSXgctANr-enrFg5XkZVUdY4N5qH"
        data_folder = os.path.join(folder_path, "data", "Localization", "italian_(italy)")
        os.makedirs(data_folder, exist_ok=True)
        save_path = os.path.join(data_folder, "global.ini")
        try:
            response = requests.get(file_url, stream=True)
            total_length = response.headers.get('content-length')
            if total_length is None:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                self.progress_signal.emit(100)
            else:
                dl = 0
                total_length = int(total_length)
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            dl += len(chunk)
                            percent = int(dl * 100 / total_length)
                            self.progress_signal.emit(percent)
            config_path = os.path.join(folder_path, "user.cfg")
            with open(config_path, 'w') as cfg_file:
                cfg_file.write("g_language=italian_(italy)\n")
                cfg_file.write("g_LanguageAudio=english\n")
            print("[DEBUG] Download + scrittura configurazione completati con successo!")
            self.finished_signal.emit(True)
        except Exception as e:
            print("[DEBUG] Errore durante il download:", e)
            self.finished_signal.emit(False)

class ProgressThread(QThread):
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(list)
    def run(self):
        folders = find_star_citizen_installations(self.progress_signal)
        self.result_signal.emit(folders)

class VersionCheckThread(QThread):
    version_found = pyqtSignal(str)
    def run(self):
        version_str = check_translation_version()
        self.version_found.emit(version_str)

# ------------------------------------------------------------
#                 FINESTRA "INFO"
# ------------------------------------------------------------
class InfoWindow(QDialog):
    def __init__(self):
        super().__init__()
        print("[DEBUG] InfoWindow __init__()")
        self.setWindowTitle("Informazioni")
        self.setFixedSize(450, 250)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #2c3e50;
                color: white;
                border: 2px solid #ffffff;
                border-radius: 0px;
            }
        """)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0,0,0,0)
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            background-color: #34495e;
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
        """)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(10,0,10,0)
        title_layout.addStretch()
        close_button = QPushButton("x")
        close_button.setFixedSize(30,30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        close_button.clicked.connect(self.close)
        title_layout.addWidget(close_button)
        title_bar.setLayout(title_layout)
        main_layout.addWidget(title_bar)
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20,20,20,20)
        label_info = QLabel("""
<p align="center">
<b>Benvenuto nell'installer di MrRevo</b><br>
Qui potresti trovare informazioni e link utili.
<br><br>
<a href="https://www.youtube.com/@MrRevoTV" style="color: #ff0000; text-decoration: none;">
    Canale YouTube di MrRevo
</a><br>
<a href="https://robertsspaceindustries.com/en/orgs/ALSE" style="color: #ffa500; text-decoration: none;">
    Pagina Org RSI (ALSE)
</a>
</p>
        """)
        label_info.setOpenExternalLinks(True)
        label_info.setFont(QFont("Arial", 14))
        label_info.setAlignment(Qt.AlignCenter)
        label_info.setWordWrap(True)
        content_layout.addWidget(label_info)
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                font-size: 16px;
                border-radius: 0px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        ok_button.clicked.connect(self.close)
        content_layout.addWidget(ok_button)
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget)
        self.setLayout(main_layout)
    def mousePressEvent(self, event):
        pass
    def mouseMoveEvent(self, event):
        pass

# ------------------------------------------------------------
#       NUOVA FINESTRA "HELP" (popup con link cliccabili)
# ------------------------------------------------------------
class HelpWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aiuto")
        self.setFixedSize(450, 250)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #2c3e50;
                color: white;
                border: 2px solid #ffffff;
                border-radius: 0px;
            }
            QLabel {
                font-size:16px;
                color: white;
            }
        """)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            background-color: #34495e;
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
        """)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(10, 0, 10, 0)
        label_title = QLabel("Help")
        label_title.setStyleSheet("color: white; font-size: 16px;")
        title_layout.addWidget(label_title)
        title_layout.addStretch()
        close_button = QPushButton("x")
        close_button.setFixedSize(30,30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        close_button.clicked.connect(self.close)
        title_layout.addWidget(close_button)
        title_bar.setLayout(title_layout)
        main_layout.addWidget(title_bar)
        body_widget = QWidget()
        body_layout = QVBoxLayout()
        body_layout.setSpacing(20)
        body_layout.setContentsMargins(10,10,10,10)
        youtube_label = QLabel('''<a href="https://youtu.be/cRBiG4wz3zs"
style="color: #00ff1a; font-size:18px; text-decoration:none;">
Apri il video di uso su YouTube
</a>''')
        youtube_label.setOpenExternalLinks(True)
        youtube_label.setAlignment(Qt.AlignCenter)
        discord_label = QLabel('''<a href="https://discord.gg/W9xYAss9yE"
style="color: #00ff1a; font-size:18px; text-decoration:none;">
Entra nel server Discord per gli aiuti
</a>''')
        discord_label.setOpenExternalLinks(True)
        discord_label.setAlignment(Qt.AlignCenter)
        body_layout.addWidget(youtube_label)
        body_layout.addWidget(discord_label)
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                font-size: 16px;
                border-radius: 0px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        ok_button.clicked.connect(self.close)
        body_layout.addWidget(ok_button)
        body_widget.setLayout(body_layout)
        main_layout.addWidget(body_widget)
        self.setLayout(main_layout)
    def mousePressEvent(self, event):
        pass
    def mouseMoveEvent(self, event):
        pass

# ------------------------------------------------------------
#        FINESTRA "IMPOSTAZIONI" (SettingsWindow)
# ------------------------------------------------------------
class SettingsWindow(QDialog):
    def __init__(self, settings):
        super().__init__()
        print("[DEBUG] SettingsWindow __init__()")
        self.setWindowTitle("Impostazioni")
        self.setFixedSize(450, 300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #2c3e50;
                color: white;
                border: 2px solid #ffffff;
                border-radius: 0px;
            }
        """)
        self.settings = settings
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            background-color: #34495e;
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
        """)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(10, 0, 10, 0)
        label_title = QLabel("Impostazioni")
        label_title.setStyleSheet("color: white; font-size: 16px;")
        title_layout.addWidget(label_title)
        title_layout.addStretch()
        close_button = QPushButton("x")
        close_button.setFixedSize(30, 30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        close_button.clicked.connect(self.close)
        title_layout.addWidget(close_button)
        title_bar.setLayout(title_layout)
        main_layout.addWidget(title_bar)
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        self.checkbox_startup = QCheckBox("Avvia con Windows")
        self.checkbox_startup.setChecked(self.settings["start_with_windows"])
        self.checkbox_startup.setStyleSheet("color: white; font-size:14px;")
        self.checkbox_startup.stateChanged.connect(self.on_startup_changed)
        content_layout.addWidget(self.checkbox_startup)
        self.checkbox_splash = QCheckBox("Usa splash screen dinamico")
        self.checkbox_splash.setChecked(self.settings["use_dynamic_splash"])
        self.checkbox_splash.setStyleSheet("color: white; font-size:14px;")
        self.checkbox_splash.stateChanged.connect(self.on_splash_changed)
        content_layout.addWidget(self.checkbox_splash)
        label_version = QLabel(f"Versione launcher: {LAUNCHER_VERSION}")
        label_version.setStyleSheet("color: white; font-size: 14px;")
        content_layout.addWidget(label_version)
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                font-size: 16px;
                border-radius: 0px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        ok_button.clicked.connect(self.close)
        content_layout.addWidget(ok_button)
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget)
        self.setLayout(main_layout)
    def mousePressEvent(self, event):
        pass
    def mouseMoveEvent(self, event):
        pass
    def on_startup_changed(self, state):
        checked = (state == Qt.Checked)
        print("[DEBUG] on_startup_changed ->", checked)
        self.settings["start_with_windows"] = checked
        # Ottieni il percorso stabile dell'updater (se non è già copiato, lo copia)
        updater_exe_path = ensure_stable_location()
        # Registra il target (l'updater stabile) per l'avvio automatico
        set_autostart_in_registry(checked, target_executable=updater_exe_path)
        save_settings(self.settings)
    def on_splash_changed(self, state):
        checked = (state == Qt.Checked)
        print("[DEBUG] on_splash_changed ->", checked)
        self.settings["use_dynamic_splash"] = checked
        save_settings(self.settings)

# ------------------------------------------------------------
#              FINESTRA WARNING (TERMINI E CONDIZIONI)
# ------------------------------------------------------------
class WarningWindow(QDialog):
    def __init__(self):
        super().__init__()
        print("[DEBUG] WarningWindow __init__()")
        self.setWindowTitle("Installer di MrRevo")
        self.setFixedSize(700, 400)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #2c3e50;
                color: white;
                border-radius: 0px;
            }
            QLabel {
                color: white;
            }
        """)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            background-color: #34495e;
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
        """)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(10, 0, 10, 0)
        title_layout.addStretch()
        close_button = QPushButton("x")
        close_button.setFixedSize(30,30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        close_button.clicked.connect(self.close)
        title_layout.addWidget(close_button)
        title_bar.setLayout(title_layout)
        main_layout.addWidget(title_bar)
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20,20,20,20)
        terms_label = QLabel("""
Attenzione:
Questo è un installer creato da MrRevo.
Continuando, accetti di assumerti la piena responsabilità per l'uso di questo software,
poiché non è un installer certificato.
        """)
        terms_label.setFont(QFont("Arial", 16, QFont.Bold))
        terms_label.setAlignment(Qt.AlignCenter)
        terms_label.setWordWrap(True)
        content_layout.addWidget(terms_label)
        self.checkBox = QCheckBox("Accetto i termini*")
        self.checkBox.setFont(QFont("Arial",16))
        self.checkBox.setStyleSheet("color: white;")
        content_layout.addWidget(self.checkBox)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius: 0px;
                padding:5px 10px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        content_layout.addWidget(button_box)
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget)
        self.setLayout(main_layout)
        self.dragPos = QPoint()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.dragPos)
            event.accept()
    def accept(self):
        print("[DEBUG] WarningWindow accept() -> checkBox.isChecked():", self.checkBox.isChecked())
        if self.checkBox.isChecked():
            super().accept()
        else:
            print("[DEBUG] Checkbox non spuntata, mostro Warning.")
            QMessageBox.warning(self, "Attenzione", "Devi accettare i termini per continuare.")

# ------------------------------------------------------------
#            FINESTRA PRINCIPALE (FOLDERSELECTION)
# ------------------------------------------------------------
class FolderSelectionWindow(QWidget):
    def __init__(self, initial_valid_folders=None, online_version=None, settings=None):
        super().__init__()
        print("[DEBUG] FolderSelectionWindow __init__()")
        self.setWindowTitle("AutoInstaller Traduzione Star Citizen di MrRevoTV")
        self.setWindowIcon(QIcon(resource_path("MrRevo.ico")))
        self.resize(900, 600)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("""
            QWidget {
                background-color:#0f2c3e;
                color:white;
                border-radius: 0px;
            }
        """)
        self.dragPos = QPoint()
        self.settings = settings or {}
        self.online_version = online_version
        self.info_window = None
        self.settings_window = None
        self.help_window = None
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0,0,0,0)
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            background-color:#34495e;
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
        """)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(10, 0, 10, 0)
        settings_button = QPushButton("Impostazioni")
        settings_button.setFixedHeight(30)
        settings_button.setStyleSheet("""
            QPushButton {
                background-color:#34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        settings_button.clicked.connect(self.show_settings_window)
        title_layout.addWidget(settings_button)
        title_layout.addStretch()
        info_button = NoFocusButton("Extra")
        info_button.setFixedSize(60,30)
        info_button.setStyleSheet("""
            QPushButton {
                background-color:#34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        info_button.clicked.connect(self.show_info_window)
        title_layout.addWidget(info_button)
        title_layout.addStretch()
        minimize_button = QPushButton("-")
        minimize_button.setFixedSize(30,30)
        minimize_button.setStyleSheet("""
            QPushButton {
                background-color:#34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        minimize_button.clicked.connect(self.showMinimized)
        title_layout.addWidget(minimize_button)
        close_button = NoFocusButton("x")
        close_button.setFixedSize(30,30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color:#34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        close_button.clicked.connect(self.close)
        title_layout.addWidget(close_button)
        title_bar.setLayout(title_layout)
        main_layout.addWidget(title_bar)
        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(10,10,10,10)
        self.valid_folders = initial_valid_folders if initial_valid_folders else []
        self.checkboxes = {}
        self.instruction_label = QLabel("SEGUI LE ISTRUZIONI RIPORTATE IN BASSO PER USARE L'INSTALLER")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.instruction_label.setStyleSheet("color:white; font-size:20px; font-weight:bold;")
        content_layout.addWidget(self.instruction_label)
        self.image_layout = QHBoxLayout()
        self.image_label1 = QLabel()
        self.image_label2 = QLabel()
        self.image_label3 = QLabel()
        pixmap1 = QPixmap(resource_path("images/image1.png"))
        pixmap2 = QPixmap(resource_path("images/image2.png"))
        pixmap3 = QPixmap(resource_path("images/image3.png"))
        for label, pixmap in zip([self.image_label1, self.image_label2, self.image_label3],
                                 [pixmap1, pixmap2, pixmap3]):
            label.setPixmap(pixmap)
            label.setScaledContents(True)
            label.setFixedSize(120,120)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_layout.addWidget(self.image_label1)
        self.image_layout.addWidget(self.image_label2)
        self.image_layout.addWidget(self.image_label3)
        content_layout.addSpacing(30)
        content_layout.addLayout(self.image_layout)
        self.placeholder_label = QLabel(
            " -Premi 'Ricerca automatica' per cercare le versioni disponibili;\n"
            "-Seleziona solo una versione alla volta;\n"
            "-Oppure seleziona manualmente il percorso di installazione;"
        )
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("font-size:18px; padding:10px; color:white;")
        content_layout.addWidget(self.placeholder_label)
        self.checkbox_widget = QWidget()
        self.checkbox_layout = QVBoxLayout()
        self.checkbox_widget.setLayout(self.checkbox_layout)
        content_layout.addWidget(self.checkbox_widget)
        self.search_status_label = QLabel("Sto cercando le tue installazioni, attendi qualche secondo...")
        self.search_status_label.setAlignment(Qt.AlignCenter)
        self.search_status_label.setStyleSheet("font-size:18px; color:yellow;")
        self.search_status_label.hide()
        content_layout.addWidget(self.search_status_label)
        self.auto_progress_bar = QProgressBar()
        self.auto_progress_bar.setRange(0,100)
        self.auto_progress_bar.hide()
        content_layout.addWidget(self.auto_progress_bar)
        self.download_progress_bar = QProgressBar()
        self.download_progress_bar.setRange(0,100)
        self.download_progress_bar.hide()
        content_layout.addWidget(self.download_progress_bar)
        installed_ver = self.settings.get("installed_translation_version", "")
        if installed_ver:
            self.installed_label = QLabel(f"Versione installata {installed_ver}")
            self.installed_label.setAlignment(Qt.AlignCenter)
            self.installed_label.setStyleSheet("color: yellow; font-size:18px;")
            content_layout.addWidget(self.installed_label)
        if self.online_version and self.online_version != installed_ver:
            self.update_label = QLabel(f"Versione disponibile {self.online_version}")
            self.update_label.setAlignment(Qt.AlignCenter)
            self.update_label.setStyleSheet("color: yellow; font-size:18px;")
            content_layout.addWidget(self.update_label)
        manual_layout = QHBoxLayout()
        self.manual_line = QLineEdit()
        self.manual_line.setPlaceholderText("Nessun percorso selezionato manualmente")
        self.manual_line.setReadOnly(True)
        manual_layout.addWidget(self.manual_line)
        manual_btn = QPushButton("Scegli cartella")
        manual_btn.setStyleSheet("""
            QPushButton {
                background-color:#34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        manual_btn.clicked.connect(self.select_manual_folder)
        manual_layout.addWidget(manual_btn)
        content_layout.addLayout(manual_layout)
        auto_btn = QPushButton("Ricerca automatica")
        auto_btn.setStyleSheet("""
            QPushButton {
                background-color:#8e44ad;
                color:white;
                font-weight:bold;
                font-size:18px;
                padding:10px 20px;
                border-radius:0px;
            }
            QPushButton:hover {
                background-color:#9b59b6;
            }
        """)
        auto_btn.clicked.connect(self.start_auto_search)
        content_layout.addWidget(auto_btn)
        self.install_button = QPushButton("Installa traduzione")
        self.install_button.setStyleSheet("""
            QPushButton {
                background-color:#4CAF50;
                color:white;
                font-weight:bold;
                font-size:18px;
                padding:10px 20px;
                border-radius:0px;
            }
            QPushButton:hover {
                background-color:#45a049;
            }
        """)
        self.install_button.clicked.connect(self.install)
        self.install_button.hide()
        content_layout.addWidget(self.install_button)
        self.remove_button = QPushButton("Rimuovi traduzione")
        self.remove_button.setStyleSheet("""
            QPushButton {
                background-color:#f44336;
                color:white;
                font-weight:bold;
                font-size:18px;
                padding:10px 20px;
                border-radius:0px;
            }
            QPushButton:hover {
                background-color:#e53935;
            }
        """)
        self.remove_button.clicked.connect(self.remove)
        self.remove_button.hide()
        content_layout.addWidget(self.remove_button)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color:white; padding:10px; font-weight:bold;")
        self.status_label.hide()
        content_layout.addWidget(self.status_label)
        help_layout = QHBoxLayout()
        help_layout.addStretch()
        help_button = QPushButton("Help")
        help_button.setFixedSize(80, 35)
        help_button.setStyleSheet("""
            QPushButton {
                background-color:#34495e;
                color:white;
                border:none;
                font-size:16px;
                border-radius:0px;
            }
            QPushButton:hover {
                background-color:#555;
            }
        """)
        help_button.clicked.connect(self.show_help_window)
        help_layout.addWidget(help_button)
        content_layout.addLayout(help_layout)
        content.setLayout(content_layout)
        main_layout.addWidget(content)
        self.setLayout(main_layout)
        self.fake_progress = 0
        self.fake_timer = QTimer(self)
        self.fake_timer.timeout.connect(self.update_fake_progress)
        last_folder = self.settings.get("last_selected_folder", "")
        if last_folder:
            if os.path.exists(last_folder):
                folder_name = os.path.basename(last_folder)
                if not any(last_folder == p for _, p in self.valid_folders):
                    self.valid_folders.append((folder_name, last_folder))
            else:
                self.settings["last_selected_folder"] = ""
                save_settings(self.settings)
                last_folder = ""
        if self.valid_folders:
            self.instruction_label.setText(
                "SELEZIONA LA VERSIONE DI STAR CITIZEN\nALLA QUALE VUOI AGGIUNGERE O RIMUOVERE LA TRADUZIONE"
            )
        self.add_checkboxes(self.valid_folders)
        if last_folder:
            for cb, (n, p) in self.checkboxes.items():
                if p == last_folder:
                    cb.setChecked(True)
                    self.placeholder_label.hide()
                    self.install_button.show()
                    self.remove_button.show()
                    break
    def show_help_window(self):
        if not self.help_window:
            self.help_window = HelpWindow()
        self.help_window.show()
    def show_settings_window(self):
        print("[DEBUG] show_settings_window() chiamato")
        if not self.settings_window:
            print("[DEBUG] Creo SettingsWindow per la prima volta.")
            self.settings_window = SettingsWindow(self.settings)
        self.settings_window.show()
    def show_info_window(self):
        print("[DEBUG] show_info_window() chiamato")
        self.info_window = InfoWindow()
        self.info_window.show()
    def closeEvent(self, event):
        print("[DEBUG] FolderSelectionWindow closeEvent - chiusura finestra.")
        if self.info_window and self.info_window.isVisible():
            self.info_window.close()
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.close()
        if self.help_window and self.help_window.isVisible():
            self.help_window.close()
        super().closeEvent(event)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.dragPos)
            event.accept()
    def update_fake_progress(self):
        self.fake_progress += 2
        self.auto_progress_bar.setValue(self.fake_progress)
        if self.fake_progress >= 80:
            self.fake_timer.stop()
    def add_checkboxes(self, folders):
        print("[DEBUG] add_checkboxes() -> folders:", folders)
        if folders:
            self.placeholder_label.hide()
        folders = sorted(folders, key=lambda f: 0 if f[0].upper() == "LIVE" else 1)
        for folder_name, folder_path in folders:
            if not any(folder_path == p for (_, p) in self.checkboxes.values()):
                checkbox = QCheckBox(folder_name)
                checkbox.folder_path = folder_path
                checkbox.setStyleSheet("""
                    QCheckBox {
                        font-size:18px;
                        color:white;
                        padding:10px;
                        min-height:50px;
                    }
                    QCheckBox::indicator {
                        subcontrol-position:left center;
                        margin-right:10px;
                    }
                """)
                self.checkbox_layout.addWidget(checkbox)
                self.checkboxes[checkbox] = (folder_name, folder_path)
    def select_manual_folder(self):
        print("[DEBUG] select_manual_folder() chiamato.")
        folder = QFileDialog.getExistingDirectory(self, "Seleziona la cartella di installazione")
        if folder:
            print("[DEBUG] Cartella selezionata manualmente:", folder)
            self.manual_line.setText(folder)
            folder_name = os.path.basename(folder)
            if not any(folder == p for (_, p) in self.valid_folders):
                self.valid_folders.append((folder_name, folder))
            self.add_checkboxes(self.valid_folders)
            for cb, (n, p) in self.checkboxes.items():
                if p == folder:
                    cb.setChecked(True)
                    self.placeholder_label.hide()
                    break
            self.install_button.show()
            self.remove_button.show()
            self.settings["last_selected_folder"] = folder
            save_settings(self.settings)
        else:
            print("[DEBUG] Nessuna cartella scelta.")
            self.manual_line.setText("Nessun percorso selezionato manualmente")
    def collect_selected_folders(self):
        return [(name, path) for cb, (name, path) in self.checkboxes.items() if cb.isChecked()]
    def install(self):
        print("[DEBUG] install() chiamato.")
        selected_folders = self.collect_selected_folders()
        if not selected_folders:
            self.show_status("Per piacere seleziona una versione", "rgba(255, 255, 0, 128)", 0)
            return
        folder = selected_folders[0]
        print("[DEBUG] Install su cartella:", folder)
        self.download_progress_bar.show()
        self.download_progress_bar.setValue(0)
        self.install_button.setEnabled(False)
        self.download_thread = DownloadThread(folder)
        self.download_thread.progress_signal.connect(self.download_progress_bar.setValue)
        self.download_thread.finished_signal.connect(self.install_finished)
        self.download_thread.start()
        self.settings["last_selected_folder"] = folder[1]
        save_settings(self.settings)
    def install_finished(self, success):
        print("[DEBUG] install_finished success=", success)
        self.install_button.setEnabled(True)
        if success:
            if self.online_version:
                self.settings["installed_translation_version"] = self.online_version
                save_settings(self.settings)
            reply = QMessageBox.question(
                self,
                "Installazione completata",
                "Traduzione installata.\nVuoi installarla anche in un'altra cartella?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                print("[DEBUG] L'utente vuole continuare a installare in altre cartelle.")
                self.status_label.setText("Puoi continuare ad usare l'installer.")
                self.status_label.setStyleSheet("background-color: rgba(0, 255, 0, 128); color:black; padding:10px; font-weight:bold;")
                self.status_label.show()
                QTimer.singleShot(3000, self.status_label.hide)
            else:
                print("[DEBUG] L'utente ha finito, chiusura in 3 secondi.")
                self.show_status("Grazie per aver supportato il progetto!\nChiusura automatica in corso", "rgba(0, 255, 0, 128)", 3000)
                QTimer.singleShot(3000, self.close)
        else:
            print("[DEBUG] Errore durante l'installazione.")
            self.show_status("Errore durante l'installazione", "rgba(255, 0, 0, 128)", 0)
        self.download_progress_bar.hide()
    def remove(self):
        print("[DEBUG] remove() chiamato.")
        selected_folders = self.collect_selected_folders()
        if not selected_folders:
            self.show_status("Per piacere seleziona una versione", "rgba(255, 255, 0, 128)", 0)
            return
        for folder_name, folder_path in selected_folders:
            print(f"[DEBUG] Rimuovo la traduzione da {folder_name} -> {folder_path}")
            data_folder = os.path.join(folder_path, "data")
            config_path = os.path.join(folder_path, "user.cfg")
            if os.path.exists(config_path):
                os.remove(config_path)
            if os.path.exists(data_folder):
                localization_folder = os.path.join(data_folder, "Localization")
                if os.path.exists(localization_folder):
                    italian_folder = os.path.join(localization_folder, "italian_(italy)")
                    if os.path.exists(italian_folder):
                        for root, dirs, files in os.walk(italian_folder, topdown=False):
                            for file in files:
                                os.remove(os.path.join(root, file))
                            for dir in dirs:
                                os.rmdir(os.path.join(root, dir))
                        os.rmdir(italian_folder)
                    if not os.listdir(localization_folder):
                        os.rmdir(localization_folder)
                if not os.listdir(data_folder):
                    os.rmdir(data_folder)
            self.show_status("Traduzione rimossa\nCHIUSURA IMMINENTE", "rgba(255, 0, 0, 128)", 5000)
            return
    def show_status(self, message, color, close_after_ms):
        print(f"[DEBUG] show_status -> {message}")
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"background-color:{color}; color:black; padding:10px; font-weight:bold;")
        self.status_label.show()
        if close_after_ms:
            QTimer.singleShot(close_after_ms, self.close)
    def start_auto_search(self):
        print("[DEBUG] start_auto_search() chiamato.")
        for i in reversed(range(self.checkbox_layout.count())):
            widget_to_remove = self.checkbox_layout.itemAt(i).widget()
            if widget_to_remove is not None:
                widget_to_remove.setParent(None)
        self.checkboxes.clear()
        self.placeholder_label.hide()
        self.search_status_label.show()
        self.auto_progress_bar.show()
        self.fake_progress = 0
        self.auto_progress_bar.setValue(self.fake_progress)
        self.fake_timer.start(210)
        self.search_thread = ProgressThread()
        self.search_thread.result_signal.connect(self.auto_search_finished)
        self.search_thread.start()
    def auto_search_finished(self, folders):
        print("[DEBUG] auto_search_finished ->", folders)
        self.fake_timer.stop()
        self.auto_progress_bar.setValue(100)
        QTimer.singleShot(500, self.auto_progress_bar.hide)
        self.search_status_label.hide()
        if folders:
            self.instruction_label.setText("SELEZIONA LA VERSIONE DI STAR CITIZEN\nALLA QUALE VUOI AGGIUNGERE O RIMUOVERE LA TRADUZIONE")
            self.add_checkboxes(folders)
            self.install_button.show()
            self.remove_button.show()
        else:
            QMessageBox.warning(self, "Ricerca completata", "Nessuna cartella valida trovata.")

# ------------------------------------------------------------
#              FLUSSO PRINCIPALE
# ------------------------------------------------------------
def handle_terms_and_update(settings, online_version):
    print("[DEBUG] handle_terms_and_update() chiamato - mostro WarningWindow.")
    warning_window = WarningWindow()
    result = warning_window.exec_()
    print("[DEBUG] Risultato di warning_window.exec_():", result)
    if result == QDialog.Accepted:
        print("[DEBUG] L'utente ha accettato i termini.")
        if online_version is None:
            online_version = CURRENT_INSTALLER_VERSION
        folder_window = FolderSelectionWindow(online_version=online_version, settings=settings)
        folder_window.show()
        global main_window
        main_window = folder_window
    else:
        print("[DEBUG] L'utente NON ha accettato i termini. sys.exit(0).")
        sys.exit(0)

def run_installer():
    print("[DEBUG] run_installer() - Avvio dell'app.")
    app = QApplication(sys.argv)
    settings = load_settings()
    print("[DEBUG] Impostazioni:", settings)
    version_thread_result = {"version": None}
    def on_version_found(version_str):
        print("[DEBUG] VersionCheckThread -> versione trovata:", version_str)
        version_thread_result["version"] = version_str
    version_thread = VersionCheckThread()
    version_thread.version_found.connect(on_version_found)
    version_thread.start()
    splash_shown = False
    if settings.get("use_dynamic_splash", True):
        splash_pixmap = download_splash_image(SPLASH_IMAGE_URL)
        if splash_pixmap:
            splash = QSplashScreen(splash_pixmap)
            splash.show()
            splash_shown = True
            QApplication.processEvents()
    else:
        local_splash_path = resource_path(STATIC_SPLASH_FILENAME)
        if os.path.exists(local_splash_path):
            static_pixmap = QPixmap(local_splash_path)
            if not static_pixmap.isNull():
                splash = QSplashScreen(static_pixmap)
                splash.show()
                splash_shown = True
                QApplication.processEvents()
            else:
                print("[DEBUG] Impossibile caricare lo splash statico: pixmap nulla.")
        else:
            print("[DEBUG] File statico non trovato:", local_splash_path)
    def close_splash_and_continue():
        if splash_shown:
            splash.close()
        handle_terms_and_update(settings, online_version=version_thread_result["version"])
    QTimer.singleShot(3000, close_splash_and_continue)
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_installer()
