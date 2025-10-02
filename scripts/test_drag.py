import os
import argparse
import time

from Actions import Actions


def main():
    parser = argparse.ArgumentParser(description="Test card placement (drag/tap) without running training")
    parser.add_argument("--slot", type=int, default=0, help="Card slot index to use (0..3)")
    parser.add_argument("--mode", choices=["drag", "tap"], default="drag", help="Placement mode")
    parser.add_argument("--target", choices=["center"], default="center", help="Target preset (center of field)")
    parser.add_argument("--pause", type=float, default=None, help="Override pyautogui global pause seconds")
    args = parser.parse_args()

    if args.pause is not None:
        os.environ["PYAUTO_PAUSE"] = str(args.pause)
    os.environ["PLACEMENT_MODE"] = args.mode

    acts = Actions()

    # compute target point
    if args.target == "center":
        tx = acts.TOP_LEFT_X + (acts.BOTTOM_RIGHT_X - acts.TOP_LEFT_X) // 2
        ty = acts.TOP_LEFT_Y + (acts.BOTTOM_RIGHT_Y - acts.TOP_LEFT_Y) // 2
    else:
        raise SystemExit("Unknown target preset")

    print(f"Using slot={args.slot}, mode={args.mode}, target=({tx},{ty})")
    time.sleep(0.8)
    acts.card_play(tx, ty, args.slot)
    print("Done")


if __name__ == "__main__":
    main()
