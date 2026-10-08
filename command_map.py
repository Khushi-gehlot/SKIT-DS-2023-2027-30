"""
The command registry: spoken phrase -> (action, target).

This file is pure data. It holds no logic and imports nothing, which is the
point: the NLU layer reads it to decide *what the user wants*, and never needs
to know how anything is carried out. The handlers that actually do the work
live in executor.py.

Adding a command is one line here. Adding a new *kind* of command means a new
action, which also needs a handler registered in executor.py.

    "open notepad": ("open_app", "notepad")
       phrase              action   target
"""

# phrase -> (action, target)
COMMANDS: dict[str, tuple[str, str | None]] = {

    # ===================== APPLICATIONS =====================

    "calculator": ("open_app", "calculator"),
    "open calculator": ("open_app", "calculator"),

    "command prompt": ("open_app", "command_prompt"),
    "open command prompt": ("open_app", "command_prompt"),
    "cmd": ("open_app", "command_prompt"),

    "control panel": ("open_app", "control_panel"),
    "open control panel": ("open_app", "control_panel"),

    "file explorer": ("open_app", "file_explorer"),
    "open file explorer": ("open_app", "file_explorer"),
    "explorer": ("open_app", "file_explorer"),

    "notepad": ("open_app", "notepad"),
    "open notepad": ("open_app", "notepad"),

    "task manager": ("open_app", "task_manager"),
    "open task manager": ("open_app", "task_manager"),


    # ===================== FOLDERS =====================

    "desktop": ("open_folder", "desktop"),
    "open desktop": ("open_folder", "desktop"),
    "open desktop folder": ("open_folder", "desktop"),

    "documents": ("open_folder", "documents"),
    "open documents": ("open_folder", "documents"),
    "open document folder": ("open_folder", "documents"),

    "downloads": ("open_folder", "downloads"),
    "open downloads": ("open_folder", "downloads"),
    "open download folder": ("open_folder", "downloads"),

    "music": ("open_folder", "music"),

    "pictures": ("open_folder", "pictures"),

    "this pc": ("open_folder", "this_pc"),

    "videos": ("open_folder", "videos"),


    # ===================== WINDOWS SETTINGS =====================

    "bluetooth settings": ("open_settings", "bluetooth"),
    "bluetooth": ("open_settings", "bluetooth"),

    "clipboard settings": ("open_settings", "clipboard"),

    "devices settings": ("open_settings", "connecteddevices"),
    "device settings": ("open_settings", "connecteddevices"),

    "time and language": ("open_settings", "dateandtime"),
    "time settings": ("open_settings", "dateandtime"),
    "date and time": ("open_settings", "dateandtime"),

    "touchpad settings": ("open_settings", "devices-touchpad"),

    "display settings": ("open_settings", "display"),
    "open display settings": ("open_settings", "display"),
    "screen settings": ("open_settings", "display"),
    "brightness settings": ("open_settings", "display"),

    "font settings": ("open_settings", "fonts"),
    "fonts": ("open_settings", "fonts"),

    "gaming settings": ("open_settings", "gaming-gamebar"),
    "game bar settings": ("open_settings", "gaming-gamebar"),
    "xbox game bar": ("open_settings", "gaming-gamebar"),

    "capture settings": ("open_settings", "gaming-gamedvr"),
    "game capture settings": ("open_settings", "gaming-gamedvr"),

    "game mode settings": ("open_settings", "gaming-gamemode"),
    "game mode": ("open_settings", "gaming-gamemode"),

    "settings": ("open_settings", "home"),
    "open settings": ("open_settings", "home"),

    "keyboard settings": ("open_settings", "keyboard"),

    "language settings": ("open_settings", "language"),

    "lock screen settings": ("open_settings", "lockscreen"),
    "lock screen": ("open_settings", "lockscreen"),

    "mouse settings": ("open_settings", "mousetouchpad"),

    "multitasking settings": ("open_settings", "multitasking"),

    "network settings": ("open_settings", "network"),
    "internet settings": ("open_settings", "network"),

    "ethernet settings": ("open_settings", "network-ethernet"),

    "wifi settings": ("open_settings", "network-wifi"),
    "wi-fi settings": ("open_settings", "network-wifi"),

    "notification settings": ("open_settings", "notifications"),
    "open notifications": ("open_settings", "notifications"),

    "personalization": ("open_settings", "personalization"),
    "personalisation": ("open_settings", "personalization"),
    "open personalization": ("open_settings", "personalization"),

    "background settings": ("open_settings", "personalization-background"),
    "change background": ("open_settings", "personalization-background"),
    "wallpaper": ("open_settings", "personalization-background"),

    "color settings": ("open_settings", "personalization-colors"),
    "colors": ("open_settings", "personalization-colors"),

    "start menu settings": ("open_settings", "personalization-start"),
    "start menu": ("open_settings", "personalization-start"),

    "power settings": ("open_settings", "powersleep"),
    "power and sleep": ("open_settings", "powersleep"),

    "printers and scanners": ("open_settings", "printers"),
    "printer settings": ("open_settings", "printers"),

    "privacy settings": ("open_settings", "privacy"),
    "privacy": ("open_settings", "privacy"),

    "region settings": ("open_settings", "regionformatting"),

    "sound settings": ("open_settings", "sound"),
    "open sound settings": ("open_settings", "sound"),
    "audio settings": ("open_settings", "sound"),
    "speaker settings": ("open_settings", "sound"),

    "storage settings": ("open_settings", "storagesense"),
    "open storage": ("open_settings", "storagesense"),

    "taskbar settings": ("open_settings", "taskbar"),
    "taskbar": ("open_settings", "taskbar"),

    "themes": ("open_settings", "themes"),
    "theme settings": ("open_settings", "themes"),

    "windows security": ("open_settings", "windowsdefender"),
    "security settings": ("open_settings", "windowsdefender"),

    "update settings": ("open_settings", "windowsupdate"),
    "windows update": ("open_settings", "windowsupdate"),


    # ===================== WEBSITES =====================

    "open google": ("open_website", "google"),
    "google": ("open_website", "google"),

    "open youtube": ("open_website", "youtube"),
    "youtube": ("open_website", "youtube"),


    # ===================== WEB SEARCH =====================

    "search google": ("search_web", "google"),
    "google search": ("search_web", "google"),

    "search youtube": ("search_web", "youtube"),
    "youtube search": ("search_web", "youtube"),


    # ===================== CURSOR MOVEMENT =====================

    "move down": ("cursor_move", "down"),
    "move cursor down": ("cursor_move", "down"),

    "move left": ("cursor_move", "left"),
    "move cursor left": ("cursor_move", "left"),

    "move right": ("cursor_move", "right"),
    "move cursor right": ("cursor_move", "right"),

    "move up": ("cursor_move", "up"),
    "move cursor up": ("cursor_move", "up"),


    # ===================== CURSOR CLICKS =====================

    "double click": ("cursor_click", "double"),

    "click": ("cursor_click", "left"),

    "right click": ("cursor_click", "right"),


    # ===================== SCROLLING =====================

    "scroll down": ("scroll", "down"),

    "scroll up": ("scroll", "up"),


    # ===================== SCREENSHOT =====================

    "take screenshot": ("screenshot", None),
    "screenshot": ("screenshot", None),


    # ===================== WINDOW MANAGEMENT =====================

    "close window": ("window", "close"),

    "maximise": ("window", "maximize"),
    "maximise window": ("window", "maximize"),

    "minimise": ("window", "minimize"),
    "minimise window": ("window", "minimize"),

    "show desktop": ("window", "show_desktop"),

    "switch window": ("window", "switch"),
    "next window": ("window", "switch"),
    "change window": ("window", "switch"),


    # ===================== VOLUME =====================

    "volume down": ("volume", "down"),
    "decrease volume": ("volume", "down"),
    "sound down": ("volume", "down"),

    "mute": ("volume", "mute"),
    "mute volume": ("volume", "mute"),

    "unmute": ("volume", "unmute"),
    "unmute volume": ("volume", "unmute"),
    "sound on": ("volume", "unmute"),

    "volume up": ("volume", "up"),
    "increase volume": ("volume", "up"),
    "sound up": ("volume", "up"),


    # ===================== MEDIA =====================

    "next song": ("media", "next"),
    "next track": ("media", "next"),

    "play pause": ("media", "play_pause"),
    "pause music": ("media", "play_pause"),
    "play music": ("media", "play_pause"),

    "previous song": ("media", "previous"),
    "previous track": ("media", "previous"),


    # ===================== POWER =====================

    "lock": ("power", "lock"),
    "lock system": ("power", "lock"),

    "restart": ("power", "restart"),
    "reboot": ("power", "restart"),

    "shutdown": ("power", "shutdown"),
    "shut down": ("power", "shutdown"),
    "turn off": ("power", "shutdown"),

    "sleep": ("power", "sleep"),
    "go to sleep": ("power", "sleep"),


    # ===================== SYSTEM INFO =====================

    "battery": ("battery", None),
    "battery status": ("battery", None),


    # ===================== EMAIL =====================

    "send email": ("send_email", None),
    "send mail": ("send_email", None),
    "compose email": ("send_email", None),


    # ===================== BROWSER (Playwright) =====================
    #
    # These drive a browser the assistant stays in control of, so it can act
    # inside a page. Commands carrying an argument (a URL, a link name, a
    # number) are parsed by nlu/keyword.py rather than listed here.

    "browser": ("browser_open", "url"),
    "open browser": ("browser_open", "url"),

    "click link": ("browser_click", "index"),
    "click the link": ("browser_click", "index"),
    "open link": ("browser_click", "index"),
    "open the link": ("browser_click", "index"),

    "list links": ("browser_links", None),
    "show links": ("browser_links", None),
    "show me the links": ("browser_links", None),
    "what links are there": ("browser_links", None),
    "read links": ("browser_links", None),

    "go back": ("browser_nav", "back"),
    "previous page": ("browser_nav", "back"),
    "go forward": ("browser_nav", "forward"),
    "next page": ("browser_nav", "forward"),
    "reload": ("browser_nav", "reload"),
    "refresh": ("browser_nav", "reload"),
    "refresh page": ("browser_nav", "reload"),

    "scroll page down": ("browser_scroll", "down"),
    "scroll page up": ("browser_scroll", "up"),
    "scroll to top": ("browser_scroll", "top"),
    "go to top": ("browser_scroll", "top"),
    "scroll to bottom": ("browser_scroll", "bottom"),
    "go to bottom": ("browser_scroll", "bottom"),

    "read page": ("browser_read", None),
    "read this page": ("browser_read", None),
    "read the page": ("browser_read", None),
    "what does this page say": ("browser_read", None),

    "page title": ("browser_title", None),
    "what page is this": ("browser_title", None),

    "close browser": ("browser_close", None),
    "close the browser": ("browser_close", None),

    "press enter": ("browser_submit", None),
    "hit enter": ("browser_submit", None),
    "submit": ("browser_submit", None),
    "submit the form": ("browser_submit", None),
}


# Every action name the registry can produce. executor.py must have a handler
# for each of these; a test asserts that.
ACTIONS = sorted({action for action, _ in COMMANDS.values()})


def phrases() -> list[str]:
    """All recognised phrases, longest first (the matcher relies on this)."""
    return sorted(COMMANDS, key=len, reverse=True)
