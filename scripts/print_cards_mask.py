import os
import sys
import json
# Ensure repository root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from env import ClashRoyaleEnv


def main():
    env = ClashRoyaleEnv()
    # Force a fresh state to compute mask against
    state = env._get_state()
    cards = env.detect_cards_in_hand()
    elixir = env.actions.count_elixir()
    print("Detected cards (left->right):")
    for i, name in enumerate(cards[:env.num_cards]):
        print(f"  slot {i}: {name}")
    print(f"Elixir: {elixir}")

    mask = env.get_action_mask(state)
    # Decode mask to per-slot availability
    per_slot = {i: 0 for i in range(env.num_cards)}
    for idx, allowed in enumerate(mask.tolist()):
        if idx >= len(env.available_actions) - 1:
            continue
        slot, xf, yf = env.available_actions[idx]
        if allowed:
            per_slot[slot] = per_slot.get(slot, 0) + 1
    print("Allowed actions per slot (>=1 means slot is playable now):")
    print(json.dumps(per_slot, indent=2))

    # Also export card crops that detector sees
    print("Saving current card bar crops to screenshots/card_*.png ...")
    env.actions.capture_individual_cards()
    print("Done")


if __name__ == "__main__":
    main()
