import pyautogui
import os
from datetime import datetime
import time
import platform
import sys
import cv2
import numpy as np
from dotenv import load_dotenv
try:
    import pygetwindow as gw
except Exception:
    gw = None

class Actions:
    def __init__(self):
        # Load environment variables (.env) early so Actions picks up config like FULLSCREEN, WINDOW_TITLE, etc.
        try:
            load_dotenv()
        except Exception:
            pass
        self.os_type = platform.system()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.images_folder = os.path.join(self.script_dir, 'main_images')
        # Window geometry (filled during calibration on Windows)
        self.WIN_LEFT = None
        self.WIN_TOP = None
        self.WIN_WIDTH = None
        self.WIN_HEIGHT = None

        # Try to enable DPI awareness on Windows to avoid coordinate scaling issues
        if self.os_type == "Windows":
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
                print("DPI awareness enabled")
            except Exception as e:
                print(f"Failed to enable DPI awareness: {e}")
        # Make pyautogui faster and avoid failsafe aborts on corner hits
        try:
            pyautogui.FAILSAFE = False
            pause = float(os.getenv('PYAUTO_PAUSE', '0.03'))
            pyautogui.PAUSE = pause
        except Exception:
            pass

        # Define screen regions based on OS
        if self.os_type == "Darwin":  # macOS
            self.TOP_LEFT_X = 1013
            self.TOP_LEFT_Y = 120
            self.BOTTOM_RIGHT_X = 1480
            self.BOTTOM_RIGHT_Y = 683
            self.FIELD_AREA = (self.TOP_LEFT_X, self.TOP_LEFT_Y, self.BOTTOM_RIGHT_X, self.BOTTOM_RIGHT_Y)

            self.WIDTH = self.BOTTOM_RIGHT_X - self.TOP_LEFT_X
            self.HEIGHT = self.BOTTOM_RIGHT_Y - self.TOP_LEFT_Y
        elif self.os_type == "Windows": # windows
            # Prefer dynamic calibration from BlueStacks window (900x1600)
            calibrated = False
            # FULLSCREEN mode: treat the entire primary display as the window
            try:
                fullscreen = (os.getenv('FULLSCREEN', '0') == '1')
            except Exception:
                fullscreen = False

            if fullscreen:
                try:
                    screen_w, screen_h = pyautogui.size()
                    self.WIN_LEFT, self.WIN_TOP = 0, 0
                    self.WIN_WIDTH, self.WIN_HEIGHT = int(screen_w), int(screen_h)
                    # Field area: central portion of the screen
                    self.TOP_LEFT_X = self.WIN_LEFT + int(0.05 * self.WIN_WIDTH)
                    self.TOP_LEFT_Y = self.WIN_TOP + int(0.12 * self.WIN_HEIGHT)
                    self.BOTTOM_RIGHT_X = self.WIN_LEFT + int(0.95 * self.WIN_WIDTH)
                    self.BOTTOM_RIGHT_Y = self.WIN_TOP + int(0.80 * self.WIN_HEIGHT)
                    self.FIELD_AREA = (self.TOP_LEFT_X, self.TOP_LEFT_Y, self.BOTTOM_RIGHT_X, self.BOTTOM_RIGHT_Y)
                    self.WIDTH = self.BOTTOM_RIGHT_X - self.TOP_LEFT_X
                    self.HEIGHT = self.BOTTOM_RIGHT_Y - self.TOP_LEFT_Y

                    # Initial card bar guess (will be refined by auto-calibration)
                    self.CARD_BAR_X = self.WIN_LEFT + int(0.08 * self.WIN_WIDTH)
                    self.CARD_BAR_Y = self.WIN_TOP + int(0.85 * self.WIN_HEIGHT)
                    self.CARD_BAR_WIDTH = int(0.84 * self.WIN_WIDTH)
                    self.CARD_BAR_HEIGHT = int(0.11 * self.WIN_HEIGHT)
                    try:
                        self._auto_calibrate_card_bar()
                        print("Fullscreen mode: auto-calibrated card bar via elixir bar detection")
                    except Exception as e:
                        print(f"Fullscreen: auto-calibration failed, keeping defaults: {e}")
                    calibrated = True
                    print("Fullscreen mode enabled (using entire primary display)")
                except Exception as e:
                    print(f"Failed to enable fullscreen mode: {e}")
                    calibrated = False

            if (not calibrated) and gw is not None:
                try:
                    window_title = os.getenv('WINDOW_TITLE') or 'BlueStacks'
                    candidates = gw.getWindowsWithTitle(window_title)
                    win = next((w for w in candidates if w.width > 0 and w.height > 0 and not w.isMinimized), None)
                    if win is not None:
                        # Use window geometry
                        left, top, width, height = win.left, win.top, win.width, win.height
                        self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT = left, top, width, height
                        try:
                            win.activate()
                        except Exception:
                            pass
                        # Field area: central portion
                        self.TOP_LEFT_X = left + int(0.05 * width)
                        self.TOP_LEFT_Y = top + int(0.12 * height)
                        self.BOTTOM_RIGHT_X = left + int(0.95 * width)
                        self.BOTTOM_RIGHT_Y = top + int(0.80 * height)
                        self.FIELD_AREA = (self.TOP_LEFT_X, self.TOP_LEFT_Y, self.BOTTOM_RIGHT_X, self.BOTTOM_RIGHT_Y)
                        self.WIDTH = self.BOTTOM_RIGHT_X - self.TOP_LEFT_X
                        self.HEIGHT = self.BOTTOM_RIGHT_Y - self.TOP_LEFT_Y

                        # Card bar: bottom strip
                        self.CARD_BAR_X = left + int(0.08 * width)
                        self.CARD_BAR_Y = top + int(0.85 * height)
                        self.CARD_BAR_WIDTH = int(0.84 * width)
                        self.CARD_BAR_HEIGHT = int(0.11 * height)
                        # Try auto-calibrate card bar using the elixir bar color if possible
                        try:
                            self._auto_calibrate_card_bar()
                            calibrated = True
                            print("Auto-calibrated card bar via elixir bar detection")
                        except Exception as e:
                            print(f"Auto-calibration of card bar failed, keeping defaults: {e}")
                        calibrated = True
                except Exception:
                    calibrated = False

            # If .env overrides for regions exist, prefer them
            try:
                f_tlx = os.getenv('FIELD_TOP_LEFT_X')
                f_tly = os.getenv('FIELD_TOP_LEFT_Y')
                f_brx = os.getenv('FIELD_BOTTOM_RIGHT_X')
                f_bry = os.getenv('FIELD_BOTTOM_RIGHT_Y')
                c_x = os.getenv('CARD_BAR_X')
                c_y = os.getenv('CARD_BAR_Y')
                c_w = os.getenv('CARD_BAR_WIDTH')
                c_h = os.getenv('CARD_BAR_HEIGHT')
                if all(v is not None for v in [f_tlx, f_tly, f_brx, f_bry, c_x, c_y, c_w, c_h]):
                    self.TOP_LEFT_X = int(f_tlx)
                    self.TOP_LEFT_Y = int(f_tly)
                    self.BOTTOM_RIGHT_X = int(f_brx)
                    self.BOTTOM_RIGHT_Y = int(f_bry)
                    self.FIELD_AREA = (self.TOP_LEFT_X, self.TOP_LEFT_Y, self.BOTTOM_RIGHT_X, self.BOTTOM_RIGHT_Y)
                    self.WIDTH = self.BOTTOM_RIGHT_X - self.TOP_LEFT_X
                    self.HEIGHT = self.BOTTOM_RIGHT_Y - self.TOP_LEFT_Y
                    self.CARD_BAR_X = int(c_x)
                    self.CARD_BAR_Y = int(c_y)
                    self.CARD_BAR_WIDTH = int(c_w)
                    self.CARD_BAR_HEIGHT = int(c_h)
                    calibrated = True
                    print("Using region overrides from .env")
            except Exception as e:
                print(f"Failed to apply .env region overrides: {e}")

            if not calibrated:
                # Fallback to previous static coordinates
                self.TOP_LEFT_X = 1376
                self.TOP_LEFT_Y = 120
                self.BOTTOM_RIGHT_X = 1838
                self.BOTTOM_RIGHT_Y = 769
                self.FIELD_AREA = (self.TOP_LEFT_X, self.TOP_LEFT_Y, self.BOTTOM_RIGHT_X, self.BOTTOM_RIGHT_Y)

                self.WIDTH = self.BOTTOM_RIGHT_X - self.TOP_LEFT_X
                self.HEIGHT = self.BOTTOM_RIGHT_Y - self.TOP_LEFT_Y

                # Card bar coordinates fallback
                self.CARD_BAR_X = 1450
                self.CARD_BAR_Y = 847
                self.CARD_BAR_WIDTH = 1862 - 1450
                self.CARD_BAR_HEIGHT = 971 - 847

                # Roughly infer window geometry from field/card bar (best-effort)
                self.WIN_LEFT = self.TOP_LEFT_X - int(0.05 * self.WIDTH)
                self.WIN_TOP = self.TOP_LEFT_Y - int(0.12 * self.HEIGHT)
                self.WIN_WIDTH = int(self.WIDTH / 0.90)
                self.WIN_HEIGHT = int(self.HEIGHT / 0.68)

        # Card position to key mapping
        self.card_keys = {
            0: '1',  # Changed from 1 to 0
            1: '2',  # Changed from 2 to 1
            2: '3',  # Changed from 3 to 2
            3: '4'   # Changed from 4 to 3
        }
        
        # Card name to position mapping (will be updated during detection)
        self.current_card_positions = {}

    def capture_area(self, save_path):
        screenshot = pyautogui.screenshot(region=(self.TOP_LEFT_X, self.TOP_LEFT_Y, self.WIDTH, self.HEIGHT))
        screenshot.save(save_path)

    def capture_card_area(self, save_path):
        """Capture screenshot of card area"""
        screenshot = pyautogui.screenshot(region=(
            self.CARD_BAR_X, 
            self.CARD_BAR_Y, 
            self.CARD_BAR_WIDTH, 
            self.CARD_BAR_HEIGHT
        ))
        screenshot.save(save_path)

    def capture_individual_cards(self):
        """Capture and split card bar into individual card images"""
        screenshot = pyautogui.screenshot(region=(
            self.CARD_BAR_X, 
            self.CARD_BAR_Y, 
            self.CARD_BAR_WIDTH, 
            self.CARD_BAR_HEIGHT
        ))
        
        # Calculate individual card widths
        card_width = self.CARD_BAR_WIDTH // 4
        cards = []
        
        # Split into 4 individual card images
        for i in range(4):
            left = i * card_width
            # Trim small margins to avoid borders/gaps between cards
            margin = max(2, int(card_width * 0.04))
            c_left = max(0, left + margin)
            c_right = min(self.CARD_BAR_WIDTH, left + card_width - margin)
            vmargin = max(2, int(self.CARD_BAR_HEIGHT * 0.06))
            card_img = screenshot.crop((c_left, vmargin, c_right, self.CARD_BAR_HEIGHT - vmargin))
            save_path = os.path.join(self.script_dir, 'screenshots', f"card_{i+1}.png")
            card_img.save(save_path)
            cards.append(save_path)
        
        return cards

    def count_elixir(self):
        if self.os_type == "Darwin":
            for i in range(10, 0, -1):
                image_file = os.path.join(self.images_folder, f"{i}elixir.png")
                try:
                    location = pyautogui.locateOnScreen(image_file, confidence=0.5, grayscale=True)
                    if location:
                        return i
                except Exception as e:
                    print(f"Error locating {image_file}: {e}")
            return 0
        elif self.os_type == "Windows":
            # Dynamic sampling along the elixir bar within the calibrated window region
            target = (225, 128, 229)
            tolerance = 80
            try:
                # Sample 10 points along a horizontal line near bottom of window
                y = self.TOP_LEFT_Y + int(self.HEIGHT * 0.95)
                x_start = self.TOP_LEFT_X + int(self.WIDTH * 0.15)
                x_end = self.TOP_LEFT_X + int(self.WIDTH * 0.85)
                steps = 10
                xs = [x_start + i * (x_end - x_start) // (steps - 1) for i in range(steps)]
                count = 0
                for x in xs:
                    r, g, b = pyautogui.pixel(x, y)
                    if (abs(r - target[0]) <= tolerance) and (abs(g - target[1]) <= tolerance) and (abs(b - target[2]) <= tolerance):
                        count += 1
                return count
            except Exception:
                # Fallback to legacy static sampling
                count = 0
                for x in range(1512, 1892, 38):
                    r, g, b = pyautogui.pixel(x, 989)
                    if (abs(r - target[0]) <= tolerance) and (abs(g - target[1]) <= tolerance) and (abs(b - target[2]) <= tolerance):
                        count += 1
                return count
        else:
            return 0

    def update_card_positions(self, detections):
        """
        Update card positions based on detection results
        detections: list of dictionaries with 'class' and 'x' position
        """
        # Sort detections by x position (left to right)
        sorted_cards = sorted(detections, key=lambda x: x['x'])
        
        # Map cards to positions 0-3 instead of 1-4
        self.current_card_positions = {
            card['class']: idx  # Removed +1 
            for idx, card in enumerate(sorted_cards)
        }

    def _clamp_to_field(self, x, y):
        """Clamp a point inside the detected field area to avoid drops outside bounds."""
        if all(v is not None for v in [self.TOP_LEFT_X, self.TOP_LEFT_Y, self.BOTTOM_RIGHT_X, self.BOTTOM_RIGHT_Y]):
            x = max(self.TOP_LEFT_X + 5, min(x, self.BOTTOM_RIGHT_X - 5))
            y = max(self.TOP_LEFT_Y + 5, min(y, self.BOTTOM_RIGHT_Y - 5))
        return x, y

    def _card_slot_center(self, card_index: int):
        """Return screen coordinates of the center of the given card slot (0..3)."""
        slot_w = max(1, int(self.CARD_BAR_WIDTH // 4))
        cx = self.CARD_BAR_X + card_index * slot_w + slot_w // 2
        cy = self.CARD_BAR_Y + self.CARD_BAR_HEIGHT // 2
        return cx, cy

    def card_play(self, x, y, card_index):
        print(f"Playing card {card_index} to ({x}, {y})")
        # Ensure target is inside the field
        x, y = self._clamp_to_field(x, y)

        mode = (os.getenv('PLACEMENT_MODE') or 'auto').lower()  # 'auto' (default), 'drag' or 'tap'

        # Compute card slot center for drag start
        try:
            slot_cx, slot_cy = self._card_slot_center(card_index)
        except Exception as e:
            print(f"Failed to get slot center for card_index={card_index}: {e}")
            slot_cx = self.CARD_BAR_X + self.CARD_BAR_WIDTH // 2
            slot_cy = self.CARD_BAR_Y + self.CARD_BAR_HEIGHT // 2

        def do_drag():
            # Drag from the card slot position to the target on the field
            drag_move_dur = float(os.getenv('DRAG_MOVE_DURATION', '0.25'))
            pre_hold = float(os.getenv('DRAG_PRE_HOLD', '0.06'))
            post_hold = float(os.getenv('DRAG_POST_HOLD', '0.04'))
            mid_offset = int(os.getenv('DRAG_MID_OFFSET', '12'))
            print(f"Dragging from slot ({slot_cx}, {slot_cy}) to ({x}, {y})")
            pyautogui.moveTo(slot_cx, slot_cy, duration=0.10)
            pyautogui.mouseDown()
            time.sleep(pre_hold)
            # Nudge slightly to ensure drag starts
            pyautogui.moveTo(slot_cx, slot_cy - mid_offset, duration=0.08)
            # Main drag
            pyautogui.dragTo(x, y, duration=drag_move_dur)
            time.sleep(post_hold)
            pyautogui.mouseUp()
            time.sleep(0.05)

        def do_tap():
            # Prefer clicking the slot to select, then tap on field
            tap_select = (os.getenv('TAP_SELECT_METHOD') or 'slot').lower()  # 'slot' or 'key'
            if tap_select == 'key' and card_index in self.card_keys:
                key = self.card_keys[card_index]
                print(f"Selecting card via key: {key}")
                pyautogui.press(key)
                time.sleep(0.10)
            else:
                print(f"Selecting card by clicking slot center ({slot_cx}, {slot_cy})")
                pyautogui.moveTo(slot_cx, slot_cy, duration=0.08)
                pyautogui.mouseDown(); time.sleep(0.02); pyautogui.mouseUp()
                time.sleep(0.08)
            print(f"Clicking field at ({x}, {y})")
            pyautogui.moveTo(x, y, duration=0.12)
            pyautogui.click()
            time.sleep(0.05)

        try:
            if mode == 'tap':
                do_tap()
            elif mode == 'drag':
                do_drag()
            else:
                # AUTO: try drag then tap to ensure drop
                do_drag()
                time.sleep(0.05)
                do_tap()
        except Exception as e:
            print(f"Placement encountered error: {e}; attempting tap fallback")
            do_tap()

    def click_battle_start(self):
        """Find and click the Battle button with robust regioning and overrides.
        Supports manual override via .env: BATTLE_BUTTON_X, BATTLE_BUTTON_Y
        """
        # 1) Manual override from environment
        try:
            bx = os.getenv("BATTLE_BUTTON_X")
            by = os.getenv("BATTLE_BUTTON_Y")
            if bx and by:
                x, y = int(bx), int(by)
                print(f"Clicking Battle via override at ({x}, {y})")
                pyautogui.moveTo(x, y, duration=0.2)
                pyautogui.click()
                return True
        except Exception:
            pass

        # 2) CV-based multiscale template search (window-relative region, fallback to full window)
        primary_region = (0.35, 0.78, 0.30, 0.18)
        threshold = float(os.getenv('BATTLE_TM_THRESHOLD', '0.78'))
        clicked = self._find_and_click_template(
            'battlestartbutton.png',
            primary_rel_region=primary_region,
            threshold=threshold,
            allow_fullscreen=(os.getenv('SEARCH_FULL_SCREEN', '0') == '1')
        )
        if clicked:
            return True

        # 4) Fallback: click approximate bottom-center of window to attempt to focus/start
        print("Battle button not found. Clicking approximate bottom-center to clear/focus...")
        if all(v is not None for v in [self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT]):
            x = self.WIN_LEFT + self.WIN_WIDTH // 2
            y = self.WIN_TOP + int(0.88 * self.WIN_HEIGHT)
        else:
            # Final fallback: a safe center-ish click
            x, y = 1600, 900
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click()
        time.sleep(1)
        return False

    def detect_game_end(self):
        try:
            winner_img = os.path.join(self.images_folder, "Winner.png")
            confidences = [0.8, 0.7, 0.6]

            # Default region near top-middle where 'Winner' text usually appears
            winner_region = (1510, 121, 1678-1510, 574-121)

            result = None
            for confidence in confidences:
                print(f"\nTrying detection with confidence: {confidence}")
                winner_location = None
                try:
                    winner_location = pyautogui.locateOnScreen(
                        winner_img, confidence=confidence, grayscale=True, region=winner_region
                    )
                except Exception as e:
                    print(f"Error locating Winner: {str(e)}")

                if winner_location:
                    _, y = pyautogui.center(winner_location)
                    print(f"Found 'Winner' at y={y} with confidence {confidence}")
                    result = "victory" if y > 402 else "defeat"
                    break

            # Whether or not we classified result, try to click the OK button to continue
            if self.click_ok_button():
                print("OK button clicked after match end")
            else:
                print("OK button not found; attempting fallback click")
                # Fallback bottom-center click
                if all(v is not None for v in [self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT]):
                    x = self.WIN_LEFT + self.WIN_WIDTH // 2
                    y = self.WIN_TOP + int(0.88 * self.WIN_HEIGHT)
                else:
                    x, y = 1600, 900
                pyautogui.moveTo(x, y, duration=0.2)
                pyautogui.click()

            return result or "done"
        except Exception as e:
            print(f"Error in game end detection: {str(e)}")
        return None

    def click_ok_button(self):
        """Find and click the OK button at end of match.
        Supports .env override: OK_BUTTON_X, OK_BUTTON_Y
        Returns True if a click was performed.
        """
        # 1) Manual override from environment
        try:
            ox = os.getenv("OK_BUTTON_X")
            oy = os.getenv("OK_BUTTON_Y")
            if ox and oy:
                x, y = int(ox), int(oy)
                print(f"Clicking OK via override at ({x}, {y})")
                pyautogui.moveTo(x, y, duration=0.2)
                pyautogui.click()
                return True
        except Exception:
            pass

        # 2) CV-based multiscale search for OK button
        primary_region = (0.35, 0.75, 0.30, 0.20)
        threshold = float(os.getenv('OK_TM_THRESHOLD', '0.80'))
        clicked = self._find_and_click_template(
            'okbutton.png',
            primary_rel_region=primary_region,
            threshold=threshold,
            allow_fullscreen=(os.getenv('SEARCH_FULL_SCREEN', '0') == '1')
        )
        return bool(clicked)

    def detect_match_over(self):
        matchover_img = os.path.join(self.images_folder, "matchover.png")
        confidences = [0.8, 0.6, 0.4]
        # Define the region where the matchover image appears (adjust as needed)
        region = (1378, 335, 1808-1378, 411-335)
        for confidence in confidences:
            try:
                location = pyautogui.locateOnScreen(
                    matchover_img, confidence=confidence, grayscale=True, region=region
                )
                if location:
                    print("Match over detected!")
                    return True
            except Exception as e:
                print(f"Error locating matchover.png: {e}")
        return False

    # ======== Computer-vision helpers (no manual coordinates) ========
    def _window_region_box(self, rel_left: float, rel_top: float, rel_w: float, rel_h: float):
        """Compute absolute region box from relative ratios inside the BlueStacks window.
        Returns (left, top, width, height). Falls back to None if window size unknown.
        """
        if all(v is not None for v in [self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT]):
            left = self.WIN_LEFT + int(rel_left * self.WIN_WIDTH)
            top = self.WIN_TOP + int(rel_top * self.WIN_HEIGHT)
            width = int(rel_w * self.WIN_WIDTH)
            height = int(rel_h * self.WIN_HEIGHT)
            return (left, top, width, height)
        return None

    def _grab_region(self, region=None):
        """Screenshot region into numpy BGR image for OpenCV. Region=(left, top, width, height)."""
        if region is None:
            img = pyautogui.screenshot()
        else:
            l, t, w, h = region
            img = pyautogui.screenshot(region=(l, t, w, h))
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        return img

    def _match_template_multiscale(self, haystack_bgr: np.ndarray, template_path: str, 
                                    method=cv2.TM_CCOEFF_NORMED, scales=(0.85, 1.0, 1.15), threshold=0.75):
        """Return best match (max_val, (center_x, center_y)) in absolute coords of the given haystack region image.
        If not found, return (None, None).
        """
        if not os.path.exists(template_path):
            print(f"Template not found: {template_path}")
            return (None, None)
        tpl = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if tpl is None:
            print(f"Failed to read template: {template_path}")
            return (None, None)
        haystack_gray = cv2.cvtColor(haystack_bgr, cv2.COLOR_BGR2GRAY)
        best = (0.0, None)
        for s in scales:
            try:
                new_w = max(1, int(tpl.shape[1] * s))
                new_h = max(1, int(tpl.shape[0] * s))
                tpl_s = cv2.resize(tpl, (new_w, new_h), interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(haystack_gray, tpl_s, method)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                if max_val > best[0]:
                    best = (max_val, (max_loc[0] + new_w // 2, max_loc[1] + new_h // 2))
            except Exception:
                continue
        if best[0] >= threshold and best[1] is not None:
            return best
        return (None, None)

    def _find_and_click_template(self, template_filename: str, 
                                 primary_rel_region=(0.35, 0.75, 0.30, 0.20),
                                 threshold=0.78,
                                 allow_fullscreen=True):
        """Try to find template in a primary window-relative region first, then in full window if enabled.
        Clicks the center if found. Returns True if clicked.
        """
        # 1) Focus window if possible
        if gw is not None:
            try:
                window_title = os.getenv('WINDOW_TITLE') or 'BlueStacks'
                win = next((w for w in gw.getWindowsWithTitle(window_title) if w.width > 0 and not w.isMinimized), None)
                if win:
                    win.activate()
            except Exception:
                pass

        # 2) Try primary region
        tpl_path = os.path.join(self.images_folder, template_filename)
        region = self._window_region_box(*primary_rel_region)
        if region is not None:
            img = self._grab_region(region)
            score, center = self._match_template_multiscale(img, tpl_path, threshold=threshold)
            if score is not None and center is not None:
                x = region[0] + center[0]
                y = region[1] + center[1]
                pyautogui.moveTo(x, y, duration=0.15)
                pyautogui.click()
                return True

        # 3) Try full window
        if allow_fullscreen and all(v is not None for v in [self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT]):
            full_region = (self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT)
            img = self._grab_region(full_region)
            score, center = self._match_template_multiscale(img, tpl_path, threshold=threshold)
            if score is not None and center is not None:
                x = full_region[0] + center[0]
                y = full_region[1] + center[1]
                pyautogui.moveTo(x, y, duration=0.15)
                pyautogui.click()
                return True
        return False

    # ======== Auto calibration via elixir bar detection ========
    def _auto_calibrate_card_bar(self):
        if not all(v is not None for v in [self.WIN_LEFT, self.WIN_TOP, self.WIN_WIDTH, self.WIN_HEIGHT]):
            raise RuntimeError("Window geometry unknown")
        # Prefer searching for elixir bar INSIDE the field area (bottom band),
        # to avoid false positives from taskbar/overlays in fullscreen mode.
        field_left, field_top = self.TOP_LEFT_X, self.TOP_LEFT_Y
        field_w, field_h = self.WIDTH, self.HEIGHT
        # Bottom 35% of field
        search_top = field_top + int(0.65 * field_h)
        region = (field_left, search_top, field_w, field_h - (search_top - field_top))
        if region is None:
            raise RuntimeError("Failed to compute bottom region")
        img = self._grab_region(region)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # Purple/magenta ranges in OpenCV HSV (0..179)
        lower1 = np.array([125, 60, 60], dtype=np.uint8)
        upper1 = np.array([165, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower1, upper1)
        # Morph close to fill gaps
        kernel = np.ones((5, 15), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            # Fallback: place card bar directly below the field
            cx = self.WIN_LEFT + int(0.08 * self.WIN_WIDTH)
            cw = int(0.84 * self.WIN_WIDTH)
            card_h = int(max(self.WIN_HEIGHT * 0.10, 80))
            card_h = min(card_h, int(self.WIN_HEIGHT * 0.20))
            gap = int(max(6, self.WIN_HEIGHT * 0.008))
            cy = self.BOTTOM_RIGHT_Y + gap
            # Clamp inside window
            cy = max(self.WIN_TOP, min(cy, self.WIN_TOP + self.WIN_HEIGHT - card_h))
            cx = max(self.WIN_LEFT, min(cx, self.WIN_LEFT + self.WIN_WIDTH - cw))
            self.CARD_BAR_X, self.CARD_BAR_Y, self.CARD_BAR_WIDTH, self.CARD_BAR_HEIGHT = cx, cy, cw, card_h
            print("Elixir bar not found; using field-bottom derived CARD_BAR rect")
            return
        # Choose the widest, low-lying contour as the elixir bar
        best = None
        best_score = -1
        H, W = mask.shape
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Score prefers wide, thin, near-bottom bars
            aspect = w / max(1.0, h)
            bottomness = (y + h) / H
            # Filter unrealistic sizes (avoid taskbar/overlays): require width spanning >= 20% of field
            if w < 0.20 * W:
                continue
            score = aspect + 2.0 * bottomness
            if aspect > 3.0 and score > best_score:
                best = (x, y, w, h)
                best_score = score
        if best is None:
            # Fallback: place card bar directly below the field
            cx = self.WIN_LEFT + int(0.08 * self.WIN_WIDTH)
            cw = int(0.84 * self.WIN_WIDTH)
            card_h = int(max(self.WIN_HEIGHT * 0.10, 80))
            card_h = min(card_h, int(self.WIN_HEIGHT * 0.20))
            gap = int(max(6, self.WIN_HEIGHT * 0.008))
            cy = self.BOTTOM_RIGHT_Y + gap
            cy = max(self.WIN_TOP, min(cy, self.WIN_TOP + self.WIN_HEIGHT - card_h))
            cx = max(self.WIN_LEFT, min(cx, self.WIN_LEFT + self.WIN_WIDTH - cw))
            self.CARD_BAR_X, self.CARD_BAR_Y, self.CARD_BAR_WIDTH, self.CARD_BAR_HEIGHT = cx, cy, cw, card_h
            print("Failed to localize elixir bar in field band; using field-bottom derived CARD_BAR rect")
            return

        ex, ey, ew, eh = best
        # Convert to absolute coords relative to screen
        ex_abs = region[0] + ex
        ey_abs = region[1] + ey

        # Derive card bar rect BELOW the field (elixir bar sits above cards in CR).
        card_h = int(max(self.WIN_HEIGHT * 0.10, 80))
        card_h = min(card_h, int(self.WIN_HEIGHT * 0.20))
        gap = int(max(6, eh * 0.5))
        cx = self.WIN_LEFT + int(0.08 * self.WIN_WIDTH)
        cw = int(0.84 * self.WIN_WIDTH)
        # Start just below field bottom; if that would go beyond window, clamp.
        cy = self.BOTTOM_RIGHT_Y + gap

        # Sanity clamp inside window
        cy = max(self.WIN_TOP, min(cy, self.WIN_TOP + self.WIN_HEIGHT - card_h))
        cx = max(self.WIN_LEFT, min(cx, self.WIN_LEFT + self.WIN_WIDTH - cw))

        self.CARD_BAR_X = cx
        self.CARD_BAR_Y = cy
        self.CARD_BAR_WIDTH = cw
        self.CARD_BAR_HEIGHT = card_h
        print(f"Auto-calibrated CARD_BAR rect (field-based): X={cx} Y={cy} W={cw} H={card_h}")