import numpy as np
import time
import os
import pyautogui
import threading
from dotenv import load_dotenv
from Actions import Actions
from inference_sdk import InferenceHTTPClient
import random

# Load environment variables from .env file
load_dotenv()

MAX_ENEMIES = 10
MAX_ALLIES = 10

SPELL_CARDS = ["Fireball", "Zap", "Arrows", "Tornado", "Rocket", "Lightning", "Freeze"]

# Very rough elixir costs (fallback defaults to 4 if unknown)
CARD_COSTS = {
    # Spells
    "Arrows": 3, "Zap": 2, "Fireball": 4, "Rocket": 6, "Lightning": 6, "Tornado": 3, "Freeze": 4,
    # Common troops (examples; expand as your detector class names allow)
    "Knight": 3, "Archers": 3, "Goblins": 2, "Spear Goblins": 2, "Skeletons": 1,
    "Valkyrie": 4, "Musketeer": 4, "Mini P.E.K.K.A": 4, "Giant": 5, "Hog Rider": 4,
}

class ClashRoyaleEnv:
    def __init__(self):
        self.actions = Actions()
        self.rf_model = self.setup_roboflow()
        self.card_model = self.setup_card_roboflow()
        self.state_size = 1 + 2 * (MAX_ALLIES + MAX_ENEMIES)

        self.num_cards = 4
        self.grid_width = 18
        self.grid_height = 28

        self.screenshot_path = os.path.join(os.path.dirname(__file__), 'screenshots', "current.png")
        self.available_actions = self.get_available_actions()
        self.action_size = len(self.available_actions)
        self.current_cards = []

        self.game_over_flag = None
        self._endgame_thread = None
        self._endgame_thread_stop = threading.Event()

        self.prev_elixir = None
        self.prev_enemy_presence = None

        self.prev_enemy_princess_towers = None

        self.match_over_detected = False

        # Heuristic assist: with some probability use a simple rule-based policy instead of RL action
        try:
            self.heuristic_assist_prob = float(os.getenv('HEURISTIC_ASSIST_PROB', '0.0'))
        except Exception:
            self.heuristic_assist_prob = 0.0

    def setup_roboflow(self):
        api_key = os.getenv('ROBOFLOW_API_KEY')
        if not api_key:
            raise ValueError("ROBOFLOW_API_KEY environment variable is not set. Please check your .env file.")
        
        return InferenceHTTPClient(
            api_url="http://localhost:9001",
            api_key=api_key
        )

    def setup_card_roboflow(self):
        api_key = os.getenv('ROBOFLOW_API_KEY')
        if not api_key:
            raise ValueError("ROBOFLOW_API_KEY environment variable is not set. Please check your .env file.")
        
        return InferenceHTTPClient(
            api_url="http://localhost:9001",
            api_key=api_key
        )

    def reset(self):
        # self.actions.click_battle_start()
        # Instead, just wait for the new game to load after clicking "Play Again"
        time.sleep(3)
        self.game_over_flag = None
        self._endgame_thread_stop.clear()
        self._endgame_thread = threading.Thread(target=self._endgame_watcher, daemon=True)
        self._endgame_thread.start()
        self.prev_elixir = None
        self.prev_enemy_presence = None
        self.prev_enemy_princess_towers = self._count_enemy_princess_towers()
        self.match_over_detected = False
        return self._get_state()

    def close(self):
        self._endgame_thread_stop.set()
        if self._endgame_thread:
            self._endgame_thread.join()

    def step(self, action_index):
        # Check for match over
        if not self.match_over_detected and hasattr(self.actions, "detect_match_over") and self.actions.detect_match_over():
            print("Match over detected (matchover.png), forcing no-op until next game.")
            self.match_over_detected = True

        # If match over, only allow no-op action (last action in list)
        if self.match_over_detected:
            action_index = len(self.available_actions) - 1  # No-op action

        if self.game_over_flag:
            done = True
            reward = self._compute_reward(self._get_state())
            result = self.game_over_flag
            if result == "victory":
                reward += 100
                print("Victory detected - ending episode")
            elif result == "defeat":
                reward -= 100
                print("Defeat detected - ending episode")
            self.match_over_detected = False  # Reset for next episode
            return self._get_state(), reward, done

        self.current_cards = self.detect_cards_in_hand()
        print("\nCurrent cards in hand:", self.current_cards)

        # If all cards are "Unknown", click at (1611, 831) and return no-op
        if all(card == "Unknown" for card in self.current_cards):
            print("All cards are Unknown, clicking at (1611, 831) and skipping move.")
            pyautogui.moveTo(1611, 831, duration=0.2)
            pyautogui.click()
            # Return current state, zero reward, not done
            next_state = self._get_state()
            return next_state, 0, False

        # Optional heuristic override
        if self.heuristic_assist_prob > 0 and random.random() < self.heuristic_assist_prob:
            try:
                h_idx = self._choose_heuristic_action()
                if h_idx is not None:
                    print(f"[HeuristicAssist] overriding action {action_index} -> {h_idx}")
                    action_index = h_idx
            except Exception as e:
                print(f"Heuristic action selection failed: {e}")

        action = self.available_actions[action_index]
        card_index, x_frac, y_frac = action
        print(f"Action selected: card_index={card_index}, x_frac={x_frac:.2f}, y_frac={y_frac:.2f}")

        spell_penalty = 0

        if card_index != -1 and card_index < len(self.current_cards):
            card_name = self.current_cards[card_index]
            print(f"Attempting to play {card_name}")
            x = int(x_frac * self.actions.WIDTH) + self.actions.TOP_LEFT_X
            y = int(y_frac * self.actions.HEIGHT) + self.actions.TOP_LEFT_Y
            self.actions.card_play(x, y, card_index)
            time.sleep(1)  # You can reduce this if needed

            # --- Spell penalty logic ---
            if card_name in SPELL_CARDS:
                state = self._get_state()
                enemy_positions = []
                for i in range(1 + 2 * MAX_ALLIES, 1 + 2 * MAX_ALLIES + 2 * MAX_ENEMIES, 2):
                    ex = state[i]
                    ey = state[i + 1]
                    if ex != 0.0 or ey != 0.0:
                        ex_px = int(ex * self.actions.WIDTH)
                        ey_px = int(ey * self.actions.HEIGHT)
                        enemy_positions.append((ex_px, ey_px))
                radius = 100
                found_enemy = any((abs(ex - x) ** 2 + abs(ey - y) ** 2) ** 0.5 < radius for ex, ey in enemy_positions)
                if not found_enemy:
                    spell_penalty = -5  # Penalize for wasting spell

        # --- Princess tower reward logic ---
        current_enemy_princess_towers = self._count_enemy_princess_towers()
        princess_tower_reward = 0
        if self.prev_enemy_princess_towers is not None:
            if current_enemy_princess_towers < self.prev_enemy_princess_towers:
                princess_tower_reward = 20
        self.prev_enemy_princess_towers = current_enemy_princess_towers

        done = False
        reward = self._compute_reward(self._get_state()) + spell_penalty + princess_tower_reward
        next_state = self._get_state()
        return next_state, reward, done

    def get_action_mask(self, state):
        """Return a boolean mask of shape [action_size] for valid actions.
        Rules:
        - If match over detected: only allow no-op
        - Disallow playing cards that are Unknown
        - Rough elixir gating: require at least 2 elixir to play any card (fallback until per-card costs available)
        - Always allow no-op
        """
        import numpy as _np
        mask = _np.zeros(self.action_size, dtype=bool)
        # Always allow no-op
        noop_index = self.action_size - 1
        mask[noop_index] = True

        # During match over only no-op
        if self.match_over_detected:
            return mask

        try:
            cards = self.detect_cards_in_hand()
        except Exception:
            cards = []

        # If detection failed, be conservative
        if not cards or all(c == "Unknown" for c in cards):
            return mask

        elixir = self.actions.count_elixir()

        playable_card_slots = set()
        for i, name in enumerate(cards):
            if i >= self.num_cards or name == "Unknown":
                continue
            cost = CARD_COSTS.get(name, 4)
            if elixir >= cost:
                playable_card_slots.add(i)

        # Set mask for all actions that use playable cards
        for idx, (card_idx, _xf, _yf) in enumerate(self.available_actions[:-1]):
            if card_idx in playable_card_slots:
                mask[idx] = True

        return mask

    def _choose_heuristic_action(self):
        """A simple rule-based policy to make the agent appear smarter before RL converges.
        Strategy:
        - Prefer playing non-Unknown, affordable cards
        - If many enemies clustered, prefer an AoE spell (Arrows/Fireball/Zap) at their centroid on our side
        - Otherwise play a troop towards closest enemy cluster on our side
        Returns an action index or None if no good action.
        """
        try:
            cards = self.current_cards or self.detect_cards_in_hand()
        except Exception:
            cards = []
        if not cards:
            return None

        elixir = self.actions.count_elixir()
        affordable_slots = [i for i, n in enumerate(cards[:self.num_cards]) if n != "Unknown" and elixir >= CARD_COSTS.get(n, 4)]
        if not affordable_slots:
            return None

        # Extract enemy coordinates from the last computed state (capture fresh)
        state = self._get_state()
        if state is None:
            return None
        enemy_coords = []
        start = 1 + 2 * MAX_ALLIES
        for i in range(start, start + 2 * MAX_ENEMIES, 2):
            ex = state[i]
            ey = state[i + 1]
            if ex != 0.0 or ey != 0.0:
                enemy_coords.append((ex, ey))

        # Default target cell: center of our half
        target_xf, target_yf = 0.5, 0.70
        if enemy_coords:
            # Centroid of enemies; clamp to our half (y >= 0.55)
            cx = sum(p[0] for p in enemy_coords) / len(enemy_coords)
            cy = sum(p[1] for p in enemy_coords) / len(enemy_coords)
            target_xf = max(0.1, min(0.9, cx))
            target_yf = max(0.55, min(0.90, cy + 0.10))  # pull a bit towards us

        # If enemy count large, prefer an AoE spell if available
        enemy_count = len(enemy_coords)
        spell_priority = ["Arrows", "Zap", "Fireball"]
        slot_choice = None
        if enemy_count >= 4:
            for sname in spell_priority:
                for i, n in enumerate(cards[:self.num_cards]):
                    if n == sname and i in affordable_slots:
                        slot_choice = i
                        break
                if slot_choice is not None:
                    break
        # Otherwise pick the first affordable non-Unknown slot
        if slot_choice is None:
            slot_choice = affordable_slots[0]

        # Find nearest grid cell among available_actions for this slot
        best_idx = None
        best_dist = 1e9
        for idx, (cidx, xf, yf) in enumerate(self.available_actions[:-1]):  # skip no-op
            if cidx != slot_choice:
                continue
            d = (xf - target_xf) ** 2 + (yf - target_yf) ** 2
            if d < best_dist:
                best_dist = d
                best_idx = idx
        return best_idx

    def _get_state(self):
        self.actions.capture_area(self.screenshot_path)
        elixir = self.actions.count_elixir()
        
        workspace_name = os.getenv('WORKSPACE_TROOP_DETECTION')
        if not workspace_name:
            raise ValueError("WORKSPACE_TROOP_DETECTION environment variable is not set. Please check your .env file.")
        
        results = self.rf_model.run_workflow(
            workspace_name=workspace_name,
            workflow_id="detect-count-and-visualize",
            images={"image": self.screenshot_path}
        )

        print("RAW results:", results)

        # Handle new structure: dict with "predictions" key
        predictions = []
        if isinstance(results, dict) and "predictions" in results:
            predictions = results["predictions"]
        elif isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict) and "predictions" in first:
                predictions = first["predictions"]
        print("Predictions:", predictions)
        if not predictions:
            print("WARNING: No predictions found in results")
            return None

        # After getting 'predictions' from results:
        if isinstance(predictions, dict) and "predictions" in predictions:
            predictions = predictions["predictions"]

        print("RAW predictions:", predictions)
        print("Detected classes:", [repr(p.get("class", "")) for p in predictions if isinstance(p, dict)])

        TOWER_CLASSES = {
            "ally king tower",
            "ally princess tower",
            "enemy king tower",
            "enemy princess tower"
        }

        def normalize_class(cls):
            return cls.strip().lower() if isinstance(cls, str) else ""

        allies = [
            (p["x"], p["y"])
            for p in predictions
            if (
                isinstance(p, dict)
                and normalize_class(p.get("class", "")) not in TOWER_CLASSES
                and normalize_class(p.get("class", "")).startswith("ally")
                and "x" in p and "y" in p
            )
        ]

        enemies = [
            (p["x"], p["y"])
            for p in predictions
            if (
                isinstance(p, dict)
                and normalize_class(p.get("class", "")) not in TOWER_CLASSES
                and normalize_class(p.get("class", "")).startswith("enemy")
                and "x" in p and "y" in p
            )
        ]

        print("Allies:", allies)
        print("Enemies:", enemies)

        # Normalize positions
        def normalize(units):
            return [(x / self.actions.WIDTH, y / self.actions.HEIGHT) for x, y in units]

        # Pad or truncate to fixed length
        def pad_units(units, max_units):
            units = normalize(units)
            if len(units) < max_units:
                units += [(0.0, 0.0)] * (max_units - len(units))
            return units[:max_units]

        ally_positions = pad_units(allies, MAX_ALLIES)
        enemy_positions = pad_units(enemies, MAX_ENEMIES)

        # Flatten positions
        ally_flat = [coord for pos in ally_positions for coord in pos]
        enemy_flat = [coord for pos in enemy_positions for coord in pos]

        state = np.array([elixir / 10.0] + ally_flat + enemy_flat, dtype=np.float32)
        return state

    def _compute_reward(self, state):
        if state is None:
            return 0

        elixir = state[0] * 10

        # Sum all enemy positions (not just the first)
        enemy_positions = state[1 + 2 * MAX_ALLIES:]  # All enemy x1, y1, x2, y2, ...
        # enemy_presence = sum(enemy_positions)
        enemy_presence = sum(enemy_positions[1::2]) # Only y coords so it does not bias left/right side
        reward = -enemy_presence

        # Elixir efficiency: reward for spending elixir if it reduces enemy presence
        if self.prev_elixir is not None and self.prev_enemy_presence is not None:
            elixir_spent = self.prev_elixir - elixir
            enemy_reduced = self.prev_enemy_presence - enemy_presence
            if elixir_spent > 0 and enemy_reduced > 0:
                reward += 2 * min(elixir_spent, enemy_reduced)  # tune this factor

        self.prev_elixir = elixir
        self.prev_enemy_presence = enemy_presence

        return reward

    def detect_cards_in_hand(self):
        try:
            card_paths = self.actions.capture_individual_cards()
            print("\nTesting individual card predictions:")

            cards = []
            workspace_name = os.getenv('WORKSPACE_CARD_DETECTION')
            if not workspace_name:
                raise ValueError("WORKSPACE_CARD_DETECTION environment variable is not set. Please check your .env file.")
            
            for card_path in card_paths:
                results = self.card_model.run_workflow(
                    workspace_name=workspace_name,
                    workflow_id="custom-workflow",
                    images={"image": card_path}
                )
                # print("Card detection raw results:", results)  # Debug print

                # Fix: parse nested structure
                predictions = []
                if isinstance(results, list) and results:
                    preds_dict = results[0].get("predictions", {})
                    if isinstance(preds_dict, dict):
                        predictions = preds_dict.get("predictions", [])
                if predictions:
                    card_name = predictions[0]["class"]
                    print(f"Detected card: {card_name}")
                    cards.append(card_name)
                else:
                    print("No card detected.")
                    cards.append("Unknown")
            return cards
        except Exception as e:
            print(f"Error in detect_cards_in_hand: {e}")
            return []

    def get_available_actions(self):
        """Generate all possible actions"""
        actions = [
            [card, x / (self.grid_width - 1), y / (self.grid_height - 1)]
            for card in range(self.num_cards)
            for x in range(self.grid_width)
            for y in range(self.grid_height)
        ]
        actions.append([-1, 0, 0])  # No-op action
        return actions

    def _endgame_watcher(self):
        while not self._endgame_thread_stop.is_set():
            result = self.actions.detect_game_end()
            if result:
                self.game_over_flag = result
                break
            # Sleep a bit to avoid hammering the CPU
            time.sleep(0.5)

    def _count_enemy_princess_towers(self):
        self.actions.capture_area(self.screenshot_path)
        
        workspace_name = os.getenv('WORKSPACE_TROOP_DETECTION')
        if not workspace_name:
            raise ValueError("WORKSPACE_TROOP_DETECTION environment variable is not set. Please check your .env file.")
        
        results = self.rf_model.run_workflow(
            workspace_name=workspace_name,
            workflow_id="detect-count-and-visualize",
            images={"image": self.screenshot_path}
        )
        predictions = []
        if isinstance(results, dict) and "predictions" in results:
            predictions = results["predictions"]
        elif isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict) and "predictions" in first:
                predictions = first["predictions"]
        return sum(1 for p in predictions if isinstance(p, dict) and p.get("class") == "enemy princess tower")