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


def open_settings_page(page: str):
    """
    Open a Windows Settings page by its ms-settings key.

    Parameterised entry point for the executor: one handler covers all forty
    settings pages instead of forty near-identical functions. An empty page
    opens the Settings home screen.
    """
    _open_ms_settings(page, page.replace("-", " ") if page else "Settings")


def ask_for_query(prompt: str) -> str | None:
    """Speak a prompt and listen for the answer. Used for search terms."""
    speak(prompt)
    return recognize_speech()


SEARCH_URLS = {
    "google": "https://www.google.com/search?q=",
    "youtube": "https://www.youtube.com/results?search_query=",
}


def search_web(engine: str, query: str):
    """Search the web in the default browser."""
    base = SEARCH_URLS.get(engine, SEARCH_URLS["google"])
    speak(f"Searching {engine} for {query}")
    webbrowser.open(base + urllib.parse.quote(query))


def open_url(url: str):
    """Open a URL in the default browser."""
    if not url.startswith("http"):
        url = "https://" + url
    speak(f"Opening {url}")
    webbrowser.open(url)


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
    """Take a screenshot, save it, and return the path."""
    try:
        screenshot = pyautogui.screenshot()
        file_path = os.path.join(os.getcwd(), "screenshot.png")
        screenshot.save(file_path)
        speak(f"Screenshot saved as screenshot.png in {os.getcwd()}")
        return file_path
    except Exception as e:
        print("Screenshot error:", e)
        speak(f"Sorry, I could not take a screenshot. Error: {e}")
        return None


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
    """Speak the battery level and return the percentage."""
    battery = psutil.sensors_battery()
    if not battery:
        speak("Cannot read battery status.")
        return None
    percent = battery.percent
    speak(f"Battery level is {percent} percent.")
    return percent


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
    # There is no "~/This PC" folder; This PC is a shell namespace location.
    subprocess.Popen("explorer shell:MyComputerFolder")


def open_youtube():
    speak("Opening YouTube.")
    webbrowser.open("https://www.youtube.com")


def open_google():
    speak("Opening Google.")
    webbrowser.open("https://www.google.com")
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

# =============== SPEAKER ENROLMENT ===============

def enrol_voice():
    """
    Walk the user through recording a voiceprint.

    Several short phrases rather than one long one: averaging across
    separate recordings captures the voice on more than one breath, so
    verification still works when the user is tired or sitting further away.
    """
    import auth
    import config
    import core

    if not auth.is_available():
        speak("Speaker verification is not installed on this computer.")
        return

    speak(
        f"I will learn your voice. Please repeat {config.ENROLMENT_SAMPLES} "
        "short phrases after me."
    )

    samples = []
    for number, phrase in enumerate(config.ENROLMENT_PHRASES[:config.ENROLMENT_SAMPLES], 1):
        speak(f"Phrase {number}. {phrase}")
        _text, audio = core.listen(timeout=8, phrase_time_limit=6)
        if audio is None:
            speak("I did not hear that one. Let us carry on.")
            continue
        samples.append(audio)

    result = auth.enroll(samples)
    speak(result.message)
    return result.allowed


def forget_voice():
    """Delete the stored voiceprint."""
    import auth
    speak(auth.unenroll().message)


def voice_status():
    """Say whether anyone is enrolled, and where their voiceprint is kept."""
    import auth
    import config
    if not auth.is_available():
        speak("Speaker verification is not installed.")
        return

    storage = auth.storage_status()
    # Printed rather than spoken: the user wants to hear whether they are
    # enrolled, not a database connection string read out loud.
    print(f"Voiceprint storage: {storage['location']}")
    if storage["fallback_reason"]:
        print(f"  (MongoDB was unavailable: {storage['fallback_reason']})")

    if not auth.is_enrolled():
        speak("No voice is enrolled yet. Say 'enrol my voice' to set it up.")
        return

    state = "on" if config.REQUIRE_SPEAKER_VERIFICATION else "off"
    where = "a database" if storage["backend"] == "mongodb" else "a local file"
    speak(
        f"Your voice is enrolled and stored in {where}, "
        f"and verification is currently {state}."
    )


def check_voice():
    """
    Record one phrase and report how closely it matches the enrolled voice.

    A diagnostic, not a gate: it runs whether or not verification is switched
    on, which makes it the way to see real match scores and pick a sensible
    threshold. Guessing a threshold without ever seeing your own numbers is
    how these systems end up either trivially bypassed or unusable.
    """
    import auth
    import config
    import core

    if not auth.is_available():
        speak("Speaker verification is not installed.")
        return
    if not auth.is_enrolled():
        speak("No voice is enrolled yet. Say 'enrol my voice' first.")
        return

    speak("Say anything, and I will tell you how well it matches.")
    _text, audio = core.listen(timeout=8, phrase_time_limit=6)
    if audio is None:
        speak("I did not hear anything.")
        return

    result = auth.verify_audio(audio)
    score = result.similarity or 0.0
    threshold = config.SPEAKER_SIMILARITY_THRESHOLD
    verdict = "a match" if result.allowed else "not a match"

    speak(f"That scored {score:.0%}. Threshold is {threshold:.0%}, so that is {verdict}.")
    print(f"  similarity {score:.3f}  threshold {threshold:.3f}  -> {verdict}")
    return score


# =============== TYPING ANYWHERE ===============
#
# Dictation into whatever window currently has focus: Notepad, a WhatsApp
# message box, a search bar, a spreadsheet cell. The browser has its own
# typing path that locates a field by label, but that only works on a web
# page - everywhere else the only thing we can rely on is that the user (or
# a previous command) has already put the caret somewhere.

def active_window_title() -> str:
    """The title of the window that has focus, or '' if it cannot be read."""
    try:
        import pygetwindow
        window = pygetwindow.getActiveWindow()
        return (window.title if window else "") or ""
    except Exception:
        return ""


def _looks_like_browser(title: str) -> bool:
    lowered = title.lower()
    return any(
        name in lowered
        for name in ("chrome", "edge", "firefox", "brave", "opera", "chromium")
    )


def type_text(text: str, submit: bool = False, newline: bool = False) -> bool:
    """
    Type text into whatever has focus.

    `keyboard.write` is preferred over pyautogui because it handles
    characters outside ASCII properly - names, currency symbols and
    punctuation that a voice command can easily contain.

    submit  press Enter afterwards (send the message, run the search)
    newline press Shift+Enter instead, for a line break inside a message
    """
    if not text:
        speak("There is nothing to type.")
        return False

    where = active_window_title()
    speak(f"Typing into {where.split(' - ')[-1] or 'the active window'}")

    try:
        keyboard.write(text, delay=0.01)
    except Exception:
        try:
            # pyautogui drops non-ASCII silently, so it is the fallback
            # rather than the first choice.
            pyautogui.typewrite(text, interval=0.01)
        except Exception as e:
            speak("I could not type that.")
            print(f"Typing failed: {type(e).__name__}: {e}")
            return False

    if newline:
        pyautogui.hotkey("shift", "enter")
    elif submit:
        pyautogui.press("enter")

    return True


def clear_field() -> bool:
    """Select everything in the focused field and delete it."""
    try:
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("delete")
        speak("Cleared.")
        return True
    except Exception as e:
        print(f"Could not clear the field: {type(e).__name__}: {e}")
        speak("I could not clear that.")
        return False


# =============== CLOSING A NAMED WINDOW ===============
#
# "close window" sends Alt+F4 to whatever has focus, which is right when the
# user means "this one" and wrong whenever they name something. Someone who
# cannot click cannot bring a window to the front first, so naming it has to
# work - otherwise the only closable window is the one already in front.

def list_open_windows() -> list[str]:
    """Titles of every visible top-level window."""
    try:
        import pygetwindow
    except ImportError:
        return []

    titles = []
    for window in pygetwindow.getAllWindows():
        title = (window.title or "").strip()
        # Windows keeps a number of zero-sized and untitled shell windows
        # around; none of them is something a person means.
        if title and window.width > 0 and window.height > 0:
            titles.append(title)
    return titles


def _match_windows(name: str):
    """Windows whose title matches `name`, best first."""
    try:
        import pygetwindow
    except ImportError:
        return []

    wanted = name.lower().strip()
    if not wanted:
        return []

    exact, partial = [], []
    for window in pygetwindow.getAllWindows():
        title = (window.title or "").strip()
        if not title or window.width <= 0 or window.height <= 0:
            continue
        lowered = title.lower()
        if lowered == wanted:
            exact.append(window)
        elif wanted in lowered:
            partial.append(window)
        else:
            # Window titles are usually "Document - Application", so the
            # application name is the last segment. "close word" should
            # find "Report.docx - Word".
            tail = lowered.replace("—", "-").split(" - ")[-1].strip()
            if tail.startswith(wanted) or wanted in tail.split():
                partial.append(window)

    return exact + partial


def close_named_window(name: str) -> bool:
    """
    Close the window the user named. True if one was closed.

    Sends the window a close request rather than killing its process, so an
    application with unsaved work still gets to ask about it. Killing would
    be more certain and is not ours to decide.
    """
    if not name:
        speak("Which window should I close?")
        return False

    matches = _match_windows(name)

    if not matches:
        titles = list_open_windows()
        speak(f"I cannot find a window called {name}.")
        if titles:
            print("Open windows:")
            for title in titles[:15]:
                print(f"  - {title}")
        return False

    # Several windows of the same application are closed together.
    #
    # Reading their titles back and waiting was the safe reading of an
    # ambiguous request, but it is not what people mean: "close chrome"
    # means close Chrome, not "tell me about Chrome". Each window is still
    # asked to close rather than killed, so anything with unsaved work
    # prompts on its own.
    if len(matches) > 1:
        speak(f"Closing {len(matches)} {name} windows.")

    closed = 0
    for window in matches:
        title = window.title
        try:
            window.close()
            closed += 1
            if len(matches) == 1:
                speak(f"Closed {title}")
        except Exception as e:
            print(f"Could not close '{title}': {type(e).__name__}: {e}")

    if closed == 0:
        speak(f"I could not close {name}.")
        return False

    if closed < len(matches):
        speak(f"Closed {closed} of {len(matches)}.")
    return True


def say_open_windows() -> list[str]:
    """Read out what is open, so a window can be named to close it."""
    titles = list_open_windows()
    if not titles:
        speak("I cannot see any open windows.")
        return []

    speak(f"There are {len(titles)} windows open.")
    for title in titles[:10]:
        speak(title)
    return titles


# =============== SCREEN BRIGHTNESS ===============
#
# Windows exposes laptop panel brightness through WMI rather than through a
# key that can be pressed, so unlike volume this cannot be done by sending a
# media key. External monitors do not answer WMI at all - they are driven
# over DDC/CI by their own firmware - so this works on a laptop screen and
# reports honestly when it cannot.

_BRIGHTNESS_READ = (
    "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness "
    "-ErrorAction Stop).CurrentBrightness"
)
_BRIGHTNESS_SET = (
    "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods "
    "-ErrorAction Stop).WmiSetBrightness(1,{level})"
)

BRIGHTNESS_STEP = 20


def _powershell(command: str) -> str | None:
    """Run one PowerShell command and return its output, or None."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=12,
        )
    except Exception as e:
        print(f"PowerShell failed: {type(e).__name__}: {e}")
        return None

    if result.returncode != 0:
        print(f"PowerShell error: {result.stderr.strip()[:160]}")
        return None
    return result.stdout.strip()


def get_brightness() -> int | None:
    """Current panel brightness as a percentage, or None if unsupported."""
    output = _powershell(_BRIGHTNESS_READ)
    if not output:
        return None
    # A multi-monitor machine returns one line per panel that answers.
    first = output.splitlines()[0].strip()
    try:
        return int(first)
    except ValueError:
        return None


def set_brightness(level: int) -> bool:
    """Set brightness to a percentage. Clamped to 0-100."""
    level = max(0, min(100, int(level)))
    if _powershell(_BRIGHTNESS_SET.format(level=level)) is None:
        speak("I cannot change the brightness on this display.")
        return False
    speak(f"Brightness {level} percent.")
    return True


def adjust_brightness(direction: str) -> bool:
    """
    Step brightness up or down.

    Reads the current value first rather than tracking it, because the user
    can change it with the keyboard at any time and a remembered value would
    drift out of step with the screen in front of them.
    """
    current = get_brightness()
    if current is None:
        speak("I cannot read the brightness on this display.")
        return False

    if direction in ("up", "increase", "brighter", "raise"):
        target = current + BRIGHTNESS_STEP
    elif direction in ("down", "decrease", "dimmer", "dim", "lower"):
        target = current - BRIGHTNESS_STEP
    elif direction == "max":
        target = 100
    elif direction == "min":
        target = 10      # not 0: a black screen is indistinguishable from a
                         # broken one, and the user may not be able to undo it
    else:
        speak(f"I do not know how to make the screen {direction}.")
        return False

    return set_brightness(target)


def say_brightness() -> int | None:
    """Report the current brightness out loud."""
    current = get_brightness()
    if current is None:
        speak("I cannot read the brightness on this display.")
        return None
    speak(f"Brightness is {current} percent.")
    return current
