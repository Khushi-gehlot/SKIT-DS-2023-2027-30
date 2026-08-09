from actions import (
    # Browser / web
   
    send_email_voice,
    search_google_voice,
    search_youtube_voice,

    # Scrolling / screen
    move_cursor_up,
    move_cursor_down,
    move_cursor_left,
    move_cursor_right,
    click_cursor,
    double_click_cursor,
    right_click_cursor,
    scroll_down,
    scroll_up,
    take_screenshot,

    # Power / battery
    shutdown_system,
    restart_system,
    show_battery,
    lock_system,
    sleep_system,

    # Apps
    open_notepad,
    open_calculator,
    open_cmd,
    open_file_explorer,
    open_control_panel,
    open_task_manager,

    # Folders
    open_downloads_folder,
    open_documents_folder,
    open_desktop_folder,
    open_videos_folder,
    open_pictures_folder,
    open_music_folder,
    open_this_pc,

    # Window management
    show_desktop,
    minimize_window,
    maximize_window,
    close_window,
    switch_window,

    # Volume / media
    volume_up,
    volume_down,
    mute_volume,
    unmute_volume,
    media_play_pause,
    media_next,
    media_previous,

    # Windows Settings sections (ms-settings)
    open_settings,
    open_display_settings,
    open_sound_settings,
    open_notifications_settings,
    open_power_sleep_settings,
    open_storage_settings,
    open_multitasking_settings,
    open_clipboard_settings,
    open_personalization_settings,
    open_background_settings,
    open_colors_settings,
    open_lock_screen_settings,
    open_themes_settings,
    open_fonts_settings,
    open_start_menu_settings,
    open_taskbar_settings,
    open_time_language_settings,
    open_date_time_settings,
    open_region_language_settings,
    open_language_settings,
    open_network_settings,
    open_wifi_settings,
    open_ethernet_settings,
    open_bluetooth_settings,
    open_devices_settings,
    open_mouse_settings,
    open_keyboard_settings,
    open_touchpad_settings,
    open_printers_settings,
    open_updates_settings,
    open_windows_security_settings,
    open_privacy_settings,
    open_gaming_settings,
    open_game_bar_settings,
    open_captures_settings,
    open_game_mode_settings,
)


COMMANDS = {

    # ================= SEARCH =================

    "search google": search_google_voice,
    "google search": search_google_voice,

    "search youtube": search_youtube_voice,
    "youtube search": search_youtube_voice,

    # ===================== BROWSER / WEB =====================


    # ================= CURSOR CONTROL =================

    "move up": move_cursor_up,
    "move down": move_cursor_down,
    "move left": move_cursor_left,
    "move right": move_cursor_right,

    "move cursor up": move_cursor_up,
    "move cursor down": move_cursor_down,
    "move cursor left": move_cursor_left,
    "move cursor right": move_cursor_right,

    "click": click_cursor,
    "double click": double_click_cursor,
    "right click": right_click_cursor,

    "scroll down": scroll_down,
    "scroll up": scroll_up,
    "take screenshot": take_screenshot,
    "screenshot": take_screenshot,

    # ===================== POWER / SYSTEM =====================

    "shutdown": shutdown_system,
    "shut down": shutdown_system,
    "turn off": shutdown_system,

    "restart": restart_system,
    "reboot": restart_system,

    "battery": show_battery,
    "battery status": show_battery,

    "lock": lock_system,
    "lock system": lock_system,

    "sleep": sleep_system,          # also used as sleep word for assistant
    "go to sleep": sleep_system,

    # ===================== BASIC APPS =====================

    "notepad": open_notepad,
    "open notepad": open_notepad,

    "calculator": open_calculator,
    "open calculator": open_calculator,

    "command prompt": open_cmd,
    "open command prompt": open_cmd,
    "cmd": open_cmd,

    "file explorer": open_file_explorer,
    "open file explorer": open_file_explorer,
    "explorer": open_file_explorer,

    "control panel": open_control_panel,
    "open control panel": open_control_panel,

    "task manager": open_task_manager,
    "open task manager": open_task_manager,

    # ===================== FOLDERS =====================

    "downloads": open_downloads_folder,
    "open downloads": open_downloads_folder,
    "open download folder": open_downloads_folder,

    "documents": open_documents_folder,
    "open documents": open_documents_folder,
    "open document folder": open_documents_folder,

    "desktop": open_desktop_folder,
    "open desktop": open_desktop_folder,
    "open desktop folder": open_desktop_folder,

    "videos": open_videos_folder,
    "pictures": open_pictures_folder,
    "music": open_music_folder,
    "this pc": open_this_pc,

    # ===================== WINDOW MANAGEMENT =====================

    "show desktop": show_desktop,

    "minimise": minimize_window,
    "minimise window": minimize_window,

    "maximise": maximize_window,
    "maximise window": maximize_window,

    "close window": close_window,

    "switch window": switch_window,
    "next window": switch_window,
    "change window": switch_window,

    # ===================== VOLUME / MEDIA =====================

    "volume up": volume_up,
    "increase volume": volume_up,
    "sound up": volume_up,

    "volume down": volume_down,
    "decrease volume": volume_down,
    "sound down": volume_down,

    "mute": mute_volume,
    "mute volume": mute_volume,

    "unmute": unmute_volume,
    "unmute volume": unmute_volume,
    "sound on": unmute_volume,

    "play pause": media_play_pause,
    "pause music": media_play_pause,
    "play music": media_play_pause,

    "next song": media_next,
    "next track": media_next,

    "previous song": media_previous,
    "previous track": media_previous,

    # ===================== MAIN SETTINGS APP =====================

    "settings": open_settings,
    "open settings": open_settings,

    # ===================== DISPLAY / SYSTEM SETTINGS =====================

    "display settings": open_display_settings,
    "open display settings": open_display_settings,
    "screen settings": open_display_settings,
    "brightness settings": open_display_settings,

    "sound settings": open_sound_settings,
    "open sound settings": open_sound_settings,
    "audio settings": open_sound_settings,
    "speaker settings": open_sound_settings,

    "notification settings": open_notifications_settings,
    "open notifications": open_notifications_settings,

    "power settings": open_power_sleep_settings,
    "power and sleep": open_power_sleep_settings,

    "storage settings": open_storage_settings,
    "open storage": open_storage_settings,

    "multitasking settings": open_multitasking_settings,

    "clipboard settings": open_clipboard_settings,

    # ===================== PERSONALIZATION =====================

    "personalization": open_personalization_settings,
    "personalisation": open_personalization_settings,
    "open personalization": open_personalization_settings,

    "background settings": open_background_settings,
    "change background": open_background_settings,
    "wallpaper": open_background_settings,

    "color settings": open_colors_settings,
    "colors": open_colors_settings,

    "lock screen settings": open_lock_screen_settings,
    "lock screen": open_lock_screen_settings,

    "themes": open_themes_settings,
    "theme settings": open_themes_settings,

    "font settings": open_fonts_settings,
    "fonts": open_fonts_settings,

    "start menu settings": open_start_menu_settings,
    "start menu": open_start_menu_settings,

    "taskbar settings": open_taskbar_settings,
    "taskbar": open_taskbar_settings,

    # ===================== TIME / LANGUAGE =====================

    "time and language": open_time_language_settings,
    "time settings": open_date_time_settings,
    "date and time": open_date_time_settings,

    "region settings": open_region_language_settings,
    "language settings": open_language_settings,

    # ================= EMAIL =================

    "send email": send_email_voice,
    "send mail": send_email_voice,
    "compose email": send_email_voice,


    # ===================== NETWORK / INTERNET =====================

    "network settings": open_network_settings,
    "internet settings": open_network_settings,

    "wifi settings": open_wifi_settings,
    "wi-fi settings": open_wifi_settings,

    "ethernet settings": open_ethernet_settings,

    # ===================== DEVICES =====================

    "bluetooth settings": open_bluetooth_settings,
    "bluetooth": open_bluetooth_settings,

    "devices settings": open_devices_settings,
    "device settings": open_devices_settings,

    "mouse settings": open_mouse_settings,
    "keyboard settings": open_keyboard_settings,
    "touchpad settings": open_touchpad_settings,
    "printers and scanners": open_printers_settings,
    "printer settings": open_printers_settings,

    # ===================== UPDATE / SECURITY / PRIVACY =====================

    "update settings": open_updates_settings,
    "windows update": open_updates_settings,

    "windows security": open_windows_security_settings,
    "security settings": open_windows_security_settings,

    "privacy settings": open_privacy_settings,
    "privacy": open_privacy_settings,

    # ===================== GAMING =====================

    "gaming settings": open_gaming_settings,
    "game bar settings": open_game_bar_settings,
    "xbox game bar": open_game_bar_settings,

    "capture settings": open_captures_settings,
    "game capture settings": open_captures_settings,

    "game mode settings": open_game_mode_settings,
    "game mode": open_game_mode_settings,
    
}
