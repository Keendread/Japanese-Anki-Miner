import time
import win32api
import win32con

VK_NAMES = {
    **{ord(c): c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **{ord(c): c for c in "0123456789"},
    win32con.VK_LCONTROL: "LCtrl",  win32con.VK_RCONTROL: "RCtrl",
    win32con.VK_LSHIFT:   "LShift", win32con.VK_RSHIFT:   "RShift",
    win32con.VK_LMENU:    "LAlt",   win32con.VK_RMENU:    "RAlt",
    **{getattr(win32con, f"VK_F{i}"): f"F{i}" for i in range(1, 13)},
    win32con.VK_SPACE:    "Space",  win32con.VK_RETURN:   "Enter",
    win32con.VK_TAB:      "Tab",    win32con.VK_ESCAPE:   "Escape",
    win32con.VK_UP:       "Up",     win32con.VK_DOWN:     "Down",
    win32con.VK_LEFT:     "Left",   win32con.VK_RIGHT:    "Right",   
}


# ── Public API ────────────────────────────────────────────────────────────

def is_held(vk: int) -> bool:
    return bool(win32api.GetAsyncKeyState(vk) & 0x8000)


def record_hotkey() -> dict:
    idle_timeout = 0.3
    print("Input your hotkey...")
    
    peak: dict[int, str] = {}
    last_held_time = None
    
    while True:
        held = {vk: name for vk, name in VK_NAMES.items()
                if win32api.GetAsyncKeyState(vk) & 0x8000}
        
        if held:
            last_held_time = time.monotonic()
            if len(held) > len(peak):
                peak = held
        elif peak and last_held_time is not None:
            if time.monotonic() - last_held_time >= idle_timeout:
                break
            
    print(f"Recorded: {' + '.join(peak.values())}")
    _NORMALIZE_VK = {
        win32con.VK_LCONTROL: win32con.VK_CONTROL,
        win32con.VK_RCONTROL: win32con.VK_CONTROL,
        win32con.VK_LSHIFT:   win32con.VK_SHIFT,
        win32con.VK_RSHIFT:   win32con.VK_SHIFT,
        win32con.VK_LMENU:    win32con.VK_MENU,
        win32con.VK_RMENU:    win32con.VK_MENU,
    }

    normalized_vks = {_NORMALIZE_VK.get(vk, vk) for vk in peak}
    return {"vks": normalized_vks, "names": set(peak.values())}


def is_combo_pressed(combo: list) -> bool:
    while True:
        all_pressed = all(is_held(vk) for vk in combo)

        if all_pressed:
            print("Combo triggered!")
            return True 
        
        time.sleep(0.02)