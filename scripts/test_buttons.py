import os
import argparse
import time

from Actions import Actions


def main():
    parser = argparse.ArgumentParser(description="Test UI button detection and click without training")
    parser.add_argument("button", choices=["battle", "ok", "both"], help="Which button to test")
    parser.add_argument("--full-screen", dest="full", action="store_true", help="Allow full-window search fallback")
    parser.add_argument("--threshold", type=float, default=None, help="Override template threshold for the chosen button")
    args = parser.parse_args()

    # Configure optional full-window search via env (Actions reads it on init)
    if args.full:
        os.environ["SEARCH_FULL_SCREEN"] = "1"

    actions = Actions()

    def test_battle():
        if args.threshold is not None:
            os.environ["BATTLE_TM_THRESHOLD"] = str(args.threshold)
        print("Testing Battle button click...")
        ok = actions.click_battle_start()
        print(f"Battle click result: {ok}")
        return ok

    def test_ok():
        if args.threshold is not None:
            os.environ["OK_TM_THRESHOLD"] = str(args.threshold)
        print("Testing OK button click...")
        ok = actions.click_ok_button()
        print(f"OK click result: {ok}")
        return ok

    result = False
    if args.button == "battle":
        result = test_battle()
    elif args.button == "ok":
        result = test_ok()
    else:  # both
        result = test_battle()
        time.sleep(1.0)
        result = test_ok() and result

    print("Done. Success=" + str(result))


if __name__ == "__main__":
    main()
