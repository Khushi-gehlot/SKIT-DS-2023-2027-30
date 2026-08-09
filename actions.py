import os
import webbrowser
import subprocess
import ctypes
import smtplib
from email.message import EmailMessage
import urllib.parse
import pyautogui
import keyboard
import psutil

from core import speak, recognize_speech

pyautogui.FAILSAFE = False


# =============== BASIC HELPERS ===============

def _open_ms_settings(page: str, description: str):
    """
    Helper to open Windows Settings pages using ms-settings: URIs.
    Example: ms-settings:display, ms-settings:sound, etc.
    """
    try:
        speak(f"Opening {description} settings.")
        subprocess.Popen(f"start ms-settings:{page}", shell=True)
    except Exception as e:
        print(f"Settings open error ({description}):", e)
        speak(f"Sorry, I could not open {description} settings. Error: {e}")


# =============== SIMPLE ACTIONS (WEB / SCROLL / SCREEN) ===============

def search_google_voice():
    speak("What do you want to search on Google?")
    query = recognize_speech()

    if not query:
        speak("I did not catch the search term.")
        return

    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)

    speak(f"Searching Google for {query}")
    webbrowser.open(url)


def search_youtube_voice():
    speak("What do you want to search on YouTube?")
    query = recognize_speech()

    if not query:
        speak("I did not catch the search term.")
        return

    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)

    speak(f"Searching YouTube for {query}")
    webbrowser.open(url)


def open_default_browser():
    speak("Opening your default browser.")
    webbrowser.open("https://www.google.com")

# =============== CURSOR CONTROL ===============

def move_cursor_up():
    x, y = pyautogui.position()
    pyautogui.moveTo(x, y - 50)
    speak("Moving cursor up")


def move_cursor_down():
    x, y = pyautogui.position()
    pyautogui.moveTo(x, y + 50)
    speak("Moving cursor down")


def move_cursor_left():
    x, y = pyautogui.position()
    pyautogui.moveTo(x - 50, y)
    speak("Moving cursor left")


def move_cursor_right():
    x, y = pyautogui.position()
    pyautogui.moveTo(x + 50, y)
    speak("Moving cursor right")


def click_cursor():
    speak("Clicking")
    pyautogui.click()


def double_click_cursor():
    speak("Double clicking")
    pyautogui.doubleClick()


def right_click_cursor():
    speak("Right click")
    pyautogui.rightClick()

def scroll_down():
    speak("Scrolling down.")
    pyautogui.scroll(-500)


def scroll_up():
    speak("Scrolling up.")
    pyautogui.scroll(500)


def take_screenshot():
    """Takes a screenshot and saves it in the current working directory."""
    try:
        screenshot = pyautogui.screenshot()
        file_path = os.path.join(os.getcwd(), "screenshot.png")
        screenshot.save(file_path)
        speak(f"Screenshot saved as screenshot.png in {os.getcwd()}")
    except Exception as e:
        print("Screenshot error:", e)
        speak(f"Sorry, I could not take a screenshot. Error: {e}")


# =============== POWER / BATTERY ===============

def shutdown_system():
    speak("Are you sure you want to shutdown? Say yes to confirm.")
    confirmation = recognize_speech()
    if confirmation and "yes" in confirmation:
        speak("Shutting down now.")
        os.system("shutdown /s /t 1")
    else:
        speak("Shutdown cancelled.")


def restart_system():
    speak("Are you sure you want to restart? Say yes to confirm.")
    confirmation = recognize_speech()
    if confirmation and "yes" in confirmation:
        speak("Restarting now.")
        os.system("shutdown /r /t 1")
    else:
        speak("Restart cancelled.")


def show_battery():
    battery = psutil.sensors_battery()
    if not battery:
        speak("Cannot read battery status.")
        return
    percent = battery.percent
    speak(f"Battery level is {percent} percent.")


# =============== APPS ===============

def open_notepad():
    speak("Opening Notepad.")
    subprocess.Popen("notepad.exe")


def open_calculator():
    speak("Opening Calculator.")
    subprocess.Popen("calc.exe")


def open_cmd():
    speak("Opening Command Prompt.")
    subprocess.Popen("cmd.exe")


def open_file_explorer():
    speak("Opening File Explorer.")
    subprocess.Popen("explorer")


def open_control_panel():
    speak("Opening Control Panel.")
    subprocess.Popen("control.exe")


def open_task_manager():
    speak("Opening Task Manager.")
    subprocess.Popen("taskmgr.exe")


# =============== FOLDERS ===============

def open_downloads_folder():
    speak("Opening Downloads folder.")
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    subprocess.Popen(f'explorer "{downloads}"')


def open_documents_folder():
    speak("Opening Documents folder.")
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    subprocess.Popen(f'explorer "{docs}"')


def open_desktop_folder():
    speak("Opening Desktop folder.")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    subprocess.Popen(f'explorer "{desktop}"')

def open_videos_folder():
    speak("Opening Videos folder.")
    videos = os.path.join(os.path.expanduser("~"), "Videos")
    subprocess.Popen(f'explorer "{videos}"')

def open_pictures_folder():
    speak("Opening Pictures folder.")
    pictures = os.path.join(os.path.expanduser("~"), "Pictures")
    subprocess.Popen(f'explorer "{pictures}"')

def open_music_folder():
    speak("Opening Music folder.")
    music = os.path.join(os.path.expanduser("~"), "Music")
    subprocess.Popen(f'explorer "{music}"')

def open_this_pc():
    speak("Opening This PC.")
    this_pc = os.path.join(os.path.expanduser("~"), "This PC")
    subprocess.Popen(f'explorer "{this_pc}"')
# =============== WINDOW MANAGEMENT ===============

def show_desktop():
    speak("Showing desktop.")
    pyautogui.hotkey("win", "d")


def minimize_window():
    speak("Minimizing current window.")
    pyautogui.hotkey("win", "down")


def maximize_window():
    speak("Maximizing current window.")
    pyautogui.hotkey("win", "up")


def close_window():
    speak("Closing current window.")
    pyautogui.hotkey("alt", "f4")


def switch_window():
    speak("Switching window.")
    pyautogui.hotkey("alt", "tab")


# =============== SYSTEM CONTROL / VOLUME / MEDIA ===============

def volume_up():
    speak("Increasing volume.")
    for _ in range(5):
        keyboard.press_and_release("volume up")


def volume_down():
    speak("Decreasing volume.")
    for _ in range(5):
        keyboard.press_and_release("volume down")


def mute_volume():
    speak("Muting volume.")
    keyboard.press_and_release("volume mute")


def unmute_volume():
    speak("Unmuting volume.")
    keyboard.press_and_release("volume mute")  # same key toggles mute/unmute


def media_play_pause():
    speak("Toggling play or pause.")
    keyboard.press_and_release("play/pause media")


def media_next():
    speak("Playing next track.")
    keyboard.press_and_release("next track")


def media_previous():
    speak("Playing previous track.")
    keyboard.press_and_release("previous track")


def lock_system():
    speak("Locking system.")
    ctypes.windll.user32.LockWorkStation()


def sleep_system():
    speak("Putting system to sleep.")
    # 0,1,0 => standby, force, disable wake events
    ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)


# =============== WINDOWS SETTINGS (ms-settings URIs) ===============

def open_settings():
    _open_ms_settings("", "Settings")


# ---- System / Display / Sound ----

def open_display_settings():
    _open_ms_settings("display", "Display")


def open_sound_settings():
    _open_ms_settings("sound", "Sound")


def open_notifications_settings():
    _open_ms_settings("notifications", "Notifications")


def open_power_sleep_settings():
    _open_ms_settings("powersleep", "Power and sleep")


def open_storage_settings():
    _open_ms_settings("storagesense", "Storage")


def open_multitasking_settings():
    _open_ms_settings("multitasking", "Multitasking")


def open_clipboard_settings():
    _open_ms_settings("clipboard", "Clipboard")


# ---- Personalization ----

def open_personalization_settings():
    _open_ms_settings("personalization", "Personalization")


def open_background_settings():
    _open_ms_settings("personalization-background", "Background")


def open_colors_settings():
    _open_ms_settings("personalization-colors", "Color")


def open_lock_screen_settings():
    _open_ms_settings("lockscreen", "Lock screen")


def open_themes_settings():
    _open_ms_settings("themes", "Themes")


def open_fonts_settings():
    _open_ms_settings("fonts", "Fonts")


def open_start_menu_settings():
    _open_ms_settings("personalization-start", "Start menu")


def open_taskbar_settings():
    _open_ms_settings("taskbar", "Taskbar")


# ---- Time & language ----

def open_time_language_settings():
    _open_ms_settings("datelanguage", "Time and language")


def open_date_time_settings():
    _open_ms_settings("dateandtime", "Date and time")


def open_region_language_settings():
    _open_ms_settings("regionlanguage", "Region and language")


def open_language_settings():
    _open_ms_settings("language", "Language")


# ---- Network & Internet ----

def open_network_settings():
    _open_ms_settings("network", "Network and Internet")


def open_wifi_settings():
    _open_ms_settings("network-wifi", "Wi-Fi")


def open_ethernet_settings():
    _open_ms_settings("network-ethernet", "Ethernet")


# ---- Devices ----

def open_bluetooth_settings():
    _open_ms_settings("bluetooth", "Bluetooth")


def open_devices_settings():
    _open_ms_settings("devices", "Devices")


def open_mouse_settings():
    _open_ms_settings("devices-mouse", "Mouse")


def open_keyboard_settings():
    _open_ms_settings("keyboard", "Keyboard")


def open_touchpad_settings():
    _open_ms_settings("devices-touchpad", "Touchpad")


def open_printers_settings():
    _open_ms_settings("printers", "Printers and scanners")


# ---- Update / Security / Privacy ----

def open_updates_settings():
    _open_ms_settings("windowsupdate", "Windows Update")


def open_windows_security_settings():
    _open_ms_settings("windowsdefender", "Windows Security")


def open_privacy_settings():
    _open_ms_settings("privacy", "Privacy")


# ---- Gaming ----

def open_gaming_settings():
    _open_ms_settings("gaming-gamebar", "Gaming")


def open_game_bar_settings():
    _open_ms_settings("gaming-gamebar", "Game bar")


def open_captures_settings():
    _open_ms_settings("gaming-gamedvr", "Captures")


def open_game_mode_settings():
    _open_ms_settings("gaming-gamemode", "Game mode")


# =============== EMAIL FUNCTION ===============

def send_email_voice():
    """
    Send an email using voice input.
    Assistant asks for receiver email, subject and body.
    """

    try:

        speak("Please say the receiver email address.")
        receiver = recognize_speech()

        if not receiver:
            speak("I could not understand the email address.")
            return

        receiver = receiver.replace(" ", "").lower()

        speak("What is the subject?")
        subject = recognize_speech()

        if not subject:
            speak("Subject not detected.")
            return

        speak("What should I write in the email?")
        body = recognize_speech()

        if not body:
            speak("Email body not detected.")
            return

        sender_email = "kryptoniantechgamer25082003@gmail.com"
        sender_password = "tniw eimb wwya yxyb"

        msg = EmailMessage()
        msg["From"] = sender_email
        msg["To"] = receiver
        msg["Subject"] = subject
        msg.set_content(body)

        speak("Sending the email.")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)

        speak("Email sent successfully.")

    except Exception as e:
        print("Email error:", e)
        speak("Sorry, I could not send the email.")