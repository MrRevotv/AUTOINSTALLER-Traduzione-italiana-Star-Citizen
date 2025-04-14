import sys
import os
import json
import requests
import subprocess
import shutil
import winreg  # Per avvio automatico su Windows

# Definisce la cartella di destinazione in LOCALAPPDATA per l’updater stabile
SETTINGS_FOLDER = os.path.join(os.getenv('LOCALAPPDATA'), "InstallerTraduzioneMRREVO")
if not os.path.exists(SETTINGS_FOLDER):
    os.makedirs(SETTINGS_FOLDER)

# URL del file remoto contenente le info di aggiornamento
LAUNCHER_UPDATE_INFO_URL = "https://www.mrrevo.it/s/LrEJSBT9dWbRLYJ/download/launcher_info.txt"
# Versione corrente, usata come fallback (in caso non si riesca a leggere il JSON)
CURRENT_INSTALLER_VERSION = "0"

def get_installed_installer_version():
    """
    Legge il file JSON "installer_version.json" nella cartella SETTINGS_FOLDER
    e restituisce il numero di versione installato. Se non esiste, restituisce "0".
    """
    json_path = os.path.join(SETTINGS_FOLDER, "installer_version.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            version = data.get("version", "0")
            print(f"DEBUG: Installed installer version (JSON): {version}")
            return version
        except Exception as e:
            print("DEBUG: Errore leggendo il file JSON della versione:", e)
            return "0"
    else:
        print("DEBUG: Nessun file JSON trovato, assumo versione '0'.")
        return "0"

def save_installed_installer_version(version):
    """
    Salva la versione installata in un file JSON nella cartella SETTINGS_FOLDER.
    """
    json_path = os.path.join(SETTINGS_FOLDER, "installer_version.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"version": version}, f, ensure_ascii=False, indent=4)
        print(f"DEBUG: Aggiornata versione nel JSON a: {version}")
    except Exception as e:
        print("DEBUG: Errore salvando il file JSON della versione:", e)

def check_installer_update():
    """
    Richiede il file remoto (launcher_info.txt) e restituisce una tupla
    (online_version, download_link). Se c'è un errore, restituisce (None, None).
    """
    try:
        print("DEBUG: Richiedo il file remoto all'URL:", LAUNCHER_UPDATE_INFO_URL)
        response = requests.get(LAUNCHER_UPDATE_INFO_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        print("DEBUG: Status code ricevuto:", response.status_code)
        print("DEBUG: Contenuto del file remoto:", repr(response.text))
        if response.status_code == 200:
            lines = response.text.strip().splitlines()
            print("DEBUG: Numero di righe lette dal file:", len(lines))
            if len(lines) >= 2:
                online_version = lines[0].strip()
                download_link = lines[1].strip()
                print("DEBUG: Versione online letta:", online_version)
                print("DEBUG: Download link letto:", download_link)
                return online_version, download_link
            else:
                print("DEBUG: Il file remoto non contiene almeno 2 righe.")
        else:
            print("DEBUG: Il server non ha restituito il codice 200.")
    except Exception as e:
        print("DEBUG: Errore nel controllo aggiornamenti:", e)
    return None, None

def download_installer(download_url, new_version):
    """
    Scarica l'installer dal download_url e lo salva nella cartella SETTINGS_FOLDER.
    Utilizza l'header "User-Agent" per simulare una richiesta da browser.
    Restituisce il percorso del file scaricato, oppure None in caso di errore.
    """
    installer_filename = f"installer_{new_version}.exe"
    installer_path = os.path.join(SETTINGS_FOLDER, installer_filename)
    try:
        print(f"DEBUG: Scarico il nuovo installer versione {new_version} in {installer_path}...")
        response = requests.get(download_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=10)
        print("DEBUG: Status code del download:", response.status_code)
        response.raise_for_status()
        with open(installer_path, 'wb') as f:
            total_bytes = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_bytes += len(chunk)
            print("DEBUG: Totale byte scaricati:", total_bytes)
        print("DEBUG: Download completato!")
        return installer_path
    except Exception as e:
        print("DEBUG: Errore nel download dell'installer:", e)
        return None

def remove_old_installers(current_version):
    """
    Rimuove tutti i file installer_*.exe nella cartella SETTINGS_FOLDER che non
    corrispondono alla current_version.
    """
    for filename in os.listdir(SETTINGS_FOLDER):
        if filename.startswith("installer_") and filename.endswith(".exe"):
            if current_version not in filename:
                file_path = os.path.join(SETTINGS_FOLDER, filename)
                try:
                    os.remove(file_path)
                    print(f"DEBUG: Eliminato vecchio installer: {file_path}")
                except Exception as e:
                    print(f"DEBUG: Errore eliminando {file_path}: {e}")

def launch_installer(installer_path):
    """
    Avvia l'installer tramite subprocess.
    """
    try:
        print(f"DEBUG: Lancio l'installer da: {installer_path}")
        subprocess.Popen([installer_path], shell=True)
    except Exception as e:
        print("DEBUG: Errore lanciando l'installer:", e)

# ===============================================
# Gestione della posizione stabile dell’updater
# ===============================================
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
    Se il file eseguibile corrente (l'updater) non si trova nella posizione stabile,
    lo copia lì e restituisce il percorso stabile.
    """
    stable_path = get_stable_updater_path()
    current_path = os.path.abspath(sys.argv[0])
    if current_path.lower() != stable_path.lower():
        try:
            shutil.copy2(current_path, stable_path)
            print(f"DEBUG: Copiato l'updater in posizione stabile: {stable_path}")
        except Exception as e:
            print("DEBUG: Errore copiando l'updater nella posizione stabile:", e)
    else:
        print("DEBUG: L'updater è già nella posizione stabile.")
    return stable_path

# ===============================================
# FLUSSO PRINCIPALE DELL'UPDATER
# ===============================================
def main():
    print("DEBUG: Avvio dell'updater.")
    # Recupera le informazioni dal file remoto
    online_version, download_link = check_installer_update()
    if online_version is None or download_link is None:
        online_version = CURRENT_INSTALLER_VERSION
        print("DEBUG: Impossibile recuperare le informazioni di aggiornamento, uso la versione corrente:", online_version)
    
    installed_version = get_installed_installer_version()
    try:
        update_needed = float(online_version) > float(installed_version)
    except Exception as e:
        print("DEBUG: Errore nel confronto delle versioni:", e)
        update_needed = online_version != installed_version

    print(f"DEBUG: Versione online: {online_version} vs Installata: {installed_version}. Update needed: {update_needed}")
    
    installer_filename = f"installer_{online_version}.exe"
    installer_path = os.path.join(SETTINGS_FOLDER, installer_filename)
    
    if update_needed or not os.path.exists(installer_path):
        print("DEBUG: Scarico la nuova versione dell'installer...")
        new_installer_path = download_installer(download_link, online_version)
        if new_installer_path is None:
            print("DEBUG: Errore nel download dell'installer. Impossibile continuare.")
            sys.exit(1)
        installer_path = new_installer_path
        save_installed_installer_version(online_version)
        remove_old_installers(online_version)
    else:
        print("DEBUG: Nessun aggiornamento necessario. Uso l'installer già presente.")
    
    if installer_path and os.path.exists(installer_path):
        launch_installer(installer_path)
    else:
        print("DEBUG: Errore: installer non disponibile.")
    
    sys.exit(0)

if __name__ == "__main__":
    # Assicuriamoci che l'updater si installi nella posizione stabile
    stable_updater_path = ensure_stable_location()
    main()
